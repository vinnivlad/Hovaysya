"""Tests for the settings file.

Two things matter and only one of them is about behaviour. The first is that a
setting actually changes what happens. The second is that nothing a person can
type into a JSON file can stop the watch: a missing file, a broken file, an
unknown key, a number of zero — all of them have to end with a running watcher.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.policy.config import (BOUNDS, DEFAULTS, Config, changed_from_default,
                                 from_dict, load)
from tools.policy.episodes import Tracker, observe
from tools.policy.rules import decide

T0 = 1_756_000_000


def _quiet(*_a, **_k):
    pass


# --- nothing here may take the watch down ----------------------------------


def test_no_file_means_the_current_behaviour(tmp_path):
    assert load(tmp_path / "absent.json", warn=_quiet) == DEFAULTS


def test_a_broken_file_means_the_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load(p, warn=_quiet) == DEFAULTS


def test_a_file_that_is_not_an_object_means_the_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('["ring_all_clear"]', encoding="utf-8")
    assert load(p, warn=_quiet) == DEFAULTS


def test_an_unknown_key_is_skipped_not_fatal():
    cfg = from_dict({"ring_all_clear": False, "нема_такого": 1}, warn=_quiet)
    assert cfg.ring_all_clear is False


def test_the_wrong_type_is_skipped():
    cfg = from_dict({"ring_memory_s": "багато", "ring_all_clear": "ні"},
                    warn=_quiet)
    assert cfg.ring_memory_s == DEFAULTS.ring_memory_s
    assert cfg.ring_all_clear is DEFAULTS.ring_all_clear


def test_numbers_are_clamped_rather_than_trusted():
    """A zero-second refractory rings on every message of a wave, and the person
    it woke has no way to tell that a config file did it."""
    for key, (lo, hi) in BOUNDS.items():
        assert getattr(from_dict({key: 0}, warn=_quiet), key) >= lo
        assert getattr(from_dict({key: 10 ** 6}, warn=_quiet), key) <= hi


# --- and a setting has to actually do something ----------------------------


def _play(texts, cfg):
    tr = Tracker(config=cfg)
    tr.official_source = True
    out = []
    for off, channel, text in texts:
        o = observe(T0 + off, text, False, channel, config=cfg)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None,
                  d.alarm if d.notify else None, d.reason)
        out.append(d)
    return out


SIREN = (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога")
CLEAR = (600, "alarm_kyiv", "🟢 м. Київ" + chr(10) + "Відбій повітряної тривоги")


def test_the_siren_and_the_all_clear_can_be_silenced():
    loud = _play([SIREN, CLEAR], DEFAULTS)
    assert loud[0].audible and loud[1].audible
    quiet = _play([SIREN, CLEAR],
                  Config(ring_alert_start=False, ring_all_clear=False))
    assert not quiet[0].audible and quiet[0].notify
    assert not quiet[1].audible and quiet[1].notify


def test_a_drone_can_ring_for_the_whole_ring_instead_of_home_alone():
    """Where it started, and which he narrowed himself after sleeping through
    five rings in fifty minutes."""
    msgs = [SIREN, (300, "kievinform_ua1", "⚠️Реактивний шахед на Вишневе.")]
    assert not _play(msgs, DEFAULTS)[1].audible
    assert _play(msgs, Config(drone_needs_home=False))[1].audible


def test_the_ring_itself_is_a_list_of_names():
    """His suggestion. The gazetteer stays the recognition layer -- every
    inflection and piece of slang -- and only the tier becomes personal."""
    cfg = Config(home="Оболонь", ring=("Оболонь", "Виноградар"))
    mine = observe(T0, "⚠️Реактивний шахед на Жуляни.", False, "kievinform_ua1")
    theirs = observe(T0, "⚠️Реактивний шахед на Жуляни.", False,
                     "kievinform_ua1", config=cfg)
    assert mine.ring_places == ("Жуляни",)
    assert theirs.ring_places == ()
    obolon = observe(T0, "⚠️Реактивний шахед на Оболонь.", False,
                     "kievinform_ua1", config=cfg)
    assert obolon.ring_places == ("Оболонь",) and obolon.at_home


def test_the_quiet_hours_keep_only_what_leaves_minutes():
    cfg = Config(quiet_hours=True, quiet_from_hour=23, quiet_to_hour=7)
    assert cfg.sounds_at(3, "ballistic")
    assert not cfg.sounds_at(3, "shahed-jet")
    assert cfg.sounds_at(12, "shahed-jet")          # outside the window
    # ...and the window wraps midnight.
    assert not cfg.sounds_at(23, "cruise")
    assert cfg.sounds_at(22, "cruise")


def test_the_startup_line_shows_only_what_was_changed():
    assert changed_from_default(DEFAULTS) == {}
    assert changed_from_default(Config(ring_memory_s=900)) == {"ring_memory_s": 900}
