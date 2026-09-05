"""A restart must not forget that there is a raid on."""

from __future__ import annotations

import json

from tools.policy import carry
from tools.policy.episodes import Episode, Sent, Tracker


class Person:
    """The bit of a recipient this module touches."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.tracker = Tracker()


def a_raid(now: int) -> Episode:
    """An episode with something in every awkward kind of field."""
    return Episode(
        opened_at=now - 3 * 3600,
        threat="ballistic",
        threat_at=now - 600,
        alert_announced=True,
        official_alert=True,
        threat_peak=3,
        launched={"ballistic", "cruise"},
        kinds_seen={"кинжал"},
        rechecked={"drone"},
        recon_at={"drone": now - 300},
        ring_seen={"Жуляни": now - 120},
        cleared={"cruise"},
        last_silent={("too-far: oblast", "drone", ("Вишневе",), "oblast"): now - 60},
        sent=[Sent(ts=now - 3 * 3600, level="alert", alarm="alert", official=True)],
        last_live=now - 60,
    )


def test_a_restart_in_the_middle_of_a_raid_still_knows_it_is_a_raid(tmp_path):
    """The whole point, stated as the thing that went wrong.

    An Android-only commit restarted the watcher during a live alert; the
    episode was older than the replay window, so the phone was told the sky was
    clear. "після оновлення не витягло активний статус тривоги".
    """
    now = 1_760_000_000
    before = Person("Володимир")
    before.tracker.episode = a_raid(now)
    before.tracker.official_seen = now - 3 * 3600
    carry.save(tmp_path, before, before.tracker, now)

    after = Person("Володимир")
    assert after.tracker.episode is None
    assert carry.load(tmp_path, after, after.tracker, now) is True

    got = after.tracker.episode
    assert got is not None
    assert got.official_alert is True
    assert got.opened_at == now - 3 * 3600
    assert after.tracker.official_seen == now - 3 * 3600


def test_every_field_survives_the_round_trip(tmp_path):
    """Sets, dicts, tuple keys and a list of dataclasses all go through JSON,
    and each of them has a way of arriving as the wrong type instead of as an
    error. Compared field by field rather than by spot-checking, because the
    encoder is driven by `dataclasses.fields` and the next field added must be
    covered by this test without anybody remembering to add it."""
    now = 1_760_000_000
    original = a_raid(now)
    back = carry.decode(json.loads(json.dumps(carry.encode(original))))
    assert back == original


def test_a_field_the_file_has_never_heard_of_keeps_its_default(tmp_path):
    """This file is written by the version that stops and read by the version
    that starts, and those differ exactly when something changed. A missing key
    is the ordinary case after adding a field."""
    now = 1_760_000_000
    data = carry.encode(a_raid(now))
    del data["threat_peak"]
    data["a_field_from_the_future"] = 7

    back = carry.decode(data)
    assert back is not None
    assert back.threat_peak == 0
    assert back.threat == "ballistic"


def test_a_file_left_behind_yesterday_is_not_believed(tmp_path):
    """A watcher that has been off for half a day has missed the all-clear along
    with everything else, and an episode restored from before it would hold the
    screen red until the next official message."""
    now = 1_760_000_000
    stale = Person("Володимир")
    stale.tracker.episode = a_raid(now - carry.STALE_S - 3600)
    carry.save(tmp_path, stale, stale.tracker, now - carry.STALE_S - 3600)

    after = Person("Володимир")
    assert carry.load(tmp_path, after, after.tracker, now) is False
    assert after.tracker.episode is None


def test_a_ten_hour_raid_is_still_restored(tmp_path):
    """Age is taken from the last sign of life, not from the opening. 20% of
    official episodes in the corpus run past ninety minutes and the 95th
    percentile is 275, so an episode that opened long ago is normal rather than
    suspicious -- it is a *silent* one that is stale."""
    now = 1_760_000_000
    long_one = a_raid(now)
    long_one.opened_at = now - 10 * 3600
    who = Person("Володимир")
    who.tracker.episode = long_one
    carry.save(tmp_path, who, who.tracker, now)

    after = Person("Володимир")
    assert carry.load(tmp_path, after, after.tracker, now) is True
    assert after.tracker.episode.opened_at == now - 10 * 3600


def test_quiet_sky_saves_and_restores_as_quiet(tmp_path):
    now = 1_760_000_000
    who = Person("Володимир")
    carry.save(tmp_path, who, who.tracker, now)

    after = Person("Володимир")
    assert carry.load(tmp_path, after, after.tracker, now) is False
    assert after.tracker.episode is None


def test_a_corrupt_file_does_not_stop_the_watcher_starting(tmp_path):
    """One lost episode against a service that will not come up. Which of those
    is worse does not need arguing at three in the morning."""
    who = Person("Володимир")
    carry.path_for(tmp_path, who).write_text("{not json", encoding="utf-8")
    assert carry.load(tmp_path, who, who.tracker, 1_760_000_000) is False


def test_a_name_cannot_reach_outside_the_directory(tmp_path):
    """Names come from whoever installed the app. The state files already take
    only the basename; this file is written from the same untrusted string and
    has to do the same."""
    who = Person("../../etc/passwd")
    assert carry.path_for(tmp_path, who).parent == tmp_path


def test_writing_the_screen_also_writes_the_memory(tmp_path, monkeypatch):
    """The wiring, not the module.

    `carry` can be perfect and still useless if nothing calls it, and the
    saving has to happen on every cycle rather than at shutdown -- a process
    that is killed, which is exactly what an update does, gets no shutdown.
    """
    from tools.live.run import Session, handle, write_state
    from tools.policy.config import DEFAULTS, replace
    from tools.policy.recipients import TELEGRAM_NAME, Recipient

    mine = Recipient(name=TELEGRAM_NAME, config=replace(DEFAULTS, home="Жуляни"))
    mine.tracker.official_source = True
    session = Session(recipients=[mine], tracker=mine.tracker,
                      announcer=mine.announcer)

    now = 1_780_000_000
    handle(session, "alarm_kyiv", 1, now, "🚨 м. Київ Повітряна тривога",
           False, now)
    assert mine.tracker.episode is not None

    import tools.live.run as run
    where = tmp_path / "carry"
    monkeypatch.setattr(run, "CARRY_DIR", where)
    write_state(session, tmp_path / "state", now)

    # A fresh process, with nothing but the files on disk.
    after = Recipient(name=TELEGRAM_NAME, config=replace(DEFAULTS, home="Жуляни"))
    assert carry.load(where, after, after.tracker, now) is True
    assert after.tracker.episode is not None
    assert after.tracker.episode.official_alert is True

def _log(directory, rows):
    """A previous run's decision log, and the path of the current one."""
    import json
    from datetime import datetime, timezone

    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "old.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            row = dict(row)
            row["at"] = datetime.fromtimestamp(
                row.pop("ts"), tz=timezone.utc).isoformat()
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return directory / "new.jsonl"


