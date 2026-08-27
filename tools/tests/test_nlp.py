"""Gazetteer and hint tests, using real message text from the corpus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.nlp import hints
from tools.nlp.gazetteer import (
    find_infrastructure,
    find_places,
    is_relevant,
    resolve_scope,
)


# --- gazetteer: morphology -------------------------------------------------


def test_matches_across_case_endings():
    for form in ("Київщину", "Київщини", "Київщина", "Київщині", "Київщиною"):
        assert resolve_scope(f"Шахед на {form}") == "oblast", form


def test_matches_across_capitalisation():
    assert resolve_scope("КИЇВ") == "city"
    assert resolve_scope("ТРОЄЩИНА") == "city"


def test_matches_slang_forms():
    assert resolve_scope("1х Борщаги") == "my-area"
    assert resolve_scope("1х Солома/Центр") == "my-area"
    assert resolve_scope("Через Трою на Труханів") == "city"


def test_matches_through_trailing_punctuation():
    assert resolve_scope("1х Жуляни.") == "my-area"
    assert resolve_scope("Дарниця, Чоколівка") == "city"


def test_informal_masyv_areas_resolve():
    assert resolve_scope("⚠️Ще 1 реактивний шахед на Лівобережний масив") == "city"
    assert resolve_scope("Мінський масив") == "city"


# --- gazetteer: tier resolution ------------------------------------------


def test_nearest_tier_wins():
    """A message naming both my area and a far one is about my area."""
    assert resolve_scope("1х Жуляни / 2х Велика Димерка") == "my-area"
    assert resolve_scope("Реактивний БпЛА курсом на Троєщину / на Боярку") == "city"


def test_kyiv_dnipro_district_is_not_the_city_of_dnipro():
    assert resolve_scope("1х Дніпровський район") == "city"
    assert resolve_scope("💥Вибух у Дніпрі") == "elsewhere"


def test_other_regions_are_elsewhere():
    assert resolve_scope("5-7 Чернігівщина.") == "elsewhere"
    assert resolve_scope("💥Вибух в Одесі, попередньо ракета Іскандер-М.") == "elsewhere"


def test_no_place_is_unknown():
    assert resolve_scope("Збито") == "unknown"
    assert resolve_scope("") == "unknown"


def test_relevance_filter_keeps_kyiv_and_oblast():
    assert is_relevant("1х Жуляни")
    assert is_relevant("Курсом на Бровари")
    assert is_relevant("⚠️3 реактивні шахеди на Київ.")


def test_relevance_filter_drops_other_regions_and_placeless():
    assert not is_relevant("5-7 Чернігівщина.")
    assert not is_relevant("⚡ Нафтовий термінал у Санкт-Петербурзі")
    assert not is_relevant("Дякую за підтримку")


def test_find_places_deduplicates():
    names = [p.name for p in find_places("Жуляни, Жулянами, Жулян")]
    assert names == ["Жуляни"]


def test_infrastructure_is_detected():
    assert find_infrastructure("Вишгород/ТЕЦ-6 увага!!") == ["ТЕЦ"]
    assert find_infrastructure("1х Жуляни") == []


# --- threat hints ---------------------------------------------------------


def test_jet_shahed_is_not_a_plain_shahed():
    assert hints.threat_hint("⚠️Реактивний шахед над Жулянами.") == "shahed-jet"
    assert hints.threat_hint("⚠️1 шахед на Білу Церкву.") == "shahed"


def test_ballistic_family():
    for t in ("Балістична ракета на Київ", "Іскандер-М", "Пуск Кинджалу з МіГ-31К",
              "2х Циркони", "застосування БРСД"):
        assert hints.threat_hint(t) == "ballistic", t


def test_cruise_family():
    for t in ("❗Група ракет Калібр на Київ.", "1х Бандероль на Жуляни",
              "Крилата ракета", "Х-101"):
        assert hints.threat_hint(t) == "cruise", t


def test_bare_rocket_falls_back_to_cruise_not_ballistic():
    """Specific names are checked first; a bare "ракета" must not be read as
    ballistic, because that would escalate every unnamed target."""
    assert hints.threat_hint("2х ракети") == "cruise"


def test_recon_and_aviation():
    assert hints.threat_hint("📡Дорозвідка розвідувальним БпЛА") == "recon"
    assert hints.threat_hint("✈️ Активність тактичної авіації") == "aviation"


def test_no_threat_words_means_none():
    assert hints.threat_hint("Дякую вам за підтримку") == "none"


def test_alarm_mapping_gives_each_reaction_class_its_own_sound():
    assert hints.alarm_for("ballistic") == "ballistic"
    assert hints.alarm_for("mig") == "mig"
    assert hints.alarm_for("cruise") == "cruise"
    assert hints.alarm_for("kab") == "cruise"
    assert hints.alarm_for("shahed-jet") == "drone-jet"
    assert hints.alarm_for("shahed") == "drone"
    assert hints.alarm_for("recon") == "recon"


def test_other_aviation_has_no_sound():
    """A bomber takeoff needs no reaction — the alert comes with the cruise
    missiles it launches, and those are their own class. An audible channel for
    it would only train the user to ignore the app."""
    assert hints.alarm_for("aviation") == "none"


# --- live shape -----------------------------------------------------------


def test_telegraphic_messages_read_as_live():
    """The finding that forced structural detection: no alarm words at all."""
    for t in ("1х Центр. / 1х Троєщина.", "1х Борщагівки. / 1х Бровари.",
              "⚠️Реактивний шахед над Жулянами.",
              "🅿️ 1х реактив Жуляни далі Центр."):
        assert hints.looks_live(t), t


def test_count_marker_is_recognised():
    assert "count-marker" in hints.live_shapes("2х БпЛА над Києвом")


def test_movement_is_recognised():
    assert "movement" in hints.live_shapes("⚠️Продовжує рух на Центр, Печерськ.")


def test_social_text_is_not_live():
    assert not hints.looks_live("Дуже вам вдячний за підтримку")


# --- modality -------------------------------------------------------------


def test_aftermath_is_detected():
    t = ("У Голосіївському районі фіксується загоряння автомобіля внаслідок "
         "ворожої атаки. Пожежу ліквідовано.")
    assert hints.modality_hint(t) == "aftermath"


def test_impact_report_is_live_not_aftermath():
    """The measured boundary: 88% of "вибух" messages land within ten minutes
    of a live threat, so demoting them would silence the app at peak danger."""
    t = "💥Вибухи у Дніпрі, над містом чисто. / ⚠️Але на місто летить ще 1 шахед."
    assert hints.modality_hint(t) == "live-threat"
    assert hints.modality_hint("💥Влучання в Дарниці") == "live-threat"


def test_nightly_summary_is_not_a_live_threat():
    t = "❗️Ворог запустив по території України 100 шахедів протягом ночі"
    assert hints.modality_hint(t) == "summary-news"


def test_social_content_is_not_a_threat():
    assert hints.modality_hint("Актуальна ставка — 100 грн. Щоб перебити задонатьте") == "non-threat"


def test_telegraphic_threat_is_live():
    assert hints.modality_hint("1х Жуляни") == "live-threat"


# --- certainty ------------------------------------------------------------


def test_lost_never_collapses_into_clear():
    assert hints.certainty_hint("📡Локаційно втрачено над Києвом.") == "lost"
    assert hints.certainty_hint("без фіксації ✈️") == "lost"
    assert hints.certainty_hint("📡дорозвідка.") == "lost"


def test_clear_is_detected():
    # "локаційно чисто" is radar showing nothing — genuinely clear, unlike
    # "локаційно втрачено", which means we stopped being able to see it.
    assert hints.certainty_hint("📡локаційно чисто.") == "clear"
    assert hints.certainty_hint("💥збито.") == "clear"
    assert hints.certainty_hint("Київ чисто.") == "clear"


def test_probable_when_hedged():
    assert hints.certainty_hint("попередньо ракета Іскандер-М") == "probable"


def test_suggest_returns_the_full_prefill():
    s = hints.suggest("⚠️Реактивний шахед курсом на Жуляни.")
    assert s["threat"] == "shahed-jet"
    assert s["alarm"] == "drone-jet"
    assert s["modality"] == "live-threat"
    assert s["shapes"]


# --- bare toponym lists ---------------------------------------------------


def test_bare_place_lists_are_live():
    """kievinform_ua1's house style: place names and an emoji, nothing else."""
    for t in ("Жуляни ✈️", "Борщагівка ✈️", "Дарниця, Чоколівка",
              "Воскресенка, ДВРЗ ⚠️", "Іподром, Теремки, Жуляни",
              "КРЮКІВЩИНА", "Вишневе", "Деміївка, Печерськ ⚠️",
              "Погреби, Зазим'я — уважно.", "Теремки/Жуляни уважно"):
        assert hints.is_bare_place_list(t), t
        assert hints.modality_hint(t) == "live-threat", t


