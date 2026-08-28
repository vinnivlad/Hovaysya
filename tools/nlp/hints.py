"""Threat type, alarm class, and modality guesses from message text.

These are *hints*: they pre-fill the labeler so a night can be labeled quickly,
and they become the first draft of the stage-6 baseline. They are deliberately
rule-based and readable — after a false alarm you must be able to see exactly
which rule fired.

Every list here came out of the corpus (docs/pattern-findings.md), including the
threat names a hand-written guess missed: Бандероль, Циркон, Іскандер-К,
Кинджал, Гербера, КН-23, and the slang мопед.
"""

from __future__ import annotations

import re

from .gazetteer import flatten, place_spans

# Ordered by specificity — the first match wins, so a jet Shahed is not read as
# a plain one, and Iskander is not read as generic "ракета".
THREAT_RULES: tuple[tuple[str, str], ...] = (
    ("ballistic", r"балісти|іскандер|кн-?23|брсд|кинжал|кинджал|циркон"),
    # The boundaries around "кр" are load-bearing: the channels abbreviate
    # крилата ракета that way, and without them it also matches Крушинка,
    # кружляють, and Крим.
    ("cruise", r"крилат|калібр|х-?101|х-?59|х-?55|бандерол|\bкр\b|\bкрів\b"),
    ("shahed-jet", r"реактив"),
    ("kab", r"\bкаб\b|\bкар\b|керован(а|их|ої)\s+авіабомб"),
    # Any other aviation is not a threat class. A bomber taking off triggers no
    # alert — the alert arrives with the cruise missiles it launches, and those
    # have their own class. Kept only so such a message can still be typed.
    # "Відбій авіаційної небезпеки" read as a FULL all-clear because no
    # threat class matched "авіаційної" — so a partial lift announced the
    # alert was over.
    ("aviation", r"авіаці[йї]н\w*|тактичн\w*\s+авіаці|су-?34|"
                 r"ту-?\s?(95|160|22)|бомбардувальник|"
                 r"стратегічн\w*\s+авіаці|ворожий борт|\bборт(и|ів)\b"),
    ("recon", r"розвідувальн|розвідник|гербер"),
    ("shahed", r"шахед|герань|мопед|\bбпла\b|дрон"),
    ("cruise", r"\bракет"),  # a bare "ракета" after the specific names failed
)

_THREAT = tuple((kind, re.compile(pat, re.IGNORECASE)) for kind, pat in THREAT_RULES)

# A MiG-31K has two states, and the transition between them is the point.
#
#   carrier up  ->  mig        the whole country is alerted, because it can
#                              release a Kinzhal anywhere along its route; it
#                              also sometimes lands without launching
#   launched    ->  ballistic  the missile is flying, and nothing about the
#                              aircraft matters any more
#
# This is intended behaviour, not a workaround for a pattern collision, so it
# lives outside the ordered rule list rather than being folded into it. The
# takeoff boilerplate reads "МіГ-31К — носій аеробалістичної ракети", which any
# ballistic pattern matches even though nothing is flying — so the carrier
# state must win until a launch is actually mentioned.
# Anticipation, not occurrence: a warning that something *may* be launched or
# used. Checked before every other certainty rule because the phrase contains
# the same words an actual event does.
# Anticipation, not occurrence: a warning that something *may* be launched
# or used, or a forecast covering the next hours or days. The user's note on
# one of these: "Здавалося б що загроза балістики, але ні! Попередження на
# наступні 2 дні просто."
_ANTICIPATED = re.compile(
    r"загроз\w*\s+(пуск|застосув|використ|удар|атак)|"
    r"можлив\w*\s+(пуск|застосув|удар)|"
    r"може\s+атакувати|можуть\s+атакувати|"
    r"ризик\w*\s+(пуск|застосув)|"
    r"ймовірн\w*|"
    r"протягом\s+\d+\s+(годин|діб|дні)|"
    r"на\s+наступн\w*|прогноз|"
    r"загроза\s+балісти|загроза\s+застосування",
    re.IGNORECASE,
)

_MIG = re.compile(r"м[іi]г-?\s?31", re.IGNORECASE)
_LAUNCHED = re.compile(r"пуск|запуск|стартув|випустив|відпрац", re.IGNORECASE)

