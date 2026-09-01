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

The list itself is deliberately not a file yet. There is one recipient and he is
in `hovaysya.json`; inventing a format for people who do not exist is the same
mistake as the second config layer that got written and deleted in an hour.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


def only(config: Config, name: str = "я") -> list[Recipient]:
    """The one-recipient case, which is today's whole world."""
    return [Recipient(name=name, config=config)]
