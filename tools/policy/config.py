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

# Bounds, not opinions: outside these a setting stops being a preference and
# becomes a broken watch. A refractory of zero rings on every message of a wave;
# one of a day silences the night.
BOUNDS: dict[str, tuple[int, int]] = {
    "ring_memory_s": (60, 3600),
    "refractory_near_s": (30, 1800),
    "refractory_s": (60, 3600),
    "silent_dedup_s": (5, 600),
    "launch_dedup_s": (30, 1800),
    "idle_close_s": (5 * 60, 6 * 3600),
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
    ring: tuple = ()

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
    # A drone rings only when his own place is named. False widens it to the
    # whole ring, which is where it started and which he narrowed himself after
    # sleeping through five rings in fifty minutes.
    drone_needs_home: bool = True

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
    # Two identical silent lines seconds apart are one line.
    silent_dedup_s: int = 60
    # Measured: p90 of the same cross-channel lag.
    launch_dedup_s: int = 4 * 60
    idle_close_s: int = 45 * 60

    # --- the quiet hours ----------------------------------------------------
    # Between these hours only ballistic and above make a sound. Off by default;
    # it exists because the vibration idea for the app needs the same notion.
    quiet_hours: bool = False
    quiet_from_hour: int = 23
    quiet_to_hour: int = 7

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
            changes[key] = tuple(value)
        elif isinstance(current, str):
            if not isinstance(value, str):
                warn(f"  ! конфіг: {key} має бути рядком — пропускаю")
                continue
            changes[key] = value
        elif isinstance(current, bool):
            if not isinstance(value, bool):
                warn(f"  ! конфіг: {key} має бути true/false — пропускаю")
                continue
            changes[key] = value
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                warn(f"  ! конфіг: {key} має бути числом — пропускаю")
                continue
            fixed = _clamp(key, value) if key in BOUNDS else value
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
