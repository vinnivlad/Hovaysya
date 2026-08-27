"""Policy tests, written from decisions the user actually made."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.policy.episodes import Tracker, observe
from tools.policy.rules import decide, run

T0 = 1_756_000_000


def play(*items):
    """items: (offset_seconds, text) or (offset, text, is_reply)."""
    obs = [observe(T0 + i[0], i[1], i[2] if len(i) > 2 else False) for i in items]
    return run(obs, Tracker())


def levels(results):
    return [(d.level if d.notify else None) for _o, d in results]


# --- sirens ---------------------------------------------------------------


def test_a_city_siren_wakes_you_once():
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (60, "🛑 ТРИВОГА"))
    assert levels(r) == ["alert", None]


def test_a_district_siren_does_not():
    """Twelve of thirteen district sirens were labelled silent, and the user
    confirmed the thirteenth was his own mistake."""
    r = play((0, "🔴 Обухівський район - повітряна тривога!"),
             (60, "🔴 Вишгородський район - повітряна тривога!"))
    assert levels(r) == [None, None]


def test_a_siren_reply_is_a_refinement_not_a_declaration():
    """"По ньому тривога" answers an earlier message. Both such messages in the
    labelled night were silent, while every standalone siren woke him."""
    r = play((0, "По ньому тривога", True))
    assert levels(r) == [None]


def test_a_district_siren_does_not_silence_the_city_one():
    """The oblast siren was setting `alert_announced` without anything being
    announced, which cost four misses."""
    r = play((0, "🔴 Вишгородський район - повітряна тривога!"),
             (120, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"))
    assert levels(r) == [None, "alert"]


def test_an_all_clear_notifies_and_closes_the_episode():
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "🟢 ВІДБІЙ ТРИВОГИ"),
             (700, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"))
    assert levels(r) == ["alert", "alert", "alert"]
    assert [d.alarm for _o, d in r][1] == "clear"


def test_waiting_for_an_all_clear_does_not_announce_one():
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "⚪️Київ очікує на відбій."))
    assert levels(r)[1] != "alert" or [d.alarm for _o, d in r][1] != "clear"


def test_another_districts_all_clear_is_not_mine():
    r = play((0, "🟢 04:03 Відбій повітряної тривоги в Фастівському районі!"))
    assert levels(r) == [None]


# --- ballistic -----------------------------------------------------------


def test_a_confirmed_launch_wakes_you_with_the_ballistic_tone():
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Курської області."))
    assert levels(r) == ["alert"]
    assert r[0][1].alarm == "ballistic"


def test_an_anticipated_launch_does_not_re_alarm():
    """From the labelled sequence: "Загроза пуску" updates the picture, the
    sound belongs to the launch."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (60, "❗️❗❗Загроза пуску балістичних ракет \"Іскандер-М\" з Курської області."))
    assert levels(r) == ["alert", None]


def test_ordinals_within_one_volley_do_not_re_alarm():
    """"спуск балістики! Друга" counts the second missile of a wave already
    announced; treating it as new fired three times in a row."""
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Брянської області."),
             (60, "‼️ Київ — спуск балістики! Друга"),
             (120, "‼️ Київ — спуск балістики! Третя"))
    assert levels(r) == ["alert", None, None]


def test_two_channels_announcing_one_launch_wake_you_once():
    """Measured median lag between channels reporting the same event: 39 s."""
    r = play((0, "‼️ Вихід балістики з Брянська. Уважно"),
             (30, "❗️❗️❗️Пуски балістичних ракет з Брянської області."))
    assert levels(r) == ["alert", None]


def test_a_ballistic_target_in_another_region_is_not_mine():
    r = play((0, "❗Балістична ракета на Запоріжжя!"))
    assert levels(r) == [None]


def test_a_bare_place_during_a_ballistic_wave_is_that_wave():
    """The user annotated exactly this case "Ця балістика вже розбудила"."""
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Брянської області."),
             (120, "Жуляни"))
    assert levels(r) == ["alert", None]


# --- drones near the ring ------------------------------------------------


def test_a_new_drone_near_you_wakes_you():
    r = play((0, "🅿️ Київ / 1х Жуляни"))
    assert levels(r) == ["alert"]
    assert r[0][1].alarm in ("drone", "drone-jet")


def test_the_same_drone_restated_does_not():
    r = play((0, "⚠️1 реактивний шахед на Жуляни."),
             (120, "Через Оболонь в сторону Жулян"))
    assert levels(r) == ["alert", None]


