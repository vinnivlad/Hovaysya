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
import os
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
from ..policy import carry
from ..policy.announce import Announcer
from ..policy.config import CONFIG_PATH, changed_from_default, load as load_config
from ..policy.episodes import (OFFICIAL_CHANNELS, Episode, Tracker, observe,
                               read)
from ..policy.recipients import TELEGRAM_NAME, decide_all, from_dir
from ..policy.rules import decide
from .notify import Notifier
from .version import startup_note

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "data" / "live"
# One JSON file per person, rewritten every poll: what the first screen shows.
STATE_DIR = LOG_DIR / "state"
# The tracker's own memory across restarts. Beside the state files but never
# served: `/state` is a contract with a phone, this is the insides.
CARRY_DIR = LOG_DIR / "carry"
# Written by the API when somebody registers or changes their settings, read here
# between polls. The watcher never writes it.
RECIPIENTS_DIR = REPO_ROOT / "data" / "recipients"
TOKEN_HINT = "data/telegram-bot.token"

# Quiet, there is nothing to be quick about: the channels post a few times an
# hour and a missed minute costs nothing. With an episode open the loop tightens,
# because that is when seconds are the product.
QUIET_INTERVAL_S = 45.0
ALERT_INTERVAL_S = 6.0

# The official channel is on its own clock, always. His design, and the corpus
# agrees with it: over 964 days an episode is open 16% of the time and an
# official alert 7%, so watching one channel every ten seconds costs about what
# the old blanket scheme cost in total — while dropping the worst case for
# seeing a siren from 45 seconds to 10. The siren is the single most urgent
# message the system can receive, and the one message rule 2 always acts on.
OFFICIAL_INTERVAL_S = 10.0

# And in between: an episode open with no siren yet. The rules that do not wait
# for one are live in that window — falling on Zhulyany, a rise in threat class,
# a ballistic launch, a target over the ring — so it is not the quiet interval.
# Costs about 4% more requests a day than the siren-only version.
WATCH_INTERVAL_S = 20.0

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
# starts from the last message this run has seen, so the window is only about
# rebuilding state, not about missing messages.
#
# Ninety minutes, and no longer sized to cover a raid -- the episode itself is
# saved and restored now (`policy.carry`), so this window's remaining job is the
# announcer's memory: not saying again, on the first cycle, what was said just
# before the restart. `already_said` covers most of that from the log; this
# covers the rest.
#
# It was sized to cover a raid once, and it could not be. Across 1453 official
# episodes in the corpus the median runs 33 minutes but p90 is 174 and p95 is
# 275, so **20% of raids outlive ninety minutes** and one restart in five
# reported calm sky over a city under attack. Widening it would have moved that
# number without fixing anything, which is his objection and the right one:
# "тягнути історію щоб знайти старт тривоги це все одно не варіант".
WARM_WINDOW_S = 90 * 60

# How old the last logged decision may be and still be believed.
#
# Twelve hours is a bound, not an estimate: if nothing has been decided for
# longer than that the process was not merely restarted, and holding a screen
# red on that basis is worse than saying nothing.
SEED_BACK_S = 12 * 3600

# ...but a message that arrived seconds ago is not backlog, it is now. An
# all-clear was published at 15:36:57 and the watcher restarted at 15:37:01,
# four seconds later, so the catch-up swallowed it and he never heard it. Every
# deploy restarts the process, which makes this a risk we create ourselves.
#
# One minute, his bound. Anything the previous run already announced is skipped
# by anchor, so a restart cannot say the same thing twice.
FRESH_ON_RESTART_S = 60

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
    # When this channel is next due. Channels run on separate clocks: the
    # official one is always close, the rest follow the siren.
    due_at: float = 0.0
    errors: int = 0
    seen: int = 0


@dataclass
class Session:
    # One recipient today, and a list because that is the shape that would have
    # been expensive to retrofit. `tracker` and `announcer` stay as the first
    # recipient's, so nothing that reads a Session had to change.
    recipients: list = field(default_factory=list)
    tracker: Tracker = field(default_factory=Tracker)
    notifier: Notifier | None = None
    announcer: Announcer = field(default_factory=Announcer)
    lags: list[float] = field(default_factory=list)
    decisions: int = 0
    audible: int = 0
    log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        """A bare `Session()` still means one recipient: me.

        Every caller that predates the list -- the tests, the smoke runs -- built
        a Session from a tracker and an announcer, and that has to keep meaning
        what it meant. So the list is derived from them rather than required
        beside them.
        """
        if not self.recipients:
            from ..policy.recipients import TELEGRAM_NAME, Recipient

            self.recipients = [Recipient(name=TELEGRAM_NAME,
                                         config=self.tracker.config,
                                         tracker=self.tracker,
                                         announcer=self.announcer)]


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
    # Read once, decide once per person. The reading is 0.58 ms of Ukrainian and
    # the personal half is 0.002 ms, so the loop is nearly free -- see
    # `episodes.Reading`.
    reading = read(ts, text, is_reply, channel)
    for who, obs, decision in decide_all(reading, session.recipients):
        utterance = who.announcer.announce(obs, decision)
        _say(session, who, channel, message_id, ts, text, obs, decision,
             utterance, now, warm)


