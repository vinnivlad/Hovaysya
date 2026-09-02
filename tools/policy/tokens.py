"""Who is allowed in, and where each person's settings live.

Split out of `recipients.py` for one reason, and it is a security one rather than
tidiness. Importing `recipients` pulls in ten modules -- the ordered rules, the
episode machinery, the gazetteer, `hints` -- and the API needs none of them. It
reads a database and compares a hash.

    tools.policy.config       ->  3 modules
    tools.policy.recipients   -> 10, including nlp.gazetteer and nlp.hints

The service exposed to the internet should carry the least code that can do its
job, and `hints.py` is where every fault in this project has lived. His
observation, and he was right: "там має бути один ендпоінт чи що, щоб читати
базу".

Tokens are stored as hashes, never as themselves. The machine also holds a bot
token, and a leak of one file should not be a leak of both.

    data/recipients/index.json     sha256(token) -> name
    data/recipients/<name>.json    that person's settings
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from .config import Config
from .config import load as load_config

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


def shipped() -> Config:
    return load_config(warn=lambda _m: None)


def config_of(name: str, directory: Path = DIR, base: Config | None = None,
              warn=None) -> Config:
    """One person's settings, over the shipped ones rather than over bare defaults.

    The difference is not academic. `hovaysya.json` is the record of how this
    behaves -- his ring, his radius, every switch -- and a recipient file holds
    only what that person changed. Layered on `DEFAULTS` instead, the first token
    minted on the watcher's own machine would have silently emptied his ring and
    set the radius to zero, because a name in the index with no file beside it
    means "changed nothing", not "configured nothing".
    """
    return load_config(_config_path(name, directory),
                       base=base if base is not None else shipped(),
                       warn=warn or (lambda _m: None))


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
