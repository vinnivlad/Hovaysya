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
    ("ballistic", r"балістик|балістичн|іскандер|кн-?23|брсд|кинжал|кинджал|циркон"),
    # The boundaries around "кр" are load-bearing: the channels abbreviate
    # крилата ракета that way, and without them it also matches Крушинка,
    # кружляють, and Крим.
    ("cruise", r"крилат|калібр|х-?101|х-?59|х-?55|бандерол|\bкр\b|\bкрів\b"),
    ("shahed-jet", r"реактивн"),
    ("kab", r"\bкаб\b|\bкар\b|керован(а|их|ої)\s+авіабомб"),
    ("aviation", r"тактичн\w*\s+авіаці|міг-?31|су-?34|ту-?95|ворожий борт|\bборт(и|ів)\b"),
    ("recon", r"розвідувальн|розвідник|гербер"),
    ("shahed", r"шахед|герань|мопед|\bбпла\b|дрон"),
    ("cruise", r"\bракет"),  # a bare "ракета" after the specific names failed
)

_THREAT = tuple((kind, re.compile(pat, re.IGNORECASE)) for kind, pat in THREAT_RULES)

ALARM_FOR_THREAT = {
    "ballistic": "ballistic",
    "cruise": "cruise",
    "kab": "cruise",
    "shahed": "drone",
    "shahed-jet": "drone",
    "aviation": "aviation",
    "recon": "aviation",
    "mixed": "ballistic",
    "unknown": "drone",
    "none": "none",
}

# Live threat is recognised by SHAPE, not by alarm words: these channels write
# telegraphically ("1х Центр.", "Жуляни ✈️") with no "загроза" anywhere. Keying
# on vocabulary alone left 78% of district messages unclassified.
_THREAT_WORD = (
    r"(шахед|бпла|ракет|балістик|циркон|іскандер|кинжал|кинджал|каб\b|"
    r"герань|бандерол|гербер|ціл[ьі]|мопед|реактив)"
)
LIVE_SHAPES: tuple[tuple[str, str], ...] = (
    ("count-marker", r"\b\d+\s*[хx]\b"),
    ("threat-toward-place", _THREAT_WORD + r".{0,40}\b(на|над|з|через|курсом)\b"),
    ("place-with-threat", r"\b(на|над)\b.{0,25}" + _THREAT_WORD),
    ("movement", r"продовжує рух|залітає|залетіл|наближ|прямує|рухається|"
                 r"зміна курсу|вектор|\bдалі\b|[ву]\s+бік|\bпадає|\bпадают|"
                 r"падаєт|перелеті|пролеті|проліта|вилеті|вилітає|заходить|"
                 r"розверн|вертаються|кружля|намотув|зниження"),
    # Place-to-place movement carries no threat word at all:
    # "З Теремки на Віта-Литовська." — 146 such statements in the corpus.
    ("place-to-place", r"\bз\s+[А-ЯЇІЄҐ][^,.]{1,28}?\s+на\s+[А-ЯЇІЄҐ]"),
    ("phase-word", r"курсом|на підльоті|підліт|пуск|швидкісн|в укрит|уважно|"
                   r"уважн|загроза|тривог"),
)
_LIVE = tuple((name, re.compile(pat, re.IGNORECASE)) for name, pat in LIVE_SHAPES)

# Consequence-management vocabulary. Measured 20-56 min from the nearest live
# threat, so it is genuinely retrospective and safe to treat as aftermath.
AFTERMATH_TERMS = (
    "пожеж", "рятувальн", "дснс", "постраждал", "поранен", "загинул", "загибл",
    "пошкодж", "вибило", "уламк", "наслідк", "ліквідовано", "евакуа", "обвал",
    "медик", "швидка допомог", "кличко", "розбор завал", "загорян",
)

# NOT aftermath. "вибух" and "влучання" sit 1.8-2.2 min from live danger, and
# 88% of "вибух" messages arrive within ten minutes of one — an explosion report
# usually means the wave is still in progress.
IMPACT_TERMS = ("вибух", "влучан", "детонац", "приліт")

SUMMARY_TERMS = (
    "за добу", "протягом ночі", "протягом доби", "протягом 24", "підсумк",
    "станом на", "ворог запустив", "за даними", "всього збито", "зафіксовано за",
    "в ніч на",
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
    for kind, rx in _THREAT:
        if rx.search(text or ""):
            return kind
    return "none"


def alarm_for(threat: str) -> str:
    return ALARM_FOR_THREAT.get(threat, "drone")


def live_shapes(text: str) -> list[str]:
    """Which structural live-threat templates the text matches, if any."""
    found = [name for name, rx in _LIVE if rx.search(text or "")]
    if is_bare_place_list(text):
        found.append("bare-place-list")
    if has_marker_emoji(text) and place_spans(text):
        found.append("emoji-with-place")
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


def looks_live(text: str) -> bool:
    return bool(live_shapes(text)) or is_bare_place_list(text)


def _hits(text: str, terms) -> bool:
    low = _low(text)
    return any(t in low for t in terms)


def modality_hint(text: str) -> str:
    """live-threat | aftermath | summary-news | non-threat.

    Order is the whole design. Summary is checked first because a nightly recap
    also contains threat words; impact terms are checked before aftermath so an
    explosion report is never demoted to retrospective.
    """
    if _hits(text, SUMMARY_TERMS):
        return "summary-news"
    if _hits(text, IMPACT_TERMS):
        return "live-threat"
    if _hits(text, SOCIAL_TERMS) and not looks_live(text):
        return "non-threat"
    if _hits(text, AFTERMATH_TERMS):
        return "aftermath"
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
    if any(t in low for t in ("ймовірн", "попередньо", "уточнюємо", "вектор")):
        return "probable"
    return "confirmed"


def suggest(text: str) -> dict[str, object]:
    """Everything the labeler pre-fills for one message.

    A live message with no threat word gets `unknown`, not `none`: the type is
    stated in an earlier message of the episode, and "we do not know what" is a
    different thing from "nothing is flying".
    """
    threat = threat_hint(text)
    if threat == "none" and looks_live(text):
        threat = "unknown"
    return {
        "threat": threat,
        "strength": live_strength(text),
        "alarm": alarm_for(threat),
        "modality": modality_hint(text),
        "certainty": certainty_hint(text),
        "shapes": live_shapes(text),
    }
