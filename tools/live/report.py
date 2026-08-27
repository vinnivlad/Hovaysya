"""Read a night's watch back as "what would have woken you".

The log is a decision per message with its reason, which is more than anyone
wants to scroll at breakfast. Three things are worth seeing:

- every moment that would have made a sound, and the sentence it would have said
- every moment that touched the near ring, whatever was decided, because that is
  where a miss hides
- the detection lag, which is what polling costs

Only the newest log is read by default. An older run's log holds messages this
one caught up on, and mixing them makes the lag figure nonsense — the first
attempt at this reported a median of two and a half hours that way.

Usage:
    python -m tools.live.report
    python -m tools.live.report --all
    python -m tools.live.report --log data/live/20260827T175144.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from ..nlp.gazetteer import MY_AREA, MY_DISTRICT, find_places

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "data" / "live"

NEAR_TIERS = {p.tier for p in (MY_AREA + MY_DISTRICT)}


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("at", ""))
    return rows


def touches_ring(text: str) -> bool:
    return any(p.tier in NEAR_TIERS for p in find_places(text))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--log", help="One specific log file.")
    ap.add_argument("--all", action="store_true",
                    help="Every log in data/live (mixes catch-up into the lag).")
    args = ap.parse_args(argv)

    if args.log:
        paths = [Path(args.log)]
    else:
        found = sorted(LOG_DIR.glob("*.jsonl"))
        if not found:
            print(f"Нема логів у {LOG_DIR}.")
            return 1
        paths = found if args.all else [found[-1]]

    rows = load(paths)
    live = [r for r in rows if not r.get("warm")]
    woke = [r for r in live if r.get("level") == "alert"]
    spoke = [r for r in live if r.get("notify") and r.get("level") != "alert"]
    ring = [r for r in live if touches_ring(r.get("text", ""))]

    print(f"{', '.join(p.name for p in paths)}")
    print(f"  {len(rows)} записів, живих {len(live)}, наздоганяння {len(rows) - len(live)}")
    print(f"  розбудило б: {len(woke)}    сказало б без звуку: {len(spoke)}")
    print()

    if woke:
        print("=== розбудило б ===")
        for r in woke:
            print(f"  {r['at'][11:19]}  «{r.get('said') or '—'}»")
            print(f"{'':<13}   <- {r['text'].replace(chr(10), ' / ')[:70]}")
        print()

    if ring:
        print("=== торкалось мого району (тут ховаються пропуски) ===")
        for r in ring:
            mark = "!!" if r.get("level") == "alert" else (".." if r.get("notify") else "  ")
            print(f"  {r['at'][11:19]} {mark} {r.get('reason', ''):<42} "
                  f"{r['text'].replace(chr(10), ' / ')[:46]}")
        print()

    lags = [r["lag_s"] for r in live if "lag_s" in r]
    if lags:
        ordered = sorted(lags)
        p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))]
        print(f"затримка виявлення: медіана {statistics.median(lags):.0f}s, "
              f"p90 {p90:.0f}s, гірша {ordered[-1]:.0f}s")
        if ordered[-1] > 600 and not args.all:
            print("  (щось понад 10 хвилин у живому потоці — або машина спала,")
            print("   або лог змішаний; перевір --log на один конкретний файл)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