def _one_person_session():
    from tools.live.run import Session
    from tools.policy.config import DEFAULTS, replace
    from tools.policy.recipients import TELEGRAM_NAME, Recipient

    who = Recipient(name=TELEGRAM_NAME, config=replace(DEFAULTS, home="Жуляни"))
    who.tracker.official_source = True
    return Session(recipients=[who], tracker=who.tracker,
                   announcer=who.announcer), who


def test_the_last_decision_says_a_raid_is_on_so_it_is(tmp_path):
    """His answer, after two more elaborate ones of mine had failed: "є останнє
    повідомлення, там live-threat shahed-jet. Що тобі ще потрібно?"

    Nothing. The log is append-only, every row carries the state, and a restart
    that reads it knows what the previous run knew.
    """
    from tools.live.run import seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 3 * 3600, "who": "telegram_channel", "level": "alert",
         "alarm": "alert", "sky": "alert", "since": now - 3 * 3600},
        {"ts": now - 300, "who": "telegram_channel", "level": "alert",
         "alarm": "shahed-jet", "sky": "alert", "since": now - 3 * 3600},
    ])
    session, who = _one_person_session()

    assert seed_from_log(session, tmp_path, skip, now) == now - 3 * 3600
    assert who.tracker.episode is not None
    assert who.tracker.episode.official_alert is True
    assert who.tracker.episode.opened_at == now - 3 * 3600


def test_reading_it_back_wakes_nobody(tmp_path):
    """A siren from three hours ago is not news, and waking somebody to tell
    them about it would be its own bug. The seed decides nothing and says
    nothing -- it only remembers."""
    from tools.live.run import seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": "telegram_channel", "level": "alert",
         "alarm": "shahed-jet", "sky": "alert", "since": now - 3 * 3600},
    ])
    session, _ = _one_person_session()

    seed_from_log(session, tmp_path, skip, now)
    assert session.log == []