# Four sounds, one per reaction class. A jet Shahed is several times faster than
# a propeller one and leaves far less time, so it gets its own tone rather than
# sharing the drone one — the point of separate sounds is knowing what is coming
# before you open your eyes.
# Six sounds, one per reaction class, ordered by how little time each leaves.
# `aviation` deliberately has none: a bomber takeoff needs no reaction, so an
# audible channel for it would only train the user to ignore the app.
ALARM_FOR_THREAT = {
    "ballistic": "ballistic",
    "mig": "mig",
    "cruise": "cruise",
    "kab": "cruise",
    "shahed-jet": "drone-jet",
    "shahed": "drone",
    "recon": "recon",
    "aviation": "none",
    "mixed": "ballistic",
    "unknown": "drone",
    "none": "none",
}

# Threats whose alert is country-wide regardless of any place named. A MiG-31K
# takeoff mentions a Russian airfield and no Ukrainian target, so a purely
# geographic filter would drop it — yet it is exactly when the whole country is
# put under alert.
NATIONWIDE_THREATS = frozenset({"mig", "ballistic"})

# Live threat is recognised by SHAPE, not by alarm words: these channels write
# telegraphically ("1х Центр.", "Жуляни ✈️") with no "загроза" anywhere. Keying
# on vocabulary alone left 78% of district messages unclassified.
_THREAT_WORD = (
    r"(шахед|бпла|ракет|балісти|циркон|іскандер|кинжал|кинджал|каб\b|"
    r"герань|бандерол|гербер|ціл[ьі]|мопед|реактив)"
)
LIVE_SHAPES: tuple[tuple[str, str], ...] = (
    ("count-marker", r"\b\d+\s*[хx]\b"),
    ("threat-toward-place", _THREAT_WORD + r".{0,40}\b(на|над|з|через|курсом)\b"),
    ("place-with-threat", r"\b(на|над)\b.{0,25}" + _THREAT_WORD),
    ("movement", r"продовжує рух|залітає|залетіл|наближ|прямує|рухається|"
                 r"зміна курсу|вектор|\bдалі\b|[ву]\s+бік|\bпадає|\bпадают|"
                 r"падаєт|перелеті|пролеті|проліта|вилеті|вилітає|заходить|"
                 r"розверн|вертаються|кружля|намота|зниження|\bколо\b"),
    # Place-to-place movement carries no threat word at all:
    # "З Теремки на Віта-Литовська." — 146 such statements in the corpus.
    ("place-to-place", r"\bз\s+[А-ЯЇІЄҐ][^,.]{1,28}?\s+на\s+[А-ЯЇІЄҐ]"),
    # A takeoff or launch report is structural evidence in its own right.
    # Without this, "Виліт винищувача МіГ-31К з аеродрому Саваслейка" matched
    # only `emoji-with-place` and counted as weak — as if the evidence were
    # the ⚠️ rather than the word "Виліт".
    ("launch", r"\bвиліт|\bвилет|\bвихід|\bзліт|\bстарт|\bпуск|\bзапуск"),
    ("phase-word", r"курсом|на підльоті|підліт|пуск|швидкісн|в укрит|уважно|"
                   r"уважн|загроза|тривог"),
)
_LIVE = tuple((name, re.compile(pat, re.IGNORECASE)) for name, pat in LIVE_SHAPES)

_THREAT_BESIDE_PLACE = re.compile(_THREAT_WORD, re.IGNORECASE)

# Consequence-management vocabulary. Measured 20-56 min from the nearest live
# threat, so it is genuinely retrospective and safe to treat as aftermath.
AFTERMATH_TERMS = (
    "пожеж", "рятувальн", "дснс", "постраждал", "поранен", "загинул", "загибл",
    "пошкодж", "вибило", "уламк", "наслідк", "ліквідовано", "евакуа", "обвал",
    "медик", "швидка допомог", "кличко", "розбор завал", "загорян",
    # Each of these woke the user in the dense night and should not have:
    # "зруйновано Епіцентр біля ДВРЗ", "рф знищила на Київщині склад".
    "зруйнован", "знищила", "знищено склад", "вигорі", "відбудов",
)

