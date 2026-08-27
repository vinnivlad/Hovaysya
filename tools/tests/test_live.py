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
