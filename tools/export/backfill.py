"""Parallel, resumable history backfill over t.me/s pages.

`?before=<id>` accepts an arbitrary id, so history is random-access. That lets
the id space be split into blocks which are walked concurrently, while each
block still follows the cursor Telegram returns — necessary because deleted
messages leave gaps, so stepping the id by a fixed page size would skip or
re-read ranges.

Throughput is bounded by the shared rate limiter, not by worker count: workers
exist to keep the request pipe full while each one waits on I/O. A 429 slows
every worker, not just the one that hit it.
"""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

from . import store
from .tme import Client, FetchError

DEFAULT_BLOCK_SIZE = 5000


@dataclass
class Progress:
    """Shared counters across worker threads."""

    pages: int = 0
    rows: int = 0
    blocks_done: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, *, pages: int = 0, rows: int = 0, blocks: int = 0, errors: int = 0):
        with self._lock:
            self.pages += pages
            self.rows += rows
            self.blocks_done += blocks
            self.errors += errors
            return self.pages


def walk_block(
    client: Client,
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    channel: str,
    lo: int,
    hi: int,
    cursor: int | None,
    progress: Progress,
    log_every: int = 25,
) -> int:
    """Walk one id block downward from `cursor` to `lo`. Returns rows added."""
    added = 0
    cursor = cursor if cursor is not None else hi + 1

    while cursor is not None and cursor > lo:
        try:
            page = client.page(channel, before=cursor)
        except FetchError as exc:
            progress.add(errors=1)
            print(f"  ! {channel} block {lo}-{hi}: {exc}")
            return added

        if not page.messages:
            # No older messages in reach: this block is exhausted.
            break

        with db_lock:
            added += store.insert_messages(conn, page.messages)

        # Telegram's own cursor is authoritative; min(ids) is the fallback when
        # the page carries no "load more" link (happens at the very beginning).
        nxt = page.before if page.before is not None else min(page.ids)
        if nxt >= cursor:  # no forward motion — stop rather than spin
            break
        cursor = nxt

        with db_lock:
            store.set_block_cursor(conn, channel, lo, cursor, done=cursor <= lo)

        n = progress.add(pages=1, rows=0)
        if n % log_every == 0:
            print(
                f"    {n} pages, {progress.rows + added} rows, "
                f"{client.bytes / 1048576:.0f} MB, {progress.errors} errors",
                end="\r",
            )

    with db_lock:
        store.set_block_cursor(conn, channel, lo, cursor, done=True)
    progress.add(rows=added, blocks=1)
    return added


def backfill_channel(
    client: Client,
    conn: sqlite3.Connection,
    channel: str,
    *,
    workers: int = 4,
    block_size: int = DEFAULT_BLOCK_SIZE,
    since: datetime | None = None,
    progress: Progress | None = None,
) -> int:
    """Plan and run the backfill for one channel. Returns rows added."""
    progress = progress or Progress()
    db_lock = threading.Lock()

    newest = client.newest_id(channel)
    floor = 1
    if since is not None:
        # Random access turns "only the last month" into ~log2(newest) requests
        # instead of a walk over the whole history.
        floor = client.find_id_at_date(channel, since, newest)
        print(f"  {channel}: since {since:%Y-%m-%d} -> ids from {floor}")

    store.plan_blocks(conn, channel, floor, newest, block_size)
    blocks = store.pending_blocks(conn, channel)
    if not blocks:
        print(f"  {channel}: nothing pending (already complete)")
        return 0

    span = newest - floor + 1
    print(
        f"  {channel}: ids {floor}-{newest} (~{span} msgs) "
        f"in {len(blocks)} pending block(s), {workers} workers"
    )

    added = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                walk_block,
                client,
                conn,
                db_lock,
                channel,
                b["lo"],
                b["hi"],
                b["cursor"],
                progress,
            ): b
            for b in blocks
        }
        for fut in as_completed(futures):
            b = futures[fut]
            try:
                added += fut.result()
            except Exception as exc:  # noqa: BLE001 - one block must not kill the run
                progress.add(errors=1)
                print(f"  ! {channel} block {b['lo']}-{b['hi']}: {exc!r}")

    with db_lock:
        store.update_channel(conn, channel, None)
    print(f"  {channel}: +{added} rows{' ' * 30}")
    return added
