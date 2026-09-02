"""What is a preference rather than a fact, in one place.

Two kinds of number live in this project and they had been sitting in the same
file. Some are measurements: the five-minute near refractory turned out to equal
the p99 of how long different channels take to report the same target, and the
four-minute launch window is the p90 of the same thing. Others are his taste:
whether a drone has to name Zhuliany, how long his own place stays "already
said", whether the start of an alert is worth a sound at all.

Only the second kind belongs here -- but he asked for the first kind too, and for
an app that is right: "якщо ми рухаємось до застосунку, то має сенс дати
користувачу змогу налаштувати під себе". So the measured ones are here as well,
each with the measurement written beside it, so that whoever changes one knows
what they are overriding.

Every number is clamped. A typo that produced a zero-second refractory would ring
two hundred times in a wave, and the person it woke would have no way to tell
that a config file did it.

Nothing here may take the watch down. A missing file means the defaults, which
are the current behaviour; a broken file means the defaults and a printed line.

    hovaysya.json             # in git, one server, one file

    {"ring_all_clear": false, "ring_memory_s": 900}

The shape is deliberately one flat object per person rather than globals,
because in the app every recipient will have their own and the decision gets
computed once per recipient. Making that a parameter now is cheaper than
threading it through later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The settings live in git, on his reasoning: a change to them is then a commit
# with a message saying why, deployed by the same pull as the code, and the
# restart that deploy performs is what applies it -- so there is nothing to
# re-read and no reload machinery to get wrong.
# One file, because there is one server. A second layer in `data/` was written
# and removed: "у нас же один сервер" -- and a machine that really wanted to
# differ can already be pointed at another file with `--config`.
CONFIG_PATH = REPO_ROOT / "hovaysya.json"

# A list of names has to be bounded too, and for a harder reason than taste.
# Once a config can arrive over the network -- which is what an app editing its
# own settings means, and he asked for it as the ring following him across the
# city -- this loader stops being merely forgiving and becomes the trust
# boundary. A ring of 50 000 names was accepted, and it moved one decision from
# 0.03 ms to 0.3 ms: at a hundred recipients that is 30 ms a message, which is a
# denial of service written in JSON.
#
# 128 is above any honest use: the gazetteer's whole near set is 122 canonical
# names, so a larger ring cannot mean anything. The longest real name is 14
# characters.
MAX_RING = 128
MAX_NAME = 64

# Bounds, not opinions: outside these a setting stops being a preference and
# becomes a broken watch. A refractory of zero rings on every message of a wave;
# one of a day silences the night.
BOUNDS: dict[str, tuple[int, int]] = {
    "ring_memory_s": (60, 3600),
    "refractory_near_s": (30, 1800),
    "refractory_s": (60, 3600),
    "inherit_class_s": (60, 3600),
    "silent_dedup_s": (5, 600),
    "home_dedup_s": (0, 600),
    "launch_dedup_s": (30, 1800),
    "idle_close_s": (5 * 60, 6 * 3600),
    "radius_km": (0, 50),
    "same_target_sector_deg": (0, 360),
    "quiet_from_hour": (0, 23),
    "quiet_to_hour": (0, 23),
}


@dataclass(frozen=True)
class Config:
    """One person's settings. Defaults are the behaviour as it stands."""

    # --- whose place this is ------------------------------------------------
    # His suggestion, and it is the honest shape: the ring is a hand-ruled list
    # of names, so a different person has a different one. Empty means "use the
    # gazetteer's own my-area tier", which is his.
    #
    # The gazetteer stays the recognition layer -- name to canonical name, with
    # every inflection and piece of slang -- and only the tier becomes personal.
    # That split is what makes this cheap: nothing about reading Ukrainian moves.
    home: str = ""
    # The ring as a radius, his direction: "рано чи пізно коло буде реально
    # колом, з усіма мікрорайонами які входять в радіус". Zero means the list
    # below is the whole ring, which is how this started.
    #
    # Six kilometres on his call, which takes in Chabany at 5.8 and Kriukivshchyna
    # at 5.5 -- both of which he had previously ruled out by hand, and both of
    # which he has now ruled back in by choosing the number.
    radius_km: float = 0.0
    # Names always in the ring whatever the radius says, and names never in it.
    # "Може можна буде налаштувати індивідуальне коло, додавши або прибравши
    # топоніми." With no radius, `ring` alone *is* the ring.
    ring: tuple = ()
    ring_drop: tuple = ()

    # --- what makes a sound -------------------------------------------------
    ring_alert_start: bool = True
    ring_all_clear: bool = True
    # "Відбій загрози МіГ-31К" and the like. He asked for these outright once:
    # "відбій по мігам".
    ring_partial_clear: bool = True
    # The cruise ladder, one rung at a time. His own order for dropping them:
    # city first, because "область мене вже розбудить і я навряд буду спати".
    ring_cruise_oblast: bool = True
    ring_cruise_city: bool = True
    # A launch after a recheck said the wave was over.
    ring_ballistic_after_recheck: bool = True
    # Ballistic says nothing at all while Kyiv has no alert on. His call after
    # a launch from Crimea aimed at Odesa woke him at 02:27 with no Kyiv siren
    # anywhere: "мабуть таке краще не показувати, коли немає тривоги в Києві".
    #
    # Measured over the corpus before switching it on: 268 ballistic bells, 214
    # of them inside a Kyiv alert. Of the 54 outside, 40 were never followed by
    # an alert at all -- and reading them, 26 are news and chatter ("Британія
    # передасть Україні далекобійні засоби", "дякую за такий великий донат"),
    # 6 are real ballistic aimed at Odesa or Rzhyshchiv, and 8 are genuine
    # launches with no stated target. The other 14 preceded a siren by a median
    # of one minute, which is what this costs: the siren rings anyway.
    ring_ballistic_needs_alert: bool = True
    # Ballistic over his own place rings every time it is named, however often.
    # "Жуляни завжди дзвонимо — головне правило", and it reversed six of his own
    # earlier labels: "Тихо з різницею в 10хв — я явно був не правий".
    ring_home_ballistic: bool = True
    # A drone rings only when his own place is named. False widens it to the
    # whole ring, which is where it started and which he narrowed himself after
    # sleeping through five rings in fifty minutes.
    drone_needs_home: bool = True

    # Two names inside one sector this wide are one thing seen twice, and only
    # the nearer gets said. Wider apart they are separate threats and both do.
    # His rule and his number: "якщо обидві цілі знаходяться в секторі 90 град
    # від мене, то беремо ближню, інакше залишаємо як є, мо скоріше то різні
    # цілі." Zero turns it off and says every name, which is how this worked
    # before coordinates existed.
    same_target_sector_deg: int = 90

    # --- what appears without a sound ---------------------------------------
    show_ballistic_detail: bool = True
    show_recheck: bool = True
    show_ballistic_destination: bool = True
    show_home_repeat: bool = True
    show_ring_drone: bool = True

    # --- how long something counts as already said --------------------------
    # His, changed twice: twenty minutes felt too long for his own place.
    ring_memory_s: int = 10 * 60
    # Measured rather than chosen: the p99 of cross-channel lag for the same
    # target is five minutes, so most of what this silences is one object being
    # reported twice.
    refractory_near_s: int = 5 * 60
    refractory_s: int = 20 * 60
    # How long a class stated by a channel may still explain **a siren**. Not
    # every message: during a track the channels write nothing but place names
    # for ten minutes at a stretch, because everyone already knows what is
    # flying, and aging that made the sentences say a bare "Вишневе." within an
    # hour of shipping it. His argument is physical rather than statistical: "а якщо не
    # балістики а крилатих ракет? Тоді ну зовсім нестиковка, телепортувались ті
    # ракети чи що повз область?" A cruise missile does not wait, so a class
    # half an hour old describes something that is now somewhere else entirely.
    #
    # The same ten minutes the announcer's own memory uses, for the same reason
    # and measured the same way: where the channels explain before a siren, the
    # median lead is two minutes and ten minutes covers 77% of them. During a
    # real wave the class is restated constantly, so this costs nothing there.
    inherit_class_s: int = 600
    # Two identical silent lines seconds apart are one line.
    silent_dedup_s: int = 60
    # The only dedup left on the rule above -- "дедуп мінімальний". It exists for
    # one shape: the same shout from two channels seconds apart, "Жуляни🚀" then
    # "ЖУЛЯНИ!" four seconds later.
    #
    # Fifteen seconds, and the corpus put it there rather than taste. Every echo
    # of that shape lands in 1-13 s -- eight pairs, at 1, 1, 1, 4, 7, 7, 9 and
    # 13 -- and then nothing until 24 s. What sits above the gap is a fresh
    # shout, not an echo: "ЖУЛЯНИ!!" and then "Жуляни уважно" from another
    # channel 35 s later, which under his rule has to ring. So the threshold
    # belongs anywhere in the empty band of 14-23 s, and the low end of it is
    # the one that assumes least.
    home_dedup_s: int = 15
    # Measured: p90 of the same cross-channel lag.
    launch_dedup_s: int = 4 * 60
    idle_close_s: int = 45 * 60

    # --- the quiet hours ----------------------------------------------------
    # Between these hours only ballistic and above make a sound. Off by default;
    # it exists because the vibration idea for the app needs the same notion.
    quiet_hours: bool = False
    quiet_from_hour: int = 23
    quiet_to_hour: int = 7

    def ring_names(self, warn=None) -> frozenset[str]:
        """See `_ring_names`. Cached, because this is called per message per
        recipient and the radius is 137 distance computations -- uncached it made
        a hundred recipients twelve times the cost of one, which is precisely the
        property `episodes.Reading` exists to protect."""
        return _ring_names(self.home, self.ring, self.ring_drop, self.radius_km,
                           warn)

    def centre(self):
        """Where he is, or None if the gazetteer has no point for it."""
        from ..nlp.coords import POINTS

        return POINTS.get(self.home) if self.home else None

    def sounds_at(self, hour: int, threat: str | None) -> bool:
        """Whether something of this class may be audible at this hour."""
        if not self.quiet_hours:
            return True
        a, b = self.quiet_from_hour, self.quiet_to_hour
        inside = a <= hour < b if a <= b else (hour >= a or hour < b)
        if not inside:
            return True
        return threat in ("ballistic", "mig", "kab", "mixed")