def test_prose_mentioning_a_place_is_not_a_bare_list():
    for t in ("У Голосіївському районі фіксується загоряння автомобіля внаслідок "
              "ворожої атаки. Пожежу ліквідовано.",
              "Перехоплення реактивного шахеду в рази складніше ніж звичайного",
              "У Києві вже четвертий день поспіль люди вийшли на мітинг",
              "26 квітня 1986 року - день найбільшої катастрофи в історії"):
        assert not hints.is_bare_place_list(t), t


def test_text_without_any_place_is_not_a_bare_list():
    assert not hints.is_bare_place_list("Збито")
    assert not hints.is_bare_place_list("")
    assert not hints.is_bare_place_list("Дякую за підтримку")


def test_bare_place_list_gets_unknown_threat_not_none():
    """"Nothing is flying" and "we are not told what" are different."""
    s = hints.suggest("Жуляни ✈️")
    assert s["threat"] == "unknown"
    assert s["modality"] == "live-threat"
    assert "bare-place-list" in s["shapes"]


def test_aftermath_still_wins_over_bare_place_detection():
    t = "У Дарницькому районі сталося загоряння складського приміщення."
    assert hints.modality_hint(t) == "aftermath"


# --- gaps found by validating against the whole corpus ---------------------


def test_kr_abbreviation_is_a_cruise_missile():
    """The channels abbreviate крилата ракета as КР; missing it filed 
    "1 КР від Крушинки на Вишневе" as non-threat."""
    assert hints.threat_hint("1 КР від Крушинки на Вишневе Борщагівки") == "cruise"
    assert hints.threat_hint("❗Група КР Калібр на Київ.") == "cruise"


