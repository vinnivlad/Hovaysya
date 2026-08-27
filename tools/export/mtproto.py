"""DEFERRED: MTProto export via a Telethon user session.

Not wired into the default CLI and not exercised by the test suite — it needs
an api_id/api_hash and a phone number, both deliberately postponed (see
README). Kept because MTProto is the likely realtime upgrade: it pushes
instead of polling and reports edits and deletions, which the HTML source
cannot see. Run standalone with `python -m tools.export.mtproto`.

Export Telegram monitoring-channel history into a local SQLite database.

Reading public channels requires MTProto with a *user* session — the Bot API
only sees channels where the bot is an administrator. Get an api_id/api_hash
from https://my.telegram.org (API development tools) and put them in .env.

Usage:
    python -m tools.export.export --limit 200          # smoke test
    python -m tools.export.export --since 2025-07-01   # last N months
    python -m tools.export.export                      # full history

Resumable: each run continues from the highest message id already stored, so an
interrupted export is restarted by simply running the command again.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameNotOccupiedError,
)

from . import store
from .config import CHANNELS, DB_PATH, SESSION_PATH

BATCH_SIZE = 500


def _media_type(message) -> str | None:
    media = getattr(message, "media", None)
    return type(media).__name__ if media is not None else None


def _fwd_from(message) -> str | None:
    fwd = getattr(message, "fwd_from", None)
    if fwd is None:
        return None
    # from_name is set for forwards from users who hide their account.
    return getattr(fwd, "from_name", None) or str(getattr(fwd, "from_id", "") or "") or None


async def export_channel(
    client: TelegramClient,
    conn,
    channel: str,
    since: datetime | None,
    limit: int | None,
) -> int:
    """Export one channel forward from the last stored id. Returns rows added."""
    try:
        entity = await client.get_entity(channel)
    except (UsernameNotOccupiedError, ChannelPrivateError, ValueError) as exc:
        print(f"  ! {channel}: cannot resolve ({type(exc).__name__}) — skipped")
        return 0

    title = getattr(entity, "title", None)
    offset_id = store.resume_id(conn, channel)

    # offset_date only applies to the initial pull; once we have a cursor, the
    # id cursor is authoritative and mixing the two would skip messages.
    offset_date = since if (since and offset_id == 0) else None
    mode = "backfill" if offset_id == 0 else f"resume from id {offset_id}"
    print(f"  · {channel} ({title}): {mode}")

    added = 0
    batch: list[store.Msg] = []
    seen = 0

    async for message in client.iter_messages(
        entity,
        reverse=True,  # ascending ids, so offset_id acts as a resume cursor
        offset_id=offset_id,
        offset_date=offset_date,
        limit=limit,
    ):
        if message.date is None:
            continue
        text = message.message or ""
        batch.append(
            store.Msg(
                channel=channel,
                message_id=message.id,
                ts=int(message.date.replace(tzinfo=timezone.utc).timestamp()),
                text_raw=text,
                edit_ts=(
                    int(message.edit_date.replace(tzinfo=timezone.utc).timestamp())
                    if message.edit_date
                    else None
                ),
                reply_to=getattr(message.reply_to, "reply_to_msg_id", None),
                media_type=_media_type(message),
                fwd_from=_fwd_from(message),
            )
        )
        seen += 1
        if len(batch) >= BATCH_SIZE:
            added += store.insert_messages(conn, batch)
            batch.clear()
            print(f"    {seen} fetched, {added} new (id {message.id})", end="\r")

    if batch:
        added += store.insert_messages(conn, batch)
    store.update_channel(conn, channel, title)
    print(f"    {seen} fetched, {added} new{' ' * 20}")
    return added


async def run(since: datetime | None, limit: int | None, channels: list[str]) -> int:
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print(
            "TELEGRAM_API_ID / TELEGRAM_API_HASH missing.\n"
            "Get them at https://my.telegram.org -> API development tools,\n"
            "then copy .env.example to .env and fill them in.",
            file=sys.stderr,
        )
        return 2

    Path(SESSION_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(DB_PATH)

    # flood_sleep_threshold lets Telethon absorb short rate limits silently;
    # anything longer is raised so we can report it instead of hanging.
    client = TelegramClient(
        str(SESSION_PATH), int(api_id), api_hash, flood_sleep_threshold=120
    )

    async with client:
        print(f"Exporting {len(channels)} channel(s) -> {DB_PATH}")
        total = 0
        for channel in channels:
            try:
                total += await export_channel(client, conn, channel, since, limit)
            except FloodWaitError as exc:
                print(
                    f"  ! {channel}: Telegram asked to wait {exc.seconds}s — "
                    f"stopping. Re-run later; progress is saved.",
                    file=sys.stderr,
                )
                break

        print(f"\nAdded {total} new messages.\n")
        print(f"{'channel':<20} {'total':>8} {'w/ text':>8}  coverage")
        for row in store.summary(conn):
            span = f"{row['first_seen'][:10]} .. {row['last_seen'][:10]}"
            print(
                f"{row['channel']:<20} {row['total']:>8} "
                f"{row['with_text']:>8}  {span}"
            )

    conn.close()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="On an initial backfill, start from this date instead of channel "
        "creation. Ignored once a channel has stored messages.",
    )
    p.add_argument(
        "--limit",
        type=int,
        help="Stop after this many messages per channel (for smoke tests).",
    )
    p.add_argument(
        "--channel",
        action="append",
        dest="channels",
        help="Export only this channel (repeatable). Defaults to config.CHANNELS.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return asyncio.run(run(since, args.limit, args.channels or list(CHANNELS)))


if __name__ == "__main__":
    raise SystemExit(main())
