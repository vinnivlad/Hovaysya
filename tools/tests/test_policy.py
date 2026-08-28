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
    assert levels(r) == ["alert", "info"]
    # `info` rather than nothing: he asked to hear the class named after the
    # siren — "Тривога", then "по балістиці" — and silence dropped it. It is
    # still not a sound, which is what this test is about.
    assert not r[1][1].audible


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


# --- a ballistic launch already has him up --------------------------------


def test_a_ring_name_after_a_ballistic_alert_stays_quiet():
    """His ruling, and the reason is the point: "якщо був пуск балістики, то на
    моє коло повторну нотифікацію не шли. Я і так не сплю."

    It also settled what no threshold could. Fitted to the dense night a ring
    re-arm wanted to ring 78 s after the last alert; fitted to the sparse one it
    had to stay quiet at 155 s — both his own rulings on the same shape."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    got = []
    for off, text in ((0, "‼️ Вихід балістики з Брянська"),
                      (60, "❗6-8 Цирконів на Київ, Бровари."),
                      (100, "‼️Київ / Бровари — спуск балістики! 9та"),
                      (120, "Жуляни🚀"),
                      (200, "‼️Київ / Бровари — спуск балістики! 10та"),
                      (205, "БОРЩАГА")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append((text, d.audible))
    assert got[0][1], got            # the launch itself wakes him
    assert not any(a for _t, a in got[1:]), got


def test_a_new_class_still_breaks_through_a_ballistic_wave():
    """The rule is about repeats of the same class, not about going quiet for
    the rest of the night."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    got = []
    for off, text in ((0, "‼️ Вихід балістики з Брянська"),
                      (120, "Жуляни🚀"),
                      (300, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append((text[:24], d.audible, d.alarm))
    assert got[-1][1] and got[-1][2] == "mig", got


def test_a_city_wide_drone_report_is_not_enough():
    """His rule from the first conversation — "для дронів «летить на правий
    берег» ще не досить". Of 78 city-scope drone moments he woke for 3."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    o = observe(T0, "⚠️4 реактивні шахеди на Київ/Бровари.")
    d = decide(o, Tracker())
    assert not d.audible, d.reason


def test_one_mig_takeoff_is_one_event_however_many_channels_report_it():
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    got = []
    for off, text in ((0, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка."),
                      (60, "✈️⚠️Зліт МіГ-31К ВПС рф. Проходимо в укриття!"),
                      (180, "🛫 Зліт МіГ-31К ВПС рф.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append(d.audible)
    assert got == [True, False, False], got


def test_a_siren_that_may_be_declared_is_not_a_siren():
    """"У Києві у найближчі хвилини можуть оголосити повітряну тривогу" — his
    note: "Можуть оголосити! Ще не зрозуміло нічого"."""
    from tools.nlp import hints

    assert hints.alert_state(
        "🔴У Києві у найближчі хвилини можуть оголосити повітряну тривогу") is None
    assert hints.alert_state("⚠️❗️КИЇВ - ТРИВОГА. В укриття!") == "alert"


# --- what he actually hears ------------------------------------------------


def _speak(texts, spacing=200):
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr, ann = Tracker(), Announcer()
    out = []
    for i, text in enumerate(texts):
        o = observe(T0 + i * spacing, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
        out.append((d.audible, u.text if u else None))
    return out


def test_his_first_example():
    """"Якщо прилітають «Загроза балістики» і слідом «Вихід на Київ», то я хочу
    почути що почалась тривога по балістиці і потім що був пуск." """
    said = _speak(["❗️❗Загроза пуску балістичних ракет Іскандер-М.",
                   "‼️ Вихід балістики з Брянська на Київ"])
    assert said[0] == (False, "Тривога. Балістика.")   # words, no sound
    # The audible one carries the siren too. Shown is not heard: he never heard
    # the first sentence, so the one that rings has to say what happened as well
    # as what is new. Sharing one memory between the two channels is how a real
    # "🛑 ТРИВОГА" came out as "Увага." on the first watched night.
    assert said[1] == (True, "Тривога. Пуск: балістика.")


def test_his_second_example():
    """"Якщо просто «Тривога», «Загроза балістики», то почути що почалась
    тривога, а потім по балістиці." """
    said = _speak(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                   "❗️❗Загроза пуску балістичних ракет Іскандер-М.",
                   "‼️ Вихід балістики з Курська"])
    assert said[0] == (True, "Тривога.")
    assert said[1] == (False, "Загроза: балістика.")
    assert said[2] == (True, "Пуск: балістика.")


def test_an_utterance_says_only_what_changed():
    """Re-reading the whole situation aloud every time is how a voice channel becomes
    noise — the failure the tone channel had when every message rang."""
    said = _speak(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                   "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"])
    assert said[0][1] == "Тривога."
    assert said[1][1] is None          # the siren is announced once


