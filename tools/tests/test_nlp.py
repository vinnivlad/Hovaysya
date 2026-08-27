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
    assert resolve_scope("1х Борщаги") == "city"
    assert resolve_scope("1х Солома/Центр") == "my-area"
    assert resolve_scope("Через Трою на Труханів") == "city"


def test_matches_through_trailing_punctuation():
    assert resolve_scope("1х Жуляни.") == "my-area"
    assert resolve_scope("Дарниця, Чоколівка") == "my-area"


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


def test_alarm_mapping_separates_the_three_sounds():
    assert hints.alarm_for("ballistic") == "ballistic"
    assert hints.alarm_for("cruise") == "cruise"
    assert hints.alarm_for("kab") == "cruise"
    assert hints.alarm_for("shahed") == "drone"
    assert hints.alarm_for("shahed-jet") == "drone"
    assert hints.alarm_for("aviation") == "aviation"


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
    assert s["alarm"] == "drone"
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
