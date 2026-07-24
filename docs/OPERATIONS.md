# Operations Runbook

This is the day-to-day guide for running PolicyPulse (the OCP CE HR Policy
Searcher) in production. It assumes no prior familiarity with the codebase —
if you can run `docker compose` and edit a text file, you can operate this.

The one thing to understand up front: **one Docker container runs
everything.** It's a single FastAPI process, on port 8000 inside the
container, serving both the JSON API (`/api/*`) and the built React app
(everything else). A `data/` folder on the host holds the one SQLite file
that is the entire database, plus logs. Nothing else needs a database
server, a message queue, or a second container.

---

## Table of Contents

- [First Deploy](#first-deploy)
- [Environment Variables](#environment-variables)
- [Backup and Restore](#backup-and-restore)
- [The Operating Calendar](#the-operating-calendar)
- [Cost Controls](#cost-controls)
- [Scheduled Jobs on the Server](#scheduled-jobs-on-the-server)
- [The Adoption Checklist](#the-adoption-checklist-ocp-taking-ownership)
- [Troubleshooting](#troubleshooting)

---

## First Deploy

1. **DNS.** Point an A record for the hostname you're using (e.g.
   `policypulse.example.org`) at the server's IP address.

2. **Get the code onto the server** (clone the repo, or copy the release
   tarball) and `cd` into it.

3. **Create the data directory before first launch**, so it isn't created
   as `root` by Docker and then unwritable by the container's non-root
   user:

   ```bash
   mkdir -p data
   sudo chown 1000:1000 data
   ```

4. **Create your `.env`** from the template and fill in the required
   values (see [Environment Variables](#environment-variables) below):

   ```bash
   cp config/example.env .env
   nano .env   # or any editor
   ```

5. **Bring it up:**

   ```bash
   docker compose up -d
   ```

   This builds the image (frontend + API in one) on first run, then starts
   the container bound to `127.0.0.1:8000` — not reachable from outside the
   server directly, on purpose. Check it's healthy:

   ```bash
   curl http://127.0.0.1:8000/health
   # {"status":"ok","admin_required":true}
   docker compose logs -f
   ```

6. **Put a reverse proxy in front of it** for TLS and the public hostname.
   With Caddy, the entire config is:

   ```caddyfile
   policypulse.example.org {
       reverse_proxy 127.0.0.1:8000
   }
   ```

   Caddy gets a TLS certificate automatically the first time it starts.
   Reload/restart Caddy after adding this block.

That's the whole deploy. `docker compose up -d` again after any code or
`.env` change to rebuild and restart.

---

## Environment Variables

All of these live in `.env` at the repo root (never commit it — see
`config/example.env` for the annotated template with signup links).

| Variable | What it is | Where the value comes from | Secret? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Funds every LLM call: policy analysis, the reader "Ask" agent, signal triage. **Required** — without it, scans skip LLM analysis and Ask returns 503. | [console.anthropic.com](https://console.anthropic.com/) | **Yes** |
| `ADMIN_TOKEN` | Gates every state-changing admin action (start a scan, chat with the agent, change settings, review queue) behind an `X-Admin-Token` header. **REQUIRED in production** — behind a reverse proxy, every visitor's request looks "local," so the loopback-only fallback below does not protect a public deployment. | Generate one yourself: `openssl rand -hex 32` | **Yes** |
| `GOOGLE_CREDENTIALS` | Service account key (raw JSON or base64) for writing discovered policies to the Google Sheet. Optional — policies are always saved to the local database regardless. | Google Cloud Console → service account → JSON key | **Yes** |
| `SPREADSHEET_ID` | Which Google Sheet to write to/read from (the long ID in the sheet's URL). | The sheet's URL | No (but see the adoption checklist — never point this at the real community sheet until then) |
| `OCP_DATA_DIR` | Where the SQLite database and logs live inside the container. Default (`data`) is correct for the shipped `docker-compose.yml`, which maps it to `./data` on the host. Only change this if you also change the compose volume mount. | Leave at default | No |
| `LEGISCAN_API_KEY`, `GOVINFO_API_KEY`, `REGULATIONSGOV_API_KEY`, `DIP_API_KEY`, `NZ_PCO_API_KEY` | Optional structured-source API keys (US state/federal legislation, Germany, New Zealand). Each source is silently disabled — not an error — until its key is set. | See the signup links and comments in `config/example.env` | **Yes** |

**If `ADMIN_TOKEN` is unset:** admin actions are restricted to requests
whose apparent origin is loopback (`127.0.0.1`). Behind Caddy's
`reverse_proxy`, every request arrives at the container looking local, so
this is not a substitute for setting the token — set it before going
live.

---

## Backup and Restore

The entire application state — every discovered policy, lead, log, cost
setting — is one file: `data/policypulse.db` (SQLite, WAL mode).

**Backup:** copy that one file somewhere safe.

```bash
cp data/policypulse.db /path/to/backups/policypulse-$(date +%F).db
```

A nightly whole-server backup (restic, or whatever your host already runs)
that includes the `data/` directory is entirely sufficient — there's
nothing special this app needs beyond "the file gets copied somewhere."

**Restore:** stop the container, put the backup file back, restart.

```bash
docker compose stop policypulse
cp /path/to/backups/policypulse-2026-07-01.db data/policypulse.db
docker compose start policypulse
```

Test a restore quarterly (see the calendar below) — copy a backup to a
scratch location and open it with `sqlite3` or a fresh container pointed
at it, rather than assuming the backup file is good.

---

## The Operating Calendar

| When | What runs | What a curator does after |
|---|---|---|
| **Every Monday** | Weekly signals sweep (`--signals`): free news/legislative-tracker sources feed Haiku-triaged leads into the review queue. Cheap — cents of Haiku triage, the underlying feeds (GDELT, Google News RSS, trade press) are free. | Open the review/leads queue in the app. For each lead: **chase** it (kick off full analysis — a real spend decision, made by a human) or dismiss it. Nothing is chased automatically. |
| **1st of the month** | Monthly scan of the full domain group (`"Scan the all group and report results"`). This is the expensive job — Sonnet-tier analysis across ~360 configured domains. | Skim the scan summary for new policies and errors. Anything that looks like a source going stale (see Troubleshooting) gets a note for the next dependency review. |
| **Quarterly** | Two things, not tied to a specific date — pick a week each quarter: | 1) **Restore-test** a backup (see above). 2) **Dependency review** — `pip list --outdated`, check for any security advisories on `anthropic`, `fastapi`, `httpx`, and update. |

---

## Cost Controls

Three independent levers keep spend bounded and predictable:

1. **Admin cost level** (Settings in the app, or `PUT /api/settings/costs`):
   `low` / `standard` / `high`. Picks which Claude models scans, discovery,
   and the reader agent use. `standard` (Haiku screening + Sonnet
   analysis) is the default and the sane choice for most deployments;
   drop to `low` (Haiku everywhere) if the monthly bill needs trimming
   further, `high` (Sonnet everywhere) only if you're chasing quality on a
   specific run.

2. **The public "Ask about policies" box** is bounded three ways
   simultaneously: a 5-iteration cap on the reader agent's own tool loop,
   a per-IP rate limit (default 5 requests/minute, `429` with
   `Retry-After` when exceeded), and an admin-set **daily question cap**
   (default 200/day, also `429` once exhausted, resets at midnight UTC).
   All three are visitor-facing safety valves, not something you need to
   watch day-to-day.

3. **Chases stay human-gated.** The only genuinely expensive operation —
   full LLM analysis of a new domain or lead — never fires on its own.
   The weekly signals sweep only *finds candidates*; a curator decides
   whether to spend money chasing each one. The monthly scan is the one
   recurring expensive job, and its schedule (once a month, one line in
   the calendar above) is the whole cost story for it.

**Realistic all-in monthly cost: $15–40.** That's Anthropic API spend
across the monthly scan, weekly signal triage, and whatever reader traffic
the "Ask" box gets — plus $0 for hosting if the Hetzner VPS is already
running other things. It will run higher only if an admin deliberately
sets cost level to `high` and/or chases every single weekly lead.

---

## Scheduled Jobs on the Server

The weekly/monthly jobs above are what GitHub Actions already runs as a
"belt and braces" copy against the `ci-data` branch (see
`.github/workflows/weekly-signals.yml` and `monthly-scan.yml`) — that
stays in place regardless of self-hosting. Running the *same* jobs on the
server too means the live database gets updated directly, without
waiting on a human to pull GitHub Actions output back in.

**cron** (edit with `crontab -e`, running as whatever user owns the
`docker compose` checkout):

```cron
# Weekly signals sweep — Monday 06:30
30 6 * * 1 cd /opt/policypulse && docker compose exec -T policypulse python -m src.agent --signals >> data/logs/cron.log 2>&1

# Monthly full scan — 1st of the month, 06:00
0 6 1 * * cd /opt/policypulse && docker compose exec -T policypulse python -m src.agent "Scan the all group and report results" >> data/logs/cron.log 2>&1
```

Or as a **systemd timer** (one example; duplicate for the monthly job with
its own `OnCalendar`):

```ini
# /etc/systemd/system/policypulse-signals.service
[Unit]
Description=PolicyPulse weekly signals sweep

[Service]
Type=oneshot
WorkingDirectory=/opt/policypulse
ExecStart=/usr/bin/docker compose exec -T policypulse python -m src.agent --signals
```

```ini
# /etc/systemd/system/policypulse-signals.timer
[Unit]
Description=Run PolicyPulse signals sweep weekly

[Timer]
OnCalendar=Mon *-*-* 06:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with `systemctl enable --now policypulse-signals.timer`.

---

## The Adoption Checklist (OCP Taking Ownership)

Steps for OCP to take over running this as the system of record, in
order. **Do not skip step 6 — never point the export at the real
community spreadsheet before it.**

1. Provision OCP's own VM (or reuse an existing one they control).
2. Copy this repo onto it, and run `docker compose up -d` following
   [First Deploy](#first-deploy) above — this brings up a fresh instance
   with its own empty database.
3. **Copy the interim `data/policypulse.db` over** to OCP's server,
   replacing the fresh one, so every policy/lead discovered so far
   carries forward.
4. Set `ANTHROPIC_API_KEY` to **OCP's own** Anthropic key (not the interim
   one).
5. Set `GOOGLE_CREDENTIALS` to **OCP's own** Google service account (not
   the interim one) — create it in OCP's Google Cloud project, share the
   real spreadsheet with its service-account email.
6. **Switch `SPREADSHEET_ID` from the interim scratch copy to the real
   Heat Reuse Policies Database spreadsheet.** This is the point of no
   return for exports — until this step, all Sheets writes must continue
   targeting the interim scratch copy, never the community sheet.
7. Set a **fresh `ADMIN_TOKEN`** — do not carry the interim one forward.
8. **Rotate or revoke every interim credential**: the interim
   `ANTHROPIC_API_KEY`, the interim Google service account key, and the
   interim `ADMIN_TOKEN`, all at the source (Anthropic console, Google
   Cloud Console) — not just removed from this app's `.env`.
9. Move DNS for the public hostname to OCP's server, and update the
   reverse-proxy block there.
10. Decommission the interim server once DNS has fully propagated and
    OCP confirms the new instance is serving correctly.

---

## Troubleshooting

**"Ask" says "not configured" / returns 503.**
`ANTHROPIC_API_KEY` is missing (or invalid) in the container's
environment. Check `.env`, then `docker compose up -d` again to pick up
the change.

**Admin action returns 403 "no ADMIN_TOKEN configured" or 401
"Administrator token required."**
403 means `ADMIN_TOKEN` isn't set at all and the request didn't look
loopback (expected behind a reverse proxy — set the token). 401 means a
token *is* set but the request's `X-Admin-Token` header is missing or
doesn't match — check the value being sent against `.env`.

**A structured source (LegiScan, GovInfo, etc.) has returned zero results
for months.**
First check the obvious: is its `*_API_KEY` still set and valid? If so,
it's likely the source's API has changed shape (a field renamed, an
endpoint moved) — treat as source drift, not a code bug in this app, and
check that source's file under `src/sources/` against its current API
docs.