def test_place_to_place_movement_needs_no_threat_word():
    for t in ("⚠️З Теремки на Віта-Литовська.",
              "⚠️З Вишневого на Боярку, Калинівка, Глеваха.",
              "⚠️З ТЕЦ-5 на Деміївку."):
        assert "place-to-place" in hints.live_shapes(t), t
        assert hints.modality_hint(t) == "live-threat", t


def test_movement_verbs_from_the_corpus():
    for t in ("Ще одна в бік Вишневого.",
              "❗Падає на Лук'янівку/Центр/Солом'янку.",
              "❗❗Перелетіли на правий берег, Центр, Борщагівка",
              "2х вертаються на Погреби/Трою.",
              "2х подовжують намотувати кола над Києвом."):
        assert hints.looks_live(t), t


def test_shelter_wording_variants():
    assert hints.looks_live("Жуляни в укритті")
    assert hints.looks_live("київ в укриття!!")


def test_banks_of_the_dnipro_are_places():
    assert resolve_scope("❗❗Перелетіли на правий берег") == "city"
    assert resolve_scope("⚠️На правий берег Києва, йде на зниження!") == "city"


def test_fundraising_is_not_strike_aftermath():
    """A donation drive mentioning wounded soldiers contains "постраждал" and
    would otherwise be filed as aftermath of a strike."""
    t = ("Друзі, ми закрили збір від фонду на комплексну реабілітацію "
         "100 бійців, серед них є постраждалі")
    assert hints.modality_hint(t) == "non-threat"


def test_civil_news_is_not_strike_aftermath():
    assert hints.modality_hint("😳🚘 Момент ДТП на Ірпінській кільцевій: є постраждалі") == "non-threat"


def test_real_strike_aftermath_still_classifies_as_aftermath():
    for t in ("У Голосіївському районі, внаслідок падіння уламків БпЛА, "
              "в 16-поверховому житловому будинку вибиті вікна",
              "❗️На Вишгородщині внаслідок нічної атаки сталося загоряння "
              "лісового настилу, яке оперативно ліквідували рятувальники"):
        assert hints.modality_hint(t) == "aftermath", t


def test_marker_emoji_with_a_place_is_live():
    """A report survives an unknown toponym or a typo when the emoji carries
    the predicate — "Жушяни/Вишневе🚀" is a misspelling of Zhuliany."""
    for t in ("⚠️Солом'янка, Центр, Клов, Печерськ.", "Жушяни/Вишневе🚀",
              "⚠️ Деміївка, Голосіїв, Печерськ, ТЕЦ-5.", "Теремки, Жуляни ⚠️🚀"):
        assert "emoji-with-place" in hints.live_shapes(t), t
        assert hints.modality_hint(t) == "live-threat", t


def test_marker_emoji_without_a_place_is_not_enough():
    assert "emoji-with-place" not in hints.live_shapes("⚠️ Увага, друзі")


