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


def alarms(results):
    return [(d.alarm if d.notify else None) for _o, d in results]


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
    # It rings, and it did not use to. A ballistic warning after a drone alert
    # is a rung up his ladder — "на кожне підвищення давати звукове
    # повідомлення" — and this is the case he gave for it: "тривога по шахеду і
    # зразу після загроза балістики".
    assert levels(r) == ["alert", "alert"]
    assert r[1][1].reason == "threat level rose"


def test_ordinals_within_one_volley_do_not_re_alarm():
    """"спуск балістики! Друга" counts the second missile of a wave already
    announced; treating it as new fired three times in a row."""
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Брянської області."),
             (60, "‼️ Київ — спуск балістики! Друга"),
             (120, "‼️ Київ — спуск балістики! Третя"))
    # Shown while the wave is over here, never heard again: his ask after the
    # ballistic night, "можна б писати хоча б тихим".
    assert levels(r) == ["alert", "info", None]


def test_two_channels_announcing_one_launch_wake_you_once():
    """Measured median lag between channels reporting the same event: 39 s."""
    r = play((0, "‼️ Вихід балістики з Брянська. Уважно"),
             (30, "❗️❗️❗️Пуски балістичних ракет з Брянської області."))
    assert levels(r) == ["alert", None]


def test_a_ballistic_target_in_another_region_is_not_mine():
    r = play((0, "❗Балістична ракета на Запоріжжя!"))
    assert levels(r) == [None]


def test_a_bare_place_during_a_ballistic_wave_is_that_wave():
    """The class is inherited -- a bare "Жуляни" mid-wave is that wave, not a
    new drone -- and since 2026-09-01 his own place rings on it.

    This test used to assert the opposite, on his annotation "Ця балістика вже
    розбудила". He reversed it after seeing all eight labels of the shape: "Тихо
    з різницею в 10хв — я явно був не правий". The inheritance is what the test
    is really about, and it is unchanged: the tone is ballistic, not the drone
    tone the text alone would earn."""
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Брянської області."),
             (120, "Жуляни"))
    assert levels(r) == ["alert", "alert"]
    assert alarms(r) == ["ballistic", "ballistic"]


def test_a_bare_ring_place_during_a_ballistic_wave_still_stays_quiet():
    """The reversal is about *his* place. Vyshneve is in the ring and not his
    street, so the older ruling stands there -- otherwise a wave naming twenty
    districts would ring twenty times."""
    r = play((0, "❗️❗Є інформація про пуск балістичної ракети з Брянської області."),
             (120, "Вишневе"))
    assert levels(r) == ["alert", "info"]


# --- drones near the ring ------------------------------------------------


def test_a_new_drone_near_you_wakes_you():
    r = play((0, "🅿️ Київ / 1х Жуляни"))
    assert levels(r) == ["alert"]
    assert r[0][1].alarm in ("drone", "drone-jet")


def test_the_same_drone_restated_does_not():
    """It is shown, not swallowed: home named again goes on the status line
    without a second sound. His words when it produced nothing at all --
    "ніякого повідомлення не було"."""
    r = play((0, "⚠️1 реактивний шахед на Жуляни."),
             (120, "Через Оболонь в сторону Жулян"))
    assert levels(r) == ["alert", "info"]
    assert r[1][1].alarm == "none"


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
    assert levels(r) == ["alert", "info"]


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
                      (120, "Вишневе🚀"),
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
    # Neither of these is a siren declaration — one is a launch *threat* and the
    # other a launch. The word "Тривога" belongs to an actual declaration and
    # nothing else: adding it to whatever rang first meant a drone over Zhuliany
    # announced an alert that did not exist, and then the official declaration,
    # the one sentence he acts on, had nothing left to say.
    assert said[0] == (False, "Загроза: балістика.")   # words, no sound
    assert said[1] == (True, "Пуск: балістика.")


def test_his_second_example():
    """"Якщо просто «Тривога», «Загроза балістики», то почути що почалась
    тривога, а потім по балістиці." """
    said = _speak(["⚠️❗️КИЇВ - ТРИВОГА. В укриття!",
                   "❗️❗Загроза пуску балістичних ракет Іскандер-М.",
                   "‼️ Вихід балістики з Курська"])
    assert said[0] == (True, "Тривога.")
    # The second one rings now: the ladder went from drone to ballistic. He
    # asked for exactly this — "почути що почалась тривога, а потім по
    # балістиці" — and the escalation rule is what finally delivers the second
    # half aloud rather than as a silent line.
    assert said[1] == (True, "Загроза: балістика.")
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
    # "Падає" is the word the whole rule exists for, and it was never said. The
    # class comes with it now that a sentence carries the whole situation rather
    # than the difference — his call, after a partial one sent him hunting a bug
    # that was not there.
    assert said[-1][1] == "Падає: реактивний шахед. Жуляни."
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


def test_a_late_chat_all_clear_is_still_a_duplicate():
    """Channels do not arrive in order. On 2026-08-28 the chat all-clear was
    stamped two seconds before the official one and reached us fifty seconds
    after it — and he heard "Відбій тривоги." twice."""
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (600, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
        (598, "kievinform_ua1", "🟢 ВІДБІЙ ТРИВОГИ"),      # earlier stamp, later arrival
    ])
    assert out[1][1], out
    assert not out[2][1], out


