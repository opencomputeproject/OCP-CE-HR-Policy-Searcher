"""In-app scheduled scans (WP-11) — an asyncio background task, not APScheduler.

Runs as an ``asyncio.create_task`` started at FastAPI startup and cancelled
at shutdown (see ``ScheduleRunner`` below, wired in ``src/api/app.py``'s
lifespan). Every ``TICK_SECONDS`` it walks every enabled schedule whose
``next_run_at`` has passed and, for each one:

1. Skips it (logging ``schedule_skipped_busy``) if ``ScanManager`` already
   has a pending/running scan for the exact same scope — two overlapping
   runs of the same domains would just race each other and double-spend.
2. Pauses it (logging ``schedule_skipped_ceiling``, setting
   ``paused_reason``) if a ``monthly_ceiling_usd`` is configured and this
   month's completed-scan spend for that scope has already reached it.
   This never disables the schedule — ``month_spend()`` resets at the next
   UTC calendar month, so a paused schedule resumes on its own the first
   time it comes due after the ceiling clears, no admin action needed.
3. Otherwise clears any stale ``paused_reason`` and fires the scan through
   ``ScanManager.start_scan`` — the exact same path a manual scan takes —
   then records the new scan_id and the newly computed ``next_run_at``.

Every decision above writes a ``log_audit_event`` (``schedule_fired`` /
``schedule_skipped_busy`` / ``schedule_skipped_ceiling``) alongside the
scan's own ``scan_started`` audit event.

Resilience: one schedule's ``start_scan`` raising, or the store's
``list()``/``month_spend()`` blowing up, must never take the other
schedules — or the next tick — down with it. Every layer that can fail is
wrapped and logged rather than left to propagate. ``run_due_schedules`` is
one tick, factored out as a standalone coroutine precisely so it can be
unit-tested without the real 60-second loop (see tests/unit/test_schedule_runner.py).
"""

import asyncio
import logging
from datetime import datetime

from ..core.log_setup import log_audit_event
from ..core.models import ScanStatus
from ..storage.schedules import SchedulesStore, compute_next_run

logger = logging.getLogger(__name__)

TICK_SECONDS = 60

# Statuses that mean "this scope is already spoken for" — see _is_busy.
_BUSY_STATUSES = (ScanStatus.PENDING, ScanStatus.RUNNING)


def _is_busy(manager, domains: str) -> bool:
    """Whether ``manager`` already has a pending/running scan for ``domains``."""
    return any(
        job.domain_group == domains and job.status in _BUSY_STATUSES
        for job in manager.jobs.values()
    )


async def fire_schedule(
    manager, store: SchedulesStore, schedule: dict, data_dir: str, now: datetime,
) -> None:
    """Fire (or skip/pause) exactly one schedule.

    Shared by the tick loop (only for schedules that are due) and the
    POST /api/schedules/{id}/run-now route (which fires immediately,
    regardless of next_run_at, but still respects the busy and ceiling
    checks below).
    """
    domains = schedule["domains"]

    if _is_busy(manager, domains):
        log_audit_event(
            data_dir=data_dir, event="schedule_skipped_busy",
            schedule_id=schedule["id"], name=schedule["name"], domains=domains,
        )
        return

    ceiling = schedule.get("monthly_ceiling_usd")
    if ceiling is not None:
        spend = store.month_spend(domains, now)
        if spend >= ceiling:
            reason = f"monthly ceiling reached (${spend:.2f} of ${ceiling:.2f})"
            store.update(schedule["id"], paused_reason=reason)
            log_audit_event(
                data_dir=data_dir, event="schedule_skipped_ceiling",
                schedule_id=schedule["id"], name=schedule["name"], domains=domains,
                reason=reason,
            )
            return

    if schedule.get("paused_reason"):
        store.update(schedule["id"], paused_reason=None)

    job = await manager.start_scan(
        domains_group=domains,
        deep=bool(schedule.get("deep")),
        channels=schedule.get("channels") or ["crawl"],
        category=schedule.get("topic"),
    )

    next_run_at = compute_next_run(schedule["cadence"], now)
    store.mark_ran(schedule["id"], scan_id=job.scan_id, ran_at=now, next_run_at=next_run_at)
    log_audit_event(
        data_dir=data_dir, event="schedule_fired",
        schedule_id=schedule["id"], name=schedule["name"], domains=domains,
        scan_id=job.scan_id,
    )


async def run_due_schedules(
    manager, store: SchedulesStore, data_dir: str = "data", now: datetime = None,
) -> None:
    """One tick: fire every enabled schedule whose next_run_at has passed.

    Never raises — a failure listing schedules, or firing any individual
    one, is logged and the tick otherwise continues.
    """
    now = now or datetime.utcnow()

    try:
        schedules = store.list()
    except Exception as e:
        logger.error("Schedule tick failed to list schedules: %s", e)
        return

    now_iso = now.isoformat()
    due = [
        s for s in schedules
        if s["enabled"] and s["next_run_at"] and s["next_run_at"] <= now_iso
    ]

    for schedule in due:
        try:
            await fire_schedule(manager, store, schedule, data_dir, now)
        except Exception as e:
            logger.error("Schedule %s failed to fire: %s", schedule["id"], e)


class ScheduleRunner:
    """Owns the background asyncio task that drives run_due_schedules()."""

    def __init__(self, manager, store: SchedulesStore, data_dir: str = "data"):
        self.manager = manager
        self.store = store
        self.data_dir = data_dir
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await run_due_schedules(self.manager, self.store, self.data_dir)
            except Exception as e:
                # Belt-and-braces: run_due_schedules already catches its own
                # errors, but the loop itself must never die either.
                logger.error("Schedule runner tick crashed: %s", e)
            await asyncio.sleep(TICK_SECONDS)
