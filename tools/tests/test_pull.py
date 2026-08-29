"""Tests for pulling the night logs off the server.

The instance is replaceable by design — Oracle does not promise notice before
reclaiming an idle Always Free machine — but `data/live/*.jsonl` are not. They
are the one thing in the project that cannot be recreated from anywhere, and
they now accumulate on a machine that can vanish.

So two failures matter here, and neither may be silent: the copy not happening,
and the copy happening but bringing nothing fresh, which means the watcher on
the far end is dead.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.pull import Outcome, STALE_AFTER_S, newest_log, plan, verdict

T0 = 1_756_000_000


def test_the_command_is_batch_safe_and_keeps_the_timestamps():
    """Run from a scheduler with nobody watching: a prompt for a password or an
    unknown host key would hang it forever instead of failing. And the mtimes
    are the liveness signal, so they have to survive the copy."""
    argv = plan(key=Path("k"), user="ubuntu", host="10.0.0.1",
                remote="/home/ubuntu/hovaysya/data/live", dest=Path("D:/out"))
    assert argv[0] == "scp"
    assert "-p" in argv and "-r" in argv
    assert "-i" in argv and "k" in " ".join(argv)
    joined = " ".join(argv)
    assert "BatchMode=yes" in joined
    assert "StrictHostKeyChecking=accept-new" in joined
    assert argv[-2] == "ubuntu@10.0.0.1:/home/ubuntu/hovaysya/data/live"
    assert argv[-1] == str(Path("D:/out"))


def test_a_failed_copy_is_reported(tmp_path):
    """The whole point. A backup that fails quietly is not a backup."""
    out = Outcome(ok=False, files=0, newest=None, error="ssh: connect: timed out")
    said = verdict(out, previous_trouble=False, now=T0)
    assert said is not None
    assert "timed out" in said


def test_a_copy_that_brings_nothing_fresh_means_the_watcher_is_dead(tmp_path):
    """Worth more than the copy check: a watcher that died at 3 a.m. is
    otherwise invisible — the phone simply stops beeping, which is exactly what
    a quiet night looks like."""
    out = Outcome(ok=True, files=31, newest=T0 - STALE_AFTER_S - 60)
    said = verdict(out, previous_trouble=False, now=T0)
    assert said is not None
    assert "мовчить" in said


def test_a_good_run_says_nothing():
    """It runs every day. Speaking every day would train him to ignore it."""
    out = Outcome(ok=True, files=31, newest=T0 - 60)
    assert verdict(out, previous_trouble=False, now=T0) is None


def test_recovery_is_announced_once():
    """Otherwise a fixed problem looks exactly like an unfixed one."""
    out = Outcome(ok=True, files=31, newest=T0 - 60)
    said = verdict(out, previous_trouble=True, now=T0)
    assert said is not None
    assert "віднов" in said.lower()


def test_the_newest_log_is_found_by_time_not_by_name(tmp_path):
    """A restart makes a new file, so names do not sort into the order the
    nights actually happened in when a run crosses midnight."""
    live = tmp_path / "live"
    live.mkdir()
    old = live / "20260101T000000.jsonl"
    new = live / "20250101T000000.jsonl"        # older name, newer file
    for path in (old, new):
        path.write_text("{}\n", encoding="utf-8")
    import os

    os.utime(old, (T0 - 9000, T0 - 9000))
    os.utime(new, (T0, T0))
    found = newest_log(tmp_path)
    assert found is not None
    assert found[0] == new.name
    assert abs(found[1] - T0) < 2


def test_no_logs_at_all_is_trouble_not_silence(tmp_path):
    """A first run against an empty destination, or a destination someone
    emptied. Either way it is not the same as a healthy copy."""
    assert newest_log(tmp_path) is None
    out = Outcome(ok=True, files=0, newest=None)
    assert verdict(out, previous_trouble=False, now=T0) is not None


def test_the_state_survives_a_round_trip(tmp_path):
    from tools.pull import read_state, write_state

    path = tmp_path / "state.json"
    assert read_state(path) is False          # nothing recorded yet
    write_state(path, trouble=True, at=T0)
    assert read_state(path) is True
    write_state(path, trouble=False, at=T0 + 60)
    assert read_state(path) is False


def test_it_speaks_through_the_same_bot_and_never_beeps():
    """He is asleep. A backup is never worth a sound."""
    import inspect

    from tools import pull

    source = inspect.getsource(pull.main)
    assert "Notifier" in source
    assert "audible=False" in source
