"""The policy: from one observation plus episode state, a decision.

Written from the first labelled night, not from imagination. Every rule below
either reproduces a decision the user made or encodes something he said
outright, and each carries the reason so a false wake-up can be traced to the
rule that caused it.

The order matters more than any single rule. Sirens first, because a declaration
always notifies and an all-clear always closes; then the things that must never
be audible; then novelty, which the labels showed is what actually drives a
wake-up; then proximity, which refines it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .episodes import Observation, Tracker

LEVELS = ("info", "alert")

# The siren that matters is the city's. Oblast districts get their own alerts
# constantly and the user labelled every one of them silent.
#
# `unknown` is included on purpose. A place-less "🛑 ТРИВОГА" is measured to be
# local: of 323 scope-less siren messages, 68% come from the Kyiv-focused
# channel and only 10 in 4.5 months name another region outright. Excluding it
# cost six misses, all of them the plain city siren.
CITY_OR_NEARER = ("my-area", "my-district", "city", "unknown")


@dataclass
class Decision:
    notify: bool
    level: str | None      # info | alert | shelter
    alarm: str | None
    reason: str            # which rule fired, for tracing a false wake-up

    @property
    def audible(self) -> bool:
        return self.notify and self.level in ("alert", "shelter")


def _silent(reason: str) -> Decision:
    return Decision(notify=False, level=None, alarm=None, reason=reason)


def _notify(level: str, alarm: str, reason: str) -> Decision:
    return Decision(notify=True, level=level, alarm=alarm, reason=reason)


def decide(obs: Observation, tracker: Tracker) -> Decision:
    """What the app should do at the moment this message arrived."""
    ep = tracker.before(obs)

    # A message stating no type inherits the episode's. "Жуляни" during a
    # ballistic wave is that wave, not a new drone — reading it in isolation
    # produced a false wake-up the user annotated "Ця балістика вже розбудила".
    threat = obs.threat
    if threat in ("none", "unknown") and ep is not None and ep.threat:
        threat = ep.threat

    # 1. The siren frames everything: a declaration always notifies and an
    #    all-clear always closes. But only *my* siren — an all-clear for Fastiv
    #    district is not an all-clear for me, and announcing those woke the user
    #    three times.
    if obs.alert_state == "clear" and obs.partial_clear:
        # Audible, with the all-clear tone. I had made this a silent status
        # update; the user labelled "⚪️ Відбій загрози МіГ-31К" as a wake-up
        # ("відбій по мігам") and asked outright to be told when a class is
        # lifted. It still does not close the episode.
        # Its own tone: the user asked for the distinction outright — "повний
        # відбій звучить по іншому" — so the two cannot share one.
        return _notify("alert", "clear-partial", "partial all-clear")
    if obs.alert_state == "clear" and obs.scope in CITY_OR_NEARER:
        return _notify("alert", "clear", "all-clear")
    if obs.alert_state == "clear":
        return _silent("too-far: another district's all-clear")

    # 2. A declaration always notifies — that premise is what lets the all-clear
    #    above be unconditional. Only once per episode, though.
    if obs.alert_state == "alert" and obs.scope in CITY_OR_NEARER:
        if ep is not None and ep.alert_announced:
            return _silent("already-notified: siren already announced")
        if obs.is_reply:
            # "По ньому тривога" answers an earlier message; it refines an
            # announcement rather than being one.
            return _silent("refinement: siren mentioned in a reply")
        return _notify("alert", "alert", "alert declared")
    if obs.alert_state == "alert":
        return _silent("too-far: another district's siren")

    # 3. Things that must never be audible, whatever else they contain.
    if obs.modality == "aftermath":
        return _silent("aftermath: nothing is flying")
    if obs.modality == "summary-news":
        return _silent("summary")
    if obs.modality == "non-threat":
        return _silent("not a threat")

    # 4. Another region's target is not our business. Checked after modality so
    #    an all-clear or a launch with no target still gets through above.
    if not obs.nationwide and obs.scope in ("elsewhere", "unknown"):
        return _silent("too-far: not near me")

    # 5. Anticipation is not an event. "Загроза пуску" updates the picture; the
    #    sound belongs to the launch. Straight from the labelled sequence.
    # `mig` is excluded on purpose: a takeoff is reported as "виліт ... з
    # аеродрому", which reads as anticipation, but for a MiG-31K the takeoff *is*
    # the event — the whole country is alerted at that moment.
    if obs.certainty == "probable" and threat in ("ballistic", "cruise"):
        if ep is not None and ep.notified:
            return _silent("already-notified: anticipation during a live episode")
        return _silent("insufficient: threatened, not launched")

    # 6. Ballistic leaves no room for geography: minutes of flight, so a
    #    confirmed launch that could reach us is a shelter call city-wide.
    if threat == "ballistic" and obs.certainty == "confirmed":
        # Novelty is a launch, not a position — and once a ballistic alert has
        # sounded, a place name over his own area adds nothing. His ruling, and
        # the reason is the point: "якщо був пуск балістики, то на моє коло
        # повторну нотифікацію не шли. Я і так не сплю."
        #
        # It also resolved something no threshold could. Fitted to his dense
        # night, a ring re-arm wanted to ring 78 s after the last alert; fitted
        # to the sparse one it had to stay quiet at 155 s. Both were his own
        # rulings on the same shape, and every feature that might have separated
        # them was measured and failed — see docs/pattern-findings.md. The rule
        # he gave instead needs no threshold at all, and scores better: 7 false
        # wake-ups against 8, with the same six misses.
        if (ep is not None and ep.notified
                and not tracker.is_fresh_launch(obs)
                and not tracker.is_new_class("ballistic")):
            return _silent("already-notified: same ballistic wave")
        # Audible, with the ballistic tone. The tone is what says "now" —
        # a separate loudness level said it twice.
        return _notify("alert", "ballistic", "confirmed ballistic")

    # 7. A MiG-31K in the air alerts the country, but the launch may be an hour
    #    away or never come — loud is wrong, silence is worse.
    if threat == "mig":
        # One takeoff, three channels: "Виліт винищувача МіГ-31К з аеродрому
        # Саваслейка", then "Зліт МіГ-31К ВПС рф" a minute later and again two
        # minutes after that. He woke for the first and called both others
        # repeats. `is_new` could not tell them apart, because every report of a
        # takeoff contains the takeoff word — so novelty here is the tone not
        # having sounded, plus the cross-channel launch window.
        if not tracker.is_new_class("mig") and not tracker.is_fresh_launch(obs):
            return _silent("already-notified: MiG already announced")
        return _notify("alert", "mig", "MiG-31K airborne")

    # 8. Novelty near the user is what the labels say wakes him. Direction only
    #    refines it: a new target *heading into* the ring is the shelter case.
    if obs.near and obs.live:
        if not tracker.is_new(obs):
            return _silent("already-notified: same target near me")
        if obs.strength == "weak":
            # An emoji sits on 26% of all messages; it may raise the status, it
            # may not wake anyone.
            return _notify("info", "none", "weak evidence near me")
        if obs.heading == "toward":
            # Shelter is ballistic's. Across a whole labelled night the user
            # used it three times and every one was ballistic — a drone heading
            # in is an alert, however close.
            return _notify("alert", obs.alarm, "new target heading into my area")
        if obs.heading == "away":
            return _notify("info", "none", "leaving my area")
        if obs.heading == "loitering":
            # Circling nearby is not an approach. The user labelled these
            # "ті самі" — worth showing, not worth a second wake-up.
            return _notify("info", "none", "circling nearby")
        return _notify("alert", obs.alarm, "new target near me")

    # 9. In the city but not near: worth knowing, not worth waking twice — and
    #    for a drone, not worth waking at all. His rule from the first
    #    conversation: "для дронів «летить на правий берег» ще не досить". The
    #    labels bear it out — of 78 city-scope drone moments he woke for 3, and
    #    "⚠️4 реактивні шахеди на Київ/Бровари" was a false wake-up twice over.
    #    A drone night is opened by the siren instead, which is rule 2.
    if obs.live and obs.scope == "city":
        if threat in ("shahed", "shahed-jet", "recon", "unknown", "none"):
            return _silent("insufficient: city-wide is not enough for a drone")
        if ep is not None and ep.notified:
            return _silent("already-notified: city-level, already awake")
        return _notify("alert", obs.alarm, "threat over the city")

    if obs.live and obs.scope == "oblast":
        return _silent("too-far: oblast, not the city")

    return _silent("nothing to act on")


def run(observations: list[Observation], tracker: Tracker | None = None
        ) -> list[tuple[Observation, Decision]]:
    """Replay a night in order, returning the decision for every message."""
    tracker = tracker or Tracker()
    out = []
    for obs in observations:
        decision = decide(obs, tracker)
        tracker.record(obs, decision.level if decision.notify else None,
                       decision.alarm if decision.notify else None)
        out.append((obs, decision))
    return out
