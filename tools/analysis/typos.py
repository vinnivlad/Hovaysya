"""Mine likely toponym typos from the corpus so they can be added as aliases.

Typos are worth solving, but not at runtime. For a closed set of ~130 place
names the misspellings that actually occur are a finite, enumerable list: mine
them once, have a human confirm them, add them to the gazetteer as extra stems.
Runtime matching then stays exact, fast, and explainable — no fuzzy matcher
deciding at 3 a.m. that "Дніпро" was probably meant to be "Дніпрові".

`Жушяни` for `Жуляни` is the motivating case, and it is not random: on the
Ukrainian ЙЦУКЕН layout Ш and Л are both the eighth key of their row, directly
above and below each other. Keyboard-adjacent substitutions are ranked
separately because they are far more likely to be real typos than arbitrary
single-character differences.

Usage:
    python -m tools.analysis.typos                 # report
    python -m tools.analysis.typos --min-count 2   # only repeated ones
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter
from pathlib import Path

from ..nlp.gazetteer import PLACES, find_places

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "messages.db"

# ЙЦУКЕН rows. Column position within a row is what makes Ш/Л neighbours.
_ROWS = ("йцукенгшщзхї", "фівапролджє", "ячсмитьбю")

TOKEN = re.compile(r"[А-ЯЇІЄҐ][а-яіїєґ'\-]{4,}")


def _adjacency() -> dict[str, set[str]]:
    """Map each letter to the letters one key away, including vertically."""
    adj: dict[str, set[str]] = {ch: set() for row in _ROWS for ch in row}
    for r, row in enumerate(_ROWS):
        for c, ch in enumerate(row):
            if c > 0:
                adj[ch].add(row[c - 1])
            if c + 1 < len(row):
                adj[ch].add(row[c + 1])
            for other in (r - 1, r + 1):
                if 0 <= other < len(_ROWS) and c < len(_ROWS[other]):
                    adj[ch].add(_ROWS[other][c])
    return adj


ADJACENT = _adjacency()


def edit_distance(a: str, b: str, cap: int = 2) -> int:
    """Levenshtein distance, giving up once it exceeds `cap`."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (ca != cb),
            )
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def substitution_pair(a: str, b: str) -> tuple[str, str] | None:
    """If a and b differ by exactly one substitution, return that pair."""
    if len(a) != len(b):
        return None
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return diffs[0] if len(diffs) == 1 else None


def is_keyboard_slip(a: str, b: str) -> bool:
    pair = substitution_pair(a, b)
    if pair is None:
        return False
    x, y = pair
    return y in ADJACENT.get(x, ())


def candidate_stems() -> list[tuple[str, str, str]]:
    """(stem, canonical name, tier) for every gazetteer stem worth comparing."""
    out = []
    for place in PLACES:
        for stem in place.stems:
            if len(stem) >= 5 and " " not in stem:
                out.append((stem, place.name, place.tier))
    return out


def mine(conn: sqlite3.Connection, min_count: int = 1) -> list[dict]:
    rows = conn.execute(
        "SELECT text_norm FROM messages WHERE text_norm <> ''"
    ).fetchall()

    unmatched: Counter[str] = Counter()
    for (text,) in rows:
        known = {p.name for p in find_places(text)}
        for token in TOKEN.findall(text):
            low = token.lower()
            # Skip tokens the gazetteer already resolved somewhere in this
            # message — cheap way to avoid reporting inflections as typos.
            if any(low.startswith(s) or s.startswith(low[:5]) for s in _known_stems(known)):
                continue
            unmatched[token] += 1

    stems = candidate_stems()
    findings = []
    for token, count in unmatched.items():
        if count < min_count:
            continue
        low = token.lower()
        best = None
        for stem, name, tier in stems:
            d = edit_distance(low[: len(stem)], stem)
            if d == 0:
                best = None
                break
            if d <= 1 and (best is None or d < best["distance"]):
                best = {
                    "token": token,
                    "count": count,
                    "suggests": name,
                    "stem": stem,
                    "tier": tier,
                    "distance": d,
                    "keyboard": is_keyboard_slip(low[: len(stem)], stem),
                }
        if best:
            findings.append(best)

    findings.sort(key=lambda f: (not f["keyboard"], -f["count"], f["token"]))
    return findings


def _known_stems(names: set[str]) -> list[str]:
    return [s for p in PLACES if p.name in names for s in p.stems]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--min-count", type=int, default=1)
    args = ap.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    findings = mine(conn, args.min_count)
    conn.close()

    kb = [f for f in findings if f["keyboard"]]
    other = [f for f in findings if not f["keyboard"]]

    print(f"{len(findings)} candidates ({len(kb)} keyboard-adjacent)\n")
    for title, group in (("Keyboard-adjacent — most likely real typos", kb),
                         ("Other single-character differences — review these", other)):
        if not group:
            continue
        print(f"== {title} ==")
        print(f"{'token':<20}{'count':>6}  {'suggests':<22}{'tier':<12}")
        for f in group[:60]:
            print(f"{f['token']:<20}{f['count']:>6}  {f['suggests']:<22}{f['tier']:<12}")
        print()

    affected = sum(f["count"] for f in findings)
    print(f"Total messages affected: {affected}")
    print("Add confirmed ones to the matching Place in tools/nlp/gazetteer.py "
          "as an extra stem, then re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
