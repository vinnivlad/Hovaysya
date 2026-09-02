"""Weigh a candidate channel against the five already in place.

One question decides it, and it is his: **does this channel ever get there
first?** A relay copies with a lag and can never lead; an observer sometimes
does. Everything else -- volume, tone, how much it writes -- is decoration.

    python -m tools.export.export --db data/probe.db --channel <name> --since ...
    python -m tools.bench.channel --db data/probe.db --channel <name>

The measure is deliberately narrow. Only messages naming a place in his ring
count, because that is the only traffic that can wake him, and a channel that is
fast about Kharkiv buys him nothing. For each such mention the corpus is asked
when it first said the same name around the same time, and the difference is the
lead. A channel worth adding shows a run of positive ones.

**A lead is not yet a reason to add it.** Two things cost more than seconds:
a name we cannot read at all is invisible however early it arrives, and a message
with no threat class opens an episode as `unknown`. Both are reported beside the
timing, because the decision is the three together.
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..nlp.gazetteer import find_places
from ..policy.config import load as load_config
from ..policy.episodes import observe_for, read

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "data" / "messages.db"
KYIV = timezone(timedelta(hours=3))

# How far apart two mentions of one place may be and still be the same event.
# The measured p99 of cross-channel lag for the same target is five minutes.
SAME_EVENT_S = 300


def rows(db: Path, channel: str | None = None):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sql = "SELECT channel, message_id, ts, text_norm FROM messages WHERE text_norm <> ''"
    args: tuple = ()
    if channel:
        sql += " AND channel = ?"
        args = (channel,)
    out = conn.execute(sql + " ORDER BY ts", args).fetchall()
    conn.close()
    return out


def classed(rows, cfg, channel):
    """(ts, text, class) for every message that states a class about here.

    The second lens, and some candidates need it rather than the ring. A channel
    that writes only "Балістика на Київ/передмістя" never names a district, so
    counting ring mentions says it is worthless when it may be the fastest source
    there is about the one class that leaves four minutes.
    """
    out = []
    for r in rows:
        o = observe_for(read(r["ts"], r["text_norm"], False, channel), cfg)
        if (o.threat not in ("none", "unknown")
                and o.modality == "live-threat"
                and o.scope in ("my-area", "my-district", "city", "oblast")):
            out.append((r["ts"], r["text_norm"], o.threat))
    return out


def lead_table(mine, theirs, key, window=SAME_EVENT_S):
    """How often the candidate said it before we did, and by how long."""
    by_key: dict[str, list[int]] = {}
    for ts, _t, k in theirs:
        by_key.setdefault(k, []).append(ts)
    leads, alone = [], []
    for ts, text, k in mine:
        near = [t for t in by_key.get(k, ()) if abs(t - ts) <= window]
        if not near:
            alone.append((ts, text))
            continue
        leads.append((min(near) - ts, ts, text))
    return leads, alone


def ring_mentions(rows, cfg, ring):
    """(ts, text, names) for every message naming a place in his ring."""
    out = []
    for r in rows:
        named = [p.name for p in find_places(r["text_norm"]) if p.name in ring]
        if named:
            out.append((r["ts"], r["text_norm"], named))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="scratch database with the candidate")
    ap.add_argument("--channel", required=True)
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--examples", type=int, default=8)
    args = ap.parse_args()

    cfg = load_config(warn=lambda _m: None)
    ring = cfg.ring_names()

    cand = rows(Path(args.db), args.channel)
    ours = rows(Path(args.corpus))
    if not cand or not ours:
        raise SystemExit("порожньо")

    # Only the window both sides cover, or the candidate is judged on days we
    # were not watching.
    lo = max(cand[0]["ts"], ours[0]["ts"])
    hi = min(cand[-1]["ts"], ours[-1]["ts"])
    cand = [r for r in cand if lo <= r["ts"] <= hi]
    ours = [r for r in ours if lo <= r["ts"] <= hi]
    days = (hi - lo) / 86400
    print(f"вікно порівняння: {datetime.fromtimestamp(lo, KYIV):%d.%m.%y} .. "
          f"{datetime.fromtimestamp(hi, KYIV):%d.%m.%y}  ({days:.0f} днів)")
    print(f"  кандидат: {len(cand)} повідомлень ({len(cand)/max(days,1):.0f} на день)")
    print(f"  наші пʼять: {len(ours)} ({len(ours)/max(days,1):.0f} на день)")

    mine = ring_mentions(cand, cfg, ring)
    theirs = ring_mentions(ours, cfg, ring)
    print(f"\nзгадок кола: кандидат {len(mine)}, наші {len(theirs)}")
    if not mine:
        print("  кандидат не називає коло взагалі — далі рахувати нема чого")
        return

    by_name: dict[str, list[int]] = {}
    for ts, _t, names in theirs:
        for n in names:
            by_name.setdefault(n, []).append(ts)

    leads, first, alone, examples = [], 0, 0, []
    for ts, text, names in mine:
        best = None
        for n in names:
            near = [t for t in by_name.get(n, ())
                    if abs(t - ts) <= SAME_EVENT_S]
            if near:
                gap = ts - min(near)
                best = gap if best is None else min(best, gap)
        if best is None:
            alone += 1
            if len(examples) < args.examples:
                examples.append((ts, text, None))
            continue
        leads.append(-best)          # позитивне = кандидат був першим
        if best < 0:
            first += 1
            if len(examples) < args.examples:
                examples.append((ts, text, -best))

    print(f"  з них збіглися з нашими: {len(leads)}, "
          f"кандидат був першим: {first}, "
          f"нічого схожого в нас: {alone}")
    if leads:
        leads.sort()
        ahead = [x for x in leads if x > 0]
        print(f"  випередження: медіана {statistics.median(leads):+.0f} с, "
              f"найкраще {max(leads):+.0f} с")
        if ahead:
            print(f"  коли веде — медіана {statistics.median(ahead):.0f} с, "
                  f"p90 {sorted(ahead)[int(len(ahead)*0.9)]:.0f} с")

    # --- друга лінза: клас, а не район -------------------------------------
    mine_c = classed(cand, cfg, args.channel)
    theirs_c = classed(ours, cfg, "mon1tor_ua")
    print(f"\nповідомлень із класом про нас: кандидат {len(mine_c)}, "
          f"наші {len(theirs_c)}")
    if mine_c:
        leads, alone = lead_table(mine_c, theirs_c, None)
        ahead = [g for g, _ts, _t in leads if g > 0]
        print(f"  збіглися за класом: {len(leads)}, "
              f"кандидат був першим: {len(ahead)}, "
              f"нічого схожого в нас: {len(alone)}")
        if ahead:
            ahead.sort()
            print(f"  коли веде: медіана {statistics.median(ahead):.0f} с, "
                  f"найкраще {max(ahead):.0f} с")
        for gap, ts, text in sorted(leads, key=lambda x: -x[0])[:5]:
            if gap <= 0:
                break
            print(f"    +{gap:4.0f}с  {datetime.fromtimestamp(ts, KYIV):%d.%m %H:%M:%S}"
                  f"  {text.replace(chr(10), ' / ')[:52]!r}")

    # Чи ми взагалі прочитаємо те, що він пише
    unread = sum(1 for _ts, t, _n in mine if not find_places(t))
    with_class = 0
    for ts, text, _n in mine:
        o = observe_for(read(ts, text, False, args.channel), cfg)
        if o.threat not in ("none", "unknown"):
            with_class += 1
    print(f"\n  клас загрози в тексті: {with_class}/{len(mine)}")
    print(f"  жодного впізнаного місця: {unread}/{len(mine)}")

    if examples:
        print("\nприклади:")
        for ts, text, lead in examples:
            when = f"+{lead:.0f}с" if lead else "тільки в нього"
            print(f"  {datetime.fromtimestamp(ts, KYIV):%d.%m %H:%M:%S} "
                  f"{when:16} {text.replace(chr(10), ' / ')[:64]!r}")


if __name__ == "__main__":
    main()