DEFAULTS = Config()


@lru_cache(maxsize=64)
def _ring_names(home: str, ring: tuple, ring_drop: tuple, radius_km: float,
                warn=None) -> frozenset[str]:
    """Every name that counts as near, radius and hand-list together.

    The radius is an overlay, not a replacement: a name with no coordinate keeps
    whatever tier the gazetteer gave it. `Кільцева` is a road thirty kilometres
    long and `Правий берег` is half a city -- there is no honest point for either,
    and inventing one would let a radius act on it.
    """
    names = set(ring)
    if home:
        names.add(home)
    if radius_km > 0:
        from ..geo.build import km
        from ..nlp.coords import POINTS

        centre = POINTS.get(home)
        if centre is None:
            if warn is not None:
                warn(f"  ! конфіг: не знаю де {home!r} — радіус не застосовую")
        else:
            names |= {name for name, point in POINTS.items()
                      if km(centre, point) <= radius_km}
    return frozenset(names) - set(ring_drop)


def _clamp(name: str, value: int) -> int:
    lo, hi = BOUNDS[name]
    return max(lo, min(hi, value))


def from_dict(raw: dict, base: Config = DEFAULTS,
              warn=print) -> Config:
    """Overlay a mapping onto the defaults, ignoring what it cannot use."""
    known = {f.name: f.type for f in fields(Config)}
    changes: dict[str, object] = {}
    for key, value in (raw or {}).items():
        if key.startswith("_"):
            continue          # a comment in a format that has none
        if key not in known:
            warn(f"  ! конфіг: невідомий ключ {key!r} — пропускаю")
            continue
        current = getattr(base, key)
        if isinstance(current, tuple):
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                warn(f"  ! конфіг: {key} має бути списком назв — пропускаю")
                continue
            if len(value) > MAX_RING:
                warn(f"  ! конфіг: {key} — {len(value)} назв, беру перші {MAX_RING}")
                value = value[:MAX_RING]
            if any(len(x) > MAX_NAME for x in value):
                warn(f"  ! конфіг: {key} — назви довші за {MAX_NAME} символів обрізано")
            changes[key] = tuple(x[:MAX_NAME] for x in value)
        elif isinstance(current, str):
            if not isinstance(value, str):
                warn(f"  ! конфіг: {key} має бути рядком — пропускаю")
                continue
            if len(value) > MAX_NAME:
                warn(f"  ! конфіг: {key} — довше за {MAX_NAME} символів, обрізаю")
            changes[key] = value[:MAX_NAME]
        elif isinstance(current, bool):
            if not isinstance(value, bool):
                warn(f"  ! конфіг: {key} має бути true/false — пропускаю")
                continue
            changes[key] = value
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                warn(f"  ! конфіг: {key} має бути числом — пропускаю")
                continue
            fixed = _clamp(key, value) if key in BOUNDS else value
            if isinstance(current, int) and not isinstance(current, bool)                     and not isinstance(current, float):
                fixed = int(fixed)
            if fixed != value:
                lo, hi = BOUNDS[key]
                warn(f"  ! конфіг: {key}={value} поза межами {lo}..{hi} — беру {fixed}")
            changes[key] = fixed
    return replace(base, **changes)


def load(path: Path = CONFIG_PATH, base: Config = DEFAULTS,
         warn=print) -> Config:
    """The file overlaid on the defaults. Never an exception."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return base
    except (OSError, ValueError) as exc:
        warn(f"  ! конфіг {path.name}: {exc} — лишаю як було")
        return base
    if not isinstance(raw, dict):
        warn(f"  ! конфіг {path.name}: очікував обʼєкт — лишаю як було")
        return base
    return from_dict(raw, base=base, warn=warn)





def changed_from_default(cfg: Config) -> dict:
    """Only what differs, for printing at startup."""
    return {f.name: getattr(cfg, f.name) for f in fields(Config)
            if getattr(cfg, f.name) != getattr(DEFAULTS, f.name)}
