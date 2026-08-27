"""Read the label set from every snapshot in `labels/`, newest per night wins.

The page exports one file holding every label for every night, so each export is
a complete snapshot rather than a delta. That makes the merge rule simple and
safe: **for each night, the newest file that mentions that night defines the
whole set for it.**

Nothing is ever deleted and nothing has to be moved. Dropping a fresh export
into `labels/` is all that is needed for it to count, and a label removed in the
page stays removed — which a plain id-level union would silently undo.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS_DIR = REPO_ROOT / "labels"


def read_file(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def snapshots(labels_dir: Path | str = LABELS_DIR) -> list[Path]:
    """Every label file, oldest first, so later ones override."""
    return sorted(Path(labels_dir).glob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def load_all(labels_dir: Path | str = LABELS_DIR
             ) -> tuple[list[dict], dict[str, str]]:
    """(labels, night -> the file that defined it), in chronological order."""
    by_night: dict[str, list[dict]] = {}
    source: dict[str, str] = {}
    for path in snapshots(labels_dir):
        rows = read_file(path)
        for night in {l.get("night") for l in rows if l.get("night")}:
            by_night[night] = [l for l in rows if l.get("night") == night]
            source[night] = path.name
    labels = [l for night in sorted(by_night) for l in by_night[night]]
    labels.sort(key=lambda l: l.get("at", ""))
    return labels, source