def test_unrelated_emoji_do_not_signal_a_threat():
    assert not hints.has_marker_emoji("😳🚘 Момент ДТП")
    assert not hints.has_marker_emoji("Дякую ❤️")


def test_emoji_shape_does_not_override_aftermath():
    t = ("❗️У Броварському районі під час ворожої атаки постраждав чоловік — "
         "він отримав уламкові поранення")
    assert hints.modality_hint(t) == "aftermath"


# --- signal strength ------------------------------------------------------


def test_text_evidence_is_strong():
    for t in ("1х Жуляни", "⚠️Реактивний шахед курсом на Жуляни.",
              "Дарниця, Чоколівка", "⚠️З Теремки на Віта-Литовська."):
        assert hints.live_strength(t) == "strong", t


def test_emoji_alone_is_only_weak():
    """⚠️ is on 26% of all messages and 93% of those already match another
    shape, so on its own it must not carry a full-volume notification."""
    t = "🔴Київ — найближчі 3 хвилини будуть дуже гучні."
    assert hints.live_shapes(t) == ["emoji-with-place"]
    assert hints.live_strength(t) == "weak"


def test_no_evidence_is_none():
    assert hints.live_strength("Дякую за підтримку") == "none"
    assert hints.live_strength("") == "none"


def test_suggest_reports_strength():
    assert hints.suggest("1х Жуляни")["strength"] == "strong"
    assert hints.suggest("🔴Київ — буде гучно.")["strength"] == "weak"


# --- apostrophes and vowel alternation ------------------------------------


def test_all_apostrophe_spellings_resolve_the_same():
    """The corpus uses U+0027, U+02BC and U+2019 interchangeably, and some
    writers use none. Matching one variant lost 37 messages, 24 of them naming
    Solomianka — the reference location's own district."""
    for form in ("Солом'янка", "Солом\u2019янка", "Солом\u02bcянка", "Соломянка"):
        assert resolve_scope(form) == "my-area", repr(form)
    for form in ("Лук'янівка", "Лук\u2019янівку", "Лукянівка"):
        assert resolve_scope(form) == "city", repr(form)
    for form in ("Зазим'я", "Зазимя"):
        assert resolve_scope(form) == "oblast", repr(form)


def test_district_form_also_resolves_without_apostrophe():
    assert resolve_scope("соломянський район") == "my-district"


def test_vowel_alternation_in_oblique_cases():
    """Ukrainian shifts і to о inside the stem: Харків/Харкова. A prefix cannot
    match through a change inside itself, so the variants are generated."""
    assert resolve_scope("Вибух у Харкова") == "elsewhere"
    assert resolve_scope("Вибухи в Чернігова") == "elsewhere"
    assert resolve_scope("обстріл Борисполі") == "oblast"
    assert resolve_scope("Фастова") == "oblast"
    assert resolve_scope("Миколаєва") == "elsewhere"


def test_the_one_mined_typo_is_pinned():
    """Жушяни: Ш sits directly above Л on ЙЦУКЕН. One occurrence in 134 days,
    so it is pinned as an alias rather than matched fuzzily at runtime."""
    assert resolve_scope("Жушяни/Вишневе") == "my-area"


# --- MiG-31K, and why other aviation is not a threat class ----------------


def test_mig_takeoff_is_its_own_class():
    """A MiG-31K in the air puts the whole country under alert because it can
    launch a Kinzhal anywhere — and it sometimes lands without launching."""
    for t in ("❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка. "
              "МіГ-31К — носій аеробалістичної ракети",
              "🛫Виліт другого винищувача МіГ-31К з аеродрому \"Саваслейка\".",
              "⚪️Борти МіГ-31К розвернулись на аеродром базування."):
        assert hints.threat_hint(t) == "mig", t
        assert hints.alarm_for("mig") == "mig"


def test_the_takeoff_boilerplate_does_not_read_as_ballistic():
    """The channels' takeoff text says "носій аеробалістичної ракети" — a
    ballistic pattern matches it even though nothing has been launched."""
    t = "Виліт МіГ-31К. МіГ-31К⚠️ — носій аеробалістичної ракети Кинжал"
    assert hints.threat_hint(t) == "mig"


def test_a_launch_from_the_mig_is_ballistic_not_the_carrier():
    t = "❗️⚠️❗Пуск аеробалістичної ракети \"Кинджал\" з винищувача МіГ-31К."
    assert hints.threat_hint(t) == "ballistic"