# Coming down, right now. Narrow on purpose: only this one word, and only over
# his own home. Widening it to the whole ring and the whole impact vocabulary
# cost two false wake-ups on the dense night — "Вишневе, Боярка — падає!" and a
# building damaged in Holosiiv — and he cut it back himself: "давай поки тільки
# падає жуляни".
#
# `збито` is deliberately absent. Shot down is the good news.
FALLING_TERMS = ("падає", "падають", "падаєт", "падают")

# NOT aftermath. "вибух" and "влучання" sit 1.8-2.2 min from live danger, and
# 88% of "вибух" messages arrive within ten minutes of one — an explosion report
# usually means the wave is still in progress.
IMPACT_TERMS = ("вибух", "влучан", "детонац", "приліт")

SUMMARY_TERMS = (
    "за добу", "за ніч", "за минулу ніч", "протягом ночі", "протягом доби",
    "протягом 24", "підсумк",
    "станом на", "ворог запустив", "за даними", "всього збито", "зафіксовано за",
    "в ніч на",
    # "У ніч на 05.08.26, згідно зі звітом Повітряних Сил..." — the morning
    # report, which named enough missiles to read as a live ballistic wave.
    "згідно зі звіт", "звітом повітряних сил", "вночі рф", "вночі ворог",
    # Long-range forecasts. They look exactly like an imminent launch threat to
    # every field — "Загроза балістичного удару по Києву протягом 48 годин" is
    # `live-threat`, `probable`, `ballistic` — and the only thing separating
    # them is the horizon. It matters now that an anticipated threat writes a
    # line into the status: a two-day forecast must not sit there saying
    # "Загроза: балістика" all night.
    "48 годин", "годин", "може атакувати", "можуть атакувати",
    "найближчої доби", "найближчу добу", "наступної доби", "наступні 2 дні",
)

# Not about an air threat at all: fundraising, channel social, civil news.
# Checked BEFORE aftermath, because a donation drive for wounded soldiers
# contains "постраждал" and would otherwise be filed as strike aftermath.
SOCIAL_TERMS = (
    "аукціон", "ставка", "задонат", "донат", "monobank", "send.mono", "банк",
    "дякую", "підтримку", "мітинг", "розігру", "картки", "грн", "збір",
    "реабілітац", "фонд", "підрозділ", "надіслати матеріал", "дтп",
    "передплат", "патреон", "реквізит", "прошу допомог",
)

RESOLUTION_CLOSING = ("чисто", "збито", "збили", "збиття", "мінус", "відбій")
RESOLUTION_UNKNOWN = ("локаційно втрачено", "без фіксації", "дорозвідка", "втрачено")


def _low(text: str) -> str:
    return (text or "").lower()


def threat_hint(text: str) -> str:
    """Best guess at what is flying. `none` when nothing suggests a threat."""
    if _MIG.search(text or "") and not _LAUNCHED.search(text or ""):
        return "mig"
    for kind, rx in _THREAT:
        if rx.search(text or ""):
            return kind
    return "none"


def cleared_class(text: str) -> str | None:
    """Which threat class a partial all-clear lifts, or None.

    "Відбій загрози МіГ-31К" lifts `mig`; "По балістиці відбій" lifts
    `ballistic`. Nothing needs to be typed for this — the class named next to
    the all-clear word is the one being lifted, which is the same positional
    reading `active_threat` uses to find what is *still* flying.

    It is worth recording separately because neither existing field can carry
    it: `threat` means what is in the air, and the whole point of a partial
    clear is that this class no longer is.
    """
    if not partial_clear(text):
        return None
    low = _low(text)
    clear_at = min(
        (low.find(t) for t in ALERT_CLEAR_TERMS if t in low), default=-1
    )
    if clear_at < 0:
        return None
    nearest, best = None, None
    # `mig` is checked ahead of the rule list in `threat_hint`, so scanning only
    # `_THREAT` never finds it — and "Відбій загрози МіГ-31К" is the commonest
    # partial clear there is.
    for kind, rx in ((("mig", _MIG),) + _THREAT):
        for m in rx.finditer(text):
            dist = abs(m.start() - clear_at)
            if best is None or dist < best:
                nearest, best = kind, dist
    return nearest


