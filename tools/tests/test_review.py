"""Tests for the label reviewer.

The reviewer exists so a labelled set cannot quietly drift, so it has to be
right about what counts as a finding — and, just as importantly, about what does
not.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.labeler.review import check, load, summarise


def label(**kw):
    base = {
        "id": "2026-08-27T22:14-01", "at": "2026-08-27T19:14:00Z",
        "night": "2026-08-27", "anchor": "mon1tor_ua/1",
        "decision": "notify", "level": "alert", "alarm": "drone",
        "threat": "shahed", "modality": "live-threat", "scope": "my-area",
        "certainty": "confirmed", "repeat_of": None, "evidence": [],
        "why": "дрон на мій район", "open_question": None,
    }
    base.update(kw)
    return base


def ids(findings, severity=None):
    return [f[2] for f in findings if severity is None or f[0] == severity]


def test_a_clean_label_produces_nothing():
    assert check([label()], {}) == []


# --- schema errors --------------------------------------------------------


def test_missing_required_field_is_an_error():
    bad = label()
    del bad["scope"]
    assert any("scope" in m for m in ids(check([bad], {}), "error"))


def test_unknown_enum_value_is_an_error():
    f = check([label(threat="кинжал")], {})
    assert any("threat" in m for m in ids(f, "error"))


def test_notify_without_why_is_an_error():
    f = check([label(why="   ")], {})
    assert any("why" in m for m in ids(f, "error"))


def test_silent_without_why_is_fine():
    """Most of a night is silent; demanding a sentence each time is what made
    dense labelling unbearable."""
    l = label(decision="silent", silent_reason="too-far", why="")
    del l["level"]
    del l["alarm"]
    assert check([l], {}) == []


def test_silent_needs_a_reason():
    l = label(decision="silent", why="")
    del l["level"]
    del l["alarm"]
    f = check([l], {})
    assert any("reason" in m for m in ids(f, "error"))


def test_duplicate_ids_are_an_error():
    f = check([label(), label()], {})
    assert any("duplicate" in m for m in ids(f, "error"))


def test_repeat_of_must_exist_and_be_earlier():
    f = check([label(repeat_of="nope")], {})
    assert any("does not exist" in m for m in ids(f, "error"))

    first = label(id="a", at="2026-08-27T20:00:00Z")
    second = label(id="b", at="2026-08-27T19:00:00Z", repeat_of="a")
    f = check([first, second], {})
    assert any("not earlier" in m for m in ids(f, "error"))


def test_unknown_anchor_is_an_error_when_the_corpus_is_available():
    f = check([label(anchor="mon1tor_ua/999")], {"mon1tor_ua/1": {"text": "x"}})
    assert any("anchor" in m for m in ids(f, "error"))


def test_anchor_is_not_checked_without_a_corpus():
    assert check([label(anchor="mon1tor_ua/999")], {}) == []


# --- consistency warnings -------------------------------------------------


def test_notify_on_another_region_warns():
    f = check([label(scope="elsewhere")], {})
    assert any("another region" in m for m in ids(f, "warning"))


def test_audible_notify_with_nothing_flying_warns():
    f = check([label(threat="none", level="alert")], {})
    assert any("nothing is flying" in m for m in ids(f, "warning"))


def test_info_level_with_nothing_flying_is_fine():
    assert check([label(threat="none", level="info", alarm="none")], {}) == []


def test_shelter_on_an_all_clear_warns():
    f = check([label(level="shelter", certainty="clear")], {})
    assert any("all-clear" in m for m in ids(f, "warning"))


def test_audible_notify_on_aftermath_warns():
    f = check([label(modality="aftermath")], {})
    assert any("aftermath" in m for m in ids(f, "warning"))


def test_shelter_on_emoji_only_evidence_warns():
    msgs = {"mon1tor_ua/1": {"text": "🔴Київ — буде гучно."}}
    f = check([label(level="shelter", alarm="drone")], msgs)
    assert any("emoji" in m for m in ids(f, "warning"))


def test_shelter_on_textual_evidence_does_not_warn():
    msgs = {"mon1tor_ua/1": {"text": "⚠️1 реактивний шахед на Жуляни."}}
    assert check([label(level="shelter")], msgs) == []


def test_already_notified_without_an_earlier_notify_warns():
    l = label(decision="silent", silent_reason="already-notified", why="")
    del l["level"]
    del l["alarm"]
    f = check([l], {})
    assert any("nothing woke you" in m for m in ids(f, "warning"))


def test_already_notified_after_a_notify_is_fine():
    first = label(id="a", at="2026-08-27T19:00:00Z")
    second = label(id="b", at="2026-08-27T19:05:00Z", decision="silent",
                   silent_reason="already-notified", why="")
    del second["level"]
    del second["alarm"]
    assert check([first, second], {}) == []


# --- the new-sound rule ---------------------------------------------------


def test_a_new_sound_on_an_anticipated_threat_warns():
    """The rule from a real sequence: "Загроза пуску" must not re-alarm; only a
    confirmed launch may."""
    first = label(id="a", at="2026-08-27T19:00:00Z", alarm="alert",
                  threat="unknown")
    second = label(id="b", at="2026-08-27T19:01:00Z", alarm="ballistic",
                   threat="ballistic", certainty="probable",
                   why="загроза пуску балістики")
    f = check([first, second], {})
    assert any("anticipated" in m for m in ids(f, "warning"))


def test_a_new_sound_on_a_confirmed_launch_is_fine():
    first = label(id="a", at="2026-08-27T19:00:00Z", alarm="alert",
                  threat="unknown")
    second = label(id="b", at="2026-08-27T19:02:00Z", alarm="ballistic",
                   threat="ballistic", certainty="confirmed",
                   why="є інформація про пуск")
    assert check([first, second], {}) == []


def test_the_same_sound_repeated_on_an_anticipation_is_fine():
    """Re-raising the sound already in play is not a new sound."""
    first = label(id="a", at="2026-08-27T19:00:00Z", alarm="ballistic",
                  threat="ballistic")
    second = label(id="b", at="2026-08-27T19:01:00Z", alarm="ballistic",
                   threat="ballistic", certainty="probable",
                   why="загроза триває")
    assert check([first, second], {}) == []


# --- loading and summary -------------------------------------------------


def test_broken_json_is_reported_not_crashed(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text('{"id": "a"}\nnot json\n', encoding="utf-8")
    loaded = load(p)
    assert any("_broken" in l for l in loaded)
    assert any("line 2" in m for m in ids(check(loaded, {}), "error"))


def test_missing_file_loads_as_empty(tmp_path):
    assert load(tmp_path / "nope.jsonl") == []


def test_summary_counts_decisions():
    out = "\n".join(summarise([label(), label(id="b", decision="silent",
                                             silent_reason="too-far")]))
    assert "2 labels" in out
    assert "1 notify" in out


# --- same situation, different answer ------------------------------------


def test_identical_situations_with_the_same_answer_are_not_reported():
    from tools.labeler.review import inconsistencies

    a = label(id="a", at="2026-08-27T19:00:00Z")
    b = label(id="b", at="2026-08-27T20:00:00Z")
    assert inconsistencies([a, b], {}) == []


def test_identical_situations_with_different_answers_are_reported():
    """This is the drift the reviewer exists to catch: the twentieth night
    judged by a different standard than the first."""
    from tools.labeler.review import inconsistencies

    a = label(id="a", at="2026-08-27T19:00:00Z", level="shelter")
    b = label(id="b", at="2026-08-27T20:00:00Z", level="alert")
    out = "\n".join(inconsistencies([a, b], {}))
    assert "2 moments, 2 different answers" in out
    assert "shelter" in out and "alert" in out


def test_a_notify_and_a_silent_on_the_same_signature_are_reported():
    from tools.labeler.review import inconsistencies

    a = label(id="a", at="2026-08-27T19:00:00Z")
    b = label(id="b", at="2026-08-27T20:00:00Z", decision="silent",
              silent_reason="too-far", why="")
    del b["level"]
    del b["alarm"]
    out = "\n".join(inconsistencies([a, b], {}))
    assert "different answers" in out


def test_different_situations_are_not_compared():
    from tools.labeler.review import inconsistencies

    a = label(id="a", scope="my-area", level="shelter")
    b = label(id="b", at="2026-08-27T20:00:00Z", scope="city", level="alert")
    assert inconsistencies([a, b], {}) == []


def test_the_reason_is_shown_so_a_split_can_be_judged():
    from tools.labeler.review import inconsistencies

    a = label(id="a", at="2026-08-27T19:00:00Z", level="shelter",
              why="йшло прямо на Жуляни")
    b = label(id="b", at="2026-08-27T20:00:00Z", level="alert",
              why="ще далеко, тільки курс")
    out = "\n".join(inconsistencies([a, b], {}))
    assert "йшло прямо на Жуляни" in out
    assert "ще далеко" in out
