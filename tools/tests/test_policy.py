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
                               (400, "kievinform_ua1", "Жуляни🚀")):
        o = observe(T0 + off, text, False, channel)
        d = decide(o, tr)
        tr.record(o, d.level if d.notify else None, d.alarm if d.notify else None)
        got.append((d.audible, d.reason))
    assert got[1][0], got                      # the launch rings
    assert not got[2][0], got                  # ...the position after it does not

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