def test_the_official_siren_arrives_carrying_the_reason():
    """His idea, from the episode at 10:54 on 2026-08-28: we knew "реактивний
    шахед, Вишневе" two minutes before the official siren, and when it came it
    said a bare "Тривога." — "тоді просто тягнемо контекст"."""
    out = _play([
        (-3600, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
        (282, "mon1tor_ua", "⚠️2 реактивні шахеди на Київ/Ірпінь/Буча."),
        (363, "mon1tor_ua", "⚠️2 реактивні шахеди на Вишневе."),
        (470, "kievinform_ua1", "🛑 ТРИВОГА"),
        (474, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
    ])
    assert out[2][3] == "Загроза: реактивний шахед. Вишневе."   # silent, on the status
    assert not out[3][1], out            # the chat siren stays quiet
    assert out[4][1], out
    assert out[4][3] == "Тривога. Реактивний шахед. Вишневе."


def test_a_wake_up_before_any_siren_does_not_claim_one():
    """A drone over Zhuliany with nothing declared: it is worth waking for, and
    it is not an air-raid alert."""
    out = _play([
        (-3600, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
        (300, "kievinform_ua1", "Жуляни ✈️"),
    ])
    assert out[1][1], out
    assert out[1][3] == "Жуляни."
    assert "Тривога" not in out[1][3]


def test_the_tone_follows_the_class_the_decision_was_made_on():
    """"Жуляни ✈️" states no class, so its own alarm is the propeller-drone
    tone — while the episode knows a jet Shahed is up. It is several times
    faster and has its own tone precisely so he knows before opening his eyes,
    which is the whole reason for separate sounds."""
    out = _play([
        (-3600, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
        (300, "mon1tor_ua", "⚠️2 реактивні шахеди на Вишневе."),
        (900, "kievinform_ua1", "Жуляни ✈️"),
    ])
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr, ann = Tracker(), Announcer()
    lead = None
    for off, channel, text in ((-3600, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги"),
                               (300, "mon1tor_ua", "⚠️2 реактивні шахеди на Вишневе."),
                               (900, "kievinform_ua1", "Жуляни ✈️")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
        if u:
            lead = u.lead
    assert lead == "drone-jet", lead
    assert out[2][1], out


def test_the_effective_class_is_stamped_on_the_observation():
    """Everything downstream wants the class the policy decided on, not the
    message's own: the notification, the log and the report all name it."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    for off, text in ((0, "⚠️2 реактивні шахеди на Київ/Бровари."),
                      (300, "Жуляни ✈️")):
        o = observe(T0 + off, text)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert o.threat == "unknown"          # the message says nothing
    assert o.effective_threat == "shahed-jet"


def test_my_own_place_is_never_dropped_as_already_said():
    """It woke him at 17:43 on "Жуляни, Вишневе, Теремки" and the sentence came
    out as "Вишневе, Теремки." — the one name that decides what he does was the
    one left out, because it had been said seven minutes earlier."""
    out = _play([
        (-3600, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (0, "kievinform_ua1", "😵‍💫БПЛА на Нивки, Жуляни йде ⚠️✈️"),
        (420, "kievinform_ua1", "Жуляни, Вишневе, Теремки⚠️"),
    ])
    assert out[2][1], out
    # The class comes with it: a sentence states the whole situation now, on his
    # instruction — "думаю краще видавати все" — and it was this very message
    # that argued for it.
    assert out[2][3] == "Загроза: шахед. Жуляни, Вишневе, Теремки."


def test_falling_is_said_out_loud():
    """The strictest rule in the policy exists for that word, and it had been
    ringing without the word ever being said."""
    out = _play([
        (-3600, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (300, "mon1tor_ua", "⚠️Реактивний шахед падає на Жуляни."),
    ])
    assert out[1][3] == "Падає: реактивний шахед. Жуляни."


def test_a_silent_official_channel_is_still_the_official_channel():
    """It speaks only when the siren changes, so "has it spoken lately" is not
    the same question as "is it being watched".

    On 2026-08-28 it had last spoken at 16:45, the watcher restarted at 18:34,
    and the 90-minute warm-up therefore contained nothing official. A chat
    all-clear at 19:09:53 rang and the real one followed four seconds later —
    two loud all-clears, which is what he heard."""
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr, ann = Tracker(), Announcer()
    tr.official_source = True          # watched, and silent for hours
    out = []
    for off, channel, text in ((0, "kievinform_ua1", "⚠️❗️КИЇВ - ТРИВОГА. В укриття!"),
                               (9000, "kievinform_ua1", "🟢 ВІДБІЙ ТРИВОГИ"),
                               (9004, "alarm_kyiv", "🟢 м. Київ\nВідбій повітряної тривоги")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
        out.append((d.audible, d.reason, u.text if u else None))
    assert not out[1][0], out          # the chat all-clear stays quiet
    assert out[2][0] and out[2][1] == "official all-clear", out


def test_without_the_official_channel_the_chats_still_close_the_alert():
    """The labelled nights predate it, and they have to keep working."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()                     # official_source stays False
    o = observe(T0, "⚠️❗️КИЇВ - ТРИВОГА. В укриття!", False, "kievinform_ua1")
    d = decide(o, tr)
    tr.record(o, d.level, d.alarm)
    d = decide(observe(T0 + 9000, "🟢 ВІДБІЙ ТРИВОГИ", False, "kievinform_ua1"), tr)
    assert d.audible and d.reason == "all-clear", d


def test_an_explosion_is_information_never_a_warning():
    """Of fifteen labels he placed on impact reports, fifteen are silent.

    Found live: "💥Повідомляють про вибухи в районі Вишневого" rang the shelter
    tone, on a ballistic class carried from a message two minutes earlier. His
    words: "цілей немає"."""
    from tools.policy.episodes import Tracker

    tr = Tracker()
    tr.official_source = True
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (200, "mon1tor_ua", "‼️ Вихід балістики з Брянська"),
        (400, "monitoring_kyiv", "💥Повідомляють про вибухи в районі Вишневого"),
        (500, "mon1tor_ua", "💥Влучання реактивного шахеду у Вишневому"),
    ])
    assert not out[2][1] and out[2][2] == "impact: it has already landed", out
    assert not out[3][1], out

    # ...and "Загроза" about a thing that has already come down is untrue.
    assert out[2][3].startswith("Вибух:")
    assert out[3][3].startswith("Влучання:")


def test_falling_is_not_an_impact():
    """A thing on its way down, and over his own street it overrides everything.
    The two vocabularies must not be confused."""
    from tools.policy.episodes import Tracker

    tr = Tracker()
    tr.official_source = True
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (300, "mon1tor_ua", "⚠️Реактивний шахед падає на Жуляни."),
    ])
    assert out[1][1] and out[1][2] == "falling on Zhuliany", out


def test_an_impact_elsewhere_is_not_even_context():
    """"У Києві велика детонація боєприпасів внаслідок влучання" is both the
    past and somebody else's street. His call: "давай лишаємо тільки коло"."""
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (200, "mon1tor_ua", "⚠️2 реактивні шахеди на Вишневе."),
        (400, "mon1tor_ua", "💥У Києві велика детонація боєприпасів внаслідок влучання"),
        (500, "mon1tor_ua", "💥Влучання реактивного шахеду у Вишневому"),
    ])
    assert out[2][3] is None, out           # nothing at all, not even a status line
    assert out[2][2] == "impact: elsewhere, and already over"
    assert out[3][3] == "Влучання: реактивний шахед. Вишневе."


# --- the ladder -----------------------------------------------------------