def _sky(episode) -> dict:
    """Where the alert state goes in a log row, in `/state`'s own vocabulary."""
    from ..policy.status import ALERT, QUIET, WATCHING

    if episode is None:
        return {"sky": QUIET, "since": None}
    return {"sky": ALERT if episode.official_alert else WATCHING,
            "since": episode.opened_at}


def _say(session: Session, who, channel: str, message_id: int, ts: int,
         text: str, obs, decision, utterance, now: float, warm: bool) -> None:
    """Everything one recipient's decision produces: numbers, log, phone, line."""

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
        # Always, even with one recipient. Left conditional it read exactly as
        # before -- and the API had nothing to filter on the day a second person
        # registered, so everyone was served the watcher's own decisions.
        "who": who.name,
        "warm": warm or None,
        # The state of the sky as of this message, in the same three words
        # `/state` uses. Written because he doubted the alternative and was
        # right to: reading it back out of `level` works 97.9% of the time --
        # measured, 1906 of 1947 corpus rows -- and the 2.1% are missiles over
        # the city before the siren, where the level says "alert" and the sky is
        # only "watching". A fact this process already knows should not be
        # recovered at 98% from a field that means something else.
        **_sky(who.tracker.episode),
    })

    if warm:
        return

    # To the phone, if a bot is configured -- and only for the recipient the bot
    # *is*. There is one notifier and it points at one chat, so sending it for
    # every recipient sends every bell as many times as there are people.
    #
    # Which is what happened, live, the evening `from_dir` started always
    # including `telegram_channel`: A already had a registered token from testing
    # the API, so it went from one recipient to two and he got two of everything.
    # He noticed on the one that is unmistakable: "тільки що прийшло 2 відбої о
    # 19:41."
    #
    # The name is the gate because the name is the fact: `telegram_channel` is a
    # delivery channel that always exists, and everyone who registers a phone is
    # delivered to by push instead. Anything cleverer -- first recipient, or
    # whoever holds the shipped config -- would be a rule that quietly stops
    # being true.
    #
    # A failure here must never take the watch down: a missing notification is a
    # bad night, a crashed watcher is no night at all.
    if (utterance is not None and session.notifier is not None
            and who.name == TELEGRAM_NAME):
        from .notify import format_message

        session.notifier.send(format_message(utterance, obs, decision),
                              audible=decision.audible)
    mark = "!!" if decision.audible else ("..." if decision.notify else "  ")
    # Whose decision this is, because there is one line per recipient and
    # without the name they read as the same line four times. His point, and it
    # inverts what I was about to do: I had it down as noise to collapse, and
    # "якщо це журнал, то треба писати id користувача ще" is the better answer --
    # four people deciding differently about one message is exactly what a
    # watcher's log is for. The JSON log has carried `who` since the day a
    # second person registered; only the human-readable line did not.
    #
    # flush on every line: this runs for hours in a terminal, and a buffered
    # alert is not an alert.
    print(f"{kyiv_dt(ts):%H:%M:%S} {fmt_lag(lag)} {mark:<3} "
          f"{who.name[:9]:<10} {channel[:9]:<10} "
          f"{text.replace(chr(10), ' / ')[:74]}", flush=True)
    if utterance:
        print(f"{'':<21}   -> «{utterance.text}»   [{utterance.lead}]", flush=True)