def active_threat(text: str) -> str:
    """The threat that is still flying, ignoring one that was just called off.

    "⚪️По балістиці відбій. / ⚠️2 шахеди на Чорноморськ" names two classes: one
    is being lifted, the other is in the air. Ordered matching answers with
    whichever appears in the rule list first, which is the wrong one here.

    Resolved positionally: a class named next to the all-clear word is the one
    being lifted, so anything named further away wins.
    """
    text = text or ""
    if not partial_clear(text):
        return threat_hint(text)

    low = text.lower()
    clear_at = min(
        (low.find(t) for t in ALERT_CLEAR_TERMS if t in low), default=-1
    )
    if clear_at < 0:
        return threat_hint(text)

    # Nearest to the all-clear word is the class being lifted; anything else is
    # still in the air. A fixed distance window does not work — in
    # "По балістиці відбій. / 2 шахеди на Одесу" both classes sit within a
    # couple of dozen characters of it.
    found: list[tuple[int, str]] = []
    for kind, rx in ((("mig", _MIG),) + _THREAT):
        for m in rx.finditer(text):
            found.append((abs(m.start() - clear_at), kind))
    if not found:
        return threat_hint(text)
    found.sort()
    lifted = found[0][1]
    for _dist, kind in found:
        if kind != lifted:
            return kind
    # Only the lifted class is named, so nothing is stated as flying. Saying
    # `mig` here would claim a MiG is up in the message announcing it is not.
    return "none"


def alarm_for(threat: str) -> str:
    return ALARM_FOR_THREAT.get(threat, "drone")


# An air-alert declaration or all-clear is the frame of the whole night: without
# it there is no way to tell when a threat passed. These messages routinely name
# no place at all — "Відбій, усім солодких снів" — so a geographic filter drops
# them, which hid 245 of the corpus's 658 alert-state messages.
ALERT_ON_TERMS = ("тривог",)
ALERT_CLEAR_TERMS = ("відбій",)


# Direction relative to the reference location. The user's rule, after a night
# of labelling: "якщо видно, що воно летить з Крюківщини в мою сторону — то
# краще б зреагувати, а якщо просто літає в тій стороні, то і не обов'язково,
# якщо то дрон."
#
# So position is not enough: a drone *in* the ring and a drone *heading into* it
# are different decisions. Nothing in `scope` or `certainty` carries that, which
# is why two labels on Kriukivshchyna looked like a contradiction when they were
# a real distinction.
#
# This is parsing, not inference. The channels state direction outright — 146
# "з A на B" statements in the corpus alone — and a parsed direction is
# auditable in a way a guessed one is not.
NEAR_TIERS = ("my-area", "my-district")

_DEST_MARKERS = (
    "курсом на", "в сторону", "у сторону", "в бік", "у бік", "в напрямку",
    "у напрямку", "залітає у", "залітає в", "залітають у", "далі", "на",
)
_ORIGIN_MARKERS = ("з ", "із ", "від ", "повз ", "через ")
_LOITER_MARKERS = ("кружля", "намотув", "довкола", "подовжують", "вертаються")


def _role_of(flat: str, start: int) -> str:
    """Whether the place at `start` is being named as a destination or origin.

    Looks back a short way for the preposition that governs it. Longest marker
    wins, so "в сторону" is not read as the bare "на" that follows it.
    """
    window = flat[max(0, start - 22):start]
    best, role = 0, "position"
    for marker in _DEST_MARKERS:
        if window.rstrip().endswith(marker) and len(marker) > best:
            best, role = len(marker), "dest"
    for marker in _ORIGIN_MARKERS:
        if window.rstrip().endswith(marker.strip()) and len(marker.strip()) > best:
            best, role = len(marker.strip()), "origin"
    return role