def test_each_rung_rings_once():
    """His rule: "дрон (будь-який) -> крилата ракета -> балістика", and every
    climb makes a sound. The case that prompted it: "тривога по шахеду і зразу
    після загроза балістики"."""
    out = _play([
        (0, "mon1tor_ua", "⚠️2 реактивні шахеди на Київ/Бровари."),
        (60, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (120, "mon1tor_ua", "⚠️Ще реактивні шахеди на Київ."),
        (200, "mon1tor_ua", "❗️❗Загроза пуску балістичних ракет Іскандер-М."),
        (400, "mon1tor_ua", "⚠️Ще реактивні шахеди на Київ."),
    ])
    assert not out[0][1], out                 # before the siren, nothing rings
    assert out[1][1], out                     # the siren itself
    assert not out[2][1], out                 # a drone is the rung it is already on
    assert out[3][1] and out[3][2] == "threat level rose", out
    assert not out[4][1], out                 # ...and back down does not ring


def test_a_fall_does_not_reset_the_ladder():
    """"Якщо в середині тривоги рівень знизився, то повторно правило не
    застосовувати." """
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (200, "mon1tor_ua", "❗️❗Загроза пуску балістичних ракет Іскандер-М."),
        (400, "mon1tor_ua", "⚠️Ще реактивні шахеди на Київ."),
        (600, "mon1tor_ua", "❗️❗Знову загроза балістики."),
    ])
    assert out[1][1] and out[1][2] == "threat level rose", out
    assert not out[3][1], out                 # the same rung, a second time