def test_circling_nearby_is_not_an_approach():
    r = play((0, "⚠️1 реактивний шахед на Жуляни."),
             (300, "🔄 1х Довкола Крюківщини Вишневого."))
    assert levels(r)[1] != "alert"


def test_leaving_the_area_is_only_a_status_update():
    r = play((0, "⚠️1 реактивний шахед на Жуляни."),
             (600, "🅿️ 1х реактив Жуляни далі Центр."))
    assert levels(r)[1] != "alert"


def test_aftermath_never_wakes_you():
    r = play((0, "У Голосіївському районі уламки БпЛА, пожежу ліквідовано"))
    assert levels(r) == [None]


def test_a_donation_drive_never_wakes_you():
    r = play((0, "Друзі, ми закрили збір від фонду на реабілітацію 100 бійців"))
    assert levels(r) == [None]


def test_every_decision_carries_the_rule_that_made_it():
    """A false wake-up has to be traceable to one rule."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"), (60, "Дякую за підтримку"))
    assert all(d.reason for _o, d in r)


# --- partial all-clears ---------------------------------------------------


def test_a_partial_all_clear_does_not_sound_the_all_clear():
    """"Відбій загрози МіГ-31К" lifts one class while the alert continues.
    The all-clear tone means "you can come out"."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "⚪️ Відбій загрози МіГ-31К."))
    assert r[1][1].level == "info"
    assert r[1][1].alarm != "clear"


def test_a_partial_all_clear_does_not_close_the_episode():
    """Closing it would forget the night and re-announce the siren."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "⚪️По балістиці відбій."),
             (700, "🛑 ТРИВОГА"))
    assert levels(r) == ["alert", "info", None]


def test_a_full_all_clear_still_closes_it():
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "🟢 ВІДБІЙ ТРИВОГИ"),
             (700, "🛑 ТРИВОГА"))
    assert levels(r) == ["alert", "alert", "alert"]


def test_the_mig_cycle_takeoff_then_launch_at_kyiv():
    """From 2026-05-23: the case the first labelled night never contained."""
    r = play((0, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка."),
             (60, "Кинджал на Київ/Вишгород."))
    assert levels(r) == ["alert", "alert"]
    assert [d.alarm for _o, d in r] == ["mig", "ballistic"]


def test_the_mig_cycle_takeoff_then_nothing():
    """From 2026-08-04: took off, then "Відбій загрози МіГ-31К"."""
    r = play((0, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка."),
             (1020, "⚪️ Відбій загрози МіГ-31К."))
    assert levels(r) == ["alert", "info"]


# --- ballistic novelty without the word "пуск" ----------------------------


def test_a_bare_vyhid_is_a_launch():
    """The user's note: a message may be just "Вихід" with no "пуск" in it."""
    r = play((0, "‼️ Вихід балістики з Брянська"))
    assert levels(r) == ["alert"]
    assert r[0][1].alarm == "ballistic"


def test_balistyka_na_kyiv_with_no_launch_word_still_wakes_you_first_time():
    """"Балістика на Київ" names no launch. It is new because the ballistic tone
    has not sounded in this episode yet, not because of any word in it."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (60, "🔴🔴🔴🚀Балістика на Київ/передмістя."))
    assert levels(r) == ["alert", "alert"]
    assert [d.alarm for _o, d in r] == ["alert", "ballistic"]


def test_the_same_wording_later_in_the_wave_is_a_refinement():
    r = play((0, "🔴🔴🔴🚀Балістика на Київ/передмістя."),
             (120, "‼️Балістика на Київ/передмістя."))
    assert levels(r) == ["alert", None]


def test_a_new_class_breaks_through_an_ongoing_wave():
    """A Kinzhal after a MiG alert is the event the MiG alert warned about."""
    r = play((0, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка."),
             (300, "Кинджал на Київ/Вишгород."))
    assert [d.alarm for _o, d in r] == ["mig", "ballistic"]


def test_the_lifted_class_is_not_read_as_the_active_one():
    """"По балістиці відбій. / 2 шахеди на Одесу" lifts ballistic while shaheds
    fly; ordered matching answered with the wrong one."""
    from tools.nlp import hints
    t = "⚪️По балістиці відбій. / ⚠️2 шахеди на Чорноморськ/Одесу."
    assert hints.active_threat(t) == "shahed"