def test_a_clear_sky_stays_clear(tmp_path):
    from tools.live.run import seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": "telegram_channel", "level": "quiet",
         "alarm": None, "sky": "quiet", "since": None},
    ])
    session, who = _one_person_session()

    assert seed_from_log(session, tmp_path, skip, now) is None
    assert who.tracker.episode is None


def test_watching_is_not_a_raid(tmp_path):
    """The 2.1% the measurement found: missiles over the city before the siren.
    `level` says "alert" there because it is worth waking somebody; the sky is
    `watching`, and the screen must not upgrade it to a declared raid."""
    from tools.live.run import seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": "telegram_channel", "level": "alert",
         "alarm": "cruise", "sky": "watching", "since": now - 600},
    ])
    session, who = _one_person_session()

    assert seed_from_log(session, tmp_path, skip, now) is None
    assert who.tracker.episode is None


def test_a_log_from_before_the_field_existed_still_rescues_the_raid(tmp_path):
    """The fallback, and the reason it is worth having: the log that has to
    rescue the raid that prompted all of this was written by the version that
    did not know to record the sky."""
    from tools.live.run import seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": "telegram_channel", "level": "alert",
         "alarm": "shahed-jet"},
    ])
    session, who = _one_person_session()

    assert seed_from_log(session, tmp_path, skip, now) == now - 300
    assert who.tracker.episode is not None


def test_an_old_log_ending_in_an_all_clear_opens_nothing(tmp_path):
    """An all-clear is `level="alert"` with `alarm="clear"`, because saying it
    out loud is an audible event. Reading the level without the alarm would
    reopen a raid on the message that ended it."""
    from tools.live.run import seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": "telegram_channel", "level": "alert",
         "alarm": "clear"},
    ])
    session, who = _one_person_session()

    assert seed_from_log(session, tmp_path, skip, now) is None
    assert who.tracker.episode is None


def test_a_log_from_yesterday_is_not_believed(tmp_path):
    from tools.live.run import SEED_BACK_S, seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - SEED_BACK_S - 600, "who": "telegram_channel",
         "level": "alert", "alarm": "alert", "sky": "alert",
         "since": now - SEED_BACK_S - 600},
    ])
    session, who = _one_person_session()

    assert seed_from_log(session, tmp_path, skip, now) is None
    assert who.tracker.episode is None


def test_no_previous_log_is_not_an_error(tmp_path):
    from tools.live.run import seed_from_log

    session, who = _one_person_session()
    assert seed_from_log(session, tmp_path, tmp_path / "new.jsonl",
                         1_780_000_000) is None
    assert who.tracker.episode is None


def test_each_person_gets_their_own_answer(tmp_path):
    """A raid over one recipient's ring is not one over another's, and the log
    already records the decision per person -- which is why it is read per
    person rather than by taking the last row."""
    from tools.live.run import Session, seed_from_log
    from tools.policy.config import DEFAULTS, replace
    from tools.policy.recipients import TELEGRAM_NAME, Recipient

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": TELEGRAM_NAME, "level": "alert",
         "alarm": "shahed-jet", "sky": "alert", "since": now - 3 * 3600},
        {"ts": now - 300, "who": "оля", "level": "quiet", "alarm": None,
         "sky": "quiet", "since": None},
    ])
    mine = Recipient(name=TELEGRAM_NAME, config=replace(DEFAULTS, home="Жуляни"))
    theirs = Recipient(name="оля", config=replace(DEFAULTS, home="Виноградар"))
    session = Session(recipients=[mine, theirs], tracker=mine.tracker,
                      announcer=mine.announcer)

    seed_from_log(session, tmp_path, skip, now)
    assert mine.tracker.episode is not None
    assert theirs.tracker.episode is None


def _official(rows):
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE messages (channel TEXT, message_id INTEGER, "
                 "ts INTEGER, text_norm TEXT, reply_to INTEGER)")
    conn.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, NULL)", rows)
    return conn


def test_a_restored_raid_survives_the_next_message(tmp_path):
    """The bug in the first version of this, which the other tests could not
    see because none of them handled a message afterwards.

    `Tracker.before` closes an episode that has been silent for 45 minutes. The
    episode was being stamped as last alive when the *raid* began, so on a raid
    three hours old the very next message closed it again -- restoring the state
    and then throwing it away in the same second.
    """
    from tools.live.run import handle, seed_from_log

    now = 1_780_000_000
    skip = _log(tmp_path, [
        {"ts": now - 300, "who": "telegram_channel", "level": "alert",
         "alarm": "shahed-jet", "sky": "alert", "since": now - 3 * 3600},
    ])
    session, who = _one_person_session()
    seed_from_log(session, tmp_path, skip, now)
    assert who.tracker.episode is not None

    handle(session, "monitoring_kyiv", 9, now, "Шахед на Вишневе", False, now)

    assert who.tracker.episode is not None, "closed as idle right after restoring"
    assert who.tracker.episode.opened_at == now - 3 * 3600


