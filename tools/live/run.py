"""Watch the channels live and say what the app would say.

The first stage of this project that runs by itself. Everything before it was
batch: export a history, mine it, label it, replay it. This polls the same
`t.me/s/<channel>?after=<id>` pages the exporter uses, feeds each new message
through the very same `observe -> decide -> announce` chain the eval replays, and
prints the utterance queue.

No server, no phone, no account — it runs in a terminal through one real night,
which is his own test of the whole idea: "подивимося чи взагалі працює цей
концепт".

Three things it does besides printing.

**It measures its own lag.** Detection delay is the price of polling instead of
holding an MTProto connection, and nobody has measured it yet. Every message logs
`lag_s` — the seconds between the channel's timestamp and our seeing it — and the
summary prints the median and the worst. That number, not a preference, decides
whether a phone number is worth getting.

**It writes to the same database.** So the night is immediately labelable:
`python -m tools.labeler.build` puts it on the page with the decisions logged
beside it.

**It polls fast only when it matters.** Quiet, the loop is cheap and a missed
minute costs nothing. With an episode open it tightens to `--alert-interval`,
because during a wave the difference between five seconds and thirty is the whole
product.

Usage:
    python -m tools.live.run                        # until Ctrl+C
    python -m tools.live.run --alert-interval 4 --quiet-interval 60
"""

from __future__ import annotations

import argparse
import json
import signal
import sqlite3
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..export import store
from ..export.config import CHANNELS, DB_PATH
from ..export.tme import Client, FetchError
from ..labeler.build import kyiv_dt
from ..policy.announce import Announcer
from ..policy.episodes import Tracker, observe
from ..policy.rules import decide
from .notify import Notifier

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "data" / "live"
TOKEN_HINT = "data/telegram-bot.token"

# Quiet, there is nothing to be quick about: the channels post a few times an
# hour and a missed minute costs nothing. With an episode open the loop tightens,
# because that is when seconds are the product.
QUIET_INTERVAL_S = 45.0
ALERT_INTERVAL_S = 6.0

# After a fetch error, wait longer each time rather than hammering a channel that
# is rate-limiting us. The exporter learned this the hard way.
BACKOFF_START_S = 5.0
BACKOFF_MAX_S = 300.0

# How often to print a still-here line while nothing is happening.
HEARTBEAT_S = 900.0

# A poll that comes back this much later than it was scheduled means the machine
# was asleep, not that the loop was slow. On S3 the process survives suspend and
# resumes mid-loop, so without this the whole missed stretch arrives at once,
# prints as if it were live, and lands in the lag statistics as a single
# forty-minute delay — destroying the one number this stage exists to produce.
SLEEP_GAP_S = 120.0

# How much recent history to replay through the tracker at startup. Polling
# catches up on what arrived while the process was down, but a restart during an
# alert has nothing to catch up on and would begin blind: no episode, so the
# first place name re-announces a wave already announced, and the loop polls at
# the quiet interval through an attack. So the warm-up reads the store instead of
# relying on the poll, and an hour and a half comfortably spans an episode.
WARM_WINDOW_S = 90 * 60

_STOP = False


def _on_signal(_signum, _frame) -> None:
    global _STOP
    _STOP = True
    print("\n  зупиняюсь — дописую лог...", flush=True)


@dataclass
class Watcher:
    """Per-channel cursor and error state."""

    channel: str
    last_id: int = 0
    backoff_until: float = 0.0
    errors: int = 0
    seen: int = 0


@dataclass
class Session:
    tracker: Tracker = field(default_factory=Tracker)
    notifier: Notifier | None = None
    announcer: Announcer = field(default_factory=Announcer)
    lags: list[float] = field(default_factory=list)
    decisions: int = 0
    audible: int = 0
    log: list[dict] = field(default_factory=list)


def fmt_lag(seconds: float) -> str:
    return f"{seconds:4.0f}s" if seconds < 600 else "  >10m"


