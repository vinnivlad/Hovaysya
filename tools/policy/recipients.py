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

    data/recipients/index.json     sha256(token) -> name
    data/recipients/<name>.json    that person's settings

Tokens are stored as hashes, never as themselves: the file sits on the machine
that also holds the bot token, and a leak of one should not be a leak of both.
An empty or missing directory means the single recipient in `hovaysya.json`, which
is what runs today.
"""

from __future__ import annotations

import hashlib
import hmac
import json
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


def only(config: Config, name: str = "я") -> list[Recipient]:
    """The one-recipient case, which is today's whole world."""
    return [Recipient(name=name, config=config)]


REPO_ROOT = Path(__file__).resolve().parents[2]
DIR = REPO_ROOT / "data" / "recipients"


def hashed(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def index(directory: Path = DIR) -> dict[str, str]:
    """sha256(token) -> name. Empty when there is no directory yet."""
    path = directory / "index.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def name_for(token: str, directory: Path = DIR) -> str | None:
    """Whose token this is, compared without leaking how far it matched."""
    wanted = hashed(token)
    for digest, name in index(directory).items():
        if hmac.compare_digest(digest, wanted):
            return name
    return None


def _config_path(name: str, directory: Path = DIR) -> Path:
    """A name from the index only, so a path can never be traversed out."""
    return directory / f"{Path(name).name}.json"


def config_of(name: str, directory: Path = DIR, warn=None) -> Config:
    from .config import load as load_config

    return load_config(_config_path(name, directory), warn=warn or (lambda _m: None))


def save_config(name: str, raw: dict, directory: Path = DIR) -> Config:
    """Store one person's settings, after the loader has had its say.

    What lands on disk is what `from_dict` accepted -- unknown keys dropped,
    numbers clamped, lists bounded -- so a hostile body cannot be written back
    out verbatim and re-read later as if it had been validated once.
    """
    from .config import changed_from_default, from_dict

    cfg = from_dict(raw, warn=lambda _m: None)
    directory.mkdir(parents=True, exist_ok=True)
    _config_path(name, directory).write_text(
        json.dumps(changed_from_default(cfg), ensure_ascii=False, indent=1,
                   default=list),
        encoding="utf-8")
    return cfg


def from_dir(directory: Path = DIR, fallback: Config | None = None) -> list[Recipient]:
    """Everyone with a config on disk, or the single fallback when there is none.

    Order is the index's, so a night's log reads the same way twice.
    """
    names = list(dict.fromkeys(index(directory).values()))
    if not names:
        return only(fallback if fallback is not None else DEFAULTS)
    return [Recipient(name=n, config=config_of(n, directory)) for n in names]