def test_an_unanswered_declaration_is_the_last_resort():
    """When the log's newest rows say the sky is clear because the watcher spent
    hours believing it, the truth is only in the declaring channel."""
    from tools.live.run import confirm_with_official

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 1, now - 5 * 3600, "🟢 м. Київ Відбій повітряної тривоги"),
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
    ])
    session, who = _one_person_session()

    assert confirm_with_official(session.recipients, conn, now) == now - 3 * 3600
    assert who.tracker.episode is not None
    assert who.tracker.episode.official_alert is True
    # Alive now, because the declaration is unanswered now.
    assert who.tracker.episode.last_live == now


def test_an_answered_declaration_opens_nothing():
    from tools.live.run import confirm_with_official

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
        ("alarm_kyiv", 3, now - 2 * 3600, "🟢 м. Київ Відбій повітряної тривоги"),
    ])
    session, who = _one_person_session()

    assert confirm_with_official(session.recipients, conn, now) is None
    assert who.tracker.episode is None


def test_a_partial_all_clear_is_not_an_answer():
    """It lifts one class and leaves the raid running."""
    from tools.live.run import confirm_with_official

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
        ("alarm_kyiv", 3, now - 2 * 3600,
         "🟡 м. Київ Відбій загрози застосування балістичного озброєння"),
    ])
    session, who = _one_person_session()

    assert confirm_with_official(session.recipients, conn, now) == now - 3 * 3600
    assert who.tracker.episode is not None


def test_somebody_who_registers_during_a_raid_is_told_there_is_one():
    """His case, and the same bug in a different hat: "це ж і для нового
    користувача є така бага. У нього немає історії".

    A new recipient gets ninety minutes of replay, which on a raid three hours
    old teaches them nothing -- and the first thing their phone would show is
    "БЕЗ ТРИВОГ" during an air raid.
    """
    from tools.live.run import warm_one
    from tools.policy.config import DEFAULTS, replace
    from tools.policy.recipients import Recipient

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
    ])
    newcomer = Recipient(name="оля", config=replace(DEFAULTS, home="Виноградар"))
    newcomer.tracker.official_source = True

    warm_one(newcomer, conn, now)

    assert newcomer.tracker.episode is not None
    assert newcomer.tracker.episode.official_alert is True


def test_how_long_the_raid_ran_survives_a_deploy(tmp_path):
    """His report, and the timestamps say it was my own deploy that erased it.

        09:53:03  the all-clear
        09:53:37  an episode reopens, as they do
        10:01     three commits pushed, and the watcher restarts on the timer
        10:32     "Відбій тривоги 09:53" on the screen with no duration beside it

    The closing line outlives the raid by an hour on purpose -- it is the one
    number people read in the official app. It was computed from
    `tracker.closed`, which is not carried across a restart at all, so the line
    survived the deploy and the number did not. Deploys are frequent; this file
    says so itself, two functions up.

    What the number actually needs is two integers -- when the alert began and
    when it was called off -- and neither of them belongs in a list of finished
    episodes."""
    from tools.policy import carry, status
    from tools.policy.config import DEFAULTS, replace
    from tools.policy.episodes import Tracker, observe
    from tools.policy.recipients import Recipient
    from tools.policy.rules import decide

    now = 1_780_000_000
    siren = ("alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога")
    clear = ("alarm_kyiv", "🟢 м. Київ" + chr(10) + "Відбій повітряної тривоги")

    before = Recipient(name="він", config=replace(DEFAULTS, home="Жуляни"))
    before.tracker.official_source = True
    for offset, (channel, text) in ((0, siren), (4800, clear)):
        o = observe(now + offset, text, False, channel)
        d = decide(o, before.tracker)
        before.tracker.record(o, d.level if d.notify else None,
                              d.alarm if d.notify else None, d.reason)

    # It worked before the restart, which is what made it hard to see.
    ran = status.snapshot(before, now=now + 5400)["ended"]
    assert ran is not None and ran["lasted_s"] == 4800, ran

    # ...and then a deploy.
    carry.save(tmp_path, before, before.tracker, now + 5400)
    after = Recipient(name="він", config=replace(DEFAULTS, home="Жуляни"))
    after.tracker.official_source = True
    carry.load(tmp_path, after, after.tracker, now + 5400)

    ran = status.snapshot(after, now=now + 5400)["ended"]
    assert ran is not None, "the deploy ate the length of the raid"
    assert ran["lasted_s"] == 4800, ran
    assert ran["at"] == now + 4800, ran


