"""Replay a night through the policy and score it against the labels.

The headline number is **false wake-ups per night**, not accuracy. An app that
wakes you twice for nothing gets deleted in a week however good its recall is,
so that number is printed first and everything else is context.

Scoring compares the label's decision with the policy's at the same moment.
Both are anchored to message arrivals, so no tolerance window is needed: the
label and the decision are about the same instant by construction.

    hit          label says notify, policy notifies at the same level or higher
    under        label says notify, policy notifies more quietly
    miss         label says notify, policy stays silent
    false wake   label says silent, policy notifies audibly
    ok-silent    both stay silent, or the policy only updates the status

Usage:
    python -m tools.eval.run
    python -m tools.eval.run --night 2026-08-26 --verbose
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from ..labeler.load import load_all
from ..policy.episodes import Tracker, observe
from ..policy.rules import run as run_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "messages.db"
LABELS_PATH = REPO_ROOT / "labels"

RANK = {None: -1, "info": 0, "alert": 1}


def load_labels(path: Path) -> list[dict]:
    """Every snapshot in the labels directory, newest per night winning.

    `--labels` may name a single file, in which case only that one is read.
    """
    if path.is_dir():
        return load_all(path)[0]
    from ..labeler.load import read_file
    return read_file(path)


def load_night(conn: sqlite3.Connection, night: str, labels: list[dict]
               ) -> list[tuple[int, str, str, bool]]:
    """Every message of the night, as (ts, key, text), in order.

    The whole night is replayed, not only the labelled messages: the policy's
    state depends on what it saw, and feeding it a filtered stream would let it
    look better than it is.
    """
    from ..labeler.build import night_id

    rows = conn.execute(
        "SELECT channel, message_id, ts, text_norm, reply_to FROM messages "
        "WHERE text_norm <> '' ORDER BY ts"
    ).fetchall()
    out = []
    for r in rows:
        if night_id(r["ts"]) != night:
            continue
        out.append((r["ts"], f"{r['channel']}/{r['message_id']}", r["text_norm"],
                    r["reply_to"] is not None))
    return out


def score(labels_by_anchor: dict[str, dict], results) -> tuple[Counter, list[dict]]:
    tally: Counter[str] = Counter()
    detail: list[dict] = []

    for obs, decision, key in results:
        label = labels_by_anchor.get(key)
        if label is None:
            # Unlabelled message. An audible notification here is still a wake-up
            # the user did not ask for, so it is counted — silence is not.
            if decision.audible:
                tally["wake-unlabelled"] += 1
                detail.append({"kind": "wake-unlabelled", "key": key, "obs": obs,
                               "decision": decision, "label": None})
            continue

        wants = label.get("decision") == "notify"
        want_level = label.get("level") if wants else None
        got_level = decision.level if decision.notify else None

        if wants:
            if not decision.notify or got_level == "info" and want_level != "info":
                kind = "miss"
            elif RANK[got_level] >= RANK[want_level]:
                kind = "hit"
            else:
                kind = "under"
        else:
            kind = "false-wake" if decision.audible else "ok-silent"

        tally[kind] += 1
        if kind != "ok-silent" and kind != "hit":
            detail.append({"kind": kind, "key": key, "obs": obs,
                           "decision": decision, "label": label})
    return tally, detail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--labels", default=str(LABELS_PATH))
    ap.add_argument("--night", help="Only this night (default: every labelled one).")
    ap.add_argument("--verbose", action="store_true", help="List every disagreement.")
    args = ap.parse_args(argv)

    labels = load_labels(Path(args.labels))
    if not labels:
        print("No labels to score against.")
        return 1

    nights = sorted({l["night"] for l in labels})
    if args.night:
        nights = [n for n in nights if n == args.night]

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    grand: Counter[str] = Counter()
    for night in nights:
        night_labels = [l for l in labels if l["night"] == night]
        by_anchor = {l["anchor"]: l for l in night_labels}
        messages = load_night(conn, night, night_labels)

        observations = [observe(ts, text, is_reply)
                        for ts, _key, text, is_reply in messages]
        keys = [key for _ts, key, _text, _r in messages]
        decisions = run_policy(observations, Tracker())
        results = [(o, d, k) for (o, d), k in zip(decisions, keys)]

        tally, detail = score(by_anchor, results)
        grand.update(tally)

        audible = sum(1 for _o, d, _k in results if d.audible)
        print(f"=== {night} — {len(messages)} messages, {len(night_labels)} labels ===")
        print(f"  FALSE WAKE-UPS: {tally['false-wake']}"
              f"   (+{tally['wake-unlabelled']} on unlabelled messages)")
        print(f"  misses: {tally['miss']}   under-level: {tally['under']}"
              f"   hits: {tally['hit']}   correct silence: {tally['ok-silent']}")
        print(f"  the policy would have made {audible} audible notifications")
        print()

        if args.verbose and detail:
            for d in detail:
                obs, dec, lab = d["obs"], d["decision"], d["label"]
                want = (f"{lab.get('level')}·{lab.get('alarm')}"
                        if lab and lab.get("decision") == "notify" else "silent")
                got = f"{dec.level}·{dec.alarm}" if dec.notify else "silent"
                print(f"  [{d['kind']:<16}] want {want:<16} got {got:<16} {dec.reason}")
                print(f"       {obs.text.replace(chr(10), ' / ')[:74]}")
                if lab and (lab.get("why") or "").strip():
                    print(f"       «{lab['why']}»")
            print()

    conn.close()

    if len(nights) > 1:
        print("=== all nights ===")
        for k in ("false-wake", "wake-unlabelled", "miss", "under", "hit", "ok-silent"):
            print(f"  {k:<18}{grand[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
