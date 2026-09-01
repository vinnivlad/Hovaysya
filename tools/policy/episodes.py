"""Episode and novelty tracking — the part the labelled night said to build first.

Measuring `heading` against 124 real labels showed direction is not what drives
the decision. Novelty is: every `position` label that woke the user says so in
its note ("новий дрон", "ще один дрон", "виліз поруч з районом"), and
`already-notified` carries 78 of the 101 silent labels.

So the state this holds is deliberately small:

- whether an episode is open, and whether the siren has been announced
- what has already been notified about, so a repeat can be recognised
- which places near the user have been named recently, so a *new* one can be

Three parameters decide behaviour, and all three are tuned against labels rather
than guessed — see `tools/eval`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..nlp import hints
from ..nlp.gazetteer import find_places, stated_count

# An episode closes on an all-clear, or after this long with no live threat.
IDLE_CLOSE_S = 45 * 60

# A place near the user counts as new again once it has been quiet this long.
# The night showed "Жуляни" waking him at 07:02 and again at 07:35 after a lull,
# with the note "новий дрон" — but 10 minutes let far too much through.
# How long a place near him counts as "already said". His call, 2026-08-31:
# "20хв це занадто" -- and the two data points in his own labels sit either side
# of ten rather than twenty: a repeat at 9 minutes he marked silent, one at 29
# he marked a wake-up. Inside the window a repeat over home is still shown, just
# without a sound; the sound is what waits for the window to pass.
#
# Ten and not eleven or twelve on his call, having seen that the case which
# prompted the change sits 39 seconds outside it and now rings: "ми тут ніколи
# не вгадаємо інтервал. Ситуації всі різні, колись хотілося б дзвону а колись
# ні." So do not tune this number against a single night -- it is a compromise
# that is wrong in both directions by design, and the thing that makes it
# tolerable is that a repeat inside the window is still *shown*.
RING_MEMORY_S = 10 * 60

# Words the channels use when adding a target rather than restating one.
#
# Ordinals are deliberately absent. "‼️ Київ — спуск балістики! Друга" counts
# the second missile of the same volley, and the user labelled all three of
# those as "уточнення попереднього" — treating them as novelty produced three
# shelter-level false wake-ups in a row.
_NOVELTY = re.compile(
    r"\bще\b|\+\s*\d|\bнов[аиійе]\w*|\bнаступн\w*|\bдодатков\w*|"
    r"\bдолетів\b|\bз.явив\w*",
    re.IGNORECASE,
)

# A launch verb marks a new event only when it names where the launch came
# from. The labelled night says this outright:
#
#   ‼️ Вихід балістики з Брянська      shelter   "Пуск невідомо куди"
#   ‼️Балістика на Київ/передмістя      silent    "уточнення попереднього"
#   ‼️ Київ — спуск балістики! Третя    silent
#
# Launched *from* somewhere is an event; arriving *at* somewhere is the same
# missiles being tracked. Keying on the verb alone re-fired four times.
# "Виліт" and "Вихід" are different words, and only the second was here —
# so "Виліт винищувача МіГ-31К" announced nothing new and was silenced as a
# repeat. For a MiG the takeoff is the event.
#
# A stray `r` in front of the commonest launch word of all disabled it outright:
# `|r\bпуск\w*|` needs a literal "r" immediately followed by a word
# boundary, which cannot happen. So "про пуск балістичної ракети" was never a
# launch, and only `спуск`/`вихід` carried the rule.
_LAUNCH = re.compile(
    r"\bвихід\w*|\bвиліт\w*|\bвилет\w*|\bзліт\w*|\bпуск\w*|"
    r"\bспуск\w*|\bстарт\w*",
    re.IGNORECASE,
)

# A launch proper, with the descent excluded. "спуск балістики" is the ninth
# missile arriving, not a tenth leaving, and his rule after the ballistic night
# is about launches: "мені треба нотифікація на будь-який пуск балістики після
# дорозвідки". Keyed separately rather than by removing `спуск` from `_LAUNCH`,
# because the wider pattern is load-bearing elsewhere.
_LAUNCH_PROPER = re.compile(
    r"\bвихід\w*|\bвиліт\w*|\bвилет\w*|\bзліт\w*|\bпуск\w*|\bстарт\w*",
    re.IGNORECASE,
)

# ...unless the message is counting off one volley. "спуск балістики! Друга"
# contains a launch verb but is the second missile of a wave already announced,
# and the user labelled every such message "уточнення попереднього". The veto
# has to be explicit because the launch verb is right there in the text.
_ORDINAL = re.compile(
    r"\bдруг[аийе]\w*|\bтрет[яійе]\w*|\bчетверт\w*|\bп.ят[аийе]\w*|"
    r"\bшост\w*",
    re.IGNORECASE,
)

# After waking someone, a bare position message must not wake them again. Only
# an explicit new target may, and only inside this window. Seven of the twenty
# false wake-ups in the first run were repeats within it.
#
# Near the user it has to be shorter: he was woken for Zhuliany at 07:02, 07:06
# and 07:35 and called each one a new drone. Twenty minutes silenced two of the
# three.
REFRACTORY_S = 20 * 60
# Five minutes near home, his number. Measured against the channels first: the
# median gap between two mentions of his ring is 42 seconds and 79% of them are
# under five minutes, so most of what this silences is one target being tracked
# rather than a second one arriving. Zhuliany itself returns more slowly —
# median two minutes, and a quarter of the gaps are over ten.
#
# Going from six minutes to five costs nothing measurable on the labelled
# nights: the same four false wake-ups, the same five misses, one extra ring on
# one night out of three.
REFRACTORY_NEAR_S = 5 * 60

# Two silent lines saying exactly the same thing, seconds apart, are one line.
# From the night of 2026-08-29: "Вишневе - увага." at 04:55:28 and "Вишневе!" at
# 04:55:35, identical in class, place and rule. Deliberately short -- a minute
# later the same place is news again, because it means the thing is still there.
SILENT_DEDUP_S = 60

# Geographic rungs for the cruise ladder.
GEO_STEP = {"oblast": 1, "city": 2, "my-district": 3, "my-area": 3}

# Two channels announcing the same launch a minute apart is one launch. The
# pattern mining measured a median 39 s lag between channels reporting the same
# event, p90 167 s, so a window of four minutes covers it.
LAUNCH_DEDUP_S = 4 * 60

NEAR_TIERS = ("my-area", "my-district")

# His ladder, in his words: "дрон (будь-який) -> крилата ракета -> балістика".
# A rung is not about danger in the abstract but about how little time it leaves,
# which is why a MiG-31K sits with ballistic: it is the thing that launches one.
THREAT_LEVEL = {
    "recon": 1, "shahed": 1, "shahed-jet": 1,
    "cruise": 2, "kab": 2,
    "ballistic": 3, "mig": 3, "mixed": 3,
}


@dataclass
class Sent:
    """A notification the policy has already issued in this episode."""

    ts: int
    level: str
    alarm: str
    # The city's siren. It wakes him, but it says nothing about his ring, so it
    # must not silence the one word that does.
    official: bool = False


@dataclass
class Episode:
    opened_at: int
    # The class of threat this episode is about, carried forward so a bare
    # "Жуляни" during a ballistic wave is not read as a fresh drone. The
    # labeler has done this since the user pointed out that judging posts in
    # isolation is the wrong unit; the policy had not.
    threat: str | None = None
    alert_announced: bool = False
    # Whether the siren we announced actually named a place. A bare "🛑 ТРИВОГА"
    # is usually his — 68% of scope-less sirens come from the Kyiv channel — but
    # not always, and when it is not, the real city siren arrives minutes later
    # and gets silenced as a repeat. Measured: ten times in the corpus, and once
    # live, where the official app declared Kyiv at 08:04 and we had already
    # spent the announcement on a district siren at 07:50.
    alert_scope_known: bool = False
    # Whether the official channel has declared the siren for this episode. It
    # is the only source that *declares* rather than reports, so once it has
    # spoken the chat channels stop being evidence about the siren and go back
    # to being evidence about what is flying.
    official_alert: bool = False
    # The highest rung reached since the siren. A rise rings; a fall does not
    # lower it, so the same rise cannot ring twice — "якщо в середині тривоги
    # рівень знизився, то повторно правило не застосовувати". Only a partial
    # all-clear moves it down, which is the one exception he made.
    threat_peak: int = 0
    # Classes for which a *confirmed launch* has already been announced, as
    # opposed to a warning about one. Without the distinction the escalation
    # rule spent the ballistic tone on "Загроза пуску" and the actual launch two
    # minutes later went out silently — the warning silencing the event.
    launched: set[str] = field(default_factory=set)
    last_launch: int | None = None
    cleared: bool = False
    # How close a cruise missile has been reported in this episode: 0 none,
    # 1 oblast, 2 city, 3 the ring. A rise rings once, the way the threat ladder
    # does -- his rule, because waking only when they reach the city is late.
    cruise_geo: int = 0
    # When a recheck last closed a wave. What follows is a new one -- but only a
    # message the channel itself calls new, because the count-off runs across
    # waves: "спуск балістики! Дев'ята" is the ninth missile of the night rather
    # than of this volley. His warning: "хвилі можуть бути різні, але канали
    # рахують ракети загалом".
    recheck_at: int = 0
    # Named missile types already seen in this episode. A type nobody has
    # mentioned yet is a new event even when no channel calls it new.
    kinds_seen: set = field(default_factory=set)
    # Whether a ballistic launch in this episode has been given a destination.
    ballistic_located: bool = False
    # signature of a silent line -> when it was last sent
    last_silent: dict = field(default_factory=dict)
    # Classes already reported as "дорозвідка" in this episode. The channels
    # repeat it, and he asked for it deduped.
    rechecked: set[str] = field(default_factory=set)
    # Whether anything has yet said what this siren was about. The official
    # channel never does.
    explained: bool = False
    sent: list[Sent] = field(default_factory=list)
    # place name -> last time it was named near the user
    ring_seen: dict[str, int] = field(default_factory=dict)
    # The highest count the channels have stated over the ring since the last
    # audible alert. His model of a drone night — "кожен дрон то як і хвиля
    # ракет" — and the roll call is where the wave count is stated out loud.
    ring_peak: int = 0
    # Classes reported lifted while this episode continues. The user asked to
    # know "що нема загрози балістики чи мігів", and the persistent status
    # notification is where that lives — so the state has to be kept.
    cleared: set[str] = field(default_factory=set)
    last_live: int = 0

    @property
    def notified(self) -> bool:
        """Whether anything audible has been sent for this episode."""
        return any(s.level != "info" for s in self.sent)

    @property
    def loudest(self) -> str | None:
        order = {"info": 0, "alert": 1}
        audible = [s for s in self.sent if s.level != "info"]
        if not audible:
            return None
        return max(audible, key=lambda s: order[s.level]).level

    def alarms_used(self) -> set[str]:
        return {s.alarm for s in self.sent if s.level != "info"}


@dataclass
class Observation:
    """What one message says, as the policy needs it."""

    ts: int
    text: str
    threat: str
    alarm: str
    modality: str
    certainty: str
    scope: str
    heading: str
    strength: str
    alert_state: str | None
    nationwide: bool
    ring_places: tuple[str, ...]
    says_new: bool
    # Whether the text says something launched, wherever it is aimed. Distinct
    # from `says_new`, which asks whether that launch is a *new* event.
    says_launch: bool = False
    # ...and without the descent, which is an arrival rather than a departure.
    says_launch_proper: bool = False
    # Whose place this is, when a config names one instead of the gazetteer.
    home: str = ""
    ring_count: int = 0
    falling: bool = False
    # Already landed, as opposed to `falling`, which is on its way down.
    impact: bool = False
    # "Дорозвідка": the alert continues, the cause is probably destroyed.
    recheck: bool = False
    # ...and its retraction: "знову виліз".
    reappeared: bool = False
    # From `alarm_kyiv`, which relays the "Повітряна тривога" app's bot and
    # posts exactly two forms for the city and nothing else.
    official: bool = False
    # The class the policy actually decided on, which is the message's own
    # unless it stated none and the episode supplied one. Stamped by `decide`,
    # because the observation cannot know it and everything downstream wants it:
    # "Жуляни ✈️" states no class at all and reported `unknown` while the policy
    # was correctly treating it as a jet Shahed.
    effective_threat: str | None = None
    cleared_class: str | None = None
    is_reply: bool = False
    partial_clear: bool = False

    @property
    def near(self) -> bool:
        return self.scope in NEAR_TIERS

    @property
    def at_home(self) -> bool:
        """Names his own place, not merely somewhere in the ring."""
        from ..nlp.gazetteer import HOME

        return (self.home or HOME) in self.ring_places

    @property
    def live(self) -> bool:
        return self.modality == "live-threat"


# The channels that declare rather than report.
OFFICIAL_CHANNELS = frozenset({"alarm_kyiv"})


def silent_signature(obs: "Observation", reason: str) -> tuple:
    """What makes two silent lines the same line: rule, class, and where."""
    return (reason, obs.effective_threat or obs.threat,
            tuple(sorted(obs.ring_places)), obs.scope)


def _near_names(cfg) -> frozenset[str]:
    """The names that count as his ring, from the config or the gazetteer."""
    if cfg is not None and (cfg.ring or cfg.radius_km):
        return cfg.ring_names()
    return frozenset()


@dataclass
class Reading:
    """One message read once, before anyone’s ring is applied.

    The split exists because the two halves cost wildly different amounts.
    Measured on 2000 real messages: `hints.suggest` is 0.579 ms and finding the
    toponyms 0.052 ms, and neither depends on who is being warned -- what is
    flying and which places are named are the same for everybody. Turning those
    names into *my* area is 0.0004 ms, and the rules on top are 0.002 ms.

    So a hundred recipients cost 0.87 ms a message against 68 ms if each one
    re-read it. That is the whole reason the decision can stay on the server
    while every recipient has their own ring.

    The gazetteer is a recognition layer, not a relevance layer: it says
    "Борщагівка is named", with every inflection and piece of slang, and the ring
    says what Борщагівка means to me.
    """

    base: "Observation"
    places: tuple           # (name, tier), found once
    static_scope: str       # what the gazetteer’s own tiers make of it


def read(ts: int, text: str, is_reply: bool = False,
         channel: str | None = None) -> Reading:
    """The half that is the same for everyone."""
    from ..nlp.gazetteer import resolve_scope

    guess = hints.suggest(text)
    places = tuple((p.name, p.tier) for p in find_places(text))
    static = resolve_scope(text)
    base = Observation(
        ts=ts,
        text=text,
        threat=str(guess["threat"]),
        alarm=str(guess["alarm"]),
        modality=str(guess["modality"]),
        certainty=str(guess["certainty"]),
        scope=static,
        heading=str(guess["heading"]),
        strength=str(guess["strength"]),
        alert_state=hints.alert_state(text),
        nationwide=hints.nationwide(text),
        ring_places=tuple(n for n, tier in places if tier in NEAR_TIERS),
        says_new=_says_new(text),
        says_launch=bool(_LAUNCH.search(text or "")),
        says_launch_proper=bool(_LAUNCH_PROPER.search(text or "")),
        ring_count=stated_count(text),
        falling=hints.falling(text),
        impact=hints._hits(text, hints.IMPACT_TERMS),
        recheck=hints.recheck(text),
        home="",
        reappeared=hints.reappeared(text),
        is_reply=is_reply,
        official=channel in OFFICIAL_CHANNELS,
        partial_clear=hints.partial_clear(text),
        cleared_class=hints.cleared_class(text),
    )
    return Reading(base=base, places=places, static_scope=static)


def observe_for(reading: Reading, config=None) -> Observation:
    """The same reading, as it looks to one person.

    A fresh object every time, and not only for tidiness: `rules` stamps
    `effective_threat` onto the observation it decided on, so two recipients
    sharing one would overwrite each other.
    """
    import dataclasses

    near = _near_names(config)
    override_scope = None
    if near:
        scope_places = tuple(n for n, _t in reading.places if n in near)
        # A configured ring replaces the gazetteer's tier for its own names: the
        # names are recognised the same way, only whose ring they are in changes.
        if scope_places:
            override_scope = "my-area"
        elif reading.static_scope in NEAR_TIERS:
            # ...and it replaces it in both directions. Without this, someone
            # whose ring is Obolon still had Zhuliany read as their own street,
            # because the gazetteer's `my-area` tier is his.
            override_scope = "city"
    else:
        scope_places = tuple(n for n, tier in reading.places if tier in NEAR_TIERS)
    return dataclasses.replace(
        reading.base,
        scope=override_scope or reading.static_scope,
        ring_places=scope_places,
        home=(config.home if config is not None and config.home else ""),
    )


def observe(ts: int, text: str, is_reply: bool = False,
            channel: str | None = None, config=None) -> Observation:
    """Read one message into the fields the policy uses, for one person.

    `is_reply` matters for sirens specifically: a reply saying "По ньому
    тривога" refines an announcement rather than making one. Both such messages
    in the labelled night were marked silent, while every standalone siren was a
    wake-up.

    Kept as one call because almost everything reads one message for one person:
    the tests, the eval, the replay. Only the live watcher needs the two halves
    apart, and it is the only place where N is not 1.
    """
    return observe_for(read(ts, text, is_reply, channel), config)


def _says_new(text: str) -> bool:
    """Whether the message announces something rather than restating it."""
    text = text or ""
    if _ORDINAL.search(text):
        return False
    if _NOVELTY.search(text):
        return True
    if _LAUNCH.search(text):
        # A launch counts only with an origin. Russian regions and airfields are
        # origins; a Ukrainian place in the same sentence is the target.
        from ..nlp.gazetteer import find_places

        places = find_places(text)
        if not places:
            return True
        return all(p.tier == "elsewhere" for p in places)
    return False


class Tracker:
    """Keeps the current episode across a stream of observations."""

    def __init__(self, idle_close_s: int | None = None,
                 ring_memory_s: int | None = None,
                 refractory_s: int | None = None,
                 refractory_near_s: int | None = None,
                 launch_dedup_s: int | None = None,
                 config=None) -> None:
        # The config carries every number; the keyword arguments stay because
        # seventy-odd tests set them one at a time, and an explicit one wins.
        from .config import DEFAULTS

        cfg = config if config is not None else DEFAULTS
        self.config = cfg
        self.idle_close_s = idle_close_s if idle_close_s is not None else cfg.idle_close_s
        self.ring_memory_s = ring_memory_s if ring_memory_s is not None else cfg.ring_memory_s
        self.refractory_s = refractory_s if refractory_s is not None else cfg.refractory_s
        self.refractory_near_s = (refractory_near_s if refractory_near_s is not None
                                  else cfg.refractory_near_s)
        self.launch_dedup_s = (launch_dedup_s if launch_dedup_s is not None
                               else cfg.launch_dedup_s)
        self.episode: Episode | None = None
        # When the official channel was last heard from at all. While it is a
        # live source the chat channels stop declaring sirens — they were only
        # ever standing in for it. On the labelled nights it is absent, and they
        # go back to declaring, which is what keeps those nights scoring.
        self.official_seen: int | None = None
        # Whether the authoritative channel is part of this stream at all. Set
        # by the caller, which is the only one that knows.
        #
        # It used to be inferred from "has it spoken recently", and that is
        # wrong for a source that speaks only at transitions: on 2026-08-28 the
        # official channel had last spoken at 16:45, the watcher restarted at
        # 18:34, and its 90-minute warm-up therefore contained nothing official.
        # A chat all-clear at 19:09:53 rang, and the real one followed four
        # seconds later — two loud all-clears, which is what he heard.
        self.official_source = False
        # When his own place last rang while ballistic was up.
        self.home_rang_at: int | None = None
        self.closed: list[Episode] = []

    # -- lifecycle ---------------------------------------------------------

    def _open(self, ts: int) -> Episode:
        self.episode = Episode(opened_at=ts, last_live=ts)
        return self.episode

    def _close(self) -> None:
        if self.episode is not None:
            self.closed.append(self.episode)
            self.episode = None

    # Channels do not arrive in order. The chat all-clear on 2026-08-28 was
    # stamped two seconds *before* the official one and reached us fifty seconds
    # after it, so a check that demanded the official message be strictly
    # earlier let the duplicate through — two "Відбій тривоги." in a row.
    OUT_OF_ORDER_S = 3600

    def official_is_live(self, ts: int, within_s: int = 24 * 3600) -> bool:
        """Whether the authoritative source is present in this stream.

        A question about the stream, not about ordering: once the official
        channel is being watched, it owns the siren for everything around it.
        """
        if self.official_source:
            return True
        if self.official_seen is None:
            return False
        return -self.OUT_OF_ORDER_S <= ts - self.official_seen <= within_s

    def before(self, obs: Observation) -> Episode | None:
        """Advance time, closing a stale episode. Call before deciding."""
        ep = self.episode
        if ep is not None and obs.ts - ep.last_live > self.idle_close_s:
            self._close()
            ep = None
        return ep

    # -- novelty -----------------------------------------------------------

    def is_new(self, obs: Observation) -> bool:
        """Whether this message introduces something not already notified.

        Nothing sent yet: anything is new. Otherwise the channel has to say so,
        or a place near the user has to have been quiet long enough to count
        again — and neither counts inside the refractory period, because during
        a volley almost every message names something not said in the last
        minute.
        """
        ep = self.episode
        if ep is None or not ep.notified:
            return True

        # A stated count above the running peak is a new object, and it is the
        # channel saying so rather than us inferring it — measured across 29
        # near-ring drone moments to mark four wake-ups and none of the twenty
        # silences, so it breaks the refractory outright.
        if obs.ring_count > ep.ring_peak:
            return True

        window = self.refractory_near_s if obs.near else self.refractory_s
        last_audible = max((s.ts for s in ep.sent
                            if s.level != "info" and not s.official), default=None)
        if last_audible is not None and obs.ts - last_audible < window:
            # Only an outright statement of a new target breaks through.
            return bool(obs.says_new and (obs.near or obs.nationwide))

        if obs.says_new and (obs.near or obs.nationwide):
            return True
        for place in obs.ring_places:
            seen = ep.ring_seen.get(place)
            if seen is None or obs.ts - seen > self.ring_memory_s:
                return True
        return False

    def is_new_class(self, alarm: str) -> bool:
        """Whether this tone has not sounded in this episode.

        A change of class is novelty in itself — the user's own rule for when a
        new sound belongs. A Kinzhal launched at Kyiv after a MiG-31K alert was
        being silenced as "the same wave" when it is the event the MiG alert was
        warning about.

        The caller passes the alarm it intends to use, not the observation's
        own: a bare "Жуляни" mid-wave carries a drone alarm of its own while the
        decision is about the ballistic wave it belongs to.
        """
        ep = self.episode
        if ep is None:
            return True
        return alarm not in ep.alarms_used()

    def is_fresh_launch(self, obs: Observation) -> bool:
        """A launch announcement not already announced by another channel.

        Cross-channel duplication, finally load-bearing: two channels reported
        the same launch from Bryansk a minute apart and the second was a false
        wake-up.
        """
        if not obs.says_new:
            return False
        ep = self.episode
        if ep is None or ep.last_launch is None:
            return True
        return obs.ts - ep.last_launch > self.launch_dedup_s

    # -- bookkeeping -------------------------------------------------------

    def record(self, obs: Observation, level: str | None, alarm: str | None,
               reason: str | None = None) -> None:
        """Fold one observation, and any notification for it, into the state."""
        # Kept on the tracker rather than the episode: it exists only to collapse
        # the same shout arriving from two channels seconds apart, and that is
        # true across an episode boundary as much as inside one.
        if level == "alert" and obs.at_home and alarm == "ballistic":
            self.home_rang_at = obs.ts
        if obs.official:
            self.official_seen = obs.ts
        # A partial all-clear lifts one threat class, not the alert. Closing the
        # episode here would forget everything the night had established.
        if obs.alert_state == "clear" and not obs.partial_clear:
            if self.episode is not None:
                self.episode.cleared = True
            self._close()
            return

        ep = self.episode
        if ep is None:
            if not (obs.live or obs.alert_state == "alert" or obs.nationwide):
                return
            ep = self._open(obs.ts)

        if obs.live or obs.alert_state == "alert":
            ep.last_live = obs.ts

        # Any audible cruise report marks the rung, not only the one the
        # geographic ladder itself produced -- the class ladder or the near
        # rules may have rung first, and the rung is about how close it got.
        if level == "alert" and (obs.effective_threat or obs.threat) in ("cruise", "kab"):
            ep.cruise_geo = max(ep.cruise_geo, GEO_STEP.get(obs.scope, 0))
        if reason == "where the ballistic is going":
            ep.ballistic_located = True
        if level == "info" and reason:
            ep.last_silent[silent_signature(obs, reason)] = obs.ts

        # Once per class, until the threat comes back. His correction, and the
        # corpus backs it: 71 of 165 episodes carry more than one "дорозвідка",
        # and the cycle he described -- recheck, "виліз там і там", recheck --
        # happens 43 times. The second one is news, not a repeat.
        #
        # The reset is gated on our having *said* something about a live threat,
        # not merely seen one. Otherwise the constant traffic about other places
        # would re-arm it every few seconds and the dedup would mean nothing.
        stated = obs.effective_threat or obs.threat
        if obs.recheck and level is not None:
            ep.rechecked.add(stated if stated not in ("none", "unknown") else "all")
            # A recheck closes the wave it is about. What comes after it is a new
            # one -- seen on the ballistic night of 2026-09-01, where a recheck
            # at 02:25 was followed by Tsirkon launches a minute later and every
            # one of them was silenced as "the same wave". Three of his findings
            # that night are this single fault: the launches went unheard, the
            # next recheck at 02:34 counted as a repeat, and the destination that
            # arrived after the 02:42 launch was never shown.
            #
            # Not by clearing `launched`: "спуск балістики! Дев'ята" carries a
            # launch word and is the ninth missile of a wave, so clearing it
            # made every descent report ring. The channel says which is which --
            # a real new launch has `says_new`, a count-off does not -- so the
            # reopening keys on that instead, from `recheck_at`.
            ep.recheck_at = obs.ts
            ep.ballistic_located = False
        elif ((level is not None and obs.live
               and stated not in ("none", "unknown"))
              or (obs.reappeared and obs.scope != "elsewhere")):
            ep.rechecked.clear()

        # Anything we actually said that named both a class and somewhere near
        # enough to matter answers "why is the siren on" -- whichever rule
        # produced it. That is what keeps the explanation from arriving twice.
        # ...but never the siren itself. Seen live: "🚨 м. Київ / Повітряна
        # тривога" carries scope `city` from its own text and inherits the
        # episode's class, so it satisfied both halves and closed the slot --
        # the one message in the stream that explains nothing marking the
        # question answered. The next line, "1 на Вишгород", then stayed
        # silent, which is precisely the thing he was waiting for.
        if level is not None and not ep.explained and not obs.official:
            stated = obs.effective_threat or obs.threat
            if (stated not in ("none", "unknown")
                    and obs.scope in ("my-area", "my-district", "city",
                                      "oblast")):
                ep.explained = True
        # Only an announcement *we made* counts. An oblast district's siren set
        # this flag and then silenced the city's, costing four misses.
        if obs.alert_state == "alert":
            newly = not ep.alert_announced
            if obs.official:
                ep.official_alert = True
                ep.alert_announced = True
                ep.alert_scope_known = True
            elif alarm == "alert":
                ep.alert_announced = True
                if obs.scope in ("my-area", "my-district", "city"):
                    ep.alert_scope_known = True
            if newly and ep.alert_announced:
                # Seeded once, with whatever was already known. A declaration
                # carries the class with it — "Тривога. Балістика. Жуляни." — so
                # starting below that made the next ballistic warning ring
                # seventy-eight seconds later, saying what he had just heard.
                #
                # Once, not on every message: recomputing it each time pushed the
                # ladder straight back up after a partial all-clear had lowered
                # it, which is the same self-cancelling shape as before.
                ep.threat_peak = max(ep.threat_peak, 1,
                                     THREAT_LEVEL.get(ep.threat or "", 0))
        if obs.cleared_class:
            ep.cleared.add(obs.cleared_class)
            # "Тоді знижуємо поточний рівень і в разі підняття знову
            # застосовуємо правило." A lift of the ballistic threat puts the
            # ladder back at cruise, and a fresh ballistic warning rings again.
            lifted = THREAT_LEVEL.get(obs.cleared_class, 0)
            if lifted:
                ep.threat_peak = min(ep.threat_peak, lifted - 1)
        # A declared siren already stands for a drone: it is what the alert is
        # for. Starting the ladder at zero made the first drone report after the
        # siren ring again, saying what "Тривога" had just said. The rungs worth
        # hearing are the ones above it — cruise, then ballistic.
        # The ladder only moves once the siren has been declared, which is the
        # whole of "правило має працювати лише після початку тривоги".
        # Not on a partial all-clear. Its own class is carried forward from the
        # episode, so "По балістиці відбій" climbed the ladder straight back to
        # ballistic and undid the very thing it announced.
        if ep.alert_announced and obs.live and not obs.partial_clear:
            climbed = THREAT_LEVEL.get(obs.effective_threat or obs.threat, 0)
            ep.threat_peak = max(ep.threat_peak, climbed)

        # ...but not from a message the policy threw out as not an event. Seen
        # live: "❗️А тепер до поганого, балістика: цієї ночі висока
        # вірогідність..." was correctly silenced as a summary and still set the
        # episode's class to ballistic. Two minutes later "Найближчий в районі
        # Вишгороду маневрує" named nothing, inherited it, and rang.
        #
        # Anticipation is deliberately still allowed through: "Загроза пуску
        # балістики" is a warning about now, not a forecast for the night, and
        # rule 8 exists precisely to let it update the picture silently.
        # The class the decision was made on, not the word in the message. A
        # bare "2 ракети Київ." during a ballistic wave is decided as ballistic
        # and used to be *stored* as cruise -- so the next bare place name
        # inherited cruise, and the whole wave turned into one.
        if (obs.threat not in ("none", "unknown") and obs.live
                and obs.modality not in ("aftermath", "summary-news",
                                         "non-threat")):
            ep.threat = obs.effective_threat or obs.threat
            # Named again as flying: whatever was lifted is back.
            ep.cleared.discard(ep.threat)
        if obs.says_new:
            ep.last_launch = obs.ts
        if (level is not None and level != "info" and obs.says_launch
                and obs.certainty == "confirmed"):
            ep.launched.add(obs.effective_threat or obs.threat)
        if obs.live:
            ep.kinds_seen |= hints.missile_kinds(obs.text)
        # Reopening a wave is a single shot. Left standing, every later "ще" and
        # "нові" rang too -- ten of them in five minutes on 2026-09-01, which is
        # the opposite of the complaint it was fixing.
        if level == "alert" and ep.recheck_at and obs.ts > ep.recheck_at:
            ep.recheck_at = 0
        # Only from a message that counted. "Жуляни/ Вишневе до вас йде" was
        # dismissed as non-threat and still stamped Zhuliany as seen, so the
        # real warning five seconds later -- "Борщагівки, Жуляни - в укриття!"
        # -- read as the same target already notified, and he got no sound.
        if obs.live and obs.modality not in ("aftermath", "summary-news",
                                             "non-threat"):
            for place in obs.ring_places:
                ep.ring_seen[place] = obs.ts
        ep.ring_peak = max(ep.ring_peak, obs.ring_count)
        if level is not None and alarm is not None:
            ep.sent.append(Sent(ts=obs.ts, level=level, alarm=alarm,
                               official=obs.official))
            # The peak resets with each alert: the question is always "more than
            # I was last told about", not "more than tonight's worst moment".
            ep.ring_peak = obs.ring_count
