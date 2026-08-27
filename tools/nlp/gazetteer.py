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
    # A landmark names a thing, not a settlement, so its city is implied rather
    # than stated. Nearly every city has a ТЕЦ-5; ours is the one meant unless
    # the message says otherwise. See `resolve_scope`.
    landmark: bool = False


def _p(name: str, tier: str, *stems: str, landmark: bool = False) -> Place:
    """Declare a place. Stems are normalised the same way message text is.

    Apostrophes are stripped here so an entry can be written the readable way
    (`солом'ян`) while still matching text where the apostrophe is a different
    character, or absent.
    """
    return Place(name, tier,
                 tuple(_strip_apostrophes(s).lower() for s in stems),
                 landmark)


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
    # `Голос` is how kievinform_ua1 abbreviates it — "Хотів - Голос - Солома в
    # укриття". Safe as a stem: the word-start check blocks it inside
    # "оголосити" and "проголосували", which is where the risk would be.
    # "голосно" and "голосування" would match, and do not occur once in 4.5
    # months of these channels; "Голос" meaning Holosiiv occurs six times.
    _p("Голосіїв", "city", "голосіїв", "голосієв", "голос"),
    _p("Феофанія", "city", "феофан"),
    _p("Звіринець", "city", "звіринец", "звіринц"),
    _p("Рембаза", "city", "рембаз"),
    _p("Теличка", "city", "теличк"),
    _p("Лісники", "city", "лісник"),
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
    # Found by sweeping the corpus for capitalised words in live messages that
    # resolved to no place at all. Every one of these is a Kyiv-oblast town the
    # channels track, and every mention of them was invisible on the page.
    # `oblast` carries no wake-up risk — the policy silences the tier outright —
    # so the only thing at stake was whether the user gets to see them.
    # The raion, not the city district — same reason, the other direction.
    _p("Києво-Святошинський район", "oblast", "києво-святошин"),
    _p("Требухів", "oblast", "требух"),
    _p("Гоголів", "oblast", "гоголів", "гоголев"),
    _p("Дударків", "oblast", "дударків", "дударков"),
    _p("Вишеньки", "oblast", "вишеньк"),        # on the approach from the south
    _p("Білогородка", "oblast", "білогородк"),
    _p("Кагарлик", "oblast", "кагарлиц", "кагарлик"),
    _p("Козин", "oblast", "козин"),
    _p("Ржищів", "oblast", "ржищ"),
    _p("Миронівка", "oblast", "миронівк", "миронівц"),
    _p("Богуслав", "oblast", "богуслав"),
    _p("Бородянка", "oblast", "бородян"),
    _p("Березань", "oblast", "березан"),
    _p("Іванків", "oblast", "іванків", "іванков"),
    _p("Пісківка", "oblast", "пісківк"),
    _p("Красятичі", "oblast", "красятич"),
    _p("Яготин", "oblast", "яготин"),
    _p("Дівички", "oblast", "дівичк"),
    _p("Тетіїв", "oblast", "тетіїв", "тетієв"),
    _p("Сквира", "oblast", "сквир"),
    _p("Чорнобиль", "oblast", "чорнобил"),
    _p("Десна", "oblast", "десну", "десною", "десни"),
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
    # Launch origins. Курська and Брянська were here in their adjectival form
    # only, so "з Брянщини" resolved to nowhere — and a message resolving to
    # nowhere now inherits the night's scope, which would have made a launch
    # from Russia read as a threat over Kyiv.
    _p("Воронежчина", "elsewhere", "вороне"),
    _p("Орловщина", "elsewhere", "орловськ", "орловщин", "орла", "орлі"),
    _p("Брянщина", "elsewhere", "брянщин"),
    _p("Курщина", "elsewhere", "курщин"),
    _p("Смоленщина", "elsewhere", "смоленськ", "смоленщин", "шаталово"),
    _p("Ростовщина", "elsewhere", "ростов", "таганрог"),
    _p("Білгородщина", "elsewhere", "бєлгород", "білгород"),
    _p("Білорусь", "elsewhere", "білорус", "мазир", "мозир", "гомел"),
    # Other regions the channels report on, likewise invisible before.
    # Hyphenated names whose second half is a Kyiv place. Longest match is what
    # keeps them apart: `корсунь-шевченків` claims the span before
    # `шевченків` can, so Cherkasy oblast stops reading as the user's city.
    # Kamianets-Podilskyi did exactly that nine times, as Podil.
    _p("Кам'янець-Подільський", "elsewhere", "камянець-подільськ", "камянц"),
    _p("Корсунь-Шевченківський", "elsewhere", "корсунь-шевченків"),
    _p("Сміла", "elsewhere", "сміл"),
    _p("Лубни", "elsewhere", "лубн"),
    _p("Миргород", "elsewhere", "миргород"),
    _p("Конотоп", "elsewhere", "конотоп"),
    _p("Коростень", "elsewhere", "коростен"),
    _p("Умань", "elsewhere", "умань", "умані"),
    _p("Старокостянтинів", "elsewhere", "старокостянтин"),
    _p("Вознесенськ", "elsewhere", "вознесенськ"),
    _p("Очаків", "elsewhere", "очаків", "очаков"),
    _p("Татарбунари", "elsewhere", "татарбунар"),
    _p("Затока", "elsewhere", "затоку", "затоці"),
    # Not Чабани. A village in Odesa oblast, one letter from a Kyiv-oblast
    # neighbour of the user's — and the corpus names it beside a southern port.
    _p("Чабанка", "elsewhere", "чабанк"),
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


