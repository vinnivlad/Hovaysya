"""Backfill walker tests, driven by a fake page source.

The walker's correctness is entirely about cursor motion: real history has
deleted-message gaps, so it must follow the cursor the server returns and must
never spin when that cursor stops advancing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import threading

from tools.export import store
from tools.export.backfill import Progress, walk_block
from tools.export.store import Msg
from tools.export.tme import Page


class FakeClient:
    """Serves pages from a fixed id set, mimicking t.me/s semantics."""

    def __init__(self, ids, page_size=20, channel="ch"):
        self.all_ids = sorted(ids)
        self.page_size = page_size
        self.channel = channel
        self.calls = []
        self.bytes = 0
        self.throttled = 0

    def page(self, channel, before=None, after=None):
        self.calls.append(before)
        pool = [i for i in self.all_ids if before is None or i < before]
        chosen = pool[-self.page_size :]
        msgs = [
            Msg(channel=channel, message_id=i, ts=1_700_000_000 + i, text_raw=f"m{i}")
            for i in chosen
        ]
        return Page(messages=msgs, before=min(chosen) if chosen else None)


class StuckClient(FakeClient):
    """Always returns the same page — the pathological no-progress case."""

    def page(self, channel, before=None, after=None):
        self.calls.append(before)
        msgs = [Msg(channel=channel, message_id=50, ts=1, text_raw="x")]
        return Page(messages=msgs, before=50)


def db(tmp_path):
    return store.connect(tmp_path / "b.db")


def walk(conn, client, lo, hi, cursor=None):
    return walk_block(
        client, conn, threading.Lock(), "ch", lo, hi, cursor, Progress()
    )


# --- plan_blocks ----------------------------------------------------------


def test_plan_blocks_covers_the_range(tmp_path):
    conn = db(tmp_path)
    assert store.plan_blocks(conn, "ch", 1, 25, 10) == 3  # grid: 0-9, 10-19, 20-25
    rows = conn.execute(
        "SELECT lo, hi FROM export_blocks WHERE channel='ch' ORDER BY lo"
    ).fetchall()
    assert [(r["lo"], r["hi"]) for r in rows] == [(0, 9), (10, 19), (20, 25)]


def test_plan_blocks_is_idempotent(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 1, 25, 10)
    assert store.plan_blocks(conn, "ch", 1, 25, 10) == 0


def test_plan_blocks_starts_cursor_above_block_top(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 10, 100)
    row = conn.execute("SELECT cursor FROM export_blocks").fetchone()
    assert row["cursor"] == 11  # before=11 must be able to return id 10


def test_pending_blocks_excludes_done_and_orders_newest_first(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 1, 30, 10)
    store.set_block_cursor(conn, "ch", 10, None, done=True)
    los = [r["lo"] for r in store.pending_blocks(conn, "ch")]
    assert los == [30, 20, 0]


# --- walk_block -----------------------------------------------------------


def test_walk_block_fetches_everything_in_range(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 50, 100)
    client = FakeClient(range(1, 51), page_size=20)
    added = walk(conn, client, 0, 50, cursor=51)
    assert added == 50


def test_walk_block_marks_the_block_done(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 50, 100)
    walk(conn, FakeClient(range(1, 51)), 0, 50, cursor=51)
    assert store.pending_blocks(conn, "ch") == []


def test_walk_block_stays_inside_its_block(tmp_path):
    """A block must not walk past its lower bound into a neighbour's range."""
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 100, 50)
    client = FakeClient(range(1, 101), page_size=20)
    walk(conn, client, 50, 99, cursor=100)
    ids = [r["message_id"] for r in conn.execute("SELECT message_id FROM messages")]
    # Overlap of at most one page is expected; nothing far below the bound.
    assert min(ids) > 30