def heading(text: str) -> str:
    """`toward` | `away` | `loitering` | `position` | `unknown`.

    Relative to the near ring, never in the abstract: "toward" means toward the
    user, and a message about two distant places is `unknown` however clearly it
    states a direction.
    """
    flat = flatten(text)
    spans = place_spans(text)
    if not spans:
        return "unknown"

    dests_near = origins_near = near_present = False
    far_dest_at: int | None = None
    near_pos_at: int | None = None
    for start, _end, place in spans:
        near = place.tier in NEAR_TIERS
        near_present = near_present or near
        role = _role_of(flat, start)
        if role == "dest":
            if near:
                dests_near = True
            elif far_dest_at is None:
                far_dest_at = start
        elif role == "origin" and near:
            origins_near = True
        elif near and near_pos_at is None:
            near_pos_at = start

    if dests_near:
        return "toward"
    if origins_near and far_dest_at is not None:
        return "away"
    # "Жуляни далі Центр" — the first place is the implicit origin, marked by
    # nothing but its position before the destination.
    if near_pos_at is not None and far_dest_at is not None and near_pos_at < far_dest_at:
        return "away"
    if near_present and any(m in flat for m in _LOITER_MARKERS):
        return "loitering"
    if near_present:
        return "position"
    return "unknown"


def partial_clear(text: str) -> bool:
    """An all-clear for one threat class while the alert itself continues.

    "⚪️ Відбій загрози МіГ-31К" and "⚪️По балістиці відбій" lift one part of a
    situation, not the situation. Reading them as the end of the alert both
    announces safety that does not exist and closes an episode that is still
    running, which loses the repeat logic for everything that follows.
    """
    if not any(t in _low(text) for t in ALERT_CLEAR_TERMS):
        return False
    return threat_hint(text) != "none"


# Waiting for a siren or an all-clear, not having one. His rule and his
# observation — "там є слово Очікує, інші випадки теж його мали" — and it holds
# across the whole corpus: of 23 messages pairing an awaiting word with `відбій`
# or `тривога`, not one is a real event. Every one is a forecast:
#
#   ⚪️Київ очікує на ймовірний відбій.       announced the all-clear mid-alert
#   🔴Київ очікує на повітряну тривогу через 10-15 хвилин.    rang the siren
#   ⚪️Борти МіГ-31К розвернулись, очікуємо на відбій.
#
# A stem rather than a word list, also on his instruction — "очікуваний
# очікуване очікуємо і тд". My own attempt was a window regex, and it broke the
# moment a word was inserted between "очікує" and "відбій", which is exactly how
# the false all-clear got through.
# `скоро` and `ймовірн` are his additions, and the second is the stronger of the
# two by a distance: of five messages pairing `ймовірн` with a siren word, four
# were being read as a declared alert and not one of them is a siren — a Russian
# test range, a forecast for tomorrow, a poll about parking during an alert, and
# the author's own commentary.
AWAITING_TERMS = (
    "очіку", "чекає", "чекаємо", "чекайте", "чекати",
    "скоро", "незабаром", "ось-ось", "ймовірн", "імовірн",
)

# The forms the channels use to state the event itself, never to forecast it.
CANONICAL_SIREN = ("відбій тривоги", "відбій повітряної тривоги",
                   "- тривога", "— тривога", "оголошено повітряну тривогу")


def alert_state(text: str) -> str | None:
    """`clear`, `alert`, or None — whether this message is about the siren.

    All-clear is checked first: "По балістиці відбій" is an all-clear even
    though a live threat may continue, and reading it as a declaration would
    invert the meaning.
    """
    low = _low(text)
    # "Київ очікує на відбій" is waiting for one, not having one. Reading it as
    # an all-clear produced a false wake-up telling the user it was over while
    # a drone was still up.
    # Waiting for one, not having one. A substring list broke on any inserted
    # word — "Київ очікує на ймовірний відбій" slipped through and announced
    # the all-clear during a live alert, which is the worst thing this can say.
    # ...unless the message also carries the canonical formula, which is never
    # a forecast. `ймовірн` is a broad stem, and a real "🟢 ВІДБІЙ ТРИВОГИ"
    # that happens to say "ймовірно збито" beside it must still be an
    # all-clear. It has not occurred in 4.5 months; it costs one line to make
    # sure it never matters.
    if _hits(text, AWAITING_TERMS) and not _hits(text, CANONICAL_SIREN):
        return None
    # The mirror case, and it woke the user for nothing: "У Києві у найближчі
    # хвилини можуть оголосити повітряну тривогу" is a forecast of a siren, and
    # he wrote "Можуть оголосити! Ще не зрозуміло нічого". A siren that may be
    # declared is not a siren.
    if any(t in low for t in ("можуть оголосити", "може бути оголошен",
                              "буде оголошен", "очікуємо тривог",
                              "можлива тривога", "можуть дати тривог",
                              # Found live, and it woke him: "Київ очікує на
                              # повітряну тривогу через 10-15 хвилин". The
                              # mirror guard covered "очікує на відбій" only.
                              "очікує на повітряну тривог",
                              "очікує на тривог", "очікуємо на тривог",
                              "чекаємо на тривог", "перед тривогою")):
        return None
    if any(t in low for t in ALERT_CLEAR_TERMS):
        return "clear"
    if any(t in low for t in ALERT_ON_TERMS):
        return "alert"
    return None