def already_said(log_dir: Path, skip: Path) -> set[str]:
    """Anchors the previous run announced out loud, from its own log."""
    logs = sorted((p for p in log_dir.glob("*.jsonl") if p != skip),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return set()
    seen = set()
    try:
        for line in logs[0].read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not row.get("warm"):
                seen.add(row["anchor"])
    except (OSError, ValueError):
        return set()
    return seen


def poll_once(client: Client, conn: sqlite3.Connection, watchers: list[Watcher],
              session: Session, warm: bool = False, args=None,
              fresh_from: float | None = None, said: set[str] | None = None) -> int:
    """One pass over the channels that are due. Returns how many arrived."""
    fresh = []
    for w in watchers:
        if w.backoff_until and time.time() < w.backoff_until:
            continue
        if args is not None and time.time() < w.due_at:
            continue
        if args is not None:
            w.due_at = time.time() + interval_for(w.channel, session.tracker, args)
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

    # Stable sort on the timestamp alone: equal seconds keep the order the
    # channels were polled in, which is why the official one is asked last.
    for channel, message_id, ts, text, is_reply in sorted(rows, key=lambda r: r[2]):
        quiet = warm
        if quiet and fresh_from is not None and ts >= fresh_from:
            quiet = f"{channel}/{message_id}" in (said or ())
        handle(session, channel, message_id, ts, text, is_reply, now, warm=quiet)
    return len(fresh)


def state_word(tracker: Tracker) -> str:
    """`тихо` | `стежу` | `ТРИВОГА` — and the last one means the siren.

    An episode opens on any live threat: a drone launched three regions away
    opens one, and should, because it tightens the polling long before anything
    arrives. Calling that "ТРИВОГА" was wrong in a way worth fixing rather than
    explaining — he read it in a restart message with no alert running, and an
    app that overstates once is discounted afterwards.
    """
    ep = tracker.episode
    if ep is None:
        return "тихо"
    return "ТРИВОГА" if ep.official_alert else "стежу"


def interval_for(channel: str, tracker: Tracker, args) -> float:
    """How often this channel should be asked, given what is happening."""
    from ..policy.episodes import OFFICIAL_CHANNELS

    if channel in OFFICIAL_CHANNELS:
        return args.official_interval
    ep = tracker.episode
    if ep is None:
        return args.quiet_interval
    return args.alert_interval if ep.official_alert else args.watch_interval


def interval_hint(args, session: Session) -> float:
    """The shortest interval in play — channels are on separate clocks now, so
    "the loop is late" means late for whichever comes due first."""
    return min(interval_for("alarm_kyiv", session.tracker, args),
               interval_for("mon1tor_ua", session.tracker, args))


def recipients_signature(directory: Path) -> tuple:
    """Enough of the recipients directory to notice a change, and nothing more.

    Names, sizes and modification times of the files the API writes. One
    `scandir` a poll, which is nothing beside seven HTTP fetches, and it means
    nobody has to be told to restart anything.
    """
    try:
        return tuple(sorted(
            (e.name, e.stat().st_size, e.stat().st_mtime_ns)
            for e in os.scandir(directory) if e.name.endswith(".json")))
    except OSError:
        return ()


def confirm_with_official(recipients, conn, now: float) -> int | None:
    """The declaring channel's last word, and it goes last.

    Third and last, and it earns its place on the two cases the others cannot
    cover, both of which he named. A watcher that has already spent hours
    believing the sky is clear has a log whose newest rows say so -- the truth
    is further up, and taking the newest row is the right rule, so the log
    cannot rescue it. And a watcher
    starting for the first time, or on a new box, has no log and no saved
    episode at all; if a raid is on, it will not find out until the next
    declaration, which for an alert already running is hours away.

    One row, and not a reconstruction. `alarm_kyiv` does not report the alert
    state, it *is* the alert state: it is the only source that declares rather
    than describes, and an unanswered "Повітряна тривога" is the fact that a
    raid is open. That is what makes this different from the window of chat he
    rejected -- "тягнути історію щоб знайти старт тривоги це все одно не
    варіант" is an argument against inferring, not against reading a
    declaration.

    Last, and that ordering is the correction. It used to run first, before the
    replay and the saved episode, and the startup log showed exactly what that
    cost: the declaration seated the raid at 10:58 correctly, and then `carry`
    overwrote it with an episode opened at 11:41 -- written by the process that
    had *already* gone blind, so an episode with no official siren in it. Which
    `status.snapshot` reports as `watching`, and the app draws as "БЕЗ ТРИВОГ".
    The right answer arrived and was then replaced by a worse one.

    A saved episode is more *detailed* than a declaration -- threat class,
    reconnaissance, what has been said -- and I let that stand in for being more
    authoritative. It is not. Detail written by a run that was wrong about the
    sky is still wrong about the sky.

    So this corrects instead of replacing: it keeps whatever detail is there and
    fixes the two facts the channel owns, which are that the siren is official
    and when it began.

    Silent. A siren from three hours ago is not news.
    """
    from ..nlp import hints

    channels = sorted(OFFICIAL_CHANNELS)
    holes = ",".join("?" for _ in channels)
    rows = conn.execute(
        f"SELECT ts, text_norm FROM messages WHERE channel IN ({holes}) "
        f"AND ts >= ? AND text_norm <> '' ORDER BY ts DESC LIMIT 40",
        (*channels, int(now) - SEED_BACK_S))

    for row in rows:
        text = row["text_norm"]
        state = hints.alert_state(text)
        # A partial all-clear lifts one class and leaves the raid running, so it
        # is not the last word about anything -- the same distinction that cost
        # 46 minutes of blindness when chat chatter was allowed to close an
        # episode.
        if state == "clear" and not hints.partial_clear(text):
            return None
        if state != "alert":
            continue
        for who in recipients:
            episode = who.tracker.episode
            if episode is None:
                who.tracker.episode = Episode(
                    opened_at=row["ts"],
                    alert_at=row["ts"],
                    # Alive now, because the declaration is unanswered now.
                    # Stamping this with the declaration's own time would have
                    # the tracker close the episode as idle on the first message
                    # it sees.
                    last_live=int(now),
                    alert_announced=True,
                    alert_scope_known=True,
                    official_alert=True,
                )
            else:
                # Kept, not replaced. The two facts below are the channel's;
                # everything else in the episode belongs to whoever built it.
                episode.official_alert = True
                episode.alert_announced = True
                episode.alert_at = min(episode.alert_at or row["ts"], row["ts"])
                # The earlier opening, because a raid that began at 10:58 did
                # not begin at 11:41 just because that is when we noticed.
                episode.opened_at = min(episode.opened_at, row["ts"])
            who.tracker.official_seen = row["ts"]
            # ...and the length of it, for the line that outlives it. Nothing
            # was announced here -- a siren from three hours ago is not news --
            # so there is no `Sent` to measure from, which is why this is a
            # number of its own.
            who.tracker.alert_began = min(
                who.tracker.alert_began or row["ts"], row["ts"])
        return row["ts"]
    return None


def _raid_since(row: dict) -> int | None:
    """When the raid this row was decided during began, if there was one.

    Two readings, and which one applies says how old the log is. `sky` is
    written now and means exactly this; before it existed the only evidence was
    the decision's own level, which is a statement about how loud to be and only
    coincides with the alert state -- 97.9% of the time, measured. The fallback
    is here because the log that has to rescue the raid that prompted all this
    was written by the version that did not know to record it.

    An all-clear is `level="alert"` with `alarm="clear"`, since saying it out
    loud is an audible event. Reading the level without the alarm would reopen a
    raid on the very message that ended it -- the same inversion that once had
    the app ringing a siren to announce an all-clear.
    """
    from ..policy.status import ALERT

    if "sky" in row:
        if row["sky"] != ALERT:
            return None
        since = row.get("since")
        return int(since) if since else _stamp(row)
    if row.get("level") != "alert":
        return None
    if (row.get("alarm") or "").startswith("clear"):
        return None
    return _stamp(row)


def _stamp(row: dict) -> int:
    return int(datetime.fromisoformat(row["at"]).timestamp())


def seed_from_log(session: Session, log_dir: Path, skip: Path,
                  now: float) -> int | None:
    """Believe the last thing we decided until something says otherwise.

    His answer, after I had built two more elaborate ones and both were wrong:
    "є останнє повідомлення, там live-threat shahed-jet. Що тобі ще потрібно?"
    Nothing. Every decision is logged with the level it produced, the log is
    append-only, and a row saying `alert` is the statement that a raid was on.
    There is no reconstruction to do.

    It has to be the log and not the state file, which is the part I had not
    thought through. Both are written every cycle, but `status.write` *replaces*
    its file -- so the moment a restarted watcher believes the sky is clear, the
    only copy of the truth is overwritten. The log is the one thing that cannot
    be overwritten by being wrong, and that is exactly why it is the place to
    look.

    Both of my earlier attempts failed for the same reason, which is worth
    keeping written down: they treated the state as something to derive -- once
    from ninety minutes of every channel, once from the official channel's own
    declarations. The second even worked, right up until the tracker closed the
    episode it had just opened for being three hours idle, because replaying two
    official messages leaves no sign of life between them. Derivation kept
    needing more machinery to hold up. Reading does not.

    Silent, and it stays silent: nothing here announces, because a siren from
    three hours ago is not news.
    """
    logs = sorted((path for path in log_dir.glob("*.jsonl") if path != skip),
                  key=lambda path: path.stat().st_mtime, reverse=True)
    if not logs:
        return None

    # The newest decision per person. Per person because they can differ: a raid
    # over one recipient's ring is not one over another's.
    last: dict[str, dict] = {}
    try:
        for line in logs[0].read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("level") or row.get("sky"):
                last[row.get("who") or ""] = row
    except (OSError, ValueError):
        return None

    opened = None
    for who in session.recipients:
        row = last.get(who.name)
        if row is None:
            continue
        when = _raid_since(row)
        if when is None:
            continue
        if now - when > SEED_BACK_S:
            continue
        who.tracker.episode = Episode(
            opened_at=when,
            # The last row's time, not the raid's opening, and the difference is
            # the whole thing working. `Tracker.before` closes an episode that
            # has been silent for `idle_close_s` -- 45 minutes -- so an episode
            # stamped as last alive when the raid began is closed by the very
            # next message on a raid three hours old, which is exactly the case
            # this exists for.
            last_live=_stamp(row),
            # Announced, because it was: this row is the log of having said it.
            # Without this the next message in the raid announces the siren
            # again, hours late.
            alert_announced=True,
            alert_scope_known=True,
            official_alert=True,
        )
        opened = when if opened is None else min(opened, when)
    return opened


def warm_one(who, conn, now: float) -> tuple[int, list]:
    """Replay the recent past into one person's tracker, telling them nothing.

    Without this a phone that registers during a raid gets a screen saying there
    are no threats, because its tracker has never seen a message. Understating is
    the worse direction: an app that says "без загроз" while the sirens are on
    does not get a second chance.

    The same window and the same code path as the watcher's own start-up warm --
    a Session of one, `warm=True` throughout -- so the decisions and the
    announcer's memory advance exactly as they would have, and nothing is sent
    about weather that has already passed.

    **The log rows are kept**, and discarding them was a mistake of mine that he
    found twice: "на мого користувача ховайся не підтягнув повідомлень". I
    reasoned that they were never said to this person, so showing them would be a
    lie -- but the watcher's own start-up warm keeps its rows and marks them
    `warm`, which is exactly the distinction that reasoning needed. The two paths
    disagreeing is what produced the asymmetry: after every deploy restart
    `telegram_channel` had ninety minutes of lines and anybody who had registered
    through the app had none, and deploys are frequent.

    They go into the caller's log rather than the throwaway one, because that is
    the log `/decisions` is served from and `said` is filtered out of.
    """
    solo = Session(recipients=[who], tracker=who.tracker,
                   announcer=who.announcer, notifier=None)
    seen = 0
    for row in conn.execute(
            "SELECT channel, message_id, ts, text_norm, reply_to FROM messages "
            "WHERE ts >= ? AND ts <= ? AND text_norm <> '' "
            "ORDER BY ts, channel IN ('alarm_kyiv')",
            (int(now) - WARM_WINDOW_S, int(now))):
        handle(solo, row["channel"], row["message_id"], row["ts"],
               row["text_norm"], row["reply_to"] is not None, now, warm=True)
        seen += 1
    # And then the declaring channel, unconditionally, exactly as the watcher's
    # own start-up does it. His point when this began: "це ж і для нового
    # користувача є така бага. У нього немає історії, як у того, що тільки
    # оновлює застосунок."
    #
    # He suggested a bigger replay window for this case. One row of declaration
    # does the same job strictly better: a window has to be guessed and 20% of
    # raids outlive ninety minutes, so any window is a bet -- while the official
    # channel's last unanswered word is the answer regardless of when the raid
    # began, and costs one query per registration instead of hours of replay.
    #
    # **Unconditionally**, and the condition it used to carry -- only when the
    # replay had left no episode at all -- is the fault he found on 2026-09-05:
    # a fresh user registered during an alert declared hours earlier, and the
    # phone still said "БЕЗ ТРИВОГ". On any real night something is flying, so
    # an ordinary live message opens an episode, and "there is an episode" was
    # being read as "we know about the sky". The one it found had been opened by
    # a drone over another oblast and carried no siren.
    #
    # `confirm_with_official` corrects rather than replaces -- that is its own
    # rule -- so calling it when there is already an episode is safe by
    # construction, and calling it when the last official word is an all-clear
    # changes nothing. The two warm paths agreeing is the point: every fault in
    # this function so far has been one of them doing something the other did
    # not.
    confirm_with_official([who], conn, now)
    return seen, solo.log


def sweep_orphans(names, state_dir: Path | None,
                  carry_dir: Path | None) -> list[str]:
    """Files left by people who were deleted while nothing was watching.

    `refresh_recipients` catches a departure it witnesses. This catches the ones
    it could not: `tools.people --forget` between restarts, which is how his
    directory came to hold five names that had been gone for days.

    Guarded on knowing more than the fallback. If the index were ever unreadable
    `from_dir` answers with the Telegram channel alone, and a sweep on that would
    throw away the carried episode of everybody real -- the one file here that
    cannot simply be rewritten on the next poll.
    """
    known = {Path(name).name for name in names}
    if len(known) <= 1:
        return []
    gone: set[str] = set()
    for directory in (state_dir, carry_dir):
        if directory is None or not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            if path.stem in known:
                continue
            gone.add(path.stem)
            try:
                path.unlink()
            except OSError:
                pass
    return sorted(gone)


def _sweep(name: str, state_dir: Path | None, carry_dir: Path | None) -> None:
    """Take the two files the watcher owns away with the person.

    His question, looking at a directory full of names he had deleted days
    earlier: "І чому повернуло стейт для видалених користувачів?" Because the
    broom swept half of it -- `tools.people --forget` owns the index and the
    settings, and these two are the watcher's.

    It is not a leak, because `/state` is served against a token and theirs is
    gone with the rest. It matters when a name comes back, which for test users
    is constantly: the new person's very first request would be answered with
    the previous one's screen, lines and all, decided from a home that is not
    theirs. `Held.clear` exists on the phone for exactly that, and this is its
    other half.

    Failing to delete is not worth stopping a watch over -- a stale file is what
    we already have -- so an unlink that cannot happen is skipped in silence.
    """
    for directory in (state_dir, carry_dir):
        if directory is None:
            continue
        try:
            (directory / f"{Path(name).name}.json").unlink(missing_ok=True)
        except OSError:
            pass


def refresh_recipients(session: Session, conn, directory: Path,
                       fallback, now: float,
                       state_dir: Path | None = None,
                       carry_dir: Path | None = None) -> list[str]:
    """Take on whoever appeared, drop whoever left, reload changed settings.

    His answer to needing a restart, and it is the better one: "чому б
    спостерігачу не перевіряти, чи не зʼявився новий користувач, і просто не
    включати його в обробку на наступній ітерації? Безшовно і не треба нічого
    перезапускати."

    Settings are the change that matters most often, and the one I would have
    missed: somebody moving across the city rewrites their own `home`, and a
    watcher holding the old one keeps ringing for the old ring until a deploy --
    "можливо навіть автоматично, при переміщенні містом".

    An existing person keeps their tracker and announcer through a settings
    change. The episode is about the sky rather than about them, and throwing it
    away because they moved would forget the alert that is running.
    """
    fresh = {who.name: who for who in from_dir(directory, fallback=fallback)}
    have = {who.name: who for who in session.recipients}
    notes = []

    for name, who in have.items():
        if name not in fresh:
            notes.append(f"-{name}")
            _sweep(name, state_dir, carry_dir)
        elif fresh[name].config != who.config:
            who.config = fresh[name].config
            who.tracker.config = who.config
            who.announcer.config = who.config
            notes.append(f"~{name}")

    for name, who in fresh.items():
        if name not in have:
            who.tracker.official_source = session.tracker.official_source
            seen, warmed = warm_one(who, conn, now)
            session.log.extend(warmed)
            notes.append(f"+{name} ({seen} прогріто)")

    # Order stays the index's, so a night's log reads the same way twice.
    session.recipients = [have.get(name) or fresh[name] for name in fresh]
    # `session.tracker` decides the polling interval and the heartbeat word. If
    # the person it belongs to has gone, it stops being fed and the watch would
    # quietly drop to the quiet interval while a raid was on.
    if session.recipients and session.tracker not in (
            who.tracker for who in session.recipients):
        session.tracker = session.recipients[0].tracker
        session.announcer = session.recipients[0].announcer
    return notes


def write_state(session: Session, directory: Path, now: float) -> None:
    """One file per person, so the app has a screen to open rather than a feed.

    Rewritten every poll rather than on change: it is a few hundred bytes and
    the alternative is remembering what changed, which is the kind of bookkeeping
    that goes wrong quietly. `/state` reads whichever file the token names.
    """
    from ..policy import carry
    from ..policy.status import SAID_ON_SCREEN, write

    for who in session.recipients:
        # The episode, saved on the same cadence as the screen it feeds. Cheap
        # -- one small file per person per cycle -- and it is the difference
        # between a restart that keeps knowing there is a raid and one that
        # asks the last ninety minutes of the database to guess.
        carry.save(CARRY_DIR, who, who.tracker, int(now))
        # `alarm` travels with the line, because the app cannot colour it
        # without knowing what kind of thing it was. Without it an all-clear --
        # which is `level="alert"` with `alarm="clear"`, since announcing it is
        # an audible event -- was drawn with the same red mark as a raid.
        said = [{"at": row["at"], "level": row["level"],
                 "alarm": row.get("alarm"), "text": row["said"]}
                for row in session.log
                if row.get("said") and row.get("who") == who.name]
        write(directory, who, said=said[-SAID_ON_SCREEN:], now=int(now))


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
    ap.add_argument("--official-interval", type=float, default=OFFICIAL_INTERVAL_S,
                    help="Seconds between polls of the official siren channel, "
                         "which is never slowed down.")
    ap.add_argument("--watch-interval", type=float, default=WATCH_INTERVAL_S,
                    help="Seconds between polls with an episode open but no "
                         "official siren yet.")
    ap.add_argument("--rps", type=float, default=2.0,
                    help="Requests per second ceiling, shared across channels.")
    ap.add_argument("--channels", action="append", dest="channels",
                    help="Watch only this channel (repeatable).")
    ap.add_argument("--config", default=str(CONFIG_PATH),
                    help="Settings file. Missing means the defaults.")
    ap.add_argument("--no-telegram", action="store_true",
                    help="Decide and print, but send nothing. For trying a "
                         "change locally without posting into the real channel "
                         "-- which a smoke test did twice, and both times the "
                         "message looked to him like the server misbehaving.")
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
    # The official channel goes last, on purpose. The page timestamps have
    # seconds and no finer, and three messages sharing a second is ordinary --
    # so at equal times the order is decided by the order channels were asked,
    # and `sorted` is stable. Asking the siren last means a chat message from
    # the same second is folded in first, and the siren then arrives already
    # knowing what it is about. His idea.
    channels = args.channels or list(CHANNELS)
    channels.sort(key=lambda c: c in OFFICIAL_CHANNELS)
    watchers = [Watcher(channel=c, last_id=store.resume_id(conn, c)) for c in channels]

    for w in watchers:
        if w.last_id == 0:
            try:
                w.last_id = client.newest_id(w.channel)
            except FetchError as exc:
                print(f"  ! {w.channel}: {exc}")

    started = time.time()
    # His settings, or the defaults if there are none. A missing file is the
    # normal case; a broken one prints a line and changes nothing, because a
    # typo must never be the reason the watch is not running at 3 a.m.
    cfg = load_config(Path(args.config))
    # Everyone with settings of their own, or just him when there are none. The
    # directory is written by the API, and the loop re-reads it between polls, so
    # somebody who registers or moves their home is taken on within one interval
    # -- see `refresh_recipients`. Nothing has to be restarted for a person to
    # appear.
    people = from_dir(fallback=cfg)
    session = Session(notifier=None if args.no_telegram else Notifier(),
                      recipients=people,
                      tracker=people[0].tracker,
                      announcer=people[0].announcer)
    # The official channel speaks only when the siren changes, so "has it spoken
    # lately" is not the same question as "is it being watched".
    # Every recipient's tracker, not only the first. It answers "is the
    # authoritative source in this stream", which is a fact about the run rather
    # than about a person -- and set on `session.tracker` alone, everybody after
    # the first would treat a chat channel's "ТРИВОГА" as the siren itself.
    # Dormant while there was one recipient, and registration is what wakes it.
    watching_official = bool(OFFICIAL_CHANNELS & set(channels))
    for who in people:
        who.tracker.official_source = watching_official
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"{stamp}.jsonl"

    print(f"Слухаю {len(watchers)} канал(и). Ctrl+C щоб зупинити.")
    print(f"  інтервал: офіційний {args.official_interval:.0f}s завжди · "
          f"решта {args.quiet_interval:.0f}s тихо / "
          f"{args.watch_interval:.0f}s стежу / "
          f"{args.alert_interval:.0f}s тривога")
    print(f"  лог: {log_path}")
    diff = changed_from_default(cfg)
    print(f"  налаштування: {diff if diff else 'усе за замовчуванням'}")
    # Each one's place, always -- not only when there are several. A recipient
    # file that emptied somebody's ring should be visible on the startup line
    # rather than deduced from a night of silence.
    for who in people:
        print(f"  отримувач {who.name}: {who.config.home or '(газетир)'} · "
              f"радіус {who.config.radius_km or 0:g} км · "
              f"{len(who.config.ring_names())} назв у колі")
    if session.notifier and session.notifier.enabled:
        who = session.notifier.chat_id or session.notifier.find_chat()
        print(f"  телефон: telegram → {who or 'напиши боту, щоб він знав куди слати'}")
    else:
        print(f"  телефон: вимкнено (нема {TOKEN_HINT})")

    # Whoever was deleted while nothing was watching leaves two files behind,
    # and the departure that would have swept them was never witnessed.
    orphans = sweep_orphans([who.name for who in session.recipients],
                            STATE_DIR, CARRY_DIR)
    if orphans:
        print(f"  прибрано екрани, яких нікому читати: {', '.join(orphans)}")

    # Warm the tracker from what is already stored, before polling at all. A
    # restart mid-alert has nothing to catch up on and would otherwise start with
    # no episode — announcing a wave already announced, at the quiet interval.
    warm_from = int(time.time()) - WARM_WINDOW_S
    fresh_from = time.time() - FRESH_ON_RESTART_S
    said = already_said(LOG_DIR, log_path)

    # Before any of that: if the last thing the previous run decided was that a
    # raid was on, it still is. One row, read rather than derived.
    declared = seed_from_log(session, LOG_DIR, log_path, time.time())
    if declared:
        print(f"  за логом тривога триває з {kyiv_dt(declared):%H:%M} — "
              "нічого не озвучую, вона вже йде")
    warmed = spoken = 0
    for row in conn.execute(
            "SELECT channel, message_id, ts, text_norm, reply_to FROM messages "
            "WHERE ts >= ? AND text_norm <> '' "
            "ORDER BY ts, channel IN ('alarm_kyiv')", (warm_from,)):
        anchor = f"{row['channel']}/{row['message_id']}"
        quiet = row["ts"] < fresh_from or anchor in said
        handle(session, row["channel"], row["message_id"], row["ts"],
               row["text_norm"], row["reply_to"] is not None, time.time(),
               warm=quiet)
        warmed += 1
        spoken += not quiet
    if warmed:
        state = state_word(session.tracker)
        note = f", з них {spoken} свіжих — озвучено" if spoken else ""
        print(f"  прогрів: {warmed} повідомлень за останні "
              f"{WARM_WINDOW_S // 60} хв{note} — стан: {state}")

    # Then put back what the previous run knew, over the top of whatever the
    # replay concluded.
    #
    # Order matters and this is the useful order. The replay's job is the
    # announcer's memory, so it has to run; the episode's job is to be true, and
    # the previous process knew it exactly -- it had seen every message, not
    # just the last ninety minutes. So the replay teaches what was already said
    # and then the saved episode overwrites what was guessed about the raid.
    #
    # Anything that happened while the process was down is still ahead of us:
    # the catch-up poll below feeds it in, against a restored episode rather
    # than an empty one.
    restored = []
    for who in people:
        if carry.load(CARRY_DIR, who, who.tracker, int(time.time())):
            restored.append(who.name)
    if restored:
        ep = people[0].tracker.episode
        since = f"{kyiv_dt(ep.opened_at):%H:%M}" if ep is not None else "?"
        print(f"  відновлено епізод з {since} — "
              f"{len(restored)} отримувач(і): {', '.join(restored)}")

    # And last of all, the declaring channel -- after the replay and after the
    # saved episode, because it is the only source here that cannot be out of
    # date about whether a siren is running.
    confirmed = confirm_with_official(session.recipients, conn, time.time())
    if confirmed:
        state = state_word(session.tracker)
        print(f"  офіційна тривога з {kyiv_dt(confirmed):%H:%M} — "
              f"стан: {state}")

    # Catch up on whatever arrived while the machine was off, silently. The
    # tracker needs it — an alert may already be running — but printing six
    # hours of backlog buries the live feed, and counting its lag would make the
    # one measurement here meaningless.
    caught = 0
    for _ in range(200):
        got = poll_once(client, conn, watchers, session, warm=True,
                         fresh_from=fresh_from, said=said)
        caught += got
        if got == 0:
            break
    if caught:
        state = state_word(session.tracker)
        print(f"  наздогнав {caught} нових — стан: {state}")

    # Only now, with everything warmed and caught up, say which version is
    # watching — silently, because a deploy is never worth waking up for. Sent
    # from here rather than from `update.sh` on purpose: that git pulled says
    # nothing about whether the process came up and reached the live feed, and
    # that is the thing the message is supposed to prove.
    state = state_word(session.tracker)
    note = startup_note(f"{state} · {len(watchers)} канал(и)",
                        settings=diff)
    if note:
        print(chr(10).join("  " + line for line in note.splitlines()), flush=True)
        if session.notifier and session.notifier.enabled:
            session.notifier.send(note, audible=False)

    print("  --- далі живий ефір ---", flush=True)
    print()

    last_beat = time.time()
    last_poll = time.time()
    # Already taken on at start-up, so the first pass through the loop has
    # nothing to do unless somebody registered in the meantime.
    last_recipients = recipients_signature(RECIPIENTS_DIR)
    while not _STOP:
        # Was the machine asleep? Then this batch is catch-up, not live.
        overslept = time.time() - last_poll
        slept = overslept > interval_hint(args, session) + SLEEP_GAP_S
        if slept:
            print(f"  · машина спала ~{overslept / 60:.0f} хв — "
                  f"наздоганяю тихо", flush=True)
        signature = recipients_signature(RECIPIENTS_DIR)
        if signature != last_recipients:
            last_recipients = signature
            for note in refresh_recipients(session, conn, RECIPIENTS_DIR, cfg,
                                           time.time(),
                                           state_dir=STATE_DIR,
                                           carry_dir=CARRY_DIR):
                print(f"  · отримувачі: {note}", flush=True)

        poll_once(client, conn, watchers, session, warm=slept, args=args)
        last_poll = time.time()
        write_log(session, log_path)
        write_state(session, STATE_DIR, last_poll)

        if time.time() - last_beat > HEARTBEAT_S:
            last_beat = time.time()
            state = state_word(session.tracker)
            print(f"  · {kyiv_dt(int(time.time())):%H:%M} {state}, "
                  f"{session.decisions} повідомлень, {session.audible} побудок",
                  flush=True)

        # Until whichever channel comes due first, not a single global tick.
        deadline = min(max(w.due_at, w.backoff_until) for w in watchers)
        while not _STOP and time.time() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.time())))

    write_log(session, log_path)
    write_state(session, STATE_DIR, time.time())
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