def test_mig_is_nationwide_even_with_no_local_geography():
    """The takeoff names a Russian airfield and no Ukrainian target, so a purely
    geographic filter would hide the one signal that alerts the whole country."""
    t = "Виліт винищувача МіГ-31К з аеродрому Саваслейка."
    assert not is_relevant(t)
    assert hints.nationwide(t)


def test_bomber_takeoff_is_not_a_threat_class():
    """It happens long before any alert and the airfield is far away. The alert
    arrives with the cruise missiles it launches, which are their own class."""
    for t in ("⚠️Виліт бомбардувальника Ту-95МС з аеродрому \"Оленья\", курс поки не відомий.",
              "🔴Очікуємо на вильоти бомбардувальників Ту-95МС/Ту-160/Ту-22М3 протягом ночі.",
              "В повітрі є 2 бомбардувальники Ту-22М3, зараз прямої загрози немає"):
        assert hints.threat_hint(t) == "aviation", t
        assert hints.alarm_for("aviation") == "none"
        assert not hints.nationwide(t)


def test_russian_airfield_is_not_a_ukrainian_town():
    """`аеродрому "Українка"` is in Amur oblast. It resolved as Ukrainka in Kyiv
    oblast and passed the relevance filter until multi-word stems could match
    across collapsed whitespace."""
    t = "Виліт бомбардувальників Ту-160 з аеродрому \"Українка\"."
    assert resolve_scope(t) == "elsewhere"
    assert not is_relevant(t)


def test_the_town_of_ukrainka_still_resolves():
    assert resolve_scope("⚠️1 шахед на Українку") == "oblast"


def test_whitespace_between_multiword_stems_is_collapsed():
    """Punctuation becomes a space, so two spaces could appear mid-stem."""
    assert resolve_scope("курсом на Велика   Димерка") == "oblast"
    assert resolve_scope("на  Білу   Церкву") == "oblast"


def test_takeoff_is_probable_not_confirmed():
    t = "⚠️Виліт бомбардувальника Ту-95МС з аеродрому \"Оленья\", курс поки не відомий."
    assert hints.certainty_hint(t) == "probable"


# --- bare impact reports --------------------------------------------------


def test_a_bare_impact_report_is_unknown_not_nothing():
    """Something arrived. "Nothing is flying" is the wrong default, and it was
    the pre-fill for 105 of the corpus's 380 impact messages."""
    for t in ("Вибухи", "Вибухи 💥💥💥 4 шт було", "Прозвучав вибух💥",
              "Чутно було вибух 💥", "💥Влучання."):
        s = hints.suggest(t)
        assert s["threat"] == "unknown", t
        assert s["certainty"] == "lost", t


def test_a_bare_impact_report_is_never_clear():
    """`clear` would say it is safe when nobody has said so, and impact reports
    sit a median of 1.8 minutes from live danger."""
    for t in ("Вибухи", "💥Влучання.", "Чутно було вибух 💥"):
        assert hints.certainty_hint(t) != "clear", t


def test_an_explicit_all_clear_still_wins_over_the_impact():
    assert hints.certainty_hint("💥Вибухи у Дніпрі, над містом чисто.") == "clear"


def test_a_named_type_survives_the_impact_promotion():
    s = hints.suggest("💥Вибух в Одесі, попередньо ракета Іскандер-М.")
    assert s["threat"] == "ballistic"
    assert s["certainty"] == "probable"


# --- alert declarations and all-clears ------------------------------------


def test_alert_declarations_and_all_clears_are_recognised():
    """Without them there is no telling when a threat passed — and 245 of the
    corpus's 658 such messages were being hidden by the geographic filter."""
    for t in ("🛑 ТРИВОГА", "🔴Оголошено повітряну тривогу у місті.",
              "⚠️У Києві тривога через шахед"):
        assert hints.alert_state(t) == "alert", t
    for t in ("🛑 Відбій тривоги", "Відбій, усім солодких снів та тихої ночі💕",
              "🟢 ВІДБІЙ ТРИВОГИ"):
        assert hints.alert_state(t) == "clear", t


def test_waiting_for_an_all_clear_is_not_an_all_clear():
    """"Київ очікує на відбій" is waiting for one. Announcing it told the user
    it was over while a drone was still up — one of the first run's false
    wake-ups."""
    assert hints.alert_state("⚪️Київ очікує на відбій.") != "clear"
    assert hints.alert_state("⚪️Очікуємо на відбій.") != "clear"


