"""Replay a night's log through the current policy, beside what actually ran.

After a batch of fixes the only question that matters is what a real night would
have sounded like, and the log holds both halves of the answer: the raw messages
in the order they arrived, and the decision the watcher made at the time. So the
night can be replayed and the two columns set against each other.

    python -m tools.live.rerun --from 02:20 --to 02:47
    python -m tools.live.rerun --day 2026-09-01 --changed

Columns are `було` and `стало`:

    🔔   an audible notification
    ·    a silent one, on the status line
    ·    nothing at all

A line marked ← is one the fixes moved, which is usually the whole point of
looking.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timedelta, timezone

from ..policy.announce import Announcer
from ..policy.episodes import Tracker, observe
from ..policy.rules import decide

KYIV = timezone(timedelta(hours=3))
LOGS = pathlib.Path("D:/Work/Hovaysya-data/live")


def load(log_dir: pathlib.Path) -> list[dict]:
    """Every live message once, in the order it arrived.

    Logs overlap: a restart re-reads the last ninety minutes, and the catch-up
    pass writes them again. The anchor is what makes a message itself.
    """
    rows, seen = [], set()
    for p in sorted(log_dir.glob("*.jsonl")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("warm") or r.get("anchor") in seen:
                continue
            seen.add(r["anchor"])
            rows.append(r)
    rows.sort(key=lambda r: r["at"])
    return rows


def mark(level: str | None, notify: bool) -> str:
    if level == "alert":
        return "🔔"
    return "·" if notify else " "


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    ap.add_argument("--logs", default=str(LOGS))
    ap.add_argument("--day", help="Only this Kyiv date, e.g. 2026-09-01.")
    ap.add_argument("--from", dest="since", default="00:00")
    ap.add_argument("--to", dest="until", default="23:59")
    ap.add_argument("--changed", action="store_true",
                    help="Only the lines the fixes moved.")
    args = ap.parse_args(argv)

    rows = load(pathlib.Path(args.logs))
    tracker, announcer = Tracker(), Announcer()
    tracker.official_source = True

    shown = moved = 0
    for r in rows:
        ts = int(datetime.fromisoformat(r["at"]).timestamp())
        obs = observe(ts, r["text"], False, r["anchor"].split("/")[0],
                      config=tracker.config)
        d = decide(obs, tracker)
        tracker.record(obs, d.level if d.notify else None,
                       d.alarm if d.notify else None, d.reason)
        utterance = announcer.announce(obs, d)

        t = datetime.fromtimestamp(ts, KYIV)
        if args.day and t.strftime("%Y-%m-%d") != args.day:
            continue
        if not (args.since <= t.strftime("%H:%M") <= args.until):
            continue

        was = mark(r.get("level"), bool(r.get("notify")))
        now = mark(d.level if d.notify else None, d.notify)
        changed = was != now
        moved += changed
        if args.changed and not changed:
            continue
        shown += 1
        flag = " ←" if changed else "  "
        text = r["text"].replace(chr(10), " / ")[:56]
        print(f"  {t:%H:%M:%S}  {was}  {now}{flag}  {text}")
        if utterance is not None and d.notify:
            print(f"{'':<14}{'':<6}      «{utterance.text}»")

    print(f"\n  показано {shown}, з них змінилося {moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