def test_a_launch_is_not_announced_as_a_threat_as_well():
    """"Загроза: балістика. Пуск: балістика." is one fact said twice."""
    said = _speak(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                   "‼️ Вихід балістики з Брянська"])
    assert said[1][1] == "Пуск: балістика."


def test_the_all_clear_wipes_what_was_said():
    said = _speak(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                   "🟢 ВІДБІЙ ТРИВОГИ",
                   "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"])
    assert said[1][1] == "Відбій тривоги."
    assert said[2][1] == "Тривога."    # a new episode says it again


def test_a_partial_all_clear_names_the_class_it_lifts():
    said = _speak(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                   "‼️ Вихід балістики з Брянська",
                   "⚪️По балістиці відбій."])
    assert said[2][1] == "Відбій по балістиці."


# --- falling on Zhuliany --------------------------------------------------


def test_falling_on_zhuliany_always_rings():
    """His rule, in his words: "якщо є «падає» і «Жуляни» то точно казати".

    Found live: `⚠️Реактивний шахед падає на Жуляни` stayed silent five and a
    half minutes after the same drone had already woken him. Defensible as a
    repeat, and also the most consequential sentence of the night."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    got = []
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (60, "На Жуляни знову коло."),
                      (90, "⚠️Реактивний шахед на Жуляни."),
                      (330, "⚠️Реактивний шахед падає на Жуляни.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append((text[:28], d.audible, d.reason))
    assert got[-1][1], got
    assert got[-1][2] == "falling on Zhuliany", got
    # ...and the message before it was still a repeat, which is the point: the
    # rule is about the thing arriving, not about relaxing the refractory.
    assert not got[2][1], got


def test_it_is_two_words_wide_and_one_place_wide():
    """The first attempt covered the near ring and the whole impact vocabulary,
    and cost two false wake-ups on the dense night. He cut it back himself:
    "давай поки тільки падає жуляни. інші нехай вже як вийде"."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    for text in ("Вишневе, Боярка — падає!",              # ring, not home
                 "💥Влучання неподалік ТРЦ Республіка.",    # impact, not falling
                 "⚠️Реактивний шахед падає на Бровари."):   # neither
        tr = Tracker()
        for off, warm in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                          (60, "⚠️Реактивний шахед на Жуляни.")):
            o = observe(T0 + off, warm)
            d = decide(o, tr)
            tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        o = observe(T0 + 400, text)
        assert decide(o, tr).reason != "falling on Zhuliany", text


