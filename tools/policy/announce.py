"""Turn decisions into spoken Ukrainian, queued in arrival order.

His design, stated outright:

    Повідомлення ставляться в чергу. Якщо прилітають "Загроза балістики" і
    слідом "Вихід на Київ", то я хочу почути що почалась тривога по балістиці і
    потім що був пуск. Якщо просто "Тривога", "Загроза балістики", то почути що
    почалась тривога, а потім по балістиці. Скоріше за все, ці звуки будуть не
    просто звуки, а слова.

Two things follow, and both are the point.

**An utterance says the whole situation.** It used to say only what had changed,
which reads well and cost him an hour: "Жуляни, Вишневе, Теремки" came out as
"Вишневе, Теремки." because Zhuliany had been named seven minutes earlier, and he
went looking for a bug in the rule that had fired correctly. A sentence that
depends on what he heard earlier is a sentence he cannot check.

The siren is the exception and stays once-only: the word belongs to a declaration,
and repeating it would claim a new alert each time.

**Nothing is dropped.** A tone that arrives while another is playing is lost; a
sentence waits its turn. So this is a queue, not a channel, and the policy's
decision to notify is separate from the wording — `alarm` still names the
reaction class, which is what picks the lead-in sound.

The queue is deliberately not de-duplicated here. The policy has already decided
what is worth saying; making that judgement twice, in two places, is how the two
drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .episodes import Observation
from .rules import Decision

# What to call each class out loud. Not the internal name: he hears these at
# three in the morning and has to act on them without thinking.
def _all_places(text: str):
    from ..nlp.gazetteer import find_places

    return [p for p in find_places(text) if not p.origin]


# How stale the remembered cause may be before it stops explaining a siren.
#
# Five minutes was his first number and covered 67% of the alerts where the
# channels spoke first. Ten covers 77%, and takes in the case that prompted the
# change: seven minutes before a siren the channels said "2 реактивні шахеди на
# Київ/Вишгород з півночі" and the siren still came out without a place. The
# median lead is 2.1 minutes; the mean is 5.7, because the tail is long.
PENDING_HORIZON_S = 10 * 60

CLASS_WORD = {
    "ballistic": "балістика",
    "cruise": "крилаті ракети",
    "kab": "керовані бомби",
    "mig": "МіГ-31",
    "shahed": "шахед",
    "shahed-jet": "реактивний шахед",
    "recon": "розвідник",
    "aviation": "авіація",
    "mixed": "комбінований удар",
}

# The genitive, for "тривога по <class>" and "відбій по <class>".
CLASS_BY = {
    "ballistic": "балістиці",
    "cruise": "крилатих ракетах",
    "kab": "керованих бомбах",
    "mig": "МіГах",
    "shahed": "шахедах",
    "shahed-jet": "реактивних шахедах",
    "recon": "розвідниках",
    "aviation": "авіації",
    "mixed": "комбінованому удару",
}


SCOPE_WORD = {
    "my-area": None,          # the place names carry it
    "my-district": "мій район",
    "city": "Київ",
    "oblast": "область",
}


def _fallback(obs, threat: str | None) -> list[str]:
    """What to say when nothing is new but he is being woken anyway.

    "Увага." was here, and he asked the obvious question: what does that even
    mean, when there are only two signals? It meant nothing — it was a hole in
    the wording, not a level.

    His rule, and it is the whole of this function: "тривога є тривога. Якщо є
    її причина — то добре, а нема — то просто «тривога»." So the class and the
    place get repeated rather than replaced, the scope stands in when neither is
    known, and the last resort is the word that is always true.
    """
    from ..nlp.gazetteer import HOME

    parts = []
    if threat in CLASS_WORD:
        parts.append(CLASS_WORD[threat].capitalize())
    if obs.ring_places:
        # One clause, not one sentence each: "Вишневе. Теремки." reads as two
        # separate reports of two separate things.
        places = sorted(obs.ring_places, key=lambda p: (p != HOME, p))
        parts.append(", ".join(places))
    if not parts and SCOPE_WORD.get(obs.scope):
        parts.append(SCOPE_WORD[obs.scope])
    return parts


def _landed_word(obs) -> str | None:
    """What to call a thing that has already arrived, or None."""
    if not getattr(obs, "impact", False) or getattr(obs, "falling", False):
        return None
    low = (obs.text or "").lower()
    if "влучан" in low or "приліт" in low:
        return "Влучання"
    return "Вибух"


def _blank() -> dict:
    return {"siren": False, "classes": set(), "launches": set(), "places": set()}


@dataclass
class Utterance:
    ts: int
    lead: str        # which attention sound plays first — the `alarm` class
    text: str        # what is said, in Ukrainian


@dataclass
class Announcer:
    """Keeps what has already been said, so each utterance can be a delta."""

    # What has been said *aloud*, and what has merely appeared on the status
    # line, are different memories. Sharing one set is how "🛑 ТРИВОГА" came out
    # without him ever hearing it. A thing shown is not a thing said.
    spoken: dict = field(default_factory=lambda: _blank())
    shown: dict = field(default_factory=lambda: _blank())
    # What we already know is flying, and where, before the official siren has
    # been declared. His idea, and it is the moment that matters most: the
    # official declaration is when he actually gets up, so it should arrive
    # carrying the reason rather than the bare word.
    #
    #   ⚠️2 реактивні шахеди на Вишневе        (we ring, officially nothing yet)
    #   🚨 м. Київ / Повітряна тривога         -> "Тривога. Реактивний шахед. Вишневе."
    pending_threat: str | None = None
    pending_places: list[str] = field(default_factory=list)
    # Towns outside the ring, kept separately and used only when the ring has
    # said nothing. A name he acts on outranks one that merely tells him the
    # direction: "Вишневе" beats "Буча, Вишневе".
    pending_far: list[str] = field(default_factory=list)
    # When the pending memory was last refreshed. Without a horizon it lived
    # from one full all-clear to the next, so a class named an hour earlier
    # could arrive as the explanation for a fresh siren. Five minutes is his
    # number, and the corpus agrees: where the channels explain before the
    # siren -- 72% of alerts -- the median lead is 102 seconds.
    pending_at: int = 0
    # Say the whole situation every time, rather than only what changed. His
    # call, and the reason is the best kind: a partial sentence made him doubt a
    # correct decision. "Жуляни, Вишневе, Теремки" came out as "Вишневе,
    # Теремки." and he went looking for a bug that was not there.
    #
    # Measured before switching: on audible messages it changes almost nothing
    # (1 of 24 on one night, 1 of 34 on another), because the policy's own
    # refractory has already removed the repetition. On the silent status lines
    # it changes 84 of 160 — every one of them becoming self-contained, at the
    # cost of "Загроза: реактивний шахед. Вишневе." appearing 37 times in a day.
    always_full: bool = True
    queue: list[Utterance] = field(default_factory=list)

    def reset(self) -> None:
        """A full all-clear ends the episode, and with it everything said."""
        self.spoken = _blank()
        self.shown = _blank()
        self.pending_threat = None
        self.pending_places = []
        self.pending_far = []
        self.pending_at = 0

    def note(self, obs: Observation) -> None:
        """Remember the cause, whether or not anything is said about it.

        Called for every observation, including the silent ones — the point is
        precisely to have an answer ready when the siren finally arrives.
        """
        if not obs.live:
            return
        # A strike that has already landed is not where anything is now.
        # "💥Влучання реактивного шахеду було у Труханів острів" at 23:14 put
        # Trukhaniv into the memory, and the siren ten minutes later opened
        # with it -- pointing him at a place the threat had already left.
        if obs.impact and not obs.falling:
            return
        self.pending_at = obs.ts
        if obs.threat not in ("none", "unknown"):
            self.pending_threat = obs.threat
        # Not only ring names. Seen live: seven minutes before a siren the
        # channels said "2 реактивні шахеди на Київ/Вишгород з півночі" and the
        # siren still came out as "Тривога. Реактивний шахед." with no place --
        # because Вишгород is not in the ring, so it never entered the memory
        # at all. A threat approaching Kyiv is outside Kyiv until it is not.
        #
        # Two guards, both learned by breaking tests: the siren's own text says
        # "м. Київ" and contributes nothing, and "Київ" as a place name is noise
        # in a sentence that is already about Kyiv.
        for place in obs.ring_places:
            if place not in self.pending_places:
                self.pending_places.append(place)
        if not obs.ring_places and not obs.official and obs.scope in ("city", "oblast"):
            from ..nlp.gazetteer import find_places

            for pl in find_places(obs.text):
                if (not pl.origin and pl.tier in ("city", "oblast")
                        and pl.name != "Київ" and pl.name not in self.pending_far):
                    self.pending_far.append(pl.name)

    def _forget_if_stale(self, ts: int) -> None:
        """The remembered cause explains a siren only while it is fresh.

        Checked when it is read rather than when it is written: a quiet stretch
        writes nothing, and it was exactly the quiet stretch that let a class
        named an hour earlier arrive as the explanation for a new siren.
        """
        if self.pending_at and ts - self.pending_at > PENDING_HORIZON_S:
            self.pending_threat = None
            self.pending_places = []
            self.pending_far = []

    def announce(self, obs: Observation, decision: Decision) -> Utterance | None:
        self._forget_if_stale(obs.ts)
        # A full all-clear ends the episode whether or not we said so. Resetting
        # only when one was announced left the memory of a finished attack
        # alive: a siren an hour later opened with "Тривога. Балістика. Жуляни."
        # on a class from before the previous all-clear.
        if obs.alert_state == "clear" and not obs.partial_clear:
            self.reset()
        self.note(obs)
        if not decision.notify:
            return None

        # An audible utterance is a delta against what he has heard; a status
        # update is a delta against what he has seen. Anything said aloud counts
        # as seen too — he was awake for it.
        said = self.spoken if decision.audible else self.shown
        parts: list[str] = []
        # The class the decision was made on, not the one this message happens
        # to state. A bare "Жуляни, Вишневе, Теремки⚠️" names none, and the
        # sentence came out classless while the policy knew a jet Shahed was up.
        stated = obs.effective_threat or obs.threat
        threat = stated if stated not in ("none", "unknown") else None

        # The siren now often carries the cause itself, so the message that was
        # written to supply it can arrive a second later saying the same words.
        # His rule: "глушимо, якщо загроза і місце однакові". This lives here
        # rather than in the rules because the announcer is the only thing that
        # knows what was actually said aloud.
        if decision.reason == "what the siren was about":
            spoken_places = self.spoken["places"]
            here = set(obs.ring_places) or {
                pl.name for pl in _all_places(obs.text)}
            if (stated in self.spoken["classes"]
                    and here and here <= spoken_places):
                return None

        # "Дорозвідка" is a status, not a threat, and the sentence machinery
        # below would render it as one -- or, with no class stated, as a bare
        # "Тривога". It says what it is.
        if obs.recheck:
            word = CLASS_BY.get(threat) if threat else None
            text = f"Дорозвідка по {word}." if word else "Дорозвідка."
            utterance = Utterance(ts=obs.ts, lead=decision.alarm or "none",
                                  text=text)
            self.queue.append(utterance)
            return utterance

        if decision.alarm == "clear":
            self.reset()
            parts.append("Відбій тривоги")
        elif decision.alarm == "clear-partial":
            lifted = obs.cleared_class
            said['classes'].discard(lifted or "")
            said['launches'].discard(lifted or "")
            parts.append("Відбій по " + CLASS_BY.get(lifted, "частині загроз")
                         if lifted else "Частковий відбій")
        else:
            # The word belongs to an actual declaration and nothing else. It
            # used to be added to whatever rang first, so a drone over Zhuliany
            # said "Тривога" before any siren existed — and then the official
            # declaration, the one sentence he actually acts on, had nothing
            # left to say and came out as "Київ."
            declaring = obs.alert_state == "alert"
            falling = getattr(obs, "falling", False) and decision.audible
            landed = _landed_word(obs)
            named_class = False
            named_places: list[str] = []
            if declaring and not said['siren']:
                parts.append("Тривога")
                said['siren'] = True
                # It arrives carrying what we already knew, even if those words
                # have been used before. His idea, and this is the moment for it.
                if self.pending_threat in CLASS_WORD:
                    parts.append(CLASS_WORD[self.pending_threat].capitalize())
                    said['classes'].add(self.pending_threat)
                    named_class = True
                # Ring names list; towns do not. Three ring names are three
                # places he might be near. Three towns are a travelogue --
                # "Тривога. Реактивний шахед. Славутич, Тетіїв, Бровари." went
                # out tonight, and Slavutych is 150 km away. What a town is for
                # is which side it is coming from *now*, so only the newest.
                remembered = (self.pending_places[-3:] if self.pending_places
                              else self.pending_far[-1:])
                if remembered:
                    named_places = list(remembered)
                    parts.append(", ".join(named_places))
                    said['places'].update(remembered)

            # A launch names its own class, so the two facts must not both be
            # said: "Загроза: балістика. Пуск: балістика." is one fact twice.
            launching = bool(
                threat and obs.certainty == "confirmed" and obs.says_launch
                and threat not in said['launches'])

            # `named_class` rather than the memory: with the whole situation
            # being stated every time, the memory no longer suppresses anything,
            # and the siren block above had already said the class — "Тривога.
            # Реактивний шахед. Вишневе. Реактивний шахед."
            if threat and not named_class and (
                    self.always_full or threat not in said['classes']):
                said['classes'].add(threat)
                if not launching:
                    word = CLASS_WORD.get(threat, threat)
                    # "Тривога. Балістика." reads as one announcement; a class
                    # arriving alone later is a change of situation and says so.
                    # And a thing coming down is not a threat any more — the
                    # strictest rule in the policy exists for that word, and it
                    # was ringing without it ever being said.
                    if falling:
                        parts.append(f"Падає: {word}")
                    elif landed:
                        # "Загроза" about something that has already come down
                        # is simply untrue.
                        parts.append(f"{landed}: {word}")
                    else:
                        parts.append(word.capitalize() if parts else f"Загроза: {word}")

            # A confirmed launch is its own event even when the class is known —
            # this is the second half of his first example.
            # `says_new` is a novelty test with an extra condition — a launch
            # counts as new only when no target is named — so reusing it here
            # lost the word "пуск" from "Вихід балістики з Брянська на Київ".
            if launching:
                said['launches'].add(threat)
                parts.append(f"Пуск: {CLASS_WORD.get(threat, threat)}")

            # Over his own area, name the place. It is the one fact that changes
            # what he does rather than what he knows.
            # His own place is never dropped as "already said". It woke him at
            # 17:43 on "Жуляни, Вишневе, Теремки" and the sentence came out as
            # "Вишневе, Теремки." — the one name that decides what he does was
            # the one left out, because it had been said seven minutes earlier.
            from ..nlp.gazetteer import HOME

            if falling and not any(part.startswith("Падає") for part in parts):
                parts.append("Падає")

            # The message that explains a siren is the one place an outside
            # town has to be named. His reason: "це мені дає інформацію з якої
            # сторони загроза" — a threat approaching Kyiv is outside Kyiv
            # until it is not, so "Вишгород" is the whole content, and the ring
            # filter was dropping exactly it.
            # Both of these exist to answer "where", so the ring filter -- which
            # would drop every name outside it -- must not apply to them.
            EXPLAINS = ("what the siren was about", "where the ballistic is going")
            speakable = obs.ring_places
            if decision.reason in EXPLAINS and not speakable:
                from ..nlp.gazetteer import find_places

                speakable = tuple(dict.fromkeys(
                    pl.name for pl in find_places(obs.text) if not pl.origin))

            fresh = [p for p in speakable
                     if p not in named_places and (
                         self.always_full or p not in said['places']
                         or (p == HOME and decision.audible))]
            if fresh:
                said['places'].update(fresh)
                # Home first when it is there: it is the word he acts on.
                fresh.sort(key=lambda p: (p != HOME, p))
                parts.append(", ".join(fresh))

        if not parts:
            # Nothing new in words, but the policy decided this is worth waking
            # Nothing new in words, but the policy decided this is worth
            # waking him for — so a new event, even if every word has been
            # said before. "Увага." stood here and he asked the obvious
            # question: what does that mean, when there are only two
            # signals? It meant nothing. The class and the place get
            # repeated rather than replaced by a word carrying none.
            parts.extend(_fallback(obs, threat) or ["Тривога"])

        if decision.audible:
            # Heard is also seen.
            for key in ("classes", "launches", "places"):
                self.shown[key] |= self.spoken[key]
            self.shown["siren"] = self.spoken["siren"]

        utterance = Utterance(ts=obs.ts, lead=decision.alarm or "none",
                              text=". ".join(parts) + ".")
        self.queue.append(utterance)
        return utterance


def announce_all(pairs) -> list[Utterance]:
    """Replay (observation, decision) pairs into the utterance queue."""
    ann = Announcer()
    for obs, decision in pairs:
        ann.announce(obs, decision)
    return ann.queue