def test_a_partial_all_clear_lowers_it_and_a_climb_rings_again():
    """The one exception he made: "коли був частковий відбій по балістиці чи
    крилатим ракетам — тоді знижуємо поточний рівень"."""
    out = _play([
        (0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
        (200, "mon1tor_ua", "❗️❗Загроза пуску балістичних ракет Іскандер-М."),
        (400, "mon1tor_ua", "⚪️По балістиці відбій."),
        (600, "mon1tor_ua", "❗️❗Загроза балістики з Курської області."),
    ])
    assert out[1][1] and out[1][2] == "threat level rose", out
    assert out[2][1] and out[2][2] == "partial all-clear", out
    assert out[3][1] and out[3][2] == "threat level rose", out


def test_the_ladder_does_not_move_before_the_siren():
    """"Правило має працювати лише після початку тривоги"."""
    out = _play([
        (0, "mon1tor_ua", "⚠️2 реактивні шахеди на Київ/Бровари."),
        (200, "mon1tor_ua", "❗️❗Загроза пуску балістичних ракет Іскандер-М."),
    ])
    assert not any(a for _t, a, _r, _s in out), out


def test_the_near_refractory_is_five_minutes():
    """His number, and the channels agree it is the right order of magnitude:
    the median gap between two mentions of his ring is 42 seconds and 79% are
    under five minutes, so most of what it silences is one target being tracked
    rather than a second one arriving."""
    from tools.policy.episodes import REFRACTORY_NEAR_S

    assert REFRACTORY_NEAR_S == 300


def test_cruise_rings_on_position_and_ballistic_on_launch():
    """A physical difference, and it decides which machinery each class uses.

    A cruise missile flies for hours, so its launch says nothing about when it
    arrives or whether it is coming here — "крилаті ракети нема сенсу дзвонити
    на пуск, воно летить кілька годин. Крилаті — тільки позиція." Ballistic is
    minutes, so the launch is the whole event and a position adds nothing."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    # Ballistic: the launch rings, and a position over the ring afterwards does not.
    tr = Tracker()
    tr.official_source = True
    got = []
    for off, channel, text in ((0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
                               (200, "war_monitor", "‼️ Вихід балістики з Брянська"),
                               (400, "kievinform_ua1", "Вишневе🚀")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append((d.audible, d.reason))
    assert got[1][0], got                      # the launch rings
    # ...and a position after it does not. Vyshneve rather than Zhuliany: since
    # 2026-09-01 his own street rings whatever else has been said, which would
    # hide the thing this test is about.
    assert not got[2][0], got

    # Cruise: the launch is hours away, so the position is what rings.
    tr = Tracker()
    tr.official_source = True
    got = []
    for off, channel, text in ((0, "alarm_kyiv", "🚨 м. Київ\nПовітряна тривога"),
                               (200, "mon1tor_ua", "❗️Пуск крилатих ракет з Ту-95МС."),
                               (900, "mon1tor_ua", "❗2 крилаті ракети на Жуляни.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append((d.audible, d.reason))
    assert not got[1][0], got                  # a launch hours away does not ring
    assert got[2][0], got                      # ...the position over the ring does


# --- "дорозвідка": the alert continues, the cause is probably gone -----------


def test_a_recheck_is_shown_silently_and_only_once_per_class():
    """His feature. 402 of these in the corpus and the policy silenced 401, so
    he had never seen one — yet it is the message that says the thing worth
    knowing: the alert is still on, but what caused it is probably destroyed."""
    tr = Tracker()
    tr.official_source = True
    said = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (300, "mon1tor_ua", "📡Київ — дорозвідка."),
            (360, "mon1tor_ua", "📡Дорозвідка."),
            (420, "mon1tor_ua", "📡Дорозвідка по ракетах."),
    ):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        said.append(d)

    assert said[1].notify and not said[1].audible
    assert said[1].reason.startswith("recheck")
    # ...and the channels repeat themselves, so the second one is not a message.
    assert not said[2].notify
    # A different class is a different fact.
    assert said[3].notify and not said[3].audible


def test_a_recheck_outside_an_alert_says_nothing():
    """"Тривога ще триває" is the whole meaning of the word."""
    tr = Tracker()
    o = observe(T0, "📡Дніпро та область — дорозвідка.", False, "mon1tor_ua")
    assert not decide(o, tr).notify


def test_a_recheck_says_what_it_is_rather_than_naming_a_threat():
    """The sentence machinery would render it as a threat, or — with no class
    stated — as a bare "Тривога", which is the opposite of what it means."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (300, "mon1tor_ua", "📡Дорозвідка по ракетах.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
    assert u is not None and "Дорозвідка" in u.text
    assert "Тривога" not in u.text


# --- what the siren was about ----------------------------------------------


def test_the_first_message_naming_a_class_and_a_place_explains_the_siren():
    """The official channel has exactly two forms and neither says why. Rule 12
    silences a city-wide drone outright, which is the commonest cause of all —
    so the alert arrived with no explanation at all."""
    tr = Tracker()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (40, "mon1tor_ua", "⚠️Реактивний шахед на Лук'янівку, Шулявку."),
            (90, "mon1tor_ua", "⚠️Реактивний шахед на Оболонь.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        out.append(d)
    assert out[1].notify and not out[1].audible
    # ...and only the first. The point is an explanation, not a commentary.
    assert out[2].reason != out[1].reason or not out[2].notify


def test_the_remembered_cause_goes_stale():
    """The announcer keeps the cause so the siren can carry it — "Тривога.
    Реактивний шахед. Вишневе." — and it used to live from one full all-clear to
    the next. An hour-old class could therefore explain a fresh siren.

    Note this is not the episode's own class, which also reaches the sentence
    and is legitimately longer-lived: while an episode is open, what it knows is
    flying is current by definition. This is the separate memory that outlived
    everything.
    """
    from tools.policy.announce import PENDING_HORIZON_S, Announcer

    ann = Announcer()
    ann.note(observe(T0, "⚠️2 реактивні шахеди на Вишневе.", False, "mon1tor_ua"))
    assert ann.pending_threat == "shahed-jet"
    ann._forget_if_stale(T0 + PENDING_HORIZON_S - 10)
    assert ann.pending_threat == "shahed-jet"
    ann._forget_if_stale(T0 + PENDING_HORIZON_S + 10)
    assert ann.pending_threat is None and ann.pending_places == []


def test_a_recheck_after_the_threat_came_back_is_news_again():
    """His correction: "кажуть дорозвідка, потім пишуть що виліз там і там, а
    потім можуть знову дорозвідка". Measured — 71 of 165 episodes carry more
    than one, and that exact cycle happens 43 times. Silencing the second one
    would hide the only good news the system ever delivers."""
    tr = Tracker()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (300, "mon1tor_ua", "📡Дорозвідка."),
            (360, "mon1tor_ua", "📡Дорозвідка."),            # a repeat: silent
            (420, "mon1tor_ua", "⚠️Реактивний шахед на Шулявку."),
            (600, "mon1tor_ua", "📡Дорозвідка.")):           # news again
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        out.append(d)
    assert out[1].reason.startswith("recheck")
    assert not out[2].notify
    assert out[3].notify
    assert out[4].reason.startswith("recheck"), out[4].reason


def test_the_retraction_of_a_recheck_is_shown_too():
    """"Або просто кажуть «знову виліз», навіть без місця." Showing the good
    news and not its retraction is the worse of the two silences — and with no
    place named these have no scope, so the geography veto killed every one."""
    tr = Tracker()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (300, "mon1tor_ua", "📡Дорозвідка."),
            (400, "mon1tor_ua", "❗️Виліз ще 1, вже 3 залітають."),
            (600, "mon1tor_ua", "📡Дорозвідка.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        out.append(d)
    assert out[1].reason.startswith("recheck")
    assert out[2].notify and not out[2].audible and out[2].reason == "it is back"
    # ...and the recheck that follows it is news again, not a repeat.
    assert out[3].reason.startswith("recheck")


def test_a_reappearance_with_nothing_to_retract_stays_quiet():
    """Before any recheck was announced, "виліз" is just the wave continuing —
    and the rules that decide whether a wave is worth a sound are the ones
    below, not this one."""
    tr = Tracker()
    tr.official_source = True
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (200, "mon1tor_ua", "❗️Виліз ще 1, вже 3 залітають.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert d.reason != "it is back"


def test_the_explanation_may_name_a_town_outside_the_city():
    """Seen live the first evening this shipped: the siren sounded for Kyiv and
    everything that followed was Вишгород, Хотянівка, Бровари — all oblast, all
    silenced, and he was left with a siren and no reason.

    A threat approaching Kyiv is outside Kyiv until it is not. His reason for
    wanting it: "це мені дає інформацію з якої сторони загроза" — so the place
    name is the content, and the ring filter was dropping exactly it."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (60, "kievinform_ua1", "Знову рБПЛА на Вишгород ⚠️✈️")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
    assert d.reason == "what the siren was about"
    assert d.notify and not d.audible
    assert "Вишгород" in u.text
    assert "реактивний шахед" in u.text.lower()


def test_an_oblast_town_is_still_not_a_wake_up_on_its_own():
    """Widened for the explanation and nowhere else — without a siren to
    explain, Vyshhorod is another district's trouble."""
    tr = Tracker()
    o = observe(T0, "Знову рБПЛА на Вишгород ⚠️✈️", False, "kievinform_ua1")
    d = decide(o, tr)
    assert not d.audible and d.reason != "what the siren was about"


def test_the_siren_does_not_count_as_its_own_explanation():
    """Seen live at 19:38. The siren carries scope `city` from its own text and
    inherits the episode's class, so it satisfied both halves of "something has
    explained this" — the one message in the stream that explains nothing,
    marking the question answered. "1 на Вишгород", twenty-two seconds later,
    then stayed silent."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            # States its own class: with nothing said before the siren there is
            # no episode class to inherit, and a bare "1 на Вишгород" explains
            # nothing on its own.
            (22, "kievinform_ua1", "⚠️Реактивний шахед на Вишгород.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
        out.append((d, u))
    assert out[0][0].audible                      # the siren still rings
    assert out[1][0].reason == "what the siren was about"
    assert "Вишгород" in out[1][1].text


def test_the_explanation_is_dropped_when_the_siren_already_said_it():
    """With a ten-minute memory the siren usually carries the cause itself, and
    the message written to supply it then arrives a second later saying the same
    words. His rule: "глушимо, якщо загроза і місце однакові"."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "mon1tor_ua", "⚠️2 реактивні шахеди на Київ/Вишгород з півночі."),
            (400, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (422, "kievinform_ua1", "1 на Вишгород")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        out.append((d, ann.announce(o, d)))
    assert "Вишгород" in out[1][1].text            # the siren carries it
    assert out[2][1] is None                       # ...so this says nothing


# Verbatim from the night he caught it. Shortened, it stops reading as a
# summary at all, and the test then passes for the wrong reason. Note it
# names Zhuliany and ТЕЦ-5 — a forecast about home is still a forecast.
FORECAST = ('❗️А тепер до поганого, балістика:' + chr(10) + '❗️Цієї ночі висока вірогідність нанесення масованого балістичного удару по Києву:' + chr(10) + '❗️Ворог планує застосувати 34 ракети різних типів, якщо точніше:' + chr(10) + '❗20 балістичних ракет Іскандер-М з Брянської області;' + chr(10) + '⚡️7 Цирконів з Курської області;' + chr(10) + '❗️7 північнокорейських балістичних ракет Кн-23.' + chr(10) + '❗️Підвищена загроза:' + chr(10) + '🔴Жуляни;' + chr(10) + '🔴Оболонь;' + chr(10) + '🔴Дарниця;' + chr(10) + '🔴Почайна;' + chr(10) + '🔴ТЕЦ-5;' + chr(10) + '🔴ТЕЦ-6;' + chr(10) + '🔴Відрадний;' + chr(10) + '🔴Борщагівка;' + chr(10) + '🔴Нивки;' + chr(10) + '🔴Шулявка;' + chr(10) + "🔴Лук'янівка." + chr(10) + '⬆️Чому стільки мікрорайонів на підвищеній небезпеці? Відповідаю, у всіх цих мікрорайонах є складські приміщення/заводи, а як ви бачите — зараз ворога цікавлять тільки складські приміщення, та заводи.')


def test_a_forecast_for_the_night_does_not_become_the_episode_class():
    """The false wake-up he caught. "❗️А тепер до поганого, балістика: цієї ночі
    висока вірогідність..." was correctly silenced as a summary — and still set
    the episode's class to ballistic. Two minutes later a message naming nothing
    inherited it, the ladder read drone → ballistic, and it rang."""
    tr = Tracker()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "mon1tor_ua", "⚠️5 реактивних шахедів з Чернігівщини на Київщину."),
            (60, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (103, "mon1tor_ua", FORECAST),
            (222, "kievinform_ua1", "Найближчий в районі Вишгороду маневрує")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        out.append(d)
    assert not out[2].notify                      # the forecast stays silent
    assert tr.episode.threat != "ballistic"       # ...and leaves no trace
    assert not out[3].audible, out[3].reason


def test_the_ladder_climbs_only_on_a_class_the_message_states():
    """"Найближчий в районі Вишгороду маневрює" names nothing at all. Calling
    that a climb to ballistic is wrong whatever the episode is carrying."""
    tr = Tracker()
    tr.official_source = True
    for off, channel, text in (
            (0, "mon1tor_ua", "‼️Вихід балістики з Брянська"),
            (60, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (300, "kievinform_ua1", "Найближчий в районі Вишгороду маневрує")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
    assert d.reason != "threat level rose"


def test_the_siren_names_one_town_not_a_travelogue():
    """"Тривога. Реактивний шахед. Славутич, Тетіїв, Бровари." went out tonight,
    and Slavutych is 150 km away. Ring names list; towns say which side."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    for off, channel, text in (
            (0, "mon1tor_ua", "3 Реактива повз Славутич в бік Водосховища."),
            (120, "mon1tor_ua", "БпЛА на Тетіїв"),
            (240, "mon1tor_ua", "До 5х реактивів від Славутича на Бровари."),
            (300, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        u = ann.announce(o, d)
    assert u.text.count(",") == 0, u.text
    assert "Славутич" not in u.text


# --- the night of 2026-08-29, eight findings ------------------------------


def _alerted():
    tr = Tracker()
    tr.official_source = True
    o = observe(T0, "🚨 м. Київ" + chr(10) + "Повітряна тривога", False, "alarm_kyiv")
    d = decide(o, tr)
    tr.record(o, d.level, d.alarm, d.reason)
    return tr


def test_clean_and_no_contact_are_rechecks_too():
    """"📡По балістиці станом на зараз чисто." is the answer he waits for through
    a ballistic alert and read as a news summary. "На зараз без фіксації БпЛА✈️"
    went by in silence at 05:08. Measured: 342 and 64 messages in the corpus,
    every one meaning nothing is being tracked."""
    tr = _alerted()
    for text in ("📡По балістиці станом на зараз чисто.",
                 "На зараз без фіксації БпЛА✈️"):
        o = observe(T0 + 300, text, False, "mon1tor_ua")
        d = decide(o, tr)
        assert d.notify and not d.audible, text
        assert d.reason.startswith("recheck"), (text, d.reason)


def test_a_recheck_needs_an_alert_not_merely_an_episode():
    """"Дорозвідка по БпЛА по областях" arrived at 06:19, forty-six minutes
    after the all-clear, into an episode passing traffic had reopened — and
    announced that a threat already called off was probably destroyed."""
    tr = Tracker()
    tr.official_source = True
    o = observe(T0, "⚠️Реактивний шахед на Бровари.", False, "mon1tor_ua")
    d = decide(o, tr)
    tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
              d.reason)
    assert tr.episode is not None and not tr.episode.alert_announced
    d = decide(observe(T0 + 60, "Дорозвідка по БпЛА по областях.", False,
                       "mon1tor_ua"), tr)
    assert not d.notify


def test_commentary_about_ballistics_is_not_a_ballistic_report():
    """"Поки чекаємо, розпишу нічні плани: по балістиці 🔴" rang at 00:32 on
    nothing but the word — no count, no place, no movement, no phase word."""
    tr = _alerted()
    d = decide(observe(T0 + 300, "Поки чекаємо, розпишу нічні плани: по балістиці 🔴"
                       + chr(10) + "Тушок не буде.", False, "mon1tor_ua"), tr)
    assert not d.audible, d.reason


def test_good_news_from_across_the_border_does_not_ring():
    """"По балістиці — над Брянською областю (рф) дуже багато наших БпЛА, ворог
    може не ризикувати" is good news about somewhere else. Geography is ignored
    for Ukrainian districts, not for Russia — a launch from there still rings."""
    tr = _alerted()
    d = decide(observe(T0 + 300, "По балістиці — над Брянською областю (рф) дуже "
                       "багато наших БпЛА, ворог може не ризикувати.", False,
                       "mon1tor_ua"), tr)
    assert not d.audible, d.reason
    tr2 = _alerted()
    d2 = decide(observe(T0 + 300, "‼️ Вихід балістики з Брянська", False,
                        "mon1tor_ua"), tr2)
    assert d2.audible


def test_the_same_silent_line_twice_in_seconds_is_one_line():
    """"Вишневе - увага." at 04:55:28 and "Вишневе!" at 04:55:35."""
    tr = _alerted()
    out = []
    for off, text in ((300, "Вишневе - увага."), (307, "Вишневе!")):
        o = observe(T0 + off, text, False, "kievinform_ua1")
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        out.append(d)
    assert out[0].notify and not out[0].audible
    assert not out[1].notify


def test_a_ballistic_launch_gets_a_destination_later():
    """A launch names where it came from, never where it is going. "Балістична
    ракета повз Полтаву на Дніпро/Кам'янське" was silenced as another region's
    business, so the answer to "is it coming here" never arrived."""
    from tools.policy.announce import Announcer

    tr, ann = _alerted(), Announcer()
    said = []
    for off, text in (
            (60, "❗️❗Є інформація про пуск балістичної ракети з Курської області."),
            (150, "❗Балістична ракета повз Полтаву на Дніпро/Кам'янське.")):
        o = observe(T0 + off, text, False, "mon1tor_ua")
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        said.append((d, ann.announce(o, d)))
    assert said[0][0].audible
    assert said[1][0].reason == "where the ballistic is going"
    assert not said[1][0].audible
    assert "Дніпропетровщина" in said[1][1].text or "Полтавщина" in said[1][1].text


def test_a_strike_that_landed_does_not_become_the_sirens_place():
    """"💥Влучання реактивного шахеду було у Труханів острів" at 23:14 put
    Trukhaniv into the memory, and the siren ten minutes later opened with it —
    pointing him at a place the threat had already left."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    for off, channel, text in (
            (0, "kievinform_ua1", "💥Влучання реактивного шахеду було у Труханів острів."),
            (600, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        u = ann.announce(o, d)
    assert "Труханів" not in u.text


def test_cruise_rings_on_the_oblast_before_it_rings_on_the_city():
    """Waking only when they reach the city is late — "якщо вона коли ракети
    залітають у місто, то це пізнувато". Where the channels report the oblast
    first that is a median of six minutes of warning, p90 sixteen."""
    tr = _alerted()
    out = []
    for off, text in ((60, "❗️Крилата ракета залітає у Бровари."),
                      (120, "❗️Крилата ракета залітає у Бровари."),
                      (400, "🔴Крилата ракета на Київ.")):
        o = observe(T0 + off, text, False, "mon1tor_ua")
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        out.append(d)
    assert out[0].audible             # the oblast rung, whichever rule rings it
    assert not out[1].notify          # one ring per rung, not per town
    assert out[2].audible             # ...and again when it reaches the city


def test_a_bare_rocket_during_a_ballistic_wave_is_that_wave():
    """`\bракет` is the last rule in the list, there because the specific names
    failed. In the labelled night mon1tor_ua wrote "❗Балістична ракета на Київ."
    and kievinform_ua1 wrote "РАКЕТА НА КИЇВ" two seconds later; the second read
    as cruise, escaped the ballistic dedup and rang again for the same missile.

    And the class the decision was made on is what the episode stores — storing
    the word instead turned a whole ballistic wave into a cruise one."""
    tr = Tracker()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (22, "war_monitor", "☄ Вихід у напрямку Києва"),
            (29, "mon1tor_ua", "❗Балістична ракета на Київ."),
            (31, "kievinform_ua1", "РАКЕТА НА КИЇВ"),
            (33, "kievinform_ua1", "Святошин!!")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        out.append((o, d))
    assert out[3][0].effective_threat == "ballistic"
    assert not out[3][1].audible                 # the same missile, not a new one
    assert tr.episode.threat == "ballistic"      # ...and the wave stays ballistic
    assert out[4][0].effective_threat == "ballistic"


def test_a_risk_level_is_not_an_event():
    """"Біла Церква — підвищена загроза масованого ракетного удару" read as a
    confirmed cruise report. His words: "це не про загрозу в моменті"."""
    o = observe(T0, "❗️Біла Церква — підвищена загроза масованого ракетного удару.",
                False, "mon1tor_ua")
    assert o.certainty == "probable"


def test_a_drone_over_his_own_place_rings_even_soon_after_the_siren():
    """The failure he caught live on 2026-08-30. A drone crossed Kyiv, the
    channels named Zhuliany at 11:17:28, and nothing rang.

    Two gates, each of which silenced it on its own.

    The city's siren at 11:13:37 had started the five-minute near refractory,
    inside which only a message explicitly announcing a new target breaks
    through -- and "Борщагівки, Жуляни - в укриття!" does not announce one. But
    the siren said nothing about his ring; it must not silence the one word that
    is the whole reason a drone rings at all.

    And "Жуляни/ Вишневе до вас йде", five seconds earlier, was dismissed as
    non-threat -- and still stamped Zhuliany into the "already seen" memory. The
    message that said nothing silenced the one that did.
    """
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    out = []
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (195, "mon1tor_ua", "⚠️Реактивний шахед з Шулявки на Відрадний, Борщагівки."),
            (226, "kievinform_ua1", "Жуляни/ Вишневе до вас йде"),
            (231, "kievinform_ua1", "Борщагівки, Жуляни - в укриття!"),
            (242, "kievinform_ua1", "Київ:" + chr(10) + "🅿️ 1х далі Жуляни / Вишневе")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        out.append((d, ann.announce(o, d)))
    assert out[1][0].notify and not out[1][0].audible   # Borshchahivka: shown
    assert out[3][0].audible, out[3][0].reason          # Zhuliany: heard
    assert "Жуляни" in out[3][1].text
    # ...and then deduped. This used to be shown on the status line without a
    # second sound; since 2026-09-01 it is not shown either, because eleven
    # seconds after the bell it is the same drone reaching a second channel --
    # "глуши повтор", after a live one arrived six seconds behind its own bell as
    # a message whose entire text was the word "Жуляни".
    #
    # The window is fifteen seconds. A repeat outside it still appears, which is
    # what keeps the 2026-08-31 case working: the drone left towards Boiarka and
    # came back ten minutes later, and that rings.
    assert not out[4][0].notify, out[4][0].reason


def test_a_message_that_said_nothing_leaves_no_trace_in_the_ring_memory():
    tr = Tracker()
    tr.official_source = True
    o = observe(T0, "Жуляни/ Вишневе до вас йде", False, "kievinform_ua1")
    d = decide(o, tr)
    assert o.modality == "non-threat"
    tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
              d.reason)
    assert tr.episode is None or "Жуляни" not in tr.episode.ring_seen


def test_the_explanation_does_not_name_kyiv_back_at_him():
    """"Загроза: реактивний шахед. Вишгород, Київ, Київщина." — of the three
    only the first says anything when the alert is already about Kyiv."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (34, "mon1tor_ua", "Київщина:" + chr(10) + "🅿️2х реактиви на Київ повз Вишгород")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        u = ann.announce(o, d)
    assert "Вишгород" in u.text
    assert "Київщина" not in u.text and "Київ." not in u.text


def test_a_climb_says_where_it_is_climbing_from():
    """Cruise will usually be flying inside an alert that drones started, so the
    ring that matters is the one when they reach the oblast — and it was saying
    "Загроза: крилаті ракети." and nothing else. The place is the content: "це
    мені дає інформацію з якої сторони загроза"."""
    from tools.policy.announce import Announcer

    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    said = []
    for off, channel, text in (
            (0, "mon1tor_ua", "⚠️5 реактивних шахедів з Чернігівщини на Київщину."),
            (60, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            # The second line is what makes it ours; without it the message is
            # about Sumshchyna and is correctly none of our business.
            (600, "mon1tor_ua", "❗️ 3 групи КР від Конотопа у напрямку Ніжина."
                                + chr(10) + "Далі рух на Київщину."),
            (1200, "mon1tor_ua", "🔴2 ракети бандероль на Оболонський район Києва.")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        said.append((d, ann.announce(o, d)))
    assert said[2][0].audible and "Конотоп" in said[2][1].text
    assert said[3][0].audible and "Оболонський" in said[3][1].text


def test_a_partial_all_clear_after_the_full_one_is_not_news():
    """"💥Реактивний шахед було збито, у Києві відбій по шахедах" arrived 102
    seconds after the official all-clear and rang — announcing the lifting of a
    threat that had already been called off in full.

    The test is "did we say anything in this episode", not "was a siren
    declared": a MiG takeoff rings without a siren, and its "Відбій загрози
    МіГ-31К" twenty minutes later is a real partial all-clear."""
    tr = Tracker()
    tr.official_source = True
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (600, "alarm_kyiv", "🟢 м. Київ" + chr(10) + "Відбій повітряної тривоги"),
            (702, "kievinform_ua1",
             "💥Реактивний шахед було збито, у Києві відбій по шахедах")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
    assert not d.audible, d.reason


def test_a_readiness_report_is_not_a_takeoff():
    """"Загалом до атаки готові 6 Ту-95мс та 7 Ту-160" rang as a MiG takeoff
    because it names the aircraft — no count, no place, no movement, no phase
    word. The third rule today to need the same guard, after ballistic and the
    climb."""
    tr = Tracker()
    tr.official_source = True
    d = decide(observe(T0, "Загалом до атаки готові 6 Ту-95мс та 7 Ту-160 "
                       "на аеродромах базування.", False, "mon1tor_ua"), tr)
    assert not d.audible, d.reason
    tr2 = Tracker()
    tr2.official_source = True
    d2 = decide(observe(T0, "❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка.",
                        False, "mon1tor_ua"), tr2)
    assert d2.audible and d2.alarm == "mig"


def test_the_ladder_does_not_climb_on_a_resolution():
    """"186 цілей були збиті/пригнічені цієї ночі" reads as `clear` and still
    rang: the ladder never asked about certainty. `lost` is the same shape —
    losing track of something is not an escalation."""
    tr = _alerted()
    d = decide(observe(T0 + 300, "❗️186 цілей були збиті/пригнічені цієї ночі."
                       + chr(10) + "▪️2 «Бандероль»", False, "war_monitor"), tr)
    assert not d.audible, d.reason


def test_home_named_again_rings_after_ten_minutes_and_not_before():
    """His call: twenty minutes was too long to stay quiet about Zhuliany even
    for the same drone. The two data points in his own labels sit either side of
    ten -- a repeat at 9 minutes he marked silent, one at 29 he marked a wake-up.

    Inside the window it is still shown, just without a sound."""
    from tools.policy.episodes import RING_MEMORY_S

    assert RING_MEMORY_S == 10 * 60

    def repeat_after(gap):
        tr = Tracker()
        tr.official_source = True
        out = []
        for off, text in ((0, "⚠️Реактивний шахед на Жуляни, Борщагівку."),
                          (gap, "⚠️Реактивний з ТЕЦ-5 на Жуляни.")):
            o = observe(T0 + off, text, False, "kievinform_ua1")
            d = decide(o, tr)
            tr.record(o, d.level if d.notify else None,
                      d.alarm if d.notify else None, d.reason)
            out.append(d)
        return out

    early = repeat_after(9 * 60)
    assert early[0].audible
    assert early[1].notify and not early[1].audible      # shown, not heard

    late = repeat_after(11 * 60)
    assert late[1].audible, late[1].reason               # the window has passed


def test_a_recheck_closes_the_wave_and_the_next_launch_is_new():
    """From the ballistic night of 2026-09-01. A recheck at 02:25 was followed
    by Tsirkon launches a minute later and every one was silenced as "the same
    wave" -- three of his findings that night are this one fault: the launches
    went unheard, the next recheck counted as a repeat, and the destination that
    arrived later was never shown.

    "Дорозвідка каже, що все вже ок, а насправді не ок і про це треба
    повідомити."
    """
    tr = _alerted()
    out = []
    for off, text in (
            (60, "‼️ Вихід балістики з Брянська"),
            (300, "📡Локаційно по балістиці чисто."),
            (389, "❗6-8 Цирконів на Київ, Бровари."),
            (400, "‼️ Київ — спуск балістики! Дев'ята"),
            (700, "📡По балістиці чисто.")):
        o = observe(T0 + off, text, False, "war_monitor")
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        out.append(d)
    assert out[0].audible                       # the launch
    assert out[1].reason.startswith("recheck")  # the wave is declared over
    assert out[2].audible, out[2].reason        # a new type, so a new wave
    # ...and the count-off that follows is not a third wave. The channels count
    # missiles across waves: "хвилі можуть бути різні, але канали рахують ракети
    # загалом".
    assert not out[3].audible, out[3].reason
    assert out[4].reason.startswith("recheck")  # ...and this recheck is news


def test_any_ballistic_launch_after_a_recheck_rings():
    """His correction after seeing the narrower version: "мені треба нотифікація
    на будь-який пуск балістики після дорозвідки: пуск без місця куди, або пуск
    по Києву."

    A descent is not a launch. "спуск балістики! Дев'ята" is the ninth missile
    arriving, and treating it as a launch rang for every count-off."""
    def wave(second):
        tr = _alerted()
        out = []
        for off, text in ((60, "‼️ Вихід балістики з Брянська"),
                          (300, "📡Локаційно по балістиці чисто."),
                          (400, second)):
            o = observe(T0 + off, text, False, "war_monitor")
            d = decide(o, tr)
            tr.record(o, d.level if d.notify else None,
                      d.alarm if d.notify else None, d.reason)
            out.append(d)
        return out[2]

    # No destination stated: nobody yet knows whether it is ours.
    assert wave("❗️❗️❗️Пуски балістичних ракет з Брянської області.").audible
    # Or a launch toward Kyiv.
    assert wave("❗️Пуск балістики по Києву.").audible
    # ...but an arrival count-off is not a launch.
    assert not wave("‼️Київ / Бровари — спуск балістики! Дев'ята").audible
    # ...and neither is a possibility.
    assert not wave("🔴Можливий повторний пуск 2-4х балістичних ракет по Києву.").audible


def test_the_wave_says_where_it_is_without_ringing_again():
    """His ask after the ballistic night: "кожен «Київ спуск балістики» під час
    балістичної тривоги можна б писати хоча б тихим... під час балістики краще
    часто оновлювати актуальною інформацією."

    A destruction near home is not a threat either -- "Знищено в районі Жулян 💥"
    came out as "Загроза: реактивний шахед. Жуляни.", the best news of the night
    announced as the worst."""
    from tools.policy.announce import Announcer

    tr, ann = _alerted(), Announcer()
    said = []
    for off, text in ((60, "‼️ Вихід балістики з Брянська"),
                      (120, "‼️ Київ — спуск балістики!"),
                      (200, "Вишневе🚀"),
                      (400, "Знищено в районі Жулян 💥")):
        o = observe(T0 + off, text, False, "war_monitor")
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None,
                  d.reason)
        said.append((d, ann.announce(o, d)))
    assert said[0][0].audible
    assert said[1][0].notify and not said[1][0].audible
    assert said[2][0].notify and not said[2][0].audible
    assert "Вишневе" in said[2][1].text
    assert said[3][1] is not None and said[3][1].text.startswith("Збито")


def test_a_repeat_over_home_is_shown_once_the_echo_window_has_passed():
    """The other side of "глуши повтор", and the reason the window is short.

    Six such repeats sit in the live log at 6, 43, 60, 60, 120 and 280 seconds
    behind their bell. Only the first is an echo; by forty seconds a second
    channel naming his street again is telling him it is still over him.
    """
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    def play(gap: int):
        tr = Tracker()
        tr.official_source = True
        for off, text in ((0, "⚠️Реактивний шахед з Шулявки на Жуляни."),
                          (gap, "Жуляни")):
            o = observe(T0 + off, text, False, "mon1tor_ua")
            d = decide(o, tr)
            tr.record(o, d.level if d.notify else None,
                      d.alarm if d.notify else None, d.reason)
        return d

    assert play(6).notify is False              # echo from a second channel
    assert play(45).notify is True              # still over you
    assert play(45).audible is False            # ...but no second sound


def test_a_remembered_place_ages_on_its_own_clock():
    """His question found this: "звідки пост про тривогу його взяв? Якщо з
    якогось попереднього поста, то наскільки він був старший."

    Live on 2026-09-01: the siren at 20:43:57 came out as "Тривога. Реактивний
    шахед. Святопетрівське." and that village was last mentioned at 20:32:48 --
    eleven minutes earlier, 8.5 km west, while the night's drones were crossing
    the left bank.

    The horizon existed and was ten minutes. It did nothing, because a single
    `pending_at` was refreshed by *any* live message, so it measured time since
    anything happened rather than time since this name was seen -- and on a busy
    night something happens every few seconds.
    """
    from tools.policy.announce import PENDING_HORIZON_S, Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    def play(gap: int, chatter: bool):
        tr, ann = Tracker(), Announcer()
        tr.official_source = True
        said = None
        steps = [(0, "mon1tor_ua", "⚠️Реактивний шахед на Святопетрівське.")]
        if chatter:
            # Exactly what kept the old memory alive: unrelated live traffic,
            # naming nothing near him, every couple of minutes.
            steps += [(t, "mon1tor_ua", "⚠️Реактивний шахед на Дарницю.")
                      for t in range(120, gap, 120)]
        steps.append((gap, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"))
        for off, channel, text in steps:
            o = observe(T0 + off, text, False, channel)
            d = decide(o, tr)
            tr.record(o, d.level if d.notify else None,
                      d.alarm if d.notify else None, d.reason)
            u = ann.announce(o, d)
            if o.alert_state == "alert" and u:
                said = u.text
        return said or ""

    inside = PENDING_HORIZON_S - 120
    outside = PENDING_HORIZON_S + 120
    assert "Святопетрівське" in play(inside, chatter=False)
    assert "Святопетрівське" not in play(outside, chatter=False)
    # ...and the chatter must not keep it alive, which is the whole defect.
    assert "Святопетрівське" not in play(outside, chatter=True)


def test_a_ring_name_used_as_an_origin_is_not_where_it_is():
    """Live on 2026-09-01: "⚠️З Республіки на Вишневе, Чабани." came out as
    "Вишневе, Республіка, Чабани" -- and Республіка is 2.2 km from home, so the
    sentence put a threat on his doorstep while the drone was heading away from
    it. `ring_places` asks which names are in the ring and never what the
    sentence does with them; `heading()` has always known, through the
    prepositions.

    Three limits, and each came from a question of his rather than from me.

    A *distant* origin is the content, not noise: "3 групи КР від Конотопа у
    напрямку Ніжина" is how he learns which side it is coming from, and two older
    tests said so before this rule did.

    The origin is kept when it is the only ring name left -- "а якщо початок у
    моєму колі?" -- because dropping it loses the one fact the sentence exists
    for.

    And his own street is never dropped at all, which is an older ruling of his:
    "тільки що було new target near me, але в повідомленні не було Жуляни".
    """
    from tools.policy.announce import Announcer
    from tools.policy.config import load as load_config
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    cfg = load_config(warn=lambda _m: None)

    def say(text: str) -> str:
        tr, ann = Tracker(config=cfg), Announcer(config=cfg)
        tr.official_source = True
        for off, line in ((0, "⚠️Реактивний шахед на Київ."), (120, text)):
            o = observe(off, line, False, "mon1tor_ua", config=cfg)
            d = decide(o, tr)
            tr.record(o, d.level if d.notify else None,
                      d.alarm if d.notify else None, d.reason)
            said = ann.announce(o, d)
        return said.text if said else ""

    # The origin goes, because two ring destinations remain.
    out = say("⚠️З Республіки на Вишневе, Чабани.")
    assert "Республіка" not in out and "Вишневе" in out

    # It stays when it is the only ring name in the sentence.
    assert "Вишневе" in say("⚠️З Вишневого на Боярку.")

    # ...and home stays whatever role it is given.
    assert "Жуляни" in say("⚠️Шахед з Жуляни на Борщагівку.")
    assert "Жуляни" in say("⚠️Реактивний шахед з Жуляни на Центр.")


def test_ballistic_says_nothing_while_kyiv_has_no_alert():
    """His call after 02:27 on 2026-09-02: a launch from Crimea aimed at Odesa
    woke him with no Kyiv siren anywhere. "Мабуть таке краще не показувати, коли
    немає тривоги в Києві."

    Measured before switching it on. Of 268 ballistic bells in the corpus, 214
    were already inside an alert. Of the 54 outside, 40 were never followed by
    one -- 26 of those are news and chatter, including a thank-you for a
    donation, 6 are missiles aimed at Odesa or Rzhyshchiv, and 8 are genuine
    launches with no stated target. The remaining 14 led the siren by a median of
    one minute, and the siren rings for itself.
    """
    from tools.policy.announce import Announcer
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    launch = "❗️❗Є інформація про пуск балістичної ракети з Криму."

    tr = Tracker()
    tr.official_source = True
    o = observe(T0, launch, False, "mon1tor_ua")
    quiet = decide(o, tr)
    assert not quiet.notify, quiet.reason

    # ...and with the siren on, it rings exactly as before.
    tr, ann = Tracker(), Announcer()
    tr.official_source = True
    for off, channel, text in (
            (0, "alarm_kyiv", "🚨 м. Київ" + chr(10) + "Повітряна тривога"),
            (60, "mon1tor_ua", launch)):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None,
                  d.alarm if d.notify else None, d.reason)
    assert d.audible and d.alarm == "ballistic", d.reason


def test_the_alert_requirement_does_not_silence_a_stream_without_the_official_channel():
    """`official_alert` is only ever set by the channel that declares. Watching
    the chats alone, requiring it would silence every ballistic there is."""
    from tools.policy.episodes import Tracker, observe
    from tools.policy.rules import decide

    tr = Tracker()
    tr.official_source = False
    o = observe(T0, "❗️❗Є інформація про пуск балістичної ракети з Криму.",
                False, "mon1tor_ua")
    assert decide(o, tr).audible