def nationwide(text: str) -> bool:
    """True when the threat is country-wide *because no target is named yet*.

    A ballistic launch or a MiG-31K takeoff names a Russian airfield and no
    Ukrainian target, and at that moment it threatens everyone — dropping it for
    lack of local geography would hide the one signal that alerts the country.

    But the moment a target is stated it stops being country-wide.
    "Балістична ракета на Запоріжжя" is a fact about Zaporizhzhia. Treating
    every ballistic message as nationwide put 30 other-region messages in front
    of the user during labelling, and they were dutifully labelled — pure waste
    caused by this function being too generous.
    """
    if threat_hint(text) not in NATIONWIDE_THREATS:
        return False
    # A resolved Ukrainian place means the target is known. Russian launch sites
    # resolve as `elsewhere` too, so ask specifically whether any *Ukrainian*
    # location was named.
    from .gazetteer import find_places

    for place in find_places(text):
        if place.tier != "elsewhere":
            return True  # named locally: relevant, and geography handles it
        if place.name not in _launch_origins():
            return False  # a target in another region: not our business
    return True


# Launch origins come from the gazetteer, where the fact belongs. Keeping a
# second list here went stale the moment Voronezh and Oryol were added as
# places: a real ballistic launch from Voronezh read as "a target in another
# region" and was silenced as too far.
def _launch_origins() -> frozenset[str]:
    from .gazetteer import launch_origins

    return launch_origins() | {"російські аеродроми", "Крим"}


def live_shapes(text: str) -> list[str]:
    """Which structural live-threat templates the text matches, if any."""
    found = [name for name, rx in _LIVE if rx.search(text or "")]
    if is_bare_place_list(text):
        found.append("bare-place-list")
    if has_marker_emoji(text) and place_spans(text):
        found.append("emoji-with-place")
    # A threat word beside a resolved place, with no preposition between them:
    # "Святошин реактив", "Десна підліт реактива", "Бровари два реактива". The
    # prepositional shapes above wanted `на` or `над` and these have neither.
    if _THREAT_BESIDE_PLACE.search(text or "") and place_spans(text):
        found.append("threat-with-place")
    return found


_TOKEN_SPLIT = re.compile(r"[^а-яіїєґёa-z0-9]+", re.IGNORECASE)

# Words that can pad a bare toponym list without making it prose.
_FILLER = frozenset((
    "уважно", "уважн", "увага", "також", "далі", "ще", "і", "та", "на", "в",
    "у", "через", "над", "з", "бік", "сторону", "район", "районі", "масив",
    "все", "весь", "столиці", "столиця", "перші", "нові", "нова", "забудова",
    "зустрічайте", "курс", "сторону", "вже", "знову", "теж",
))


def is_bare_place_list(text: str) -> bool:
    """True when the message is essentially just place names.

    `kievinform_ua1` reports this way — `Жуляни ✈️`, `Дарниця, Чоколівка`,
    `Іподром, Теремки, Жуляни`. There is no threat word anywhere, yet these are
    live reports; keying only on vocabulary classified 38.6% of my-area messages
    as non-threat. The emoji is the predicate.

    Implemented by subtracting the resolved place spans and asking what content
    survives, filler words aside. Tokenised rather than regex-substituted: a
    single-letter filler like "з" applied as a pattern would eat that letter out
    of real words and make the test far too permissive.
    """
    spans = place_spans(text)
    if not spans:
        return False
    flat = flatten(text)
    kept, cursor = [], 0
    for span_start, span_end, _place in spans:
        kept.append(flat[cursor:span_start])
        cursor = span_end
    kept.append(flat[cursor:])
    tokens = [t for t in _TOKEN_SPLIT.split(" ".join(kept)) if t]
    residue = "".join(t for t in tokens if t not in _FILLER)
    return len(residue) <= 3


