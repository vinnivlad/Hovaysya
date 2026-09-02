"""Who is being warned, and the loop that decides for each of them.

Until now the watcher computed one decision for one person. That is the shape
that would have been expensive to change later, so it is changed now, while the
answer is still N=1 and nothing can break by being wrong.

His question is what forced it: "як сервер може вирішити що варте звуку? Локація
і коло у кожного користувача своя". The answer is that the reading is shared and
only the last step is personal -- see `episodes.Reading` for the measurements
that make it nearly free. A hundred recipients cost 1.72 ms a message against
0.82 ms for one, measured on 2000 real messages.

**A recipient owns three things and shares none of them**: their settings, their
episode state (what they were already told, when their place last rang), and the
sentences said to them. Sharing any one would leak one person's night into
another's -- and the episode state is the subtle one, because it is what makes a
repeat a repeat.

The list became a directory on 2026-09-01, and only because something finally
needed it: "користувачі мають мати можливість змінювати свій конфіг" means a
config that lives per person and changes without a commit, which `hovaysya.json`
cannot be. Until then it was deliberately absent -- inventing a format for people
who do not exist is the mistake the second config layer already made.

An empty or missing directory means the single recipient in `hovaysya.json`,
which is what runs today. The files themselves, and the token hashing, are in
`tokens.py` -- see there for why they are apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .announce import Announcer
from .config import Config, DEFAULTS
from .episodes import Observation, Reading, Tracker, observe_for
from .rules import Decision, decide


@dataclass
class Recipient:
    """One person being watched over."""

    name: str
    config: Config = DEFAULTS
    tracker: Tracker = None            # type: ignore[assignment]
    announcer: Announcer = field(default_factory=Announcer)

    def __post_init__(self) -> None:
        if self.tracker is None:
            self.tracker = Tracker(config=self.config)
        # The announcer needs the ring too, to tell one threat named twice from
        # two threats: see `_worth_saying`.
        if self.announcer.config is None:
            self.announcer.config = self.config

    def decide(self, reading: Reading) -> tuple[Observation, Decision]:
        """What this one message means to this one person."""
        obs = observe_for(reading, self.config)
        decision = decide(obs, self.tracker)
        self.tracker.record(obs, decision.level if decision.notify else None,
                            decision.alarm if decision.notify else None,
                            decision.reason)
        return obs, decision


def decide_all(reading: Reading, recipients: list[Recipient]):
    """One message, read once, decided once per person.

    Order is stable -- the list's own -- so a log of a night reads the same way
    twice.
    """
    return [(r, *r.decide(reading)) for r in recipients]


def only(config: Config, name: str | None = None) -> list[Recipient]:
    """The one-recipient case, which is today's whole world.

    The name is resolved when this is called rather than when it is defined,
    because `TELEGRAM_NAME` is imported at the foot of this module -- see the
    note there on why that import is where it is.
    """
    return [Recipient(name=name or TELEGRAM_NAME, config=config)]


# Tokens and per-person config files live in `tokens.py`, which imports three
# modules instead of ten. The API needs those and nothing else here; this module
# is the part that decides, and deciding needs the rules.
from .tokens import (DIR, TELEGRAM_NAME, config_of, hashed,  # noqa: F401
                     index, name_for, save_config, shipped as _shipped)


def from_dir(directory: Path = DIR, fallback: Config | None = None,
             telegram: str | None = TELEGRAM_NAME) -> list[Recipient]:
    """The Telegram recipient, who always exists, plus everyone who registered.

    His call, and it settles what had been a conditional: "телеграм - нехай буде
    користувач за замовченням який завжди вже створений в системі." So it is not
    a fallback for an empty index -- it is a recipient, unconditionally, and its
    settings are `hovaysya.json` rather than a file in this directory.

    That used to appear only when the index was empty, which was invisible for as
    long as nobody could register. Open registration would have made it a silent
    fault: the first stranger to install the app would have taken its place, and
    the Telegram bell -- the only delivery there is today -- would have stopped,
    with nothing anywhere to say why.

    Its name is reserved, so nobody can register under it and layer their own
    settings over his. Pass `telegram=None` for the plain reading of the index.

    Order puts it first and then follows the index, so a night's log reads the
    same way twice.
    """
    names = list(dict.fromkeys(index(directory).values()))
    base = fallback if fallback is not None else _shipped()
    people = [Recipient(name=n, config=config_of(n, directory, base=base))
              for n in names if n != telegram]
    if telegram is None:
        return people or only(base)
    return only(base, name=telegram) + people
