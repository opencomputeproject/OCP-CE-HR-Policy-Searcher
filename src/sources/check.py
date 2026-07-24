"""Diagnostic: which structured sources are configured and reachable.

Run it any time a new API key lands to confirm the source went live:

    python -m src.sources.check          # key status for every source
    python -m src.sources.check --live   # also probe each ready source

Never prints key values — only whether the required env var is set.
"""

import argparse
import asyncio
import os
import sys

from . import SOURCE_REGISTRY
from .base import SourceError

# Minimal, cheap probe params per source so --live spends nothing on the
# paid pipeline (these calls hit only the free source APIs, not the LLM).
_PROBE_PARAMS = {
    "riksdagen": {"query_terms": ["fjärrvärme"], "max_documents": 1},
    "uk_bills": {"query_terms": ["heat networks"], "max_documents": 1},
    "legisinfo": {"terms": ["energy"], "max_documents": 1},
    "folketing": {"query_terms": ["fjernvarme"], "max_documents": 1},
    "eurlex_nim": {"max_documents": 1},
    "legiscan": {"query_terms": ["waste heat"], "max_documents": 1, "max_api_calls": 3},
    "govinfo": {"query_terms": ["district heating"], "max_documents": 1},
    "regulations_gov": {"query_terms": ["waste heat"], "max_documents": 1},
    "dip": {"query_terms": ["Abwärme"], "max_documents": 1},
    "ris_austria": {"terms": ["Fernwärme"], "max_documents": 1},
}


def source_key_status() -> list[dict]:
    """Report key readiness for every registered source (no key values)."""
    rows = []
    for source_id, cls in sorted(SOURCE_REGISTRY.items()):
        env = cls.api_key_env
        key_present = bool(env and os.environ.get(env))
        rows.append({
            "id": source_id,
            "api_key_env": env,
            "key_present": key_present,
            # Keyless sources are always ready; keyed ones need their key.
            "ready": env is None or key_present,
        })
    return rows


async def _probe(source_id: str) -> tuple[str, str]:
    from . import get_source
    source = get_source(source_id)
    params = _PROBE_PARAMS.get(source_id, {"max_documents": 1})
    try:
        results = await source.fetch({"id": f"probe_{source_id}", "source_params": params})
    except SourceError as e:
        return "CONFIG-ERROR", str(e)[:80]
    except Exception as e:  # noqa: BLE001 - diagnostic must never crash
        return "ERROR", f"{type(e).__name__}: {e}"[:80]
    if results:
        sample = results[0]
        return "OK", f"{len(results)} doc(s), e.g. {sample.url[:60]}"
    return "EMPTY", "reachable, 0 documents this probe"


async def _run_live(rows: list[dict]) -> dict[str, tuple[str, str]]:
    probes = {}
    for row in rows:
        if not row["ready"]:
            probes[row["id"]] = ("SKIP", "no key configured")
            continue
        probes[row["id"]] = await _probe(row["id"])
    return probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check structured policy sources")
    parser.add_argument("--live", action="store_true",
                        help="probe each ready source with a tiny live fetch")
    args = parser.parse_args(argv)

    # Load .env so keys stored there are visible when this runs standalone
    # (the API/agent load it at startup; this CLI needs its own load).
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

    rows = source_key_status()
    live = asyncio.run(_run_live(rows)) if args.live else {}

    print(f"{'SOURCE':<18} {'KEY':<22} {'READY':<7} {'PROBE'}")
    print("-" * 78)
    for row in rows:
        env = row["api_key_env"] or "(none — free)"
        key_state = env if row["ready"] else f"{env}  MISSING"
        ready = "yes" if row["ready"] else "no"
        probe = ""
        if args.live:
            status, detail = live[row["id"]]
            probe = f"{status}  {detail}"
        print(f"{row['id']:<18} {key_state:<22} {ready:<7} {probe}")

    ready_count = sum(1 for r in rows if r["ready"])
    print("-" * 78)
    print(f"{ready_count}/{len(rows)} sources ready "
          f"({len(rows) - ready_count} awaiting an API key).")

    # LegiScan monthly query budget (only source with a hard monthly cap).
    if os.environ.get("LEGISCAN_API_KEY"):
        from .legiscan import monthly_usage
        u = monthly_usage()
        pct = (u["used"] / u["limit"] * 100) if u["limit"] else 0
        print(f"\nLegiScan queries this month ({u['month']}): "
              f"{u['used']:,} / {u['limit']:,} used ({pct:.1f}%), "
              f"{u['remaining']:,} remaining.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