def handle(session: Session, channel: str, message_id: int, ts: int, text: str,
           is_reply: bool, now: float, warm: bool = False) -> None:
    """Run one message through the policy and say what comes out.

    `warm` is the catch-up pass. Resuming after the machine was off means there
    is a backlog, and it has to go through the tracker or the run starts blind to
    an alert that is already on — but it must not print, and above all must not
    count towards the lag statistics, where a six-hour-old message would drown
    the number the whole exercise is here to measure.
    """
    obs = observe(ts, text, is_reply, channel)
    decision = decide(obs, session.tracker)
    session.tracker.record(obs, decision.level if decision.notify else None,
                           decision.alarm if decision.notify else None)
    utterance = session.announcer.announce(obs, decision)

    lag = max(0.0, now - ts)
    if not warm:
        session.lags.append(lag)
        session.decisions += 1
        if decision.audible:
            session.audible += 1

    session.log.append({
        "at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "anchor": f"{channel}/{message_id}",
        "lag_s": round(lag, 1),
        "text": text,
        "notify": decision.notify,
        "level": decision.level,
        "alarm": decision.alarm,
        "reason": decision.reason,
        "said": utterance.text if utterance else None,
        "warm": warm or None,
    })

    if warm:
        return

    # To the phone, if a bot is configured. A failure here must never take the
    # watch down: a missing notification is a bad night, a crashed watcher is no
    # night at all.
    if utterance is not None and session.notifier is not None:
        from .notify import format_message

        session.notifier.send(format_message(utterance, obs, decision),
                              audible=decision.audible)
    mark = "!!" if decision.audible else ("..." if decision.notify else "  ")
    # flush on every line: this runs for hours in a terminal, and a buffered
    # alert is not an alert.
    print(f"{kyiv_dt(ts):%H:%M:%S} {fmt_lag(lag)} {mark:<3} {channel[:9]:<10} "
          f"{text.replace(chr(10), ' / ')[:84]}", flush=True)
    if utterance:
        print(f"{'':<21}   -> «{utterance.text}»   [{utterance.lead}]", flush=True)


def poll_once(client: Client, conn: sqlite3.Connection, watchers: list[Watcher],
              session: Session, warm: bool = False) -> int:
    """One pass over every channel. Returns how many new messages arrived."""
    fresh = []
    for w in watchers:
        if w.backoff_until and time.time() < w.backoff_until:
            continue
        try:
            page = client.page(w.channel, after=w.last_id or None)
        except FetchError as exc:
            w.errors += 1
            wait = min(BACKOFF_START_S * (2 ** min(w.errors, 6)), BACKOFF_MAX_S)
            w.backoff_until = time.time() + wait
            print(f"  ! {w.channel}: {exc} — пауза {wait:.0f}s", flush=True)
            continue
        w.errors = 0
        w.backoff_until = 0.0
        new = [m for m in page.messages if m.message_id > w.last_id]
        if new:
            w.last_id = max(m.message_id for m in new)
            w.seen += len(new)
            fresh.extend(new)

    if not fresh:
        return 0

    # Store first, then read the normalized text back out. The policy has to see
    # exactly what the labeler and the eval see, and normalization lives there.
    store.insert_messages(conn, fresh)
    conn.commit()

    now = time.time()
    rows = []
    for msg in fresh:
        row = conn.execute(
            "SELECT ts, text_norm, reply_to FROM messages "
            "WHERE channel = ? AND message_id = ?",
            (msg.channel, msg.message_id)).fetchone()
        if row is None or not row["text_norm"]:
            continue          # a photo with no caption decides nothing
        rows.append((msg.channel, msg.message_id, row["ts"], row["text_norm"],
                     row["reply_to"] is not None))

    for channel, message_id, ts, text, is_reply in sorted(rows, key=lambda r: r[2]):
        handle(session, channel, message_id, ts, text, is_reply, now, warm=warm)
    return len(fresh)


def interval_hint(args, session: Session) -> float:
    """The interval the last sleep was supposed to be."""
    return (args.alert_interval if session.tracker.episode is not None
            else args.quiet_interval)