# Marker emoji the channels use as the predicate of a bare report. Documented
# in docs/pattern-findings.md: "Жуляни ✈️" has no verb — the emoji is the verb.
# Relied on here because a report can survive an unknown toponym or a typo
# ("Жушяни/Вишневе🚀") and still be unmistakably live.
MARKER_EMOJI = (
    "⚠",      # warning
    "🚀",  # rocket
    "✈",      # airplane
    "💥",  # collision
    "🔴",  # red circle
    "🅿",  # negative squared P — war_monitor section header
    "❗",      # exclamation
    "‼",      # double exclamation
    "🚨",  # siren
    "🔄",  # arrows (loitering)
)


def has_marker_emoji(text: str) -> bool:
    return any(e in (text or "") for e in MARKER_EMOJI)


# Shapes that stand on their own. `emoji-with-place` is deliberately absent:
# measured over the corpus, ⚠️ appears on 26.0% of all messages and 93% of those
# already match another shape, so it discriminates almost nothing. Where it is
# the sole evidence (593 messages, 5.1%) it is right about 95% of the time —
# useful for recall, not trustworthy enough to act on alone. A fundraising post
# ("🚨Терміновий збір для ГУР МОУ на далекобійні FPV дрони🚨") clears it.
STRONG_SHAPES = frozenset({
    "count-marker",
    "launch",
    "threat-with-place",
    "threat-toward-place",
    "place-with-threat",
    "movement",
    "place-to-place",
    "phase-word",
    "bare-place-list",
})


def live_strength(text: str) -> str:
    """`strong` | `weak` | `none` — how much the live-threat reading is worth.

    The policy consequence, enforced in the baseline rather than here: weak-only
    evidence may raise `info` or `alert`, never `shelter`. Waking someone at
    full volume on an emoji is not acceptable at 3 a.m.
    """
    shapes = set(live_shapes(text))
    if shapes & STRONG_SHAPES:
        return "strong"
    if shapes:
        return "weak"
    return "none"


def falling(text: str) -> bool:
    """Whether the message says something is coming down."""
    return _hits(text, FALLING_TERMS)


def looks_live(text: str) -> bool:
    return bool(live_shapes(text)) or is_bare_place_list(text)


def _hits(text: str, terms) -> bool:
    low = _low(text)
    return any(t in low for t in terms)


_DONATION_OPENER = re.compile(r"^\s*[^\w]{0,4}донат\s*\d", re.IGNORECASE)


def _strongly_social(text: str) -> bool:
    """Social content that no threat word inside it should override."""
    low = _low(text)
    if _DONATION_OPENER.match(text or ""):
        return True
    return sum(1 for t in SOCIAL_TERMS if t in low) >= 3


# Saying what *will* be attacked is a forecast, however urgent the wording.
# "🚨Під атакою реактивних шахедів буде Київ, Бровари та ймовірно Вишневе" woke
# him on the first evening of live watching: it names his own neighbour and
# nothing was in the air yet.
#
# Deliberately narrow. Several live reports carry a forecast clause — "⚠️Нові 2
# реактивні шахеди з акваторії Чорного моря на Миколаївщину, будуть атакувати" —
# and those are drones already flying. So the patterns below match the shapes
# where the forecast *is* the message, not where it trails a live report.
_FORECAST = re.compile(
    r"під атакою.{0,40}\bбуде\b|"
    r"\bатака буде\b|"
    r"ймовірні мікрорайони|"
    r"ворог (планує|готує|може завдати)|"
    r"попередження про (ймовірн|можлив)",
    re.IGNORECASE,
)


