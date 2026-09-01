"""Pre-label a night with what the policy already decides.

His instruction, and the right one: "спочатку розміть все по вже існуючим
правилам. Я буду тільки коригувати". A 696-message night is a scroll and a few
disagreements that way, instead of an evening of data entry.

**A pre-filled label is not evidence, and this is why the file lands in `data/`
rather than in `labels/`.** Labels made by the policy, scored against the policy,
produce a perfect night and say nothing at all. Only the pass he has actually
looked at counts, and that is the export from the page, which he saves into
`labels/` himself.

Every row carries `"prefilled": true`. The page drops that flag the moment he
saves a label, so afterwards the flag says exactly which rows he touched and
which he merely let stand -- and the second group is worth having too, but only
because he looked at them.

    python -m tools.labeler.prefill --night 2026-08-31
    python -m tools.labeler.build --prefill data/prefill-2026-08-31.jsonl
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..eval.run import load_night
from ..labeler.build import night_id
from ..labeler.load import load_all
from ..policy.config import load as load_config
from ..policy.episodes import OFFICIAL_CHANNELS, Tracker, observe

REPO_ROOT = Path(__file__).resolve().parents[2]
KYIV = timezone(timedelta(hours=3))

# The four the schema keeps, because they need his judgement. The rules already
# name them at the front of their reason, which is not a coincidence -- the
# reason strings were written against this list.
SILENT_REASONS = ("too-far", "already-notified", "resolved", "insufficient")


def silent_reason(reason: str) -> str | None:
    head = reason.split(":", 1)[0].strip()
    return head if head in SILENT_REASONS else None


def row(obs, dec, anchor: str, night: str, seq: Counter) -> dict:
    at = datetime.fromtimestamp(obs.ts, tz=timezone.utc)
    minute = at.astimezone(KYIV).strftime("%Y-%m-%dT%H:%M")
    seq[minute] += 1
    channel, _, mid = anchor.partition("/")
    out = {
        "id": f"{minute}-{seq[minute]:02d}",
        "night": night,
        "anchor": anchor,
        "at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decision": "notify" if dec.notify else "silent",
        "threat": obs.threat,
        "modality": obs.modality,
        "scope": obs.scope,
        "certainty": obs.certainty,
        "heading": obs.heading,
        "cleared": None,
        # Left for him: the episode knows which message opened it, but calling
        # that a repeat is a judgement about identity and it is the judgement
        # the labels exist to record.
        "repeat_of": None,
        "evidence": [{"channel": channel, "message_id": int(mid)}],
        # The rule that fired, verbatim. It is the most useful thing on the
        # screen: a disagreement is then with a named rule, not with a verdict.
        "why": dec.reason,
        "open_question": None,
        "prefilled": True,
    }
    if dec.notify:
        out["level"] = dec.level or "info"
        out["alarm"] = dec.alarm or "none"
    else:
        out["silent_reason"] = silent_reason(dec.reason)
    return out


def build(night: str, db: Path) -> list[dict]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    messages = load_night(conn, night, [])

    # The same path the eval replays, which is the same path production runs --
    # anything else would pre-fill with decisions the watcher never made.
    from ..eval.run import run_policy

    observations = [observe(ts, text, is_reply, anchor.split("/")[0])
                    for ts, anchor, text, is_reply in messages]
    tracker = Tracker(config=load_config())
    tracker.official_source = any(
        anchor.split("/")[0] in OFFICIAL_CHANNELS
        for _ts, anchor, _t, _r in messages)

    seq: Counter[str] = Counter()
    out = []
    for (obs, dec), (_ts, anchor, _t, _r) in zip(
            run_policy(observations, tracker), messages):
        out.append(row(obs, dec, anchor, night, seq))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--night", required=True, metavar="YYYY-MM-DD")
    ap.add_argument("--db", default=str(REPO_ROOT / "data" / "messages.db"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    have, _src = load_all()
    already = sum(1 for l in have if l.get("night") == args.night)
    if already:
        # Refusing rather than warning: overwriting a hand-labelled night with
        # the policy's own output is the one mistake that would quietly destroy
        # the only thing in this repository that cannot be regenerated.
        raise SystemExit(f"ніч {args.night} вже має {already} ручних міток — "
                         f"передзаповнення її не торкається")

    rows = build(args.night, Path(args.db))
    out = Path(args.out or REPO_ROOT / "data" / f"prefill-{args.night}.jsonl")
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + chr(10)
                           for r in rows), encoding="utf-8")

    rang = sum(1 for r in rows if r.get("level") == "alert")
    quiet = sum(1 for r in rows if r["decision"] == "notify"
                and r.get("level") != "alert")
    print(f"{out}: {len(rows)} міток — {rang} зі звуком, {quiet} тихих, "
          f"{len(rows) - rang - quiet} без нічого")
    print("  далі: python -m tools.labeler.build --prefill " + str(out))


if __name__ == "__main__":
    main()
