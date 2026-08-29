"""Copy everything that is not in git somewhere it will survive.

Two things live outside version control, for good reasons, and they are not
equally replaceable:

- `data/messages.db` — the exported history. Losing it costs ten minutes of
  re-export.
- `data/live/*.jsonl` — one file per night of watching, holding every decision
  the policy made and why. **These cannot be recreated.** They are the training
  set: 2000-odd decisions with their reasons, growing by a few hundred a night.
- `data/telegram-*.token`, `.id` — credentials. Replaceable, annoying.

Labels are committed, so they are already safe.

The database is copied through SQLite's own backup rather than as a file. It
runs in WAL mode, so a plain copy taken while pages still sit in the `-wal`
file produces a database that looks fine and is corrupt.

Usage:
    python -m tools.backup                       # to the default destination
    python -m tools.backup --to D:/Work/Hovaysya/data
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "data"
DEFAULT_DEST = Path("D:/Work/Hovaysya/data")


def copy_database(src: Path, dst: Path) -> int:
    """Through SQLite, so a WAL-mode database arrives whole."""
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(str(dst))
    with target:
        source.backup(target)
    count = target.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    ok = target.execute("PRAGMA integrity_check").fetchone()[0]
    target.close()
    source.close()
    if ok != "ok":
        raise RuntimeError(f"copied database reports {ok!r}")
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="src", default=str(SOURCE))
    ap.add_argument("--to", dest="dst", default=str(DEFAULT_DEST))
    args = ap.parse_args(argv)

    src, dst = Path(args.src), Path(args.dst)
    if not src.exists():
        print(f"Нема чого копіювати: {src}")
        return 1
    dst.mkdir(parents=True, exist_ok=True)

    db = src / "messages.db"
    if db.exists():
        n = copy_database(db, dst / "messages.db")
        print(f"  messages.db      {n} повідомлень, цілісність ok")

    files = nights = 0
    for item in sorted(src.iterdir()):
        if item.name.startswith("messages.db"):
            continue          # including -wal and -shm, which the backup makes moot
        if item.is_dir():
            shutil.copytree(item, dst / item.name, dirs_exist_ok=True)
            nights += len(list(item.glob("*.jsonl")))
        else:
            shutil.copy2(item, dst / item.name)
            files += 1

    print(f"  live/            {nights} логів ночей")
    print(f"  решта            {files} файлів")
    total = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
    print(f"  всього           {total // 1024 // 1024} МБ у {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
