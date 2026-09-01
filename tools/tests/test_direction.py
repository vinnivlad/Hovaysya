"""Choosing between two names by direction rather than distance.

His case, 2026-08-30: the siren said Obolon and the explanation said Vyshhorod,
both true, and the pair read as a contradiction. His rule, 2026-09-01: "якщо
обидві цілі знаходяться в секторі 90 град від мене, то беремо ближню, інакше
залишаємо як є, мо скоріше то різні цілі."
"""
from tools.nlp.coords import POINTS
from tools.nlp.direction import bearing, say, spread

HOME = POINTS["Жуляни"]


def test_two_names_in_one_sector_are_one_threat():
    """Obolon and Vyshhorod are both north, ten degrees apart. The pair that
    started this."""
    assert say(["Оболонь", "Вишгород"], HOME) == ["Оболонь"]
    assert say(["Бровари", "Бориспіль"], HOME) == ["Бровари"]


def test_names_on_opposite_sides_are_two_threats():
    """And this is the case the rule exists to protect. One threat over Obolon
    and another coming from Vasylkiv in the south: the nearest name is the
    harmless one, and saying only it would be a lie by omission."""
    assert say(["Оболонь", "Васильків"], HOME) == ["Оболонь", "Васильків"]
    assert say(["Голосіїв", "Вишневе"], HOME) == ["Голосіїв", "Вишневе"]


def test_home_wins_whenever_it_is_named():
    """Nothing is nearer, and a bearing from a point to itself means nothing."""
    assert say(["Вишневе", "Жуляни"], HOME) == ["Жуляни"]


def test_a_name_without_a_coordinate_stops_the_whole_judgement():
    """Rather than being quietly dropped. `Київ` has no point on purpose -- it is
    fifty kilometres wide -- and deciding that Zhuliany is nearer than the city
    would lose whichever of them mattered."""
    assert say(["Жуляни", "Київ"], HOME) == ["Жуляни", "Київ"]


def test_zero_turns_it_off():
    """Which is how this behaved before coordinates existed."""
    assert say(["Оболонь", "Вишгород"], HOME, 0) == ["Оболонь", "Вишгород"]


def test_the_spread_is_measured_the_way_a_circle_works():
    """Bearings of 350 and 10 are twenty degrees apart, not three hundred and
    forty. Getting this wrong would split every threat coming from due north."""
    assert spread([350.0, 10.0]) == 20.0
    assert spread([10.0, 350.0]) == 20.0
    assert spread([0.0, 90.0, 180.0]) == 180.0
    assert spread([5.0]) == 0.0


def test_the_bearings_point_the_way_the_city_lies():
    """A sanity check on the table rather than on the arithmetic: Obolon is north
    of Zhuliany, Vasylkiv south, Brovary east, Vyshneve west."""
    assert 340 < bearing(HOME, POINTS["Оболонь"]) or bearing(HOME, POINTS["Оболонь"]) < 40
    assert 150 < bearing(HOME, POINTS["Васильків"]) < 210
    assert 40 < bearing(HOME, POINTS["Бровари"]) < 130
    assert 230 < bearing(HOME, POINTS["Вишневе"]) < 320
