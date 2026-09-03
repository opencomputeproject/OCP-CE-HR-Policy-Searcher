"""Send each recorded screening window to the screening model once and keep
the raw answers, so the replay test can check the gate against real model
output without spending anything on every test run.

Reads ``tests/fixtures/screening/index.json`` and the ``<slug>.txt`` windows
written by ``record_screening_fixtures.py``; uses the live ``CLASSIFY_PROMPT``
from ``src.core.llm`` and the configured screening model; writes
``tests/fixtures/screening/responses.json`` (slug -> raw response text) and
prints the token counts and the cost. Rows without a recorded window are
skipped and listed.

Costs money, deliberately once: about 60 Haiku calls at the 1 September
average of 1,885 input tokens is well under a dollar. Re-run only when the
prompt changes (the replay test names the prompt hash it was recorded for).

Run from the repo root with the app venv and a ``.env`` holding
``ANTHROPIC_API_KEY``::

    .venv\\Scripts\\python.exe scripts\\record_screening_responses.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from src.core import llm as llm_module  # noqa: E402
from src.core.scope import DEFAULT_SETTING, screening_scope_line  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX_DIR = ROOT / "tests" / "fixtures" / "screening"
HAIKU_IN_PER_MTOK = 1.00
HAIKU_OUT_PER_MTOK = 5.00


def prompt_hash() -> str:
    return hashlib.sha256(llm_module.CLASSIFY_PROMPT.encode("utf-8")).hexdigest()[:12]


async def main() -> int:
    load_dotenv(ROOT / ".env", override=True)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not api_key.startswith("sk-ant"):
        print("ANTHROPIC_API_KEY is not set; nothing recorded.")
        return 2
    import anthropic

    model = os.environ.get("SCREENING_MODEL", "claude-haiku-4-5-20251001")
    client = anthropic.AsyncAnthropic(api_key=api_key)
    index = json.loads((FIX_DIR / "index.json").read_text(encoding="utf-8"))
    scope_line = screening_scope_line(DEFAULT_SETTING)
    responses: dict[str, str] = {}
    skipped: list[str] = []
    tokens_in = tokens_out = 0
    for entry in index:
        path = FIX_DIR / f"{entry['slug']}.txt"
        if entry["chars"] == 0 or not path.exists():
            skipped.append(entry["slug"])
            continue
        content = path.read_text(encoding="utf-8")
        prompt = llm_module.CLASSIFY_PROMPT.format(
            scope_line=scope_line, url=entry["url"], content=content,
        )
        message = await client.messages.create(
            model=model, max_tokens=300, temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(block.text for block in message.content if getattr(block, "text", None))
        responses[entry["slug"]] = raw
        tokens_in += message.usage.input_tokens
        tokens_out += message.usage.output_tokens
        print(f"{entry['slug']:<48} {entry['verdict']:<6} {raw[:90].replace(chr(10), ' ')}")
    out = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "prompt_sha256_12": prompt_hash(),
        "scope_setting": DEFAULT_SETTING,
        "responses": responses,
    }
    (FIX_DIR / "responses.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n",
    )
    cost = tokens_in / 1e6 * HAIKU_IN_PER_MTOK + tokens_out / 1e6 * HAIKU_OUT_PER_MTOK
    print(f"\nrecorded {len(responses)} responses, skipped {len(skipped)} without a window: {skipped}")
    print(f"tokens in {tokens_in:,} out {tokens_out:,}; cost about ${cost:.3f}; prompt {prompt_hash()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