def modality_hint(text: str) -> str:
    """live-threat | aftermath | summary-news | non-threat.

    Order is the whole design. Summary is checked first because a nightly recap
    also contains threat words; impact terms are checked before aftermath so an
    explosion report is never demoted to retrospective.
    """
    if _hits(text, SUMMARY_TERMS) or _FORECAST.search(text or ""):
        return "summary-news"
    if _hits(text, IMPACT_TERMS):
        return "live-threat"
    # A donation round-up quotes its donors, and one of them wrote "Гепарди по
    # реактивним шахедам працюють" — enough to make the whole post read as a
    # live jet-drone threat. Strong social evidence therefore wins outright:
    # several markers, or the post opening as a donation list.
    if _strongly_social(text):
        return "non-threat"
    if _hits(text, SOCIAL_TERMS) and not looks_live(text):
        return "non-threat"
    if _hits(text, AFTERMATH_TERMS):
        return "aftermath"
    # Resolutions are part of the live situation, not social chatter. "Збито"
    # and "чисто" close an episode, and they are precisely the messages that
    # need the earlier context — they name neither type nor place.
    if _hits(text, RESOLUTION_CLOSING) or _hits(text, RESOLUTION_UNKNOWN):
        return "live-threat"
    if looks_live(text):
        return "live-threat"
    if threat_hint(text) != "none":
        return "live-threat"
    return "non-threat"


def certainty_hint(text: str) -> str:
    """confirmed | probable | lost | clear.

    `lost` must never collapse into `clear`: "локаційно втрачено" means we no
    longer know, which is not safety.
    """
    low = _low(text)
    if any(t in low for t in RESOLUTION_UNKNOWN):
        return "lost"
    if any(t in low for t in RESOLUTION_CLOSING):
        return "clear"
    # A bare impact report — "Вибухи 💥💥💥", "Чутно було вибух" — names no place
    # and says nothing about whether anything is still in the air. That is an
    # unknown state, not a confirmed one, and above all not safety.
    if _hits(text, IMPACT_TERMS) and not place_spans(text):
        return "lost"
    # An anticipatory warning is not an event. "Загроза пуску балістичних ракет"
    # and "Є інформація про пуск" both contain "пуск", but only the second means
    # something is in the air — and the difference decides whether a new sound
    # fires at all, so it cannot be blurred.
    if _ANTICIPATED.search(text or ""):
        return "probable"
    # A takeoff is a possibility, not a fact: the corpus has
    # "Борти МіГ-31К розвернулись на аеродром базування" as often as it has a
    # launch, and "курс поки не відомий" says so outright.
    if any(t in low for t in ("виліт", "вильот", "аеродром", "курс поки",
                              "очікуємо", "готує", "ймовірн", "попередньо",
                              "уточнюємо", "вектор")):
        return "probable"
    return "confirmed"


def suggest(text: str) -> dict[str, object]:
    """Everything the labeler pre-fills for one message.

    A live message with no threat word gets `unknown`, not `none`: the type is
    stated in an earlier message of the episode, and "we do not know what" is a
    different thing from "nothing is flying".
    """
    threat = active_threat(text)
    # Something arrived, so "nothing is flying" is the wrong default even when
    # no type is named. 105 of the corpus's 380 impact messages were pre-filled
    # as `none` before this.
    if threat == "none" and (looks_live(text) or _hits(text, IMPACT_TERMS)):
        threat = "unknown"
    # An all-clear says the opposite: nothing is flying any more. Only when no
    # type was actually named — "По балістиці відбій. 2 шахеди на Одесу" keeps
    # its shaheds.
    state = alert_state(text)
    if threat == "unknown" and state == "clear":
        threat = "none"

    # A siren is not a target. A declaration with no type stated must not
    # borrow a threat tone — sounding like a drone when nobody said drone is how
    # the tones stop meaning anything.
    if state == "clear":
        alarm = "clear"
    elif state == "alert":
        alarm = "alert"
    else:
        alarm = alarm_for(threat)

    return {
        "threat": threat,
        "strength": live_strength(text),
        "alarm": alarm,
        "heading": heading(text),
        "cleared": cleared_class(text),
        "modality": modality_hint(text),
        "certainty": certainty_hint(text),
        "shapes": live_shapes(text),
    }
