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
