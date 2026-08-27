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


def test_a_partial_all_clear_is_worth_hearing():
    """The user labelled "⚪️ Відбій загрози МіГ-31К" as a wake-up — "відбій по
    мігам" — and asked to be told when a class is lifted. It was a silent status
    update until he said so."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "⚪️ Відбій загрози МіГ-31К."))
    assert r[1][1].level == "alert"
    # Its own tone: "повний відбій звучить по іншому", so the two must not share
    # one — hearing "you can come out" when only one class was lifted is worse
    # than hearing nothing.
    assert r[1][1].alarm == "clear-partial"


def test_a_partial_all_clear_does_not_close_the_episode():
    """Closing it would forget the night and re-announce the siren."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "⚪️По балістиці відбій."),
             (700, "🛑 ТРИВОГА"))
    # Heard, but the siren is not re-announced: the episode is still open.
    assert levels(r) == ["alert", "alert", None]


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
    assert levels(r) == ["alert", "alert"]
    assert [d.alarm for _o, d in r] == ["mig", "clear-partial"]


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


# --- forecasts are not events ---------------------------------------------


def test_a_multi_day_forecast_is_not_a_threat():
    """The user's note: "Здавалося б що загроза балістики, але ні! Попередження
    на наступні 2 дні просто."""
    r = play((0, "❗️Загроза балістичного удару по Києву, та околицям протягом 48 годин"))
    assert levels(r) == [None]


def test_a_speculative_forecast_is_not_a_threat():
    r = play((0, "❗️Київ може атакувати десятки балістичних ракет та гіперзвукових"))
    assert levels(r) == [None]


def test_a_probability_assessment_is_not_a_threat():
    r = play((0, "🟧 Ймовірність комбінованої атаки на середньому рівні."))
    assert levels(r) == [None]


def test_an_actual_launch_still_is():
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Курської області."))
    assert levels(r) == ["alert"]


def test_a_full_all_clear_keeps_its_own_tone():
    """The distinction only works if the full one is unmistakable."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (600, "🟢 ВІДБІЙ ТРИВОГИ"))
    assert [d.alarm for _o, d in r] == ["alert", "clear"]


def test_kyiv_oblast_siren_is_not_the_city_siren():
    """"КИЇВСЬКА ОБЛАСТЬ ОГОЛОШЕНА ПОВІТРЯНА ТРИВОГА" resolved as the city
    because "київська" starts with "київ"."""
    r = play((0, "🚨❗️КИЇВСЬКА ОБЛАСТЬ ОГОЛОШЕНА ПОВІТРЯНА ТРИВОГА"),
             (60, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"))
    assert levels(r) == [None, "alert"]


def test_a_mig_takeoff_announces_even_mid_episode():
    """"Виліт" is a takeoff and was absent from the launch words, so a MiG
    takeoff during a running alert was silenced as a repeat."""
    r = play((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
             (3000, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка."))
    assert levels(r) == ["alert", "alert"]
    assert [d.alarm for _o, d in r] == ["alert", "mig"]


def test_a_donation_round_up_is_not_a_threat():
    """One donor wrote "Гепарди по реактивним шахедам працюють", which made the
    whole post read as a live jet-drone threat."""
    t = chr(10).join([
        "Донат 1 від Артема:",
        "Гепарди по реактивним шахедам працюють, майже ніч не спали",
        "Донат 2: ❤️🫡",
        "Дякую за підтримку, збір триває, картка для донатів, грн",
    ])
    r = play((0, t))
    assert levels(r) == [None]


# --- per-class state, for the status line ---------------------------------


def test_the_episode_remembers_which_classes_were_lifted():
    """The user asked to know "що нема загрози балістики чи мігів" — the
    persistent status is where that lives, so the state has to be kept."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (300, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка."),
                      (900, "⚪️ Відбій загрози МіГ-31К.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert tr.episode is not None
    assert tr.episode.cleared == {"mig"}


def test_a_class_named_flying_again_is_no_longer_lifted():
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (300, "⚪️По балістиці відбій."),
                      (600, "❗️❗Є інформація про пуск балістичної ракети з Брянської області.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert tr.episode is not None
    assert "ballistic" not in tr.episode.cleared


def test_a_full_all_clear_ends_the_episode_and_its_state():
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (300, "⚪️По балістиці відбій."),
                      (600, "🟢 ВІДБІЙ ТРИВОГИ")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert tr.episode is None


# --- the commonest launch word of all -------------------------------------


def test_puskh_is_a_launch_word():
    """A stray `r` in the alternation disabled it: the pattern demanded a
    literal "r" immediately followed by a word boundary, which cannot happen.
    So the single most common launch report in the corpus was never a launch."""
    from tools.policy.episodes import _LAUNCH

    assert _LAUNCH.search("Є інформація про пуск балістичної ракети з Курської області.")
    assert _LAUNCH.search("Вихід балістики з Брянська")
    assert _LAUNCH.search("Виліт винищувача МіГ-31К")


def test_a_launch_from_a_russian_region_announces_something_new():
    o = observe(T0, "❗️❗Є інформація про пуск балістичної ракети з Курської області.")
    assert o.says_new
