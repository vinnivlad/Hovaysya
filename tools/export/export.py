"""Export Telegram monitoring-channel history into a local SQLite database.

Reads the public `t.me/s/<channel>` web preview: no account, no phone number,
no API key. See `tme.py` for the measured properties this relies on.

Usage:
    python -m tools.export.export --channel mon1tor_ua --since 2026-08-26
    python -m tools.export.export --since 2026-07-27   # labeling set
    python -m tools.export.export                      # full history
    python -m tools.export.export --status             # what is left to do

Resumable and idempotent. History is split into id blocks with their own
cursors, so an interrupted run is continued by repeating the command; nothing is
re-fetched that already completed, and nothing is duplicated if it is.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
from datetime import datetime, timezone

from . import store
from .backfill import DEFAULT_BLOCK_SIZE, Progress, backfill_channel
from .config import CHANNELS, DB_PATH
from .tme import Client, FetchError


def print_summary(conn) -> None:
    rows = store.summary(conn)
    if not rows:
        print("No messages stored yet.")
        return
    print(f"\n{'channel':<18}{'total':>9}{'w/ text':>9}{'replies':>9}  coverage")
    for row in rows:
        replies = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE channel = ? AND reply_to IS NOT NULL",
            (row["channel"],),
        ).fetchone()[0]
        span = f"{row['first_seen'][:10]} .. {row['last_seen'][:10]}"
        print(
            f"{row['channel']:<18}{row['total']:>9}{row['with_text']:>9}"
            f"{replies:>9}  {span}"
        )
    total = sum(r["total"] for r in rows)
    print(f"{'TOTAL':<18}{total:>9}")


def print_status(conn) -> None:
    rows = store.block_progress(conn)
    if not rows:
        print("No backfill planned yet.")
    else:
        print(f"{'channel':<18}{'blocks':>8}{'done':>8}{'left':>8}")
        for r in rows:
            done = int(r["done"] or 0)
            print(
                f"{r['channel']:<18}{r['blocks']:>8}{done:>8}"
                f"{r['blocks'] - done:>8}"
            )
    print_summary(conn)


def run(args: argparse.Namespace) -> int:
    # A candidate channel is measured before it is trusted, and measuring it must
    # not touch the corpus: the eval replays every night from that file, so a
    # channel dropped into it would silently rewrite the history every number in
    # this project is checked against.
    db = pathlib.Path(getattr(args, "db", None) or DB_PATH)
    conn = store.connect(db)

    if args.status:
        print_status(conn)
        conn.close()
        return 0

    channels = args.channels or list(CHANNELS)
    since = (
        datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.since
        else None
    )

    client = Client(rps=args.rps, retries=args.retries)
    progress = Progress()
    started = time.monotonic()

    print(f"Exporting {len(channels)} channel(s) -> {db}")
    print(f"  rate {args.rps} req/s, {args.workers} workers, block {args.block_size}\n")

    total = 0
    for channel in channels:
        try:
            total += backfill_channel(
                client,
                conn,
                channel,
                workers=args.workers,
                block_size=args.block_size,
                since=since,
                progress=progress,
            )
        except FetchError as exc:
            print(f"  ! {channel}: {exc}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nInterrupted — progress is saved, re-run to continue.")
            break

    elapsed = time.monotonic() - started
    print(
        f"\nAdded {total} rows in {elapsed / 60:.1f} min — "
        f"{client.requests} requests, {client.bytes / 1048576:.1f} MB, "
        f"{client.throttled} throttled, {progress.errors} errors"
    )
    print_summary(conn)
    conn.close()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Only export messages from this date onward. Found by binary "
        "search over the id space, so it costs ~15 extra requests per channel.",
    )
    p.add_argument(
        "--channel",
        action="append",
        dest="channels",
        help="Export only this channel (repeatable). Defaults to config.CHANNELS.",
    )
    p.add_argument(
        "--rps",
        type=float,
        default=2.0,
        help="Global request rate. 1.25 req/s was measured clean; 2.0 is the "
        "default. Throughput is bounded by this, not by --workers.",
    )
    p.add_argument("--db", default=None,
                   help="Write somewhere other than the corpus. Use it for a "
                        "candidate channel: the eval replays the corpus, so a "
                        "channel dropped into it rewrites every measurement.")
    p.add_argument("--workers", type=int, default=4, help="Concurrent block walkers.")
    p.add_argument(
        "--block-size",
        type=int,
        default=DEFAULT_BLOCK_SIZE,
        help="Ids per block. Smaller blocks resume at finer granularity.",
    )
    p.add_argument("--retries", type=int, default=4, help="Per-request retry budget.")
    p.add_argument(
        "--status",
        action="store_true",
        help="Print backfill progress and stored coverage, then exit.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
