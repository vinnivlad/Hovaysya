"""Re-apply the current normaliser to `text_norm` already in the database.

Needed once, when the normaliser changes and the messages cannot be fetched
again -- `t.me/s/` serves a window, not the archive, so the stored text is the
only copy of anything old.

The case it was written for: apostrophes. The channels use four characters for
one letter, and every rule downstream had to know that until the fold moved to
`normalize_text`. Rows normalised before the fold keep their original character,
so the eval would run on text the live watcher would never see again -- which is
the worst kind of difference, silent and only in the past.

Idempotent: running it twice changes nothing the second time.

    python -m tools.export.refold                # this machine
    python -m tools.export.refold --dry-run

**The instance does not need this**, and 1b28cf8 claimed it did. Its database is
read in exactly two places and both look at the last ninety minutes: the tracker
warm-up on start, and the row of a message just written. Everything the watcher
stores after a deploy is already folded, the handful of older rows inside the warm
window age out within the hour, and what they could affect is one pattern. The
reasoning that made the run necessary here -- the eval replays four months, so 152
unfolded rows would stay in it forever -- does not transfer to a machine that
never looks further back than ninety minutes.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .normalize import fold_apostrophes

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "messages.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT channel, message_id, text_norm FROM messages WHERE text_norm <> ''"
    ).fetchall()

    changed = [(fold_apostrophes(r["text_norm"]), r["channel"], r["message_id"])
               for r in rows
               if fold_apostrophes(r["text_norm"]) != r["text_norm"]]

    print(f"{len(rows)} рядків, змінює {len(changed)}")
    for text, channel, mid in changed[:5]:
        print(f"  {channel}/{mid}: {text[:60]!r}")
    if args.dry_run or not changed:
        return

    con.executemany(
        "UPDATE messages SET text_norm = ? WHERE channel = ? AND message_id = ?",
        changed)
    con.commit()
    print("записано")


if __name__ == "__main__":
    main()