def test_an_all_clear_wins_over_the_word_alert_in_the_same_message():
    """"Відбій тривоги" contains both; reading it as a declaration would invert
    the meaning."""
    assert hints.alert_state("🛑 Відбій тривоги") == "clear"
    assert hints.alert_state("⚪️По балістиці відбій. Тривога триває.") == "clear"


def test_ordinary_threat_messages_are_not_alert_state():
    assert hints.alert_state("⚠️1 реактивний шахед на Жуляни.") is None
    assert hints.alert_state("1х Центр.") is None


def test_the_remaining_oblasts_resolve_as_elsewhere():
    """An alert in another region should not reach the local feed."""
    for t in ("На Закарпатті тривога превентивна", "Тривога на Рівненщині",
              "Відбій у Чернівцях", "тривога на Волині", "Івано-Франківщина"):
        assert resolve_scope(t) == "elsewhere", t


# --- nothing vs not-yet-known ---------------------------------------------


def test_a_bare_alert_declaration_is_unknown_not_nothing():
    """"Тривога" says something is coming without saying what. `none` would
    claim the sky is empty."""
    for t in ("🛑 ТРИВОГА", "🔴Оголошено повітряну тривогу у місті."):
        assert hints.suggest(t)["threat"] == "unknown", t


def test_an_all_clear_means_nothing_is_flying():
    for t in ("🛑 Відбій тривоги", "Відбій, усім солодких снів 💕"):
        assert hints.suggest(t)["threat"] == "none", t


def test_a_partial_all_clear_keeps_what_is_still_named():
    """"По балістиці відбій" closes one class while another still flies."""
    t = "⚪️По балістиці відбій. / ⚠️2 шахеди на Чорноморськ/Одесу."
    assert hints.suggest(t)["threat"] == "shahed"


def test_informational_text_is_nothing_not_unknown():
    assert hints.suggest("Дякую за підтримку")["threat"] == "none"


# --- the near ring is a ruling, not a radius ------------------------------


def test_the_near_ring_follows_the_approach_corridor_not_distance():
    """The user's rule: "не завжди питання в відстані, а також якою дорогою
    найчастіше воно летить". Gatne is in and its neighbour Chabany is out;
    Solomianka is in and Chokolivka is not. Deriving this from geometry would
    get both pairs wrong."""
    assert resolve_scope("Гатне") == "my-area"
    assert resolve_scope("Чабани") == "oblast"
    assert resolve_scope("Солом'янка") == "my-area"
    assert resolve_scope("Чоколівка") == "city"


def test_the_ring_holds_exactly_what_was_ruled_in():
    from tools.nlp.gazetteer import MY_AREA

    assert {p.name for p in MY_AREA} == {
        "Жуляни", "Вишневе", "Борщагівка", "Солом'янка", "Деміївка",
        "Іподром", "Гатне", "Теремки", "Крюківщина",
    }


def test_places_ruled_out_are_still_recognised_just_not_near():
    """Ruled out of the ring, not out of the gazetteer — they still resolve, so
    a message naming them is still Kyiv-relevant."""
    for name, tier in (("Мишоловка", "city"), ("Караваєві Дачі", "city"),
                       ("Віта-Поштова", "oblast"), ("Крушинка", "oblast")):
        assert resolve_scope(name) == tier, name


# --- heading: direction relative to the ring ------------------------------


def test_a_destination_in_the_ring_is_toward_me():
    for t in ("🅿️ 1х реактив на Крюківщину / Борщагівки.",
              "Реактивний БпЛА курсом на Жуляни",
              "Через Оболонь в сторону Жулян",
              "1х рБПЛА повз Гореничі на Борщагівку/Вишневе"):
        assert hints.heading(t) == "toward", t


def test_a_place_in_the_ring_with_no_direction_is_only_a_position():
    """The distinction that resolved a apparent contradiction: a drone *in* the
    ring and one *heading into* it are different decisions."""
    assert hints.heading("Крюківщина") == "position"
    assert hints.heading("Деміївка, Мишоловка") == "position"


def test_leaving_the_ring_is_away():
    assert hints.heading("⚠️З Теремки на Віта-Литовська.") == "away"
    assert hints.heading("🅿️ 1х реактив Жуляни далі Центр.") == "away"


def test_circling_nearby_is_loitering():
    assert hints.heading("🔄 1х Довкола Крюківщини Вишневого.") == "loitering"


def test_somewhere_else_entirely_is_unknown():
    assert hints.heading("❗Балістична ракета на Запоріжжя!") == "unknown"
    assert hints.heading("Дякую за підтримку") == "unknown"