def test_walk_block_resumes_from_a_stored_cursor(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 50, 100)
    client = FakeClient(range(1, 51), page_size=20)
    walk(conn, client, 0, 50, cursor=21)
    ids = {r["message_id"] for r in conn.execute("SELECT message_id FROM messages")}
    assert max(ids) == 20  # nothing above the resume point was re-fetched


def test_walk_block_handles_id_gaps(tmp_path):
    """Deleted messages must not stall or skip the walk."""
    conn = db(tmp_path)
    ids = [i for i in range(1, 61) if i % 7]  # holes throughout
    store.plan_blocks(conn, "ch", 0, 60, 100)
    added = walk(conn, FakeClient(ids, page_size=20), 0, 60, cursor=61)
    assert added == len(ids)


def test_walk_block_stops_when_history_is_exhausted(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 50, 100)
    client = FakeClient(range(1, 11), page_size=20)
    added = walk(conn, client, 0, 50, cursor=51)
    assert added == 10
    assert len(client.calls) <= 3


def test_walk_block_does_not_spin_when_cursor_stops_advancing(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 100, 200)
    client = StuckClient([50])
    walk(conn, client, 0, 100, cursor=101)
    assert len(client.calls) <= 2


def test_walk_block_is_idempotent_across_reruns(tmp_path):
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 50, 100)
    walk(conn, FakeClient(range(1, 51)), 0, 50, cursor=51)
    second = walk(conn, FakeClient(range(1, 51)), 0, 50, cursor=51)
    assert second == 0
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert total == 50


def test_walk_block_works_from_a_worker_thread(tmp_path):
    """Regression: sqlite connections are thread-bound by default, so a walker
    running inside the pool failed with ProgrammingError while the same call
    from the main thread passed."""
    from concurrent.futures import ThreadPoolExecutor

    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 0, 40, 100)
    lock = threading.Lock()
    client = FakeClient(range(1, 41), page_size=20)
    with ThreadPoolExecutor(max_workers=2) as pool:
        added = pool.submit(
            walk_block, client, conn, lock, "ch", 0, 40, 41, Progress()
        ).result()
    assert added == 40


def test_plan_blocks_snaps_to_a_global_grid(tmp_path):
    """Block identities must not depend on where the range happens to start."""
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 10_014, 10_200, 5000)
    los = [r["lo"] for r in conn.execute(
        "SELECT lo FROM export_blocks WHERE channel='ch' ORDER BY lo")]
    assert los == [10_000]  # not 10_014


def test_widening_the_range_reuses_existing_blocks(tmp_path):
    """A --since run followed by a full run must not re-plan the same history."""
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 10_014, 10_200, 5000)      # narrow, recent
    store.set_block_cursor(conn, "ch", 10_000, None, done=True)
    added = store.plan_blocks(conn, "ch", 1, 10_200, 5000)   # full history
    los = sorted(r["lo"] for r in conn.execute(
        "SELECT lo FROM export_blocks WHERE channel='ch'"))
    assert los == [0, 5000, 10_000]
    assert added == 2                                        # 10_000 was reused
    assert [r["lo"] for r in store.pending_blocks(conn, "ch")] == [5000, 0]


def test_a_done_top_block_is_reopened_when_the_channel_grows(tmp_path):
    """Without this, every message above a finished block's hi is invisible."""
    conn = db(tmp_path)
    store.plan_blocks(conn, "ch", 1, 10_200, 5000)
    store.set_block_cursor(conn, "ch", 10_000, None, done=True)
    assert store.pending_blocks(conn, "ch") and 10_000 not in [
        r["lo"] for r in store.pending_blocks(conn, "ch")
    ]

    store.plan_blocks(conn, "ch", 1, 12_400, 5000)  # channel grew
    top = conn.execute(
        "SELECT hi, cursor, done FROM export_blocks WHERE channel='ch' AND lo=10000"
    ).fetchone()
    assert top["hi"] == 12_400
    assert top["cursor"] == 12_401
    assert top["done"] == 0
