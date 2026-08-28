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