def test_separate_groups_are_not_read_as_movement():
    """"1х Жуляни / 2х Велика Димерка" is two groups, not one trajectory."""
    assert hints.heading("1х Жуляни / 2х Велика Димерка/Бровари (вектор)") == "position"


def test_toward_wins_over_away_when_both_appear():
    """If anything is heading into the ring, that is the answer."""
    assert hints.heading("З Центру на Жуляни") == "toward"


def test_suggest_reports_the_heading():
    assert hints.suggest("Реактивний БпЛА курсом на Жуляни")["heading"] == "toward"


# --- siren replies are refinements ----------------------------------------


def test_a_siren_reply_still_reads_as_a_siren_lexically():
    """The reply flag is not in the text, so `alert_state` cannot see it — the
    distinction lives in the policy, which is where the reply is known."""
    assert hints.alert_state("По ньому тривога") == "alert"
    assert hints.alert_state("По цих БПЛА тривога") == "alert"


# --- which class a partial all-clear lifts ---------------------------------


def test_the_lifted_class_is_derived_not_typed():
    """Neither existing field can carry it: `threat` means what is in the air,
    and the point of a partial clear is that this class no longer is."""
    assert hints.cleared_class("⚪️ Відбій загрози МіГ-31К.") == "mig"
    assert hints.cleared_class("⚪️По балістиці відбій.") == "ballistic"
    assert hints.cleared_class("⚪️ Відбій загрози балістики.") == "ballistic"
    assert hints.cleared_class("⚪️ Відбій авіаційної небезпеки.") == "aviation"


def test_a_full_all_clear_lifts_no_particular_class():
    assert hints.cleared_class("🟢 ВІДБІЙ ТРИВОГИ") is None
    assert hints.cleared_class("Відбій, усім солодких снів 💕") is None


def test_an_ordinary_threat_message_lifts_nothing():
    assert hints.cleared_class("⚠️1 шахед на Жуляни") is None


def test_a_pure_partial_clear_reports_nothing_flying():
    """Answering `mig` would claim a MiG is up in the very message announcing
    that it is not."""
    s = hints.suggest("⚪️ Відбій загрози МіГ-31К.")
    assert s["threat"] == "none"
    assert s["cleared"] == "mig"


def test_a_partial_clear_naming_another_class_reports_that_one():
    s = hints.suggest("⚪️По балістиці відбій. / ⚠️2 шахеди на Чорноморськ/Одесу.")
    assert s["threat"] == "shahed"
    assert s["cleared"] == "ballistic"


# --- a takeoff report is not an emoji -------------------------------------


def test_a_takeoff_is_structural_evidence_not_a_decoration():
    """Before the `launch` shape existed this matched only `emoji-with-place`
    and came out weak — as if the evidence were the ⚠️ rather than "Виліт"."""
    text = ('❗️⚠️Виліт винищувача МіГ-31К з аеродрому Саваслейка.\n'
            'МіГ-31К⚠️ — носій аеробалістичної ракети Х-47М2 "Кинджал"')
    assert "launch" in hints.live_shapes(text)
    assert hints.live_strength(text) == "strong"


def test_an_ordinary_bare_place_report_is_still_weak_on_its_emoji():
    """The launch shape must not quietly promote everything else."""
    assert hints.live_strength("Жуляни ⚠️") != "none"


# --- landmarks ------------------------------------------------------------


def test_a_named_power_plant_is_a_place_in_the_city():
    """`ТЕЦ-5` is named 44 times in the corpus, more often than most districts,
    and every one of those messages used to resolve to `unknown` and vanish from
    the Kyiv view. The user found it: a reply quoting "На ТЕЦ-5! Падає" whose
    parent was nowhere on the page."""
    assert resolve_scope("⚠️На ТЕЦ-5! Падає") == "city"
    assert resolve_scope("⚠️Реактивний шахед на Троєщину/ТЕЦ-6.") == "city"
    assert resolve_scope("⚠️1 реактивний шахед на ТЦ Проспект.") == "city"
    assert resolve_scope("Завели ціль Над столицею, Видубичі") == "city"


def test_a_settlement_named_beside_a_landmark_outranks_it():
    """Nearly every city has a ТЕЦ-5. "Залітає у Черкаси курсом на ТЕЦ-5" is
    about theirs, and without this rule the nearest tier wins and someone
    else's city reads as ours."""
    assert resolve_scope("🔴Залітає у Черкаси курсом на ТЕЦ-5, Сади.") == "elsewhere"
    assert resolve_scope("⚠️1 шахед на Чернігівську ТЕЦ!") == "elsewhere"


