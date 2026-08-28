"""Our wake-ups against the official app's siren, side by side.

The question he actually wants answered about a night: **when it woke me, was it
warranted — and did the official app fire too?**

The second half needs no phone. `alarm_kyiv` relays the "Повітряна тривога" bot
and posts nothing but `🚨 м. Київ / Повітряна тривога` and `🟢 м. Київ / Відбій`,
which is the same state the app shows, verified to the second. So the official
siren is a set of intervals, and every decision we made either falls inside one
or does not.

That splits the night four ways, and only one of the four is ambiguous:

    both rang            the city siren, and we said so
    only we rang         our whole reason for existing — a threat over his own
                         area while the city siren says nothing new. Also where
                         a false wake-up would hide.
    only the app rang    we missed the city siren outright
    both quiet           nothing to report

"Warranted or not" stays his column. Nothing here can answer it, and pretending
otherwise would be the same mistake as scoring a label against the message it
sits on rather than the moment it is about.

Usage:
    python -m tools.live.compare                  # the newest live log
    python -m tools.live.compare --night 2026-08-26
"""

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..export.config import DB_PATH
from ..labeler.build import kyiv_dt, night_id
from ..nlp import hints
from ..policy.episodes import Tracker, observe
from ..policy.rules import decide

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "data" / "live"
OFFICIAL = "alarm_kyiv"

# How close an official transition has to be to count as the same event.
TOLERANCE_S = 120


def official_spans(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """(start, end) of every official city alert, end open as a huge number."""
    rows = conn.execute(
        "SELECT ts, text_norm FROM messages WHERE channel = ? ORDER BY ts",
        (OFFICIAL,)).fetchall()
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for r in rows:
        state = hints.alert_state(r["text_norm"])
        if state == "alert" and start is None:
            start = r["ts"]
        elif state == "clear" and start is not None:
            spans.append((start, r["ts"]))
            start = None
    if start is not None:
        spans.append((start, 1 << 62))
    return spans


def official_on(spans: list[tuple[int, int]], ts: int) -> bool:
    i = bisect.bisect_right([s for s, _e in spans], ts) - 1
    return i >= 0 and spans[i][1] > ts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--night", help="Replay a whole night from the database.")
    ap.add_argument("--log", help="One live log instead of the newest.")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    spans = official_spans(conn)

    ours: list[tuple[int, str, str]] = []      # ts, what was said, source text
    if args.night:
        tracker = Tracker()
        from ..policy.announce import Announcer

        ann = Announcer()
        for r in conn.execute(
                "SELECT channel, ts, text_norm, reply_to FROM messages "
                "WHERE text_norm <> '' ORDER BY ts"):
            if night_id(r["ts"]) != args.night:
                continue
            o = observe(r["ts"], r["text_norm"], r["reply_to"] is not None,
                        r["channel"])
            d = decide(o, tracker)
            tracker.record(o, d.level if d.notify else None,
                           d.alarm if d.notify else None)
            u = ann.announce(o, d)
            if d.audible:
                ours.append((r["ts"], u.text if u else "—",
                             r["text_norm"].replace("\n", " / ")[:44]))
        window = [args.night]
    else:
        logs = sorted(LOG_DIR.glob("*.jsonl"))
        if not logs:
            print(f"Нема логів у {LOG_DIR}.")
            return 1
        path = Path(args.log) if args.log else logs[-1]
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("warm") or row.get("level") != "alert":
                continue
            ts = int(datetime.fromisoformat(row["at"]).timestamp())
            ours.append((ts, row.get("said") or "—",
                         row["text"].replace("\n", " / ")[:44]))
        window = [path.name]

    starts = [s for s, _e in spans]
    ends = [e for _s, e in spans]

    both, only_us = [], []
    for ts, said, src in ours:
        on = official_on(spans, ts)
        i = bisect.bisect_left(starts, ts - TOLERANCE_S)
        near_start = i < len(starts) and starts[i] <= ts + TOLERANCE_S
        j = bisect.bisect_left(ends, ts - TOLERANCE_S)
        near_end = j < len(ends) and ends[j] <= ts + TOLERANCE_S
        (both if (near_start or near_end) else only_us).append((ts, said, src, on))

    ring_ts = [ts for ts, _s, _x in ours]
    missed = []
    for s, e in spans:
        for edge, what in ((s, "тривога"), (e, "відбій")):
            if edge > 1 << 40:
                continue
            if args.night and night_id(edge) != args.night:
                continue
            k = bisect.bisect_left(ring_ts, edge - TOLERANCE_S)
            if not (k < len(ring_ts) and ring_ts[k] <= edge + TOLERANCE_S):
                missed.append((edge, what))

    print(f"{', '.join(window)}")
    print(f"  наших побудок: {len(ours)}     офіційних переходів у вікні:"
          f" {len(both) + len(missed)}")
    print()

    if both:
        print("=== обидва спрацювали ===")
        for ts, said, src, _on in both:
            print(f"  {kyiv_dt(ts):%H:%M:%S}  «{said}»")
        print()

    if only_us:
        print("=== розбудив тільки наш ===")
        print("  (це те, заради чого все робилось — і те місце, де ховається"
              " хибна побудка)")
        for ts, said, src, on in only_us:
            state = "тривога триває" if on else "офіційно відбій"
            print(f"  {kyiv_dt(ts):%H:%M:%S}  «{said}»   [{state}]")
            print(f"{'':<13}   <- {src}")
        print()

    if missed:
        print("=== офіційний спрацював, наш промовчав ===")
        for ts, what in missed:
            print(f"  {kyiv_dt(ts):%H:%M:%S}  {what}")
        print()

    print("«По ділу чи ні» — твоя колонка. Нічого тут на це не відповість.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
