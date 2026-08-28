"""Turn decisions into spoken Ukrainian, queued in arrival order.

His design, stated outright:

    Повідомлення ставляться в чергу. Якщо прилітають "Загроза балістики" і
    слідом "Вихід на Київ", то я хочу почути що почалась тривога по балістиці і
    потім що був пуск. Якщо просто "Тривога", "Загроза балістики", то почути що
    почалась тривога, а потім по балістиці. Скоріше за все, ці звуки будуть не
    просто звуки, а слова.

Two things follow, and both are the point.

**An utterance says what changed, not what is true.** The second announcement in
each of his examples is shorter than the first, because the siren has already
been announced by then. Re-reading the whole situation aloud every time is how a
voice channel becomes noise — the same failure the tone channel had when every
message rang.

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


@dataclass
class Utterance:
    ts: int
    lead: str        # which attention sound plays first — the `alarm` class
    text: str        # what is said, in Ukrainian


@dataclass
class Announcer:
    """Keeps what has already been said, so each utterance can be a delta."""

    siren_said: bool = False
    classes_said: set[str] = field(default_factory=set)
    launches_said: set[str] = field(default_factory=set)
    places_said: set[str] = field(default_factory=set)
    queue: list[Utterance] = field(default_factory=list)

    def reset(self) -> None:
        """A full all-clear ends the episode, and with it everything said."""
        self.siren_said = False
        self.classes_said = set()
        self.launches_said = set()
        self.places_said = set()

    def announce(self, obs: Observation, decision: Decision) -> Utterance | None:
        if not decision.notify:
            return None

        parts: list[str] = []
        threat = obs.threat if obs.threat not in ("none", "unknown") else None

        if decision.alarm == "clear":
            self.reset()
            parts.append("Відбій тривоги")
        elif decision.alarm == "clear-partial":
            lifted = obs.cleared_class
            self.classes_said.discard(lifted or "")
            self.launches_said.discard(lifted or "")
            parts.append("Відбій по " + CLASS_BY.get(lifted, "частині загроз")
                         if lifted else "Частковий відбій")
        else:
            # The siren frames everything, and it is said once.
            if not self.siren_said:
                parts.append("Тривога")
                self.siren_said = True

            # A launch names its own class, so the two facts must not both be
            # said: "Загроза: балістика. Пуск: балістика." is one fact twice.
            launching = bool(
                threat and obs.certainty == "confirmed" and obs.says_launch
                and threat not in self.launches_said)

            if threat and threat not in self.classes_said:
                self.classes_said.add(threat)
                if not launching:
                    word = CLASS_WORD.get(threat, threat)
                    # "Тривога. Балістика." reads as one announcement; a class
                    # arriving alone later is a change of situation and says so.
                    parts.append(word.capitalize() if parts else f"Загроза: {word}")

            # A confirmed launch is its own event even when the class is known —
            # this is the second half of his first example.
            # `says_new` is a novelty test with an extra condition — a launch
            # counts as new only when no target is named — so reusing it here
            # lost the word "пуск" from "Вихід балістики з Брянська на Київ".
            if launching:
                self.launches_said.add(threat)
                parts.append(f"Пуск: {CLASS_WORD.get(threat, threat)}")

            # Over his own area, name the place. It is the one fact that changes
            # what he does rather than what he knows.
            fresh = [p for p in obs.ring_places if p not in self.places_said]
            if fresh:
                self.places_said.update(fresh)
                parts.append(", ".join(fresh))

        if not parts:
            # Nothing new in words, but the policy decided this is worth waking
            # him for — so a new event, even if every word has been said before.
            # It said "Увага." three times on the first night, which is the least
            # useful sentence available: it wakes him and tells him nothing.
            # So the class and the place are repeated rather than withheld.
            said = [CLASS_WORD[threat].capitalize()] if threat in CLASS_WORD else []
            said += list(obs.ring_places)
            parts.extend(said or ["Увага"])

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