def test_a_landmark_still_loses_to_a_nearer_district():
    """The rule is about settlements outranking landmarks, not about landmarks
    dragging a message down a tier."""
    assert resolve_scope("ТЕЦ-5, Деміївка, Голосіїв") == "my-area"


def test_the_nameless_infrastructure_category_still_works():
    """`find_infrastructure` answers "is a power plant involved at all", which
    is a different question from where it is."""
    assert "ТЕЦ" in find_infrastructure("⚠️На Чернігівську ТЕЦ")


# --- a hyphen joins two places, it does not hide one -----------------------


def test_the_second_half_of_a_hyphenated_pair_is_found():
    """Zhurivka was already in the gazetteer and never matched: the hyphen
    counted as a word character, so every "X-Y" pair lost Y."""
    assert resolve_scope("2х БПЛА Яготин-Згурівка") == "oblast"
    assert resolve_scope("1х Обухів-Васильків") == "oblast"
    assert resolve_scope("Конча-Заспа") == "city"


def test_a_hyphenated_name_is_not_two_places():
    """`шевченків` and `подільськ` are Kyiv districts, and the hyphen fix
    exposed them inside towns hundreds of kilometres away — Kamianets-Podilskyi
    read as Podil nine times. Longest match is what keeps them apart."""
    assert resolve_scope("Корсунь-Шевченківський 3х реактивних БпЛА") == "elsewhere"
    assert resolve_scope("Шахед на Кам'янець-Подільський") == "elsewhere"
    assert resolve_scope("Києво-Святошинському районі") == "oblast"
    # ...while a hyphenated name that really is in Kyiv still is.
    assert resolve_scope("Києво-Печерська лавра") == "city"


def test_launch_origins_resolve_to_a_region_rather_than_nowhere():
    """Left `unknown` they inherit the night's scope from the feed, which would
    have made a launch from Russia read as a threat over Kyiv."""
    for text in ("⚠️Пуски реактивних шахедів з Орла.",
                 "Запуск реактивних БпЛА з Брянщини",
                 "з Воронезької області", "з Орловської області"):
        assert resolve_scope(text) == "elsewhere", text


def test_chabanka_is_not_chabany():
    """One letter apart: a village in Odesa oblast and a neighbour of the
    user's."""
    assert resolve_scope("3х реактива у напрямку Південний порт / Чабанка") == "elsewhere"
    assert resolve_scope("На Чабани, Гатне") == "my-area"


def test_a_plant_written_with_a_space_is_the_same_plant():
    """`kievinform_ua1` writes "ТЕЦ 5", `mon1tor_ua` writes "ТЕЦ-5". Six
    occurrences went missing on the space form — one of them sixteen seconds
    before the message the user came looking for."""
    assert resolve_scope("ТЕЦ 5") == "city"
    assert resolve_scope("ТЕЦ 6✈️") == "city"
    assert resolve_scope("Черкаську ТЕЦ 5 і Сади") == "elsewhere"


def test_the_channels_own_abbreviations_resolve():
    """`kievinform_ua1` writes districts the way a person shouts them —
    "Хотів - Голос - Солома в укриття"."""
    assert resolve_scope("Голос✈️") == "city"
    assert resolve_scope("Хотів - Голос - Солома в укриття") == "my-area"
    assert resolve_scope("Феофанія✈️") == "city"
    assert resolve_scope("Рембаза") == "city"
    assert resolve_scope("Требухів✈️") == "oblast"
    assert resolve_scope("Гоголів") == "oblast"


def test_a_verb_that_starts_with_a_district_name_is_not_a_district():
    """`голос` is a prefix of "оголосити". The word-start check is what keeps
    "можуть оголосити повітряну тривогу" from resolving as Holosiiv."""
    assert resolve_scope("можуть оголосити тривогу") == "unknown"
    assert resolve_scope("проголосували") == "unknown"


def test_launch_origins_come_from_the_gazetteer():
    """A separate list went stale the moment Voronezh and Oryol were added as
    places: a real ballistic launch from Voronezh read as "a target in another
    region" and was silenced as too far."""
    assert hints.nationwide(
        "❗️❗Є інформація про пуск балістичної ракети з Воронезької області.")
    assert hints.nationwide("‼️ Вихід балістики з Брянська")
    # ...and a stated target is still not country-wide.
    assert not hints.nationwide("❗️Балістична ракета на Запоріжжя!")
