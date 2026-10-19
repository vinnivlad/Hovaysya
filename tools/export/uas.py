"""The city's siren, read out of `UkraineAlarmSignal`.

The official source since 2026-10-19, in place of `alarm_kyiv`. That channel
relays the "Повітряна тривога" app's own bot, and from the evening of
2026-10-18 the bot itself fell behind: one to four minutes on most transitions
and ten on the 07:21 all-clear of the 19th, identically on `kyivalarm`, which
relays the same bot. Measured against `alarm_kyiv` while it was still on time
(2026-09-20 to 10-18 22:00), this channel carried 223 of 223 city sirens at a
median +12 s and 223 of 223 all-clears at +14 s, with nothing false.

It covers the whole country, about 1200 posts a day, of which some 16 are
about the city. So it is filtered at the door: a post that says nothing about
the city never reaches the database, the policy or the log, and one that does
is rewritten into the exact form `alarm_kyiv` used, which everything
downstream already reads -- `hints.alert_state`, the threat level, the
all-clear dedup, the start-up confirmation. One place knows this format, and
it is this file.

The format, as it is:

- A post of its own: "🟡 Київ" / "Жовтий рівень тривоги. Прямуйте в укриття!"
- Or sections, each a heading and the places under it, several events to a
  post: "🟡 Жовтий рівень тривоги", "🔴 Червоний рівень тривоги",
  "🟡 Відбій червоної тривоги", "🟢 Відбій тривоги". Places carry a bullet
  since about 2026-09-26 and stood on bare lines before.
- The city is the line "Київ" and nothing else. Every place in the oblast,
  Київ-named or not, carries "(Київська обл.)".

The sections come in a fixed order and not in the order things happened, so a
post can lift the city and declare it again without saying which came last.
That is read as the siren: once in a month (2026-10-18 20:00:46), and the siren
was the truth.

"🛸 Київ", "🚀 Київ" and "⚠️ Київ" -- drones, fast targets, explosions in the
press -- are threat notices, not the siren, and are dropped. The chats carry
what is flying; whether the official "🚀" should count as a ballistic warning is
a policy question nobody has asked yet.
"""

from __future__ import annotations

from dataclasses import replace

from .store import Msg

CHANNEL = "UkraineAlarmSignal"

# What `alarm_kyiv` said, word for word, for each thing this channel can say.
YELLOW = "🟡 Київ\nПовітряна тривога · жовтий рівень\nДронова загроза"
RED = "🔴 Київ\nПовітряна тривога · червоний рівень\nРакетна загроза"
LOWER = "🟡 Київ\nРівень знижено до жовтого\nДронова загроза"
CLEAR = "🟢 Київ\nВідбій повітряної тривоги"

_SINGLE = {"🟡 Київ": YELLOW, "🔴 Київ": RED, "🟢 Київ": CLEAR}
_HEADINGS = {
    "🟡 Жовтий рівень тривоги": YELLOW,
    "🔴 Червоний рівень тривоги": RED,
    "🟡 Відбій червоної тривоги": LOWER,
    "🟢 Відбій тривоги": CLEAR,
}
# Which one wins when the city stands under several headings of one post: a
# siren over anything else, and the higher level over the lower.
_RANK = (RED, YELLOW, LOWER, CLEAR)


def city_says(text: str) -> str | None:
    """The city's part of a post, in `alarm_kyiv`'s words, or None."""
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    if not lines:
        return None
    if lines[0] in _SINGLE:
        return _SINGLE[lines[0]]
    said = set()
    section = None
    for line in lines:
        if line in _HEADINGS:
            section = _HEADINGS[line]
            continue
        place = line[1:].strip() if line.startswith("•") else line
        if place == "Київ" and section is not None:
            said.add(section)
    return next((form for form in _RANK if form in said), None)


def adapt(messages: list[Msg]) -> list[Msg]:
    """This channel's posts reduced to the city's, every other channel as is."""
    out = []
    for msg in messages:
        if msg.channel != CHANNEL:
            out.append(msg)
            continue
        form = city_says(msg.text_raw)
        if form is not None:
            out.append(replace(msg, text_raw=form))
    return out
