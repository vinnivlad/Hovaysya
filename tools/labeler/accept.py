"""Take a labelling export and keep only what he actually decided.

The page exports every night in one file, and after a pre-filled pass most of
those rows are the policy's own output. Dropping that file into `labels/` would
make the eval score the policy against itself for that night and report a
perfect one -- see `tools/labeler/prefill.py` for why that matters.

So this is the gate. A row still carrying `prefilled` is scaffolding and is
dropped; `save()` in the page removes the flag, so what survives is exactly what
he opened, looked at and stored. A night can come out sparse, which is fine --
2026-08-26 was labelled sparsely on purpose and counts fully.

It also prints what each kept row changed against the pre-fill, because that
diff is the useful artefact: a disagreement with a named rule.

    python -m tools.labeler.accept "~/Downloads/moments (1).jsonl"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .load import load_all, read_file

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS_DIR = REPO_ROOT / "labels"
DATA_DIR = REPO_ROOT / "data"

# What a disagreement can be about. Everything else in a row is bookkeeping.
FIELDS = ("decision", "level", "alarm", "silent_reason", "threat", "modality",
          "scope", "certainty", "heading", "cleared", "repeat_of", "why",
          "open_question")


def compare(kept: list[dict], night: str) -> list[str]:
    """What his rows say that the pre-fill did not."""
    path = DATA_DIR / f"prefill-{night}.jsonl"
    if not path.exists():
        return []
    before = {r["id"]: r for r in read_file(path)}
    out = []
    for row in sorted(kept, key=lambda r: r["id"]):
        was = before.get(row["id"])
        if was is None:
            out.append(f"  + {row['id']}  нова мітка: {row.get('decision')}")
            continue
        moved = [f"{f}: {was.get(f)!r} → {row.get(f)!r}"
                 for f in FIELDS if was.get(f) != row.get(f)]
        if moved:
            out.append(f"  ~ {row['id']}")
            out.extend("      " + m for m in moved)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", help="the file the page downloaded")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = read_file(Path(args.export).expanduser())
    have, _src = load_all(LABELS_DIR)
    known = {}
    for label in have:
        known.setdefault(label.get("night"), set()).add(label.get("id"))

    nights = sorted({r.get("night") for r in rows if r.get("night")})
    for night in nights:
        mine = [r for r in rows if r.get("night") == night]
        kept = [r for r in mine if not r.get("prefilled")]
        dropped = len(mine) - len(kept)

        if not kept:
            print(f"{night}: жодної власної мітки — не чіпаю "
                  f"({dropped} передзаповнених відкинуто)")
            continue
        # Nothing new to say about a night whose labels are already in place.
        if {r.get("id") for r in kept} == known.get(night) and not dropped:
            print(f"{night}: без змін ({len(kept)})")
            continue

        diff = compare(kept, night)
        print(f"{night}: {len(kept)} твоїх, {dropped} передзаповнених відкинуто")
        for line in diff:
            print(line)

        out = LABELS_DIR / f"moments_{night}.jsonl"
        if args.dry_run:
            print(f"  (не пишу, --dry-run) → {out.name}")
            continue
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + chr(10)
                               for r in kept), encoding="utf-8")
        print(f"  → {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