def test_a_busy_night_does_not_hide_the_raid_from_a_newcomer():
    """The same case again, and the test above could not see it.

    His report, 2026-09-05: registered a fresh test user on the emulator during
    an alert declared long before, and the phone still said "БЕЗ ТРИВОГ".

    The replay window is ninety minutes and the declaration was older, which the
    test above covers -- but only because nothing else happened in those ninety
    minutes. On a real night something is always flying, an ordinary live
    message opens an episode, and the guard read "there is an episode" as "we
    know about the sky". The episode it found was opened by a drone over
    somebody else's oblast and carried no siren at all.

    The watcher's own start-up asks the declaring channel unconditionally. This
    path asked only when it had nothing, and that asymmetry between the two warm
    paths is the same shape as the last two faults in this file."""
    from tools.live.run import warm_one
    from tools.policy.config import DEFAULTS, replace
    from tools.policy.recipients import Recipient

    now = 1_780_000_000
    conn = _official([
        # Declared three hours ago: outside any replay window.
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
        # ...and the night went on, as nights do. Inside the window, live,
        # somebody else's region, and enough to open an episode.
        ("mon1tor_ua", 7, now - 900,
         "⚠️2 шахеди з Сумщини на Полтавщину, Лубенський район."),
    ])
    newcomer = Recipient(name="тест", config=replace(DEFAULTS, home="Жуляни"))
    newcomer.tracker.official_source = True

    warm_one(newcomer, conn, now)

    episode = newcomer.tracker.episode
    assert episode is not None
    assert episode.official_alert is True, "the siren is the declaring channel's"
    assert episode.alert_announced is True
    # And seated when it began rather than when we noticed.
    assert episode.opened_at == now - 3 * 3600


def test_the_declaration_corrects_a_worse_episode_instead_of_losing_to_it():
    """The ordering fault the startup log exposed.

    The declaration seated the raid at 10:58, and then the saved episode --
    written by the process that had already gone blind, so carrying no official
    siren -- replaced it with one opened at 11:41. `status.snapshot` calls that
    `watching`, and the app draws `watching` as "БЕЗ ТРИВОГ": the right answer
    arrived and was overwritten by a worse one.

    Detail is not authority. A saved episode knows more about the threat class
    than a declaration ever will, and none of that makes it right about whether
    a siren is running.
    """
    from tools.live.run import confirm_with_official
    from tools.policy.episodes import Episode

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
    ])
    session, who = _one_person_session()
    # What a blind run saves: an episode it opened later, off chat traffic.
    who.tracker.episode = Episode(
        opened_at=now - 2 * 3600, last_live=now - 60, threat="shahed-jet",
        official_alert=False)

    assert confirm_with_official(session.recipients, conn, now) == now - 3 * 3600

    episode = who.tracker.episode
    assert episode.official_alert is True, "the siren is the channel's to declare"
    assert episode.opened_at == now - 3 * 3600, "the raid began when it began"
    assert episode.threat == "shahed-jet", "detail kept, not thrown away"


def test_a_correct_episode_is_not_disturbed():
    from tools.live.run import confirm_with_official
    from tools.policy.episodes import Episode

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
    ])
    session, who = _one_person_session()
    who.tracker.episode = Episode(
        opened_at=now - 3 * 3600, last_live=now - 60, threat="ballistic",
        threat_peak=3, official_alert=True)

    confirm_with_official(session.recipients, conn, now)

    assert who.tracker.episode.threat_peak == 3
    assert who.tracker.episode.opened_at == now - 3 * 3600


def test_the_state_reported_after_confirming_is_the_alert():
    """End to end, because every piece of this has been right on its own while
    the answer the phone got was wrong."""
    from tools.live.run import confirm_with_official
    from tools.policy.episodes import Episode
    from tools.policy.status import snapshot

    now = 1_780_000_000
    conn = _official([
        ("alarm_kyiv", 2, now - 3 * 3600, "🚨 м. Київ Повітряна тривога"),
    ])
    session, who = _one_person_session()
    who.tracker.episode = Episode(
        opened_at=now - 2 * 3600, last_live=now - 60, official_alert=False)

    confirm_with_official(session.recipients, conn, now)

    assert snapshot(who, said=[], now=now)["state"] == "alert"
