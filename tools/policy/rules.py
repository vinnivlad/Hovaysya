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

from ..nlp import hints
from .episodes import THREAT_LEVEL, Observation, Tracker

LEVELS = ("info", "alert")

# The siren that matters is the city's. Oblast districts get their own alerts
# constantly and the user labelled every one of them silent.
#
# `unknown` is included on purpose. A place-less "🛑 ТРИВОГА" is measured to be
# local: of 323 scope-less siren messages, 68% come from the Kyiv-focused
# channel and only 10 in 4.5 months name another region outright. Excluding it
# cost six misses, all of them the plain city siren.
CITY_OR_NEARER = ("my-area", "my-district", "city", "unknown")

# The tones that mean something slow enough to watch. Ballistic and cruise are
# absent on purpose: minutes of flight leave no time to find out whose street.
DRONE_TONES = ("drone", "drone-jet", "recon")


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
    inherited = False
    if threat in ("none", "unknown") and ep is not None and ep.threat:
        threat = ep.threat
        inherited = True
    # Stamped so the notification, the log and the report all name the class the
    # decision was actually made on.
    obs.effective_threat = threat
    # ...and the tone follows the class the decision was made on. "Жуляни ✈️"
    # states no class, so its own alarm is the propeller-drone tone — while the
    # episode knows a jet Shahed is up, which is several times faster and has
    # its own tone precisely so he knows before opening his eyes.
    alarm = hints.ALARM_FOR_THREAT.get(threat, obs.alarm) or obs.alarm

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
    # The official channel declares; everything else reports. Once it is in the
    # stream it owns the siren outright — his design: "повідомлення з інших
    # каналів для уточнення причини". Two of the last false wake-ups were chat
    # all-clears that were about somebody else's district, and he wrote on both
    # of them "вся надія на сервіси".
    if obs.alert_state == "clear" and obs.official:
        return _notify("alert", "clear", "official all-clear")
    if obs.alert_state == "clear" and tracker.official_is_live(obs.ts):
        # Whether or not this episode saw an official declaration: while the
        # authoritative source is in the stream, a chat all-clear is a report
        # about somebody's district and not the end of his alert.
        return _silent("refinement: the official channel closes the alert")
    if obs.alert_state == "clear" and obs.scope in CITY_OR_NEARER:
        return _notify("alert", "clear", "all-clear")
    if obs.alert_state == "clear":
        return _silent("too-far: another district's all-clear")

    # 2. A declaration always notifies — that premise is what lets the all-clear
    #    above be unconditional. Only once per episode, though.
    if obs.alert_state == "alert" and obs.official:
        if ep is not None and ep.official_alert:
            return _silent("already-notified: official siren already declared")
        return _notify("alert", "alert", "official siren")

    # While the official channel is a live source, the chat channels stop
    # declaring sirens — they were standing in for it. Two rings two seconds
    # apart is what happens otherwise, one from each. On the labelled nights it
    # is absent and they declare as before.
    if obs.alert_state == "alert" and tracker.official_is_live(obs.ts):
        return _silent("refinement: siren reported, not declared")

    if obs.alert_state == "alert" and obs.scope in CITY_OR_NEARER:
        # A siren that names the city outranks one that named nowhere. The
        # scope-less form is a guess — a good one, 68% of the time — and when it
        # is wrong the real declaration follows minutes later and must not be
        # swallowed as a repeat. This is the failure he caught live: the
        # official app declared Kyiv at 08:04 while we had already spent the
        # announcement on a bare "🛑 ТРИВОГА" at 07:50.
        explicit = obs.scope in ("my-area", "my-district", "city")
        if (ep is not None and ep.alert_announced
                and not (explicit and not ep.alert_scope_known)):
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

    # 4b. "Дорозвідка": the alert is still on, but what caused it is probably
    #     destroyed -- it may return, or the all-clear may follow. He asked to
    #     see these, silently. 402 in the corpus and the policy silenced 401,
    #     so he had never seen one. Once per class per episode, because the
    #     channels repeat it; and only inside an episode, since "тривога ще
    #     триває" is the whole meaning of the word.
    #     Placed before the geography veto on purpose: "📡Дорозвідка." names
    #     nowhere at all, and under our own siren that silence means us. A
    #     *named* far region still loses -- "Дніпро та область — дорозвідка"
    #     is not our news.
    if obs.recheck and obs.scope != "elsewhere":
        if ep is None:
            return _silent("recheck: no alert running")
        key = threat if threat not in ("none", "unknown") else "all"
        if key in ep.rechecked:
            return _silent("already-notified: recheck")
        return _notify("info", "none", "recheck: probably gone, alert continues")

    # 4a. "Знову виліз" -- a recheck retracted. Showing the good news and not
    #     its retraction is the worse of the two silences, and these messages
    #     name no place at all, so the geography veto below killed every one.
    if (obs.reappeared and obs.scope != "elsewhere"
            and ep is not None and ep.rechecked):
        return _notify("info", "none", "it is back")

    # 4. Another region's target is not our business. Checked after modality so
    #    an all-clear or a launch with no target still gets through above.
    if not obs.nationwide and obs.scope in ("elsewhere", "unknown"):
        return _silent("too-far: not near me")

    # 5. Falling on Zhuliany always rings, whatever has already been said. His
    #    rule, in his words: "якщо є «падає» і «Жуляни» то точно казати".
    #
    #    Two words wide and one place wide, and that is the whole design. The
    #    first attempt covered the near ring and the full impact vocabulary and
    #    cost two false wake-ups on the dense night — "Вишневе, Боярка — падає!"
    #    and a building damaged in Holosiiv. He cut it back to this himself.
    #
    #    Found because `⚠️Реактивний шахед падає на Жуляни` stayed silent five
    #    and a half minutes after the same drone had woken him: defensible as a
    #    repeat, and also the most consequential sentence of the night.
    if obs.falling and obs.at_home and obs.live:
        return _notify("alert", alarm, "falling on Zhuliany")

    # 6. An explosion has already happened. It is information, never a warning:
    #    of fifteen labels he placed on impact reports, fifteen are silent, and
    # categories he used are `already-notified` and `insufficient` — either he was
    # awake for it or there was nothing to act on.
    #
    # Found live: "💥Повідомляють про вибухи в районі Вишневого" rang the shelter
    # tone, on a ballistic class carried from a message two minutes earlier. His
    # words: "цілей немає".
    #
    # `падає` is deliberately not here. That is a thing on its way down, and over
    # his own street it is the one rule that overrides everything.
    if obs.impact and not obs.falling:
        # Only when it landed on his own ring. "У Києві велика детонація
        # боєприпасів" is both the past and somebody else's street, so it is not
        # even context — his call: "давай лишаємо тільки коло".
        if obs.near:
            return _notify("info", "none", "impact: it has already landed")
        return _silent("impact: elsewhere, and already over")

    # 7. The threat has climbed a rung since the siren started. His rule: an
    #    alert for a drone followed by a ballistic warning is a different
    #    situation, and that warning was arriving silently, because
    #    anticipation does not ring.
    # Once per rung. A fall does not lower the ladder, so the same climb cannot
    # ring twice — "якщо в середині тривоги рівень знизився, то повторно правило
    # не застосовувати". A partial all-clear is the one exception, and it is the
    # only thing that moves the ladder down.
    #
    # After the impact rule on purpose: an explosion names a class too, and a
    # thing that has already landed is not a climb.
    if ep is not None and ep.alert_announced and obs.live:
        climbed = THREAT_LEVEL.get(threat, 0)
        if climbed > ep.threat_peak:
            return _notify("alert", alarm, "threat level rose")

    # 8. Anticipation is not an event. "Загроза пуску" updates the picture; the
    #    sound belongs to the launch. Straight from the labelled sequence.
    # `mig` is excluded on purpose: a takeoff is reported as "виліт ... з
    # аеродрому", which reads as anticipation, but for a MiG-31K the takeoff *is*
    # the event — the whole country is alerted at that moment.
    if obs.certainty == "probable" and threat in ("ballistic", "cruise"):
        if ep is not None and ep.notified:
            # Also words, no sound — this is the second half of his example:
            # "Тривога", then "Загроза балістики", and he wants to hear the
            # class named after the siren. Silence dropped it entirely.
            return _notify("info", "none",
                           "already-notified: anticipation during a live episode")
        # Words, no sound. He asked to hear "почалась тривога по балістиці" and
        # then "був пуск" as two separate things — but of eleven anticipated
        # threats in the labels exactly one is a wake-up, and sounding every
        # episode's first one costs three false wake-ups. `info` is the channel
        # that was already there for this: the announcement queue and the
        # persistent status get the sentence, nothing rings.
        return _notify("info", "none", "insufficient: threatened, not launched")

    # 9. Ballistic leaves no room for geography: minutes of flight, so a
    #    confirmed launch that could reach us is a shelter call city-wide.
    # An inherited class does not carry the geography exemption. "Княжичі✈️"
    # said nothing about ballistic — the episode did — and ringing the shelter
    # tone for an oblast village on a carried class woke him with "Увага." and
    # no information. A *stated* ballistic report anywhere still rings, because
    # minutes of flight leave no time to ask whose district.
    if (threat == "ballistic" and inherited
            and obs.scope not in CITY_OR_NEARER):
        return _silent("too-far: carried class, another district")

    # Cruise deliberately does not join this rule, and the reason is physical:
    # a cruise missile flies for hours, so its launch says nothing about when it
    # arrives or whether it is coming here at all. What matters is where it is
    # now — "крилаті ракети нема сенсу дзвонити на пуск, воно летить кілька
    # годин. Крилаті — тільки позиція."
    #
    # So cruise stays on the position path with its five-minute refractory, and
    # ballistic stays here on the launch path with none. Moving cruise across
    # was proposed and refused; do not propose it again.
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
        # A confirmed launch that has not been announced yet always rings, even
        # when the tone has sounded for a warning about it. The escalation rule
        # spends the ballistic tone on "Загроза пуску", and without this the
        # launch itself — the thing the warning was about — went out silent.
        first_launch = (obs.says_launch and ep is not None
                        and threat not in ep.launched)
        if (ep is not None and ep.notified and not first_launch
                and not tracker.is_fresh_launch(obs)
                and not tracker.is_new_class("ballistic")):
            return _silent("already-notified: same ballistic wave")
        # Audible, with the ballistic tone. The tone is what says "now" —
        # a separate loudness level said it twice.
        return _notify("alert", "ballistic", "confirmed ballistic")

    # 10. A MiG-31K in the air alerts the country, but the launch may be an hour
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

    # 11. Novelty near the user is what the labels say wakes him. Direction only
    #    refines it: a new target *heading into* the ring is the shelter case.
    if obs.near and obs.live:
        # A drone has to name his own place. The ring was too wide for this
        # class, and he has the only proof that settles it: "реально — я собі
        # спав, поки воно там щось намотувало." One drone looping Nyvky →
        # Sviatoshyn → Borshchahivka → Vyshneve rang five times in fifty
        # minutes, and he slept through all of it.
        #
        # Still `info`, not silence: it belongs on the status line and in the
        # queue, it just does not ring. Ballistic and cruise keep the ring,
        # because minutes of flight leave no time to find out whose street.
        # Keyed on the tone rather than the class name: a bare "🅿️ 1х Нивки →
        # Вишневе" states no class at all and would ring the drone tone, which
        # is what makes it a drone for this purpose.
        if alarm in DRONE_TONES and not obs.at_home:
            return _notify("info", "none", "a drone near me, but not my street")
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
            return _notify("alert", alarm, "new target heading into my area")
        if obs.heading == "away":
            return _notify("info", "none", "leaving my area")
        if obs.heading == "loitering":
            # Circling nearby is not an approach. The user labelled these
            # "ті самі" — worth showing, not worth a second wake-up.
            return _notify("info", "none", "circling nearby")
        return _notify("alert", alarm, "new target near me")

    # 11b. The official siren never says why it sounded. In 72% of alerts the
    #      channels have already said, and the announcer carries that into the
    #      siren sentence -- but for the rest the first message naming both a
    #      class and a place is the answer, and rule 12 below would silence it
    #      outright for a drone. Measured: 98% of alerts get such a message, a
    #      median of 35 seconds after the siren.
    if (ep is not None and ep.official_alert and not ep.explained and obs.live
            and threat not in ("none", "unknown")
            and obs.scope in ("my-area", "my-district", "city")):
        return _notify("info", "none", "what the siren was about")

    # 12. In the city but not near: worth knowing, not worth waking twice — and
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
        return _notify("alert", alarm, "threat over the city")

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