def write_log(session: Session, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in session.log:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarise(session: Session, started: float) -> None:
    minutes = (time.time() - started) / 60
    print()
    print(f"=== {minutes:.0f} хв, {session.decisions} повідомлень, "
          f"{session.audible} побудок ===")
    if session.lags:
        lags = sorted(session.lags)
        p90 = lags[min(len(lags) - 1, int(len(lags) * 0.9))]
        print(f"  затримка виявлення: медіана {statistics.median(lags):.0f}s, "
              f"p90 {p90:.0f}s, гірша {lags[-1]:.0f}s")
        print("  (це ціна опитування замість постійного зʼєднання — те число,")
        print("   що вирішує, чи потрібен MTProto і телефонний номер)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--quiet-interval", type=float, default=QUIET_INTERVAL_S,
                    help="Seconds between polls with no episode open.")
    ap.add_argument("--alert-interval", type=float, default=ALERT_INTERVAL_S,
                    help="Seconds between polls while an episode is open.")
    ap.add_argument("--rps", type=float, default=2.0,
                    help="Requests per second ceiling, shared across channels.")
    ap.add_argument("--channels", action="append", dest="channels",
                    help="Watch only this channel (repeatable).")
    ap.add_argument("--memory-floor-mb", type=int, default=0,
                    help="Hold this much memory. See deploy/README.md — it "
                         "exists to clear a cloud provider's idle threshold.")
    args = ap.parse_args(argv)

    # Held for the life of the process. Stated plainly rather than disguised as
    # a cache: Oracle reclaims an Always Free instance whose CPU, network *and*
    # memory all sit under 20% for a week, and this watcher uses a few tens of
    # megabytes. A cache that exists to fool a monitor is a lie in the code; a
    # named ballast is at least honest about what it is doing and why.
    #
    # It goes away when the classifier arrives and clears the threshold for real.
    ballast = bytearray(args.memory_floor_mb * 1024 * 1024) if args.memory_floor_mb else None
    if ballast is not None:
        # Touch every page, or the kernel never actually commits it and the
        # reported usage stays at nothing.
        for offset in range(0, len(ballast), 4096):
            ballast[offset] = 1
        print(f"  памʼять: тримаю {args.memory_floor_mb} МБ "
              f"(поріг простою хмари, див. deploy/README.md)")

    signal.signal(signal.SIGINT, _on_signal)
    # Also on SIGTERM, so the log survives being stopped by anything other than
    # Ctrl+C — a scheduled task, a shutdown, a `timeout` in a test.
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_signal)

    conn = store.connect(args.db)
    client = Client(rps=args.rps)
    channels = args.channels or list(CHANNELS)
    watchers = [Watcher(channel=c, last_id=store.resume_id(conn, c)) for c in channels]

    for w in watchers:
        if w.last_id == 0:
            try:
                w.last_id = client.newest_id(w.channel)
            except FetchError as exc:
                print(f"  ! {w.channel}: {exc}")

    started = time.time()
    session = Session(notifier=Notifier())
    # The official channel speaks only when the siren changes, so "has it spoken
    # lately" is not the same question as "is it being watched".
    from ..policy.episodes import OFFICIAL_CHANNELS

    session.tracker.official_source = bool(OFFICIAL_CHANNELS & set(channels))
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"{stamp}.jsonl"

    print(f"Слухаю {len(watchers)} канал(и). Ctrl+C щоб зупинити.")
    print(f"  інтервал: {args.quiet_interval:.0f}s тихо / "
          f"{args.alert_interval:.0f}s під тривогу")
    print(f"  лог: {log_path}")
    if session.notifier and session.notifier.enabled:
        who = session.notifier.chat_id or session.notifier.find_chat()
        print(f"  телефон: telegram → {who or 'напиши боту, щоб він знав куди слати'}")
    else:
        print(f"  телефон: вимкнено (нема {TOKEN_HINT})")

    # Warm the tracker from what is already stored, before polling at all. A
    # restart mid-alert has nothing to catch up on and would otherwise start with
    # no episode — announcing a wave already announced, at the quiet interval.
    warm_from = int(time.time()) - WARM_WINDOW_S
    warmed = 0
    for row in conn.execute(
            "SELECT channel, message_id, ts, text_norm, reply_to FROM messages "
            "WHERE ts >= ? AND text_norm <> '' ORDER BY ts", (warm_from,)):
        handle(session, row["channel"], row["message_id"], row["ts"],
               row["text_norm"], row["reply_to"] is not None, time.time(), warm=True)
        warmed += 1
    if warmed:
        state = "ТРИВОГА" if session.tracker.episode is not None else "тихо"
        print(f"  прогрів: {warmed} повідомлень за останні "
              f"{WARM_WINDOW_S // 60} хв — стан: {state}")

    # Catch up on whatever arrived while the machine was off, silently. The
    # tracker needs it — an alert may already be running — but printing six
    # hours of backlog buries the live feed, and counting its lag would make the
    # one measurement here meaningless.
    caught = 0
    for _ in range(200):
        got = poll_once(client, conn, watchers, session, warm=True)
        caught += got
        if got == 0:
            break
    if caught:
        state = "ТРИВОГА" if session.tracker.episode is not None else "тихо"
        print(f"  наздогнав {caught} нових — стан: {state}")
    print("  --- далі живий ефір ---", flush=True)
    print()

    last_beat = time.time()
    last_poll = time.time()
    while not _STOP:
        # Was the machine asleep? Then this batch is catch-up, not live.
        overslept = time.time() - last_poll
        slept = overslept > interval_hint(args, session) + SLEEP_GAP_S
        if slept:
            print(f"  · машина спала ~{overslept / 60:.0f} хв — "
                  f"наздоганяю тихо", flush=True)
        poll_once(client, conn, watchers, session, warm=slept)
        last_poll = time.time()
        write_log(session, log_path)

        open_episode = session.tracker.episode is not None
        interval = args.alert_interval if open_episode else args.quiet_interval

        if time.time() - last_beat > HEARTBEAT_S:
            last_beat = time.time()
            state = "ТРИВОГА" if open_episode else "тихо"
            print(f"  · {kyiv_dt(int(time.time())):%H:%M} {state}, "
                  f"{session.decisions} повідомлень, {session.audible} побудок",
                  flush=True)

        deadline = time.time() + interval
        while not _STOP and time.time() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.time())))

    write_log(session, log_path)
    summarise(session, started)
    if session.notifier and session.notifier.enabled:
        print(f"  на телефон надіслано: {session.notifier.sent}"
              f"   помилок: {session.notifier.failures}")
    print(f"  лог: {log_path}")
    print("  розмітити цю ніч: python -m tools.labeler.build")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
