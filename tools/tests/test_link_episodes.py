"""Tests for episode linking.

`repeat_of` was empty across a whole night of real labelling because the form
only offered the field on notify labels. Filling it is mechanical for
`already-notified` — but only within a bound, or two separate waves get fused
into one fictional episode.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.labeler.link_episodes import (
    contradictions,
    fill_alarms,
    link,
)


def notify(at, lid, alarm="drone", **kw):
    d = {"id": lid, "at": at, "night": "2026-08-26", "decision": "notify",
         "level": "alert", "alarm": alarm, "threat": "shahed",
         "why": "x", "repeat_of": None}
    d.update(kw)
    return d


def silent(at, lid, reason="already-notified", **kw):
    d = {"id": lid, "at": at, "night": "2026-08-26", "decision": "silent",
         "silent_reason": reason, "threat": "shahed", "why": "", "repeat_of": None}
    d.update(kw)
    return d


# --- linking --------------------------------------------------------------


def test_already_notified_links_to_the_last_wake_up():
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              silent("2026-08-26T20:05:00Z", "b")]
    filled, distant = link(labels)
    assert filled == [("b", "a")]
    assert labels[1]["repeat_of"] == "a"
    assert distant == []


def test_the_most_recent_wake_up_wins():
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              notify("2026-08-26T20:10:00Z", "b"),
              silent("2026-08-26T20:15:00Z", "c")]
    link(labels)
    assert labels[2]["repeat_of"] == "b"


def test_an_all_clear_ends_the_episode():
    """After відбій there is no episode left to be a repeat of."""
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              notify("2026-08-26T20:30:00Z", "clr", alarm="clear"),
              silent("2026-08-26T20:35:00Z", "c")]
    filled, _ = link(labels)
    assert filled == []
    assert labels[2]["repeat_of"] is None


def test_a_gap_over_an_hour_is_declined_not_guessed():
    """A real label sat 154 minutes after the nearest wake-up. Linking it would
    have fused two separate waves into one fictional episode."""
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              silent("2026-08-26T23:00:00Z", "b")]
    filled, distant = link(labels)
    assert filled == []
    assert labels[1]["repeat_of"] is None
    assert distant and distant[0][0] == "b" and distant[0][2] == 3 * 3600


def test_an_existing_link_is_left_alone():
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              notify("2026-08-26T20:10:00Z", "b"),
              silent("2026-08-26T20:15:00Z", "c", repeat_of="a")]
    link(labels)
    assert labels[2]["repeat_of"] == "a"


def test_too_far_is_not_an_episode_claim():
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              silent("2026-08-26T20:05:00Z", "b", reason="too-far")]
    filled, _ = link(labels)
    assert filled == []


def test_nights_do_not_link_across_each_other():
    labels = [notify("2026-08-26T20:00:00Z", "a"),
              silent("2026-08-27T20:05:00Z", "b", night="2026-08-27")]
    filled, _ = link(labels)
    assert filled == []


# --- alarms ---------------------------------------------------------------


def test_a_missing_alarm_is_derived_from_the_threat():
    """A notify with no alarm cannot fire on any channel."""
    labels = [notify("2026-08-26T20:00:00Z", "a", alarm=None,
                     threat="shahed-jet")]
    assert fill_alarms(labels) == [("a", "drone-jet")]
    assert labels[0]["alarm"] == "drone-jet"


def test_an_existing_alarm_is_not_overwritten():
    labels = [notify("2026-08-26T20:00:00Z", "a", alarm="clear")]
    assert fill_alarms(labels) == []


def test_silent_labels_need_no_alarm():
    assert fill_alarms([silent("2026-08-26T20:00:00Z", "a")]) == []


# --- contradictions -------------------------------------------------------


def test_a_note_about_direction_contradicts_already_notified():
    """The real case: 20 labels said "не в мою сторону летить" while the reason
    said the episode had already woken them."""
    labels = [silent("2026-08-26T20:00:00Z", "a", why="не в мою сторону летить")]
    out = contradictions(labels)
    assert out and out[0][1] == "already-notified" and out[0][2] == "too-far"


def test_a_note_about_sameness_contradicts_too_far():
    labels = [silent("2026-08-26T20:00:00Z", "a", reason="too-far",
                     why="уточнення тої самої тривоги")]
    out = contradictions(labels)
    assert out and out[0][2] == "already-notified"


def test_a_matching_note_is_not_reported():
    labels = [silent("2026-08-26T20:00:00Z", "a", why="летять ті самі ракети")]
    assert contradictions(labels) == []


def test_an_empty_note_is_not_reported():
    assert contradictions([silent("2026-08-26T20:00:00Z", "a", why="")]) == []


def test_notify_labels_are_not_checked_for_reason_clashes():
    assert contradictions([notify("2026-08-26T20:00:00Z", "a", why="далеко")]) == []


# --- reasons that were never the labeller's to get wrong -------------------


def test_geography_outranks_the_note():
    """"Балістика на Кременчук" is silenced by the message alone, with no state
    at all — rule 4 fires before any novelty rule. So "не в мою сторону" is a
    restatement of `too-far`, not a disagreement with it."""
    labels = [silent("2026-08-26T23:30:00Z", "a", reason="too-far",
                     scope="elsewhere", modality="live-threat",
                     why="не в мою сторону летить")]
    assert contradictions(labels) == []


def test_the_same_note_on_a_nearby_threat_is_still_a_disagreement():
    """Near me, geography does not decide — only the episode does, so the note
    and the reason really do point at different rules."""
    labels = [silent("2026-08-26T23:30:00Z", "a", reason="already-notified",
                     scope="my-area", modality="live-threat",
                     why="не в мою сторону летить")]
    assert [c[0] for c in contradictions(labels)] == ["a"]


def test_a_mechanically_silent_modality_needs_no_reason_at_all():
    """"Тривога триватиме ще 2 години" is commentary. It was filed as
    `already-notified` because none of the four fit, and asking which episode it
    repeats has no answer."""
    labels = [notify("2026-08-26T20:00:00Z", "wake"),
              silent("2026-08-26T22:07:00Z", "a", modality="summary-news",
                     why="роздуми на тему скільки триватиме тривога")]
    assert contradictions(labels) == []
    filled, _distant = link(labels)
    assert filled == []
