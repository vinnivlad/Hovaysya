"""Tests for the live watcher.

Two things matter here and neither is about the policy, which is tested
elsewhere: that the catch-up pass cannot pollute the one measurement this stage
exists to produce, and that a run is reconstructable from its log alone.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.live.run import Session, handle, write_log

T0 = 1_756_000_000


def _run(texts, warm=False, now=None):
    session = Session()
    now = now if now is not None else T0 + len(texts) * 10
    for i, text in enumerate(texts):
        handle(session, "mon1tor_ua", 100 + i, T0 + i * 10, text, False, now,
               warm=warm)
    return session


def test_the_catch_up_pass_does_not_count_towards_the_lag():
    """Resuming after the machine was off means a backlog of messages hours old.
    Counting those would drown the number the whole stage exists to measure."""
    warm = _run(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!", "🅿️ Київ / 1х Жуляни"],
                warm=True, now=T0 + 6 * 3600)
    assert warm.lags == []
    assert warm.decisions == 0
    assert warm.audible == 0


def test_the_catch_up_pass_still_warms_the_tracker():
    """It has to, or a run started mid-attack begins blind to the alert."""
    warm = _run(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!"], warm=True)
    assert warm.tracker.episode is not None
    assert warm.tracker.episode.alert_announced


def test_a_live_message_is_measured():
    session = _run(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!"], now=T0 + 8)
    assert session.decisions == 1
    assert session.audible == 1
    assert session.lags == [8.0]


def test_the_log_holds_the_decision_and_the_words():
    session = _run(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                    "‼️ Вихід балістики з Брянська"])
    rows = session.log
    assert [r["notify"] for r in rows] == [True, True]
    assert rows[0]["said"] == "Тривога."
    assert rows[1]["said"] == "Пуск: балістика."
    assert all(r["reason"] for r in rows)
    assert all(r["anchor"].startswith("mon1tor_ua/") for r in rows)


def test_the_log_is_one_json_object_per_line(tmp_path):
    session = _run(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!", "💥 Вибухи Київ."])
    path = tmp_path / "night.jsonl"
    write_log(session, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        row = json.loads(line)
        assert set(row) >= {"at", "anchor", "lag_s", "text", "notify", "reason"}


def test_the_warm_flag_is_recorded_so_a_log_can_be_filtered(tmp_path):
    """A night's log gets read back as evidence, and a caught-up message is not
    evidence about latency or about what he would have heard."""
    session = _run(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!"], warm=True)
    assert session.log[0]["warm"] is True


def test_a_gap_means_the_machine_slept_not_that_the_loop_was_slow():
    """On S3 the process survives suspend and resumes mid-loop, so the whole
    missed stretch arrives at once. Printed as live it looks like an attack
    happening now; counted as live it lands in the lag statistics as one
    forty-minute delay, destroying the only number this stage produces."""
    import argparse

    from tools.live.run import SLEEP_GAP_S, interval_hint

    args = argparse.Namespace(quiet_interval=45.0, alert_interval=6.0)
    session = Session()
    assert interval_hint(args, session) == 45.0
    handle(session, "mon1tor_ua", 1, T0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
           False, T0 + 1)
    assert interval_hint(args, session) == 6.0     # tighter with an episode open
    threshold = interval_hint(args, session) + SLEEP_GAP_S
    assert 40 * 60 > threshold          # forty minutes is a suspend
    assert 20 < threshold               # twenty seconds is just a slow poll


def test_a_restart_mid_alert_must_not_begin_blind():
    """The failure this guards against was seen live: restarting during a real
    alert found nothing to catch up on, so the tracker started with no episode —
    the next place name would re-announce a wave already announced, and the loop
    polled at the quiet interval right through an attack. The warm-up reads the
    store rather than relying on the poll."""
    from tools.live.run import WARM_WINDOW_S

    assert WARM_WINDOW_S >= 45 * 60      # an episode closes after 45 min idle

    session = Session()
    handle(session, "kievinform_ua1", 1, T0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
           False, T0 + 5, warm=True)
    assert session.tracker.episode is not None
    # ...and the first live ring message after that is a repeat, not an opening.
    handle(session, "kievinform_ua1", 2, T0 + 60, "Жуляни ✈️", False, T0 + 62)
    assert session.log[-1]["reason"] != "alert declared"


# --- the phone -------------------------------------------------------------


def test_no_token_means_no_notifier_and_no_crash(tmp_path):
    """The watch has to run identically whether or not a bot is configured."""
    from tools.live.notify import Notifier

    n = Notifier(tmp_path / "absent.token", tmp_path / "absent.id")
    assert not n.enabled
    assert n.send("Тривога.") is False
    assert n.failures == 0          # not configured is not a failure


def test_a_configured_notifier_needs_a_chat_before_it_sends(tmp_path):
    from tools.live.notify import Notifier

    token = tmp_path / "t"
    token.write_text("123:fake", encoding="utf-8")
    n = Notifier(token, tmp_path / "absent.id")
    assert n.enabled
    assert n.chat_id is None


def test_the_two_levels_map_onto_telegram(tmp_path):
    """`alert` beeps, `info` arrives silently — which is the whole of what the
    phone needs to distinguish."""
    from tools.live.notify import Notifier

    token = tmp_path / "t"
    token.write_text("123:fake", encoding="utf-8")
    chat = tmp_path / "c"
    chat.write_text("42", encoding="utf-8")
    n = Notifier(token, chat)
    calls = []
    n._call = lambda method, **kw: calls.append((method, kw)) or {"ok": True}
    n.send("Тривога.", audible=True)
    n.send("Загроза: балістика.", audible=False)
    assert calls[0][1]["disable_notification"] == "false"
    assert calls[1][1]["disable_notification"] == "true"
    assert n.sent == 2


def test_only_a_chat_that_said_the_code_is_added(tmp_path):
    """A bot's username is public. "Whoever wrote last" was the first version,
    and a stranger who found the bot and wrote before he did would have been
    cached as the recipient of his alerts."""
    from tools.live.notify import Notifier

    token = tmp_path / "t"
    token.write_text("123:fake", encoding="utf-8")
    n = Notifier(token, tmp_path / "c", code="hovaysya")
    n._call = lambda method, **kw: {"ok": True, "result": [
        {"message": {"chat": {"id": 999, "type": "private"}, "text": "привіт"}},
        {"message": {"chat": {"id": 42, "type": "private"}, "text": "Hovaysya"}},
    ]}
    assert n.find_chat() == "42"
    assert n.chats == ["42"]


def test_a_stranger_without_the_code_is_ignored(tmp_path):
    from tools.live.notify import Notifier

    token = tmp_path / "t"
    token.write_text("123:fake", encoding="utf-8")
    n = Notifier(token, tmp_path / "c", code="hovaysya")
    n._call = lambda method, **kw: {"ok": True, "result": [
        {"message": {"chat": {"id": 999, "type": "private"}, "text": "/start"}},
    ]}
    assert n.find_chat() is None
    assert n.chats == []


def test_it_sends_to_everyone_on_the_list(tmp_path):
    """A private channel for the few people he wants, or several direct chats —
    and one failing recipient must not stop the others."""
    from tools.live.notify import Notifier

    token = tmp_path / "t"
    token.write_text("123:fake", encoding="utf-8")
    chats = tmp_path / "c"
    chats.write_text("-1001234567890\n42\n", encoding="utf-8")
    n = Notifier(token, chats)
    seen = []

    def call(method, **kw):
        seen.append(kw["chat_id"])
        return {"ok": kw["chat_id"] != "42",
                "description": "chat not found"}

    n._call = call
    assert n.send("Тривога.") is True        # the channel worked
    assert seen == ["-1001234567890", "42"]  # ...and the other was still tried
    assert n.sent == 1 and n.failures == 1


def test_the_bell_marks_what_made_a_sound(tmp_path):
    """In a channel every post looks alike afterwards. "Дзвоник допоміг би" —
    he had taken a silent status line for a wake-up."""
    from tools.live.notify import format_message
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr, ann = Tracker(), Announcer()
    said = []
    for off, channel, text in ((0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
                               (300, "mon1tor_ua", "⚠️2 реактивні шахеди на Вишневе.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        said.append(format_message(ann.announce(o, d), o, d))

    assert said[0].startswith("🔔 ")
    assert not said[1].startswith("🔔 ")
    # ...and every label the policy assigned, in the schema's own words, so a
    # post can be compared against labels/*.jsonl directly.
    assert "shahed-jet" in said[1] and "my-area" in said[1]
    assert "a drone near me, but not my street" in said[1]


# --- keeping what is not in git -------------------------------------------


def test_the_database_is_copied_through_sqlite_not_as_a_file(tmp_path):
    """It runs in WAL mode, so a plain copy taken while pages still sit in the
    `-wal` file produces a database that looks fine and is corrupt."""
    import sqlite3

    from tools.backup import copy_database

    src = tmp_path / "a.db"
    con = sqlite3.connect(src)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE messages (id INTEGER)")
    con.executemany("INSERT INTO messages VALUES (?)", [(i,) for i in range(500)])
    con.commit()          # deliberately left open, with pages still in the WAL

    n = copy_database(src, tmp_path / "b.db")
    assert n == 500
    con.close()


def test_a_backup_carries_the_night_logs(tmp_path):
    """These are the part that cannot be recreated: one file per night, every
    decision and its reason."""
    from tools.backup import main

    src = tmp_path / "data"
    (src / "live").mkdir(parents=True)
    (src / "live" / "20260828T000000.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (src / "telegram-bot.token").write_text("123:fake", encoding="utf-8")
    dst = tmp_path / "keep"
    assert main(["--from", str(src), "--to", str(dst)]) == 0
    assert (dst / "live" / "20260828T000000.jsonl").exists()
    assert (dst / "telegram-bot.token").read_text(encoding="utf-8") == "123:fake"


# --- saying that a new version is up ---------------------------------------


def _version(sha="af814ab", subject="Leave an orientation"):
    from tools.live.version import Version

    return Version(commit=sha, subject=subject)


def test_a_first_start_says_it_started(tmp_path):
    """The Oracle case: nothing has ever run here, and the only proof the
    instance works is a message arriving from it."""
    from tools.live.version import startup_note

    note = startup_note("тихо · 5 каналів", _version(),
                        state_path=tmp_path / "v.json", now=T0)
    assert note is not None
    assert "запущено" in note
    assert "af814ab" in note
    assert "тихо · 5 каналів" in note


def test_a_new_commit_says_it_was_improved(tmp_path):
    """What he asked for: a deploy announces itself, in the same chat, without
    a sound."""
    from tools.live.version import remember, startup_note

    state = tmp_path / "v.json"
    remember(state, "2a5020c", T0 - 3600)
    note = startup_note("тихо", _version("af814ab", "Leave an orientation"),
                        state_path=state, now=T0)
    assert "Оновлено" in note
    assert "Leave an orientation" in note


def test_a_restart_on_the_same_commit_is_quiet_for_a_while(tmp_path):
    """systemd restarts forever with a ten-second gap, so a crash loop would
    otherwise send six messages a minute. Rare enough to still be a signal that
    something is wrong, quiet enough not to be the alarm itself."""
    from tools.live.version import RESTART_COOLDOWN_S, remember, startup_note

    state = tmp_path / "v.json"
    remember(state, "af814ab", T0)
    assert startup_note("тихо", _version(), state_path=state,
                        now=T0 + 60) is None
    later = startup_note("тихо", _version(), state_path=state,
                         now=T0 + RESTART_COOLDOWN_S + 1)
    assert later is not None and "Перезапуск" in later


def test_the_state_is_written_only_when_something_was_said(tmp_path):
    """Or a crash loop would keep pushing the timestamp forward and the restart
    would never be reported at all."""
    from tools.live.version import last_seen, remember, startup_note

    state = tmp_path / "v.json"
    remember(state, "af814ab", T0)
    startup_note("тихо", _version(), state_path=state, now=T0 + 60)
    assert last_seen(state) == ("af814ab", T0)


def test_several_commits_are_listed_but_not_all_of_them(tmp_path):
    """A deploy that carries a week of work must not arrive as a wall of text
    on a phone at three in the morning."""
    from tools.live.version import startup_note

    subjects = [f"commit number {i}" for i in range(9)]
    note = startup_note("тихо", _version("af814ab", subjects[0]),
                        changes=subjects, state_path=tmp_path / "v.json",
                        now=T0)
    assert note.count(chr(10)) <= 6
    assert "ще 5" in note


def test_a_checkout_without_git_still_announces(tmp_path):
    """A tarball, a container, a `git` that is not installed — none of those are
    a reason for the instance to stay silent about being alive."""
    from tools.live.version import describe, startup_note

    version = describe(tmp_path)          # not a repository
    assert version.commit == ""
    note = startup_note("тихо", version, state_path=tmp_path / "v.json", now=T0)
    assert note is not None
    assert "запущено" in note


def test_it_arrives_without_a_sound():
    """He is asleep. A deploy is not worth waking up for, ever."""
    import inspect

    from tools.live import run

    source = inspect.getsource(run.main)
    assert "startup_note" in source
    assert "audible=False" in source


# --- saying what the state actually is -------------------------------------


def test_the_state_word_claims_an_alert_only_when_the_siren_is_on():
    """He read "стан: ТРИВОГА" in a restart message with no alert running.

    An episode opens on any live threat — "З Донецька вилетіло 3 реактивні
    БпЛА" opens one, and should, because it tightens the polling long before
    anything arrives. But an episode is not a siren, and saying so loosely is
    the kind of thing that teaches him to discount the messages that matter.
    """
    from tools.live.run import state_word

    session = Session()
    assert state_word(session.tracker) == "тихо"

    handle(session, "war_monitor", 1, T0,
           "⚠️З Донецька вилетіло від 3 одиниць Реактивних БпЛА", False, T0 + 1)
    assert session.tracker.episode is not None      # tracking, on purpose
    assert state_word(session.tracker) == "стежу"

    session.tracker.official_source = True
    handle(session, "alarm_kyiv", 2, T0 + 60, "🚨 м. Київ\nПовітряна тривога",
           False, T0 + 61)
    assert state_word(session.tracker) == "ТРИВОГА"


def test_every_place_that_prints_the_state_uses_the_same_word():
    """There were four copies of the same ternary, which is how one of them
    would have kept the wrong answer after the others were fixed."""
    import inspect

    from tools.live import run

    source = inspect.getsource(run)
    assert 'if session.tracker.episode is not None else' not in source
    assert source.count("state_word(") >= 4