def test_a_wake_up_always_says_something():
    """It said "Увага." three times on the first night — the least useful
    sentence available, because it wakes him and tells him nothing. If the
    policy decided this is worth waking for, it is a new event, and the class
    and place are repeated rather than withheld."""
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr, ann = Tracker(), Announcer()
    said = []
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (400, "⚠️Реактивний шахед на Жуляни."),
                      (1200, "⚠️Реактивний шахед падає на Жуляни.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
        said.append((d.audible, u.text if u else None))
    assert all(a for a, _t in said), said
    assert said[-1][1] == "Реактивний шахед. Жуляни."
    assert "Увага" not in (said[-1][1] or "")


def test_a_drone_has_to_name_my_own_place():
    """The ring was too wide for this class, and he has the proof that settles
    it: "реально — я собі спав, поки воно там щось намотувало." One drone
    looping Nyvky → Sviatoshyn → Borshchahivka → Vyshneve rang five times in
    fifty minutes and he slept through all of it."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (60, "⚠️2 реактивні шахеди на Київ/Бровари.")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)

    ring_not_home = observe(T0 + 3000, "Київ: / 🅿️ 1х Нивки → Вишневе.")
    d = decide(ring_not_home, tr)
    assert d.notify and not d.audible, d          # on the status line, silent

    home = observe(T0 + 3600, "Жуляни")
    assert decide(home, tr).audible


def test_ballistic_keeps_the_whole_ring():
    """Minutes of flight leave no time to find out whose street."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (60, "‼️ Вихід балістики з Брянська")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert decide(observe(T0 + 3000, "❗2 балістичні ракети на Вишневе."), tr).audible


def test_a_carried_class_does_not_carry_the_geography_exemption():
    """"Княжичі✈️" said nothing about ballistic — the episode did — and the
    shelter tone rang for an oblast village with nothing to say."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                      (60, "‼️ Вихід балістики з Брянська")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    d = decide(observe(T0 + 3000, "Княжичі✈️"), tr)
    assert not d.audible, d


def test_when_there_is_no_reason_it_just_says_alert():
    """"Тривога є тривога. Якщо є її причина — то добре, а нема — то просто
    «тривога»." What stood here was "Увага.", and he asked what that could
    possibly mean when there are only two signals."""
    from tools.policy.announce import _fallback
    from tools.policy.episodes import observe

    named = observe(T0, "⚠️Реактивний шахед на Жуляни.")
    assert _fallback(named, "shahed-jet") == ["Реактивний шахед", "Жуляни"]

    placeless = observe(T0, "Ще ціль")
    assert _fallback(placeless, None) == []      # ...so the caller says Тривога


# --- the channel that declares --------------------------------------------


def _play(seq):
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr, ann, out = Tracker(), Announcer(), []
    for off, channel, text in seq:
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
        out.append((text[:26], d.audible, d.reason, u.text if u else None))
    return out


def test_the_official_channel_declares_and_the_chats_report():
    """His design: "повідомлення з інших каналів для уточнення причини". The
    official app declared Kyiv at 08:04 while `kievinform_ua1` had already said
    a bare "🛑 ТРИВОГА" at 07:50 for a district — and that spent the
    announcement on the wrong siren."""
    out = _play([
        (0, "kievinform_ua1", "🛑 ТРИВОГА"),
        (840, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (900, "kievinform_ua1", "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
    ])
    assert out[1][1], out          # the official declaration always rings
    assert out[1][2] == "official siren"
    assert not out[2][1], out      # ...and the chat repeat does not


def test_a_chat_all_clear_does_not_close_the_official_alert():
    """Two of the last false wake-ups were chat all-clears about somebody else's
    district, and he wrote on both "вся надія на сервіси"."""
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (600, "kievinform_ua1", "🟢 ВІДБІЙ ТРИВОГИ"),
        (900, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
    ])
    assert not out[1][1], out      # the district's all-clear stays quiet
    assert out[2][1] and out[2][2] == "official all-clear", out
    assert out[2][3] == "Відбій тривоги."


def test_a_chat_siren_still_declares_when_nothing_official_has_spoken():
    """The other half of his rule — "ну або якщо є Київ + тривога" — and it is
    what keeps the labelled nights working, where this channel was not yet a
    source."""
    out = _play([(0, "kievinform_ua1", "⚠️❗️КИЇВ - ТРИВОГА. В укриття!")])
    assert out[0][1] and out[0][2] == "alert declared", out


def test_the_chat_channels_stop_declaring_while_the_official_one_is_live():
    """Two rings two seconds apart, one from each — 09:54:43 "Тривога." from the
    chat and 09:54:45 "Київ." from the official channel."""
    out = _play([
        (0, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
        (600, "kievinform_ua1", "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
        (602, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
    ])
    assert not out[1][1], out          # the chat report stays quiet
    assert out[2][1] and out[2][3] == "Тривога.", out


def test_a_chat_all_clear_never_closes_it_while_the_official_one_is_live():
    """It fired at 13:51 on a night the official channel had covered all day —
    the branch that caught it sat below the one that answered first."""
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (600, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
        (5000, "kievinform_ua1", "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
        (9000, "kievinform_ua1", "🟢 ВІДБІЙ ТРИВОГИ"),
    ])
    assert not out[3][1], out
