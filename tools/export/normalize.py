"""Text normalization for Telegram monitoring-channel messages.

Channel posts carry a lot of noise that is irrelevant to threat extraction:
zero-width characters, decorative emoji, and trailing promo footers
("Subscribe", bot links, ad markers). Stripping it here keeps the
gazetteer and the classifier from learning channel-specific boilerplate.

Normalization is deliberately conservative: when in doubt, keep the text.
Losing a toponym is far worse than keeping a footer.
"""

from __future__ import annotations

import re

# Characters Telegram clients insert that carry no meaning.
_INVISIBLE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060\ufeff]"
)
_NBSP = re.compile("[\u00a0\u2007\u202f]")

# Promo markers. A trailing line is dropped only if it matches one of these
# AND carries little other content — see _is_footer_line.
_PROMO_PATTERNS = [
    r"підпис(атися|атись|уйся|ка)",
    r"підпишись",
    r"наш(і)?\s+(бот|канал|чат)",
    r"реклам[ауи]",
    r"співпраця",
    r"надіслати\s+новин",
    r"запропонувати\s+новин",
    r"прислати\s+новин",
    r"бот\s+для\s+зв.язку",
    r"^\s*@[\w_]+\s*$",
    r"^\s*https?://\S+\s*$",
    r"^\s*t\.me/\S+\s*$",
]
_PROMO = re.compile("|".join(_PROMO_PATTERNS), re.IGNORECASE)

# Emoji / symbol runs used purely as decoration.
_DECOR = re.compile(
    "["
    "\U0001f000-\U0001faff"   # emoji, pictographs, symbols
    "\u2600-\u27bf"           # misc symbols & dingbats
    "\u2b00-\u2bff"           # arrows & geometric extras
    "\u2190-\u21ff"           # arrows
    "\ufe0f\u20e3\u25aa-\u25ff"  # variation selector, keycap, geometric
    "]+"
)


def _strip_decor(line: str) -> str:
    return _DECOR.sub(" ", line).strip()


def _is_footer_line(line: str) -> bool:
    """True if the line is promo boilerplate rather than content.

    Requires a promo marker AND that the line is mostly that marker —
    a sentence that merely mentions a bot is content, not a footer.
    """
    if not _PROMO.search(line):
        return False
    residue = _PROMO.sub(" ", _strip_decor(line))
    residue = re.sub(
        r"[\s|/:,.!()\[\]\\\u2013\u2014\u2022\u00b7-]+", "", residue
    )
    return len(residue) <= 12


def strip_footer(text: str) -> str:
    """Drop trailing promo lines, keeping everything above them."""
    lines = text.split("\n")
    while lines:
        tail = lines[-1]
        if not tail.strip() or _is_footer_line(tail):
            lines.pop()
            continue
        break
    return "\n".join(lines)


# Ukrainian is written with an apostrophe and the channels use four different
# characters for it: U+0027 in most messages, U+02BC and U+2019 in a few hundred,
# and sometimes none at all. His call, and the right one -- fold them at the
# boundary rather than spell out variants in every rule downstream: "може
# заміняй всі апострофи на якийсь один стандартний на самому початку, щоб потім
# не морочитись з трьома різними в правилах".
#
# The gazetteer strips apostrophes on both sides already, so places were never
# affected. What was is anything written as a plain pattern -- `REAPPEAR_TERMS`
# carried "з'явив" and "зявив" by hand and still missed the other two forms.
_APOSTROPHES = re.compile("[" + chr(0x2019) + chr(0x02BC) + chr(0x2018)
                          + chr(0x00B4) + chr(0x0060) + "]")
APOSTROPHE = chr(39)


def fold_apostrophes(text: str) -> str:
    return _APOSTROPHES.sub(APOSTROPHE, text or "")


def normalize_text(raw: str | None) -> str:
    """Normalize a raw message body into comparable, analyzable text.

    Collapses whitespace, removes invisible characters, folds every apostrophe
    variant onto one, and strips promo footers. Line structure is preserved (blank-line-separated blocks
    become single newlines) because monitoring channels use one line per
    target group, and that grouping is a real signal.
    """
    if not raw:
        return ""
    text = fold_apostrophes(_INVISIBLE.sub("", raw))
    text = _NBSP.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = strip_footer(text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


def content_fingerprint(text: str) -> str:
    """Loose fingerprint for cross-channel duplicate detection.

    Three channels reporting the same event rarely use identical wording,
    but they do reuse the same tokens. Lowercased, punctuation-free,
    decor-free text is a cheap first-pass key; semantic dedup comes later.
    """
    text = _strip_decor(normalize_text(text)).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())