# Named landmarks with a fixed address. These were missing entirely, and the
# cost was not theoretical: `ТЕЦ-5` is named 44 times in the corpus, more often
# than most districts, and every one of those messages resolved to `unknown`
# and vanished from the Kyiv view. The user found it himself — a reply quoting
# "На ТЕЦ-5! Падає" whose parent was nowhere on the page.
#
# `city` rather than the near ring: ТЕЦ-5 sits in Holosiiv, and the corpus shows
# it on the approach corridor to the user's home again and again
# (`З Позняків на ТЕЦ-5` -> `на Деміївку` -> `З Деміївки на Жуляни`), which is
# an argument for promoting it. That is his call to make, not mine, and `city`
# keeps the messages visible without turning each one into a wake-up.
LANDMARKS = [
    _p("Конча-Заспа", "city", "конча-заспа", "кончі-заспі", "заспа", "заспі"),
    _p("Нижні Сади", "city", "нижні сади", "нижних сад", "нижні сад"),
    # `kievinform_ua1` writes "ТЕЦ 5" with a space, `mon1tor_ua` writes "ТЕЦ-5".
    # Six occurrences went missing on the space form alone — including the one
    # sixteen seconds before the message the user came looking for.
    _p("ТЕЦ-5", "city", "тец-5", "тец 5", "тец5", landmark=True),   # Голосіїв
    _p("ТЕЦ-6", "city", "тец-6", "тец 6", "тец6", landmark=True),   # Троєщина
    _p("ТЕЦ-2", "city", "тец-2", "тец 2", "тец2", landmark=True),   # Дарниця
    _p("ТЦ Проспект", "city", "тц проспект", landmark=True),
    _p("Видубичі", "city", "видубич"),
    _p("Залісся", "oblast", "залісся"),
]

PLACES: tuple[Place, ...] = tuple(
    _with_alternations(p)
    for p in (MY_AREA + MY_DISTRICT + CITY + OBLAST + ELSEWHERE + LANDMARKS)
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
    """Whether position i begins a word, treating a hyphen as a separator.

    The channels join neighbours with a hyphen — "Яготин-Згурівка",
    "Погреби-Троєщина" — and Zhurivka was already in the gazetteer yet never
    matched, because the hyphen counted as a word character and so the second
    half of every pair was mid-word. Stems containing their own hyphen (`тец-5`)
    are unaffected: they start after a space either way.
    """
    return i == 0 or flat[i - 1] == "-" or not _WORDCHAR.match(flat[i - 1])


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
    # "Залітає у Черкаси курсом на ТЕЦ-5" is about Cherkasy's plant, not ours.
    # A landmark carries no city of its own, so a settlement named in the same
    # message outranks it — otherwise the nearest tier wins and a message about
    # another region reads as ours. One such message in 4.5 months, but it is
    # exactly the shape that produces a 3 a.m. wake-up for somebody else's city.
    settlements = [p for p in found if not p.landmark]
    if settlements and any(p.landmark for p in found):
        found = settlements
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
