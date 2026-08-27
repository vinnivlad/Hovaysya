"""Toponym gazetteer with morphology, and resolution to a relevance tier.

Built from the corpus, not from a map: every entry here was observed in the
mined channel history (see docs/pattern-findings.md), including slang and
informal areas that no official dataset carries — `Солома`, `Борщаги`,
`Лівобережний масив`, `ДВРЗ`.

Matching is by **stem prefix**, never by exact string. Ukrainian case endings
make exact matching useless: `Київщину / Київщини / Київщина / Київщині /
Київщиною` are one place, and channels are inconsistent about capitalisation
(`КИЇВ`, `ТРОЄЩИНА`). A short lowercase prefix collapses each family, which was
verified against every inflection family in the corpus.

Tiers are relative to the reference location, Zhuliany:

    my-area    the approach corridor, curated from the user's rulings — not a
               radius, see MY_AREA
    my-district Solomianskyi district generally
    city       elsewhere in Kyiv
    oblast     Kyiv oblast outside the city
    elsewhere  another region — 22% of the corpus, discardable
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tiers, ordered most to least relevant. Order matters: resolution returns the
# most relevant tier present in a message, because "Жуляни та Троєщина" is about
# my area even though it also names a far one.
TIERS = ("my-area", "my-district", "city", "oblast", "elsewhere")


_APOSTROPHES = str.maketrans(
    {ch: "" for ch in ("'", "ʼ", "’", "‘", "´", "`")}
)


def _strip_apostrophes(text: str) -> str:
    return (text or "").translate(_APOSTROPHES)


@dataclass(frozen=True)
class Place:
    name: str  # canonical display form
    tier: str
    stems: tuple[str, ...]  # lowercase prefixes that identify it


def _p(name: str, tier: str, *stems: str) -> Place:
    """Declare a place. Stems are normalised the same way message text is.

    Apostrophes are stripped here so an entry can be written the readable way
    (`солом'ян`) while still matching text where the apostrophe is a different
    character, or absent.
    """
    return Place(name, tier, tuple(_strip_apostrophes(s).lower() for s in stems))


# The near ring — the places whose trouble is the user's trouble.
#
# This is NOT a radius, and deriving it from distance would be wrong. In the
# user's words: "не завжди питання в відстані, а також якою дорогою найчастіше
# воно летить і які топоніми мелькають в чаті" — it is the approach corridor
# plus the names that actually recur in the channels. Gatne is in and
# neighbouring Chabany is out; Solomianka is in and Chokolivka is not.
#
# Every entry below is the user's explicit ruling after labelling a full night,
# except where marked. Do not "tidy" this into a geometric rule.
MY_AREA = [
    _p("Жуляни", "my-area", "жулян", "жушян"),   # home
    _p("Вишневе", "my-area", "вишнев"),
    _p("Борщагівка", "my-area", "борщагів", "борщаг"),
    _p("Солом'янка", "my-area", "солом'ян", "соломян", "солома", "соломи"),
    _p("Деміївка", "my-area", "деміїв"),
    _p("Іподром", "my-area", "іподром"),
    _p("Гатне", "my-area", "гатне"),
    _p("Теремки", "my-area", "теремк"),
    # Inferred, not ruled: woken for once ("реактив на Крюківщину/Борщагівки"),
    # marked far once. Left in pending a decision.
    _p("Крюківщина", "my-area", "крюківщ"),
]

MY_DISTRICT = [
    _p("Солом'янський район", "my-district", "солом'янськ", "соломянськ"),
]

# The rest of Kyiv, including the informal "масив" areas the channels use.
CITY = [
    # Ruled out of the near ring by the user after the first night: in Kyiv,
    # but not on the corridor that matters to them.
    _p("Чоколівка", "city", "чоколів"),
    _p("Мишоловка", "city", "мишолов"),
    _p("Караваєві Дачі", "city", "караваєв"),
    _p("Совки", "city", "совки"),
    _p("Троєщина", "city", "троєщ", "троєща", "троя", "трою"),
    _p("Оболонь", "city", "оболон"),
    _p("Дарниця", "city", "дарниц"),
    _p("Позняки", "city", "позняк"),
    _p("Лук'янівка", "city", "лук'янів", "лукянів"),
    _p("Виноградар", "city", "виноградар", "виноград"),
    _p("Святошин", "city", "святошин"),
    _p("Голосіїв", "city", "голосіїв", "голосієв"),
    _p("Печерськ", "city", "печерс"),
    _p("Поділ", "city", "подільс", "поділ"),
    _p("Осокорки", "city", "осокорк"),
    _p("Русанівка", "city", "русанів"),
    _p("Нивки", "city", "нивк"),
    _p("Сирець", "city", "сирец"),
    _p("Куренівка", "city", "куренівк"),
    _p("Пріорка", "city", "пріорк"),
    _p("Березняки", "city", "березняк"),
    _p("Воскресенка", "city", "воскресенк"),
    _p("ДВРЗ", "city", "дврз"),
    _p("Бортничі", "city", "бортнич"),
    _p("Академмістечко", "city", "академмістечк", "академ"),
    _p("Відрадний", "city", "відрадн"),
    _p("Лісовий масив", "city", "лісовий"),
    _p("Лівобережний масив", "city", "лівобережн"),
    _p("Харківський масив", "city", "харківський масив"),
    _p("Дарницький масив", "city", "дарницький масив"),
    _p("Мінський масив", "city", "мінський масив"),
    _p("Соцмісто", "city", "соцміст"),
    _p("Труханів", "city", "труханів"),
    _p("Центр", "city", "центр"),
    _p("Шевченківський район", "city", "шевченківс"),
    _p("Деснянський район", "city", "деснянс"),
    _p("Дніпровський район", "city", "дніпровськ"),
    _p("Оболонський район", "city", "оболонськ"),
    _p("Дарницький район", "city", "дарницьк"),
    _p("Пуща-Водиця", "city", "пуща-водиц", "пущу-водиц"),
    _p("Правий берег", "city", "правий берег", "правобереж"),
    _p("Лівий берег", "city", "лівий берег", "лівобереж"),
    _p("Шулявка", "city", "шулявк"),
    _p("Клов", "city", "клов"),
    _p("Антонов", "city", "антонов"),
    _p("Мостицький", "city", "мостиц"),
    _p("Виставковий центр", "city", "ввц", "виставков"),
    _p("Київ", "city", "київ", "києв", "києм"),
]

OBLAST = [
    # Also ruled out of the near ring — "Віта Поштова: зовсім далеко".
    _p("Чабани", "oblast", "чабани"),
    _p("Віта-Поштова", "oblast", "віта-поштов", "віту-поштов"),
    _p("Віта-Литовська", "oblast", "віта-литовськ"),
    _p("Крушинка", "oblast", "крушинк"),
    _p("Бровари", "oblast", "бровар"),
    _p("Вишгород", "oblast", "вишгород"),
    _p("Бориспіль", "oblast", "бориспіл", "борисполь", "борисполя"),
    _p("Обухів", "oblast", "обухів", "обухов"),
    _p("Васильків", "oblast", "васильків", "василькова"),
    _p("Ірпінь", "oblast", "ірпін"),
    _p("Буча", "oblast", "буча", "бучі"),
    _p("Гостомель", "oblast", "гостомел"),
    _p("Біла Церква", "oblast", "біла церкв", "білу церкв", "білоцерків"),
    _p("Фастів", "oblast", "фастів"),
    _p("Переяслав", "oblast", "переяслав"),
    _p("Славутич", "oblast", "славутич"),
    _p("Жукин", "oblast", "жукин"),
    _p("Згурівка", "oblast", "згурівк"),
    _p("Баришівка", "oblast", "баришівк"),
    _p("Макарів", "oblast", "макарів"),
    _p("Боярка", "oblast", "боярк"),
    # Prefix, not full forms: the accusative is Українку. Dropping "українц"
    # on purpose — it would match "українців" in ordinary prose.
    _p("Українка", "oblast", "українк"),
    _p("Димер", "oblast", "димер"),
    _p("Велика Димерка", "oblast", "велика димерк", "великої димерк"),
    _p("Погреби", "oblast", "погреб"),
    _p("Зазим'я", "oblast", "зазим"),
    _p("Коцюбинське", "oblast", "коцюбинс"),
    _p("Мощун", "oblast", "мощун"),
    _p("Горенка", "oblast", "горенк", "горенич"),
    _p("Княжичі", "oblast", "княжич"),
    _p("Гнідин", "oblast", "гнідин"),
    _p("Глеваха", "oblast", "глевах"),
    _p("Хотянівка", "oblast", "хотянівк"),
    # Longer stems than the city's, so longest-match resolves them here:
    # "КИЇВСЬКА ОБЛАСТЬ ОГОЛОШЕНА ПОВІТРЯНА ТРИВОГА" was resolving as the
    # city and being announced as my siren.
    _p("Київщина", "oblast", "київщин", "київська область",
       "київській області", "київську область", "київської області",
       "київщині", "київщину"),
]

ELSEWHERE = [
    _p("Одещина", "elsewhere", "одес", "одещин"),
    _p("Дніпропетровщина", "elsewhere", "дніпр", "дніпропетровщин"),
    _p("Харківщина", "elsewhere", "харків", "харківщин"),
    _p("Полтавщина", "elsewhere", "полтав"),
    _p("Черкащина", "elsewhere", "черкас", "черкащин"),
    _p("Миколаївщина", "elsewhere", "миколаїв"),
    _p("Запоріжжя", "elsewhere", "запоріж", "запорізьк"),
    _p("Херсонщина", "elsewhere", "херсон"),
    _p("Сумщина", "elsewhere", "сумщин", "суми", "сумах", "сумам"),
    _p("Чернігівщина", "elsewhere", "чернігів"),
    _p("Житомирщина", "elsewhere", "житомир"),
    _p("Кіровоградщина", "elsewhere", "кіровоградщин", "кропивницьк"),
    _p("Вінниччина", "elsewhere", "вінниц", "вінниччин"),
    _p("Хмельниччина", "elsewhere", "хмельниц", "хмельнич"),
    _p("Львівщина", "elsewhere", "львів"),
    _p("Закарпаття", "elsewhere", "закарпат", "ужгород", "мукачев"),
    _p("Івано-Франківщина", "elsewhere", "івано-франків", "франківщ", "прикарпат"),
    _p("Чернівеччина", "elsewhere", "чернівц", "буковин"),
    _p("Рівненщина", "elsewhere", "рівненщ", "рівне", "рівному", "сарни"),
    _p("Волинь", "elsewhere", "волин", "луцьк"),
    _p("Тернопільщина", "elsewhere", "тернопіл", "тернопільщ"),
    _p("Донеччина", "elsewhere", "донеччин", "донецьк", "краматорськ", "слов'янськ"),
    _p("Луганщина", "elsewhere", "луганщин", "луганськ"),
    _p("Чорноморськ", "elsewhere", "чорноморськ"),
    _p("Кременчук", "elsewhere", "кременчу"),
    # Named as ballistic targets during the labelled night and resolving as
    # nowhere, which let `nationwide` treat them as untargeted launches.
    _p("Павлоград", "elsewhere", "павлоград"),
    _p("Кам'янське", "elsewhere", "кам'янськ", "камянськ"),
    _p("Знам'янка", "elsewhere", "знам'янк", "знамянк"),
    _p("Прилуки", "elsewhere", "прилук"),
    _p("Ніжин", "elsewhere", "ніжин"),
    _p("Полтава", "elsewhere", "полтав"),
    _p("Ізюм", "elsewhere", "ізюм"),
    _p("Лозова", "elsewhere", "лозов"),
    _p("Синельникове", "elsewhere", "синельников"),
    _p("Кривий Ріг", "elsewhere", "кривий ріг", "кривого рог", "кривим рог",
       "кривом", "криворіж", "криворізьк"),
    _p("Крим", "elsewhere", "крим", "криму"),
    _p("Ізмаїл", "elsewhere", "ізмаїл"),
    _p("Брянщина", "elsewhere", "брянськ", "брянсько"),
    _p("Курщина", "elsewhere", "курськ", "курсько"),
    # Russian airfields, named in launch-origin and takeoff reports. Listed so
    # they resolve as elsewhere instead of being mistaken for Ukrainian places:
    # `аеродрому "Українка"` is in Amur oblast, and without the longer stem it
    # matched Ukrainka in Kyiv oblast and passed the relevance filter.
    _p("російські аеродроми", "elsewhere",
       "аеродрому українка", "аеродром українка",
       "саваслейк", "оленья", "оленя", "енгельс", "дягілев", "дягілєв",
       "шайковк", "міллеров", "ахтубінськ", "ахтубинськ", "таганрог",
       "приморсько-ахтарськ", "приморсько ахтарськ", "гвардійськ",
       "балбасов", "мозир", "рязан", "морозовськ", "мілитопол"),
]

def _with_alternations(place: Place) -> Place:
    """Add oblique-case stems produced by Ukrainian vowel alternation.

    Names in -ів/-їв/-іл shift the vowel in the genitive and locative:
    Харків/Харкова, Миколаїв/Миколаєва, Бориспіль/Борисполі. A prefix stem
    cannot match across a change inside itself, so the variants are generated
    once here rather than typed out for every name.
    """
    extra: list[str] = []
    for stem in place.stems:
        if stem.endswith("їв"):
            extra.append(stem[:-2] + "єв")
        elif stem.endswith("ів"):
            extra.append(stem[:-2] + "ов")
        elif stem.endswith("іл"):
            extra.append(stem[:-2] + "ол")
    if not extra:
        return place
    merged = tuple(dict.fromkeys(place.stems + tuple(extra)))
    return Place(place.name, place.tier, merged)


PLACES: tuple[Place, ...] = tuple(
    _with_alternations(p)
    for p in (MY_AREA + MY_DISTRICT + CITY + OBLAST + ELSEWHERE)
)

# Named infrastructure. Not a tier of its own: a power plant matters because of
# where it is, and the corpus names them alongside districts.
INFRASTRUCTURE = (
    ("ТЕЦ", "тец"),
    ("аеропорт", "аеропорт"),
    ("вокзал", "вокзал"),
    ("метро", "метро"),
    ("підстанція", "підстанц"),
)

_WORDISH = re.compile(r"[^а-яіїєґёa-z0-9'\- ]+", re.IGNORECASE)


# Apostrophes are deleted rather than unified: the channels use U+0027, U+02BC
# and U+2019 interchangeably — matching only one lost 37 messages, 24 of them
# naming Solomianka — and plenty of people type none at all. Deleting collapses
# `Солом'янка`, `Солом’янка`, `Соломʼянка` and `Соломянка` into one string.
def _flatten(text: str) -> str:
    """Lowercase, drop apostrophes, strip punctuation, collapse whitespace.

    Collapsing matters for every multi-word stem: punctuation becomes a space,
    so `з аеродрому "Українка"` flattened to two spaces between the words and
    the stem `аеродрому українка` could never match — leaving a Russian
    airfield resolving as Ukrainka in Kyiv oblast, which then passed the
    relevance filter.
    """
    return re.sub(r"\s+", " ", _WORDISH.sub(" ", _strip_apostrophes(text).lower()))


_WORDCHAR = re.compile(r"[а-яіїєґёa-z0-9'\-]", re.IGNORECASE)


def _at_word_start(flat: str, i: int) -> bool:
    return i == 0 or not _WORDCHAR.match(flat[i - 1])


def _word_end(flat: str, i: int) -> int:
    """Extend to the end of the word containing position i.

    Stems are prefixes, so a match on `деміїв` inside `деміївка` would otherwise
    leave `ка` behind. Callers that subtract place spans from the text need the
    whole word gone, or every inflected toponym leaves debris.
    """
    while i < len(flat) and _WORDCHAR.match(flat[i]):
        i += 1
    return i


def _stem_matches(flat: str) -> list[tuple[int, int, int, Place]]:
    """Every (length, start, end, place) stem occurrence, word-aligned."""
    found: list[tuple[int, int, int, Place]] = []
    for place in PLACES:
        for stem in place.stems:
            start = flat.find(stem)
            while start != -1:
                if _at_word_start(flat, start):
                    end = _word_end(flat, start + len(stem))
                    found.append((len(stem), start, end, place))
                start = flat.find(stem, start + 1)
    return found


def find_places(text: str) -> list[Place]:
    """Gazetteer entries named in the text, resolved by longest match.

    Longest-match is not a nicety: `київ` is a prefix of `київщин`, so without
    it every "Київщину" would resolve as the city rather than the oblast — and
    since city outranks oblast in relevance, 906 corpus messages would report
    the wrong tier. The same applies to `дніпро` inside `дніпровський`.
    """
    flat = _flatten(text)
    candidates = sorted(_stem_matches(flat), key=lambda c: (-c[0], c[1]))
    taken: list[tuple[int, int]] = []
    resolved: dict[str, Place] = {}
    for _length, start, end, place in candidates:
        if any(start < t_end and end > t_start for t_start, t_end in taken):
            continue  # a longer stem already claimed this span
        taken.append((start, end))
        resolved.setdefault(place.name, place)
    return list(resolved.values())


def place_spans(text: str) -> list[tuple[int, int, Place]]:
    """Resolved, non-overlapping (start, end, place) spans in flattened text.

    Exposed so callers can subtract place names from a message and ask what is
    left — the test for the bare-toponym-list template.
    """
    flat = _flatten(text)
    candidates = sorted(_stem_matches(flat), key=lambda c: (-c[0], c[1]))
    taken: list[tuple[int, int, Place]] = []
    for _length, start, end, place in candidates:
        if any(start < t_end and end > t_start for t_start, t_end, _ in taken):
            continue
        taken.append((start, end, place))
    return sorted(taken, key=lambda t: t[0])


def flatten(text: str) -> str:
    """Public form of the normalisation `place_spans` indexes against."""
    return _flatten(text)


def resolve_scope(text: str) -> str:
    """The most relevant tier named in the text, or `unknown` if none is.

    Most relevant wins: "Жуляни та Троєщина" is about my area even though it
    also names a distant one, because the notification decision hinges on the
    nearest threat.
    """
    found = find_places(text)
    if not found:
        return "unknown"
    tiers = {p.tier for p in found}
    for tier in TIERS:
        if tier in tiers:
            return tier
    return "unknown"


def find_infrastructure(text: str) -> list[str]:
    flat = _flatten(text)
    return [name for name, stem in INFRASTRUCTURE if stem in flat]


def is_relevant(text: str) -> bool:
    """True unless the message is only about other regions, or names nowhere.

    This is the cheap first-stage filter: measured against the corpus it drops
    roughly 62% of traffic before anything expensive runs.
    """
    return resolve_scope(text) in ("my-area", "my-district", "city", "oblast")
