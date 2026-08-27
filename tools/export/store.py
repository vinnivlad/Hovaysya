"""SQLite storage for exported Telegram channel history.

The export is resumable and idempotent: re-running it never duplicates rows and
picks up where the previous run stopped. That matters because a full history
pull across several channels takes a long time and will be interrupted.

Normalized text and fingerprints are computed at write time so that downstream
tools (labeler, gazetteer, eval harness) all read the same normalization and
cannot drift from the runtime pipeline.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .normalize import content_fingerprint, normalize_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    channel     TEXT    NOT NULL,
    message_id  INTEGER NOT NULL,
    ts          INTEGER NOT NULL,
    date_utc    TEXT    NOT NULL,
    text_raw    TEXT,
    text_norm   TEXT,
    fingerprint TEXT,
    edit_ts     INTEGER,
    reply_to    INTEGER,
    reply_text  TEXT,
    media_type  TEXT,
    fwd_from    TEXT,
    PRIMARY KEY (channel, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages (ts);
CREATE INDEX IF NOT EXISTS idx_messages_fp ON messages (fingerprint);
CREATE INDEX IF NOT EXISTS idx_messages_channel_ts ON messages (channel, ts);

CREATE TABLE IF NOT EXISTS export_blocks (
    channel TEXT    NOT NULL,
    lo      INTEGER NOT NULL,
    hi      INTEGER NOT NULL,
    cursor  INTEGER,
    done    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (channel, lo)
);

CREATE TABLE IF NOT EXISTS channels (
    channel    TEXT PRIMARY KEY,
    title      TEXT,
    max_id     INTEGER NOT NULL DEFAULT 0,
    first_ts   INTEGER,
    last_ts    INTEGER,
    updated_at TEXT
);
"""


@dataclass(frozen=True)
class Msg:
    """A single exported message, already normalized."""

    channel: str
    message_id: int
    ts: int
    text_raw: str
    edit_ts: int | None = None
    reply_to: int | None = None
    reply_text: str | None = None
    media_type: str | None = None
    fwd_from: str | None = None

    @property
    def date_utc(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False lets the backfill's worker threads share one
    # connection. Safe only because every write goes through the caller's
    # db_lock (see backfill.walk_block) — do not add unsynchronized access.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL keeps the labeler readable while an export is still writing.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
    for column, decl in (("reply_text", "TEXT"),):
        if column not in have:
            conn.execute(f"ALTER TABLE messages ADD COLUMN {column} {decl}")


def insert_messages(conn: sqlite3.Connection, msgs: Iterable[Msg]) -> int:
    """Insert messages, ignoring ones already stored. Returns rows added."""
    rows = []
    for m in msgs:
        norm = normalize_text(m.text_raw)
        rows.append(
            (
                m.channel,
                m.message_id,
                m.ts,
                m.date_utc,
                m.text_raw,
                norm,
                content_fingerprint(norm) if norm else None,
                m.edit_ts,
                m.reply_to,
                normalize_text(m.reply_text) or None,
                m.media_type,
                m.fwd_from,
            )
        )
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO messages (
            channel, message_id, ts, date_utc, text_raw, text_norm,
            fingerprint, edit_ts, reply_to, reply_text, media_type, fwd_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def resume_id(conn: sqlite3.Connection, channel: str) -> int:
    """Highest message id already stored for a channel, or 0 if none.

    Used as the export offset: we always walk forward in ascending id order,
    so this is the only cursor needed for both the initial backfill and
    subsequent incremental runs.
    """
    row = conn.execute(
        "SELECT MAX(message_id) AS m FROM messages WHERE channel = ?", (channel,)
    ).fetchone()
    return int(row["m"] or 0)


def update_channel(conn: sqlite3.Connection, channel: str, title: str | None) -> None:
    """Refresh the per-channel summary row from the messages actually stored."""
    row = conn.execute(
        """
        SELECT MAX(message_id) AS max_id, MIN(ts) AS first_ts, MAX(ts) AS last_ts
        FROM messages WHERE channel = ?
        """,
        (channel,),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO channels (channel, title, max_id, first_ts, last_ts, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel) DO UPDATE SET
            title      = COALESCE(excluded.title, channels.title),
            max_id     = excluded.max_id,
            first_ts   = excluded.first_ts,
            last_ts    = excluded.last_ts,
            updated_at = excluded.updated_at
        """,
        (
            channel,
            title,
            int(row["max_id"] or 0),
            row["first_ts"],
            row["last_ts"],
            datetime.now(tz=timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def summary(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Per-channel counts and date coverage, for the post-export report."""
    return conn.execute(
        """
        SELECT
            m.channel,
            COUNT(*)                                   AS total,
            SUM(CASE WHEN m.text_norm <> '' THEN 1 ELSE 0 END) AS with_text,
            MIN(m.date_utc)                            AS first_seen,
            MAX(m.date_utc)                            AS last_seen
        FROM messages m
        GROUP BY m.channel
        ORDER BY m.channel
        """
    ).fetchall()


# --------------------------------------------------------------------------
# Backfill progress
#
# History is walked in id blocks so the work can run in parallel and survive
# interruption. Each block keeps its own cursor: the next `before` value to
# request. A block is done when its walk drops below the block's lower bound.
# --------------------------------------------------------------------------


def plan_blocks(
    conn: sqlite3.Connection, channel: str, lo: int, hi: int, size: int
) -> int:
    """Create or extend blocks covering [lo, hi]. Returns blocks added.

    Boundaries are snapped to a global grid of `size`, not to `lo`, so block
    identities do not depend on where a particular run's range starts. A
    `--since` run followed by a full-history run therefore reuses the finished
    blocks instead of laying a second, overlapping grid over the same history.

    The topmost block grows as the channel does. If a stored block's `hi` is
    below the range now being requested, it is extended and reopened — otherwise
    a block marked done would permanently hide every message posted above the
    `hi` it happened to be created with.
    """
    added = 0
    start = (lo // size) * size
    while start <= hi:
        end = min(start + size - 1, hi)
        row = conn.execute(
            "SELECT hi, done FROM export_blocks WHERE channel = ? AND lo = ?",
            (channel, start),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO export_blocks (channel, lo, hi, cursor, done) "
                "VALUES (?, ?, ?, ?, 0)",
                (channel, start, end, end + 1),
            )
            added += 1
        elif row["hi"] < end:
            conn.execute(
                "UPDATE export_blocks SET hi = ?, cursor = ?, done = 0 "
                "WHERE channel = ? AND lo = ?",
                (end, end + 1, channel, start),
            )
        start = end + 1
    conn.commit()
    return added


def pending_blocks(conn: sqlite3.Connection, channel: str) -> list[sqlite3.Row]:
    """Blocks still to walk, newest ids first so recent history lands early."""
    return conn.execute(
        "SELECT channel, lo, hi, cursor FROM export_blocks "
        "WHERE channel = ? AND done = 0 ORDER BY lo DESC",
        (channel,),
    ).fetchall()


def set_block_cursor(
    conn: sqlite3.Connection, channel: str, lo: int, cursor: int | None, done: bool
) -> None:
    conn.execute(
        "UPDATE export_blocks SET cursor = ?, done = ? WHERE channel = ? AND lo = ?",
        (cursor, 1 if done else 0, channel, lo),
    )
    conn.commit()


def block_progress(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT channel, COUNT(*) AS blocks, SUM(done) AS done "
        "FROM export_blocks GROUP BY channel ORDER BY channel"
    ).fetchall()
