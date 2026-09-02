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
import os
import re
import tempfile
import threading
from pathlib import Path

from .config import Config
from .config import load as load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
DIR = REPO_ROOT / "data" / "recipients"

# How many people this can hold. Not a licence count -- registration is open, on
# his instruction: "нащо ти намагаєшся робити так щоб я адміністрував всіх
# користувачів? Нехай собі ставлять застосунок, самі вибирають дім і все." The
# ceiling exists because the push sender walks every registration on every alert
# and FCM takes them five hundred at a time, so unbounded growth costs delivery
# time to the people who are really there.
#
# Being a ceiling, it is also the denial: somebody who fills it locks out the
# next real person. That is why registrations are throttled and logged rather
# than merely counted -- see the throttle in `serve.api` -- and why `--list` and
# `--revoke` stay. It is not a defence against a determined stranger, and
# pretending otherwise would be worse than saying so.
MAX_RECIPIENTS = 500

# A label for the log, never a credential. It ends up as a filename, so the
# allowlist is the defence and `_config_path` is the second one.
NAME_MAX = 24
FALLBACK_NAME = "хтось"

# One name cannot be a person's, because a person's name is a filename here and
# this one is already taken by the index. Left alone, a device registering as
# "index" would be handed `data/recipients/index.json` as its settings file, and
# its first `PUT /config` would overwrite the index -- locking everybody out,
# with no error anywhere and no way back short of re-registering every phone.
#
# Registration gives it the same visible suffix a repeated name gets, so the
# choice is kept rather than silently replaced.
#
# `telegram_channel` is reserved for the second reason: it is a user
# that always exists rather than one that registered -- "телеграм - нехай буде
# користувач за замовченням який завжди вже створений в системі" -- and its
# settings are `hovaysya.json`. A stranger registering under that name would
# have had their own file layered over his ring.
# His name for it, and it says what it is rather than who: a delivery channel
# that exists whether or not anybody has installed anything.
TELEGRAM_NAME = "telegram_channel"
RESERVED_NAMES = frozenset({"index", TELEGRAM_NAME})
_NAME_DROP = re.compile(r"[^\w \-]", re.UNICODE)
_NAME_SPACE = re.compile(r"\s+")

# Read-modify-write on one file from a threaded server. The CLI can still race
# it, but that is a person typing a command, not a request.
_WRITE = threading.Lock()

_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")


class Refused(Exception):
    """Why a registration did not happen, in the words the app should show."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def clean_name(raw: object) -> str:
    """A person's chosen label, reduced to something safe to keep.

    Kept at all because of what he wants to do with it: "якщо я проситиму тебе
    аналізувати сесію якогось користувача" and "просто попрошу подивитись а хто
    є користувачі". A 64-character hash cannot answer either question.
    """
    text = raw if isinstance(raw, str) else ""
    text = _NAME_SPACE.sub(" ", _NAME_DROP.sub("", text)).strip()
    return text[:NAME_MAX].strip() or FALLBACK_NAME


def write_index(index: dict[str, str], directory: Path = DIR) -> None:
    """Replace the index in one step, and leave it readable by the group.

    Atomic because a torn index is everybody locked out at once. Mode 0660
    explicitly: `mkstemp` makes 0600, and the service that reads this file is a
    different user in the same group, so inheriting that would have locked the
    API out of its own index the first time a person ran the CLI.
    """
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".index-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o660)
        os.replace(tmp, directory / "index.json")
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def register(digest: object, name: object, directory: Path = DIR,
             ceiling: int = MAX_RECIPIENTS) -> str:
    """Take a device's own hash into the index and answer with its stored name.

    The app generates a secret, keeps it, and sends only `sha256` of it -- so
    this machine never holds anything that would let it impersonate a phone, the
    same property `token.py` has always had. It also means a stolen index is not
    a set of working tokens.

    A digest already present is refused rather than added under a second name.
    Two names on one hash would make `name_for` answer with whichever the dict
    happened to yield first, which is an identity anyone who learned a hash could
    take over.
    """
    if not isinstance(digest, str) or not _DIGEST.match(digest):
        raise Refused(400, "потрібен hash: 64 шістнадцяткові символи")

    label = clean_name(name)
    with _WRITE:
        current = index(directory)
        if digest in current:
            raise Refused(409, "цей пристрій уже зареєстрований")
        if len(current) >= ceiling:
            raise Refused(507, f"більше за {ceiling} отримувачів не влізе")

        # Two people can pick one name -- his warning, and he is right, so the
        # suffix is always visible rather than clever. Folded for the comparison
        # because "Оля" and "оля" are the same person to everybody but a
        # filesystem, and seeded with the name the index itself holds.
        taken = {n.casefold() for n in current.values()} | RESERVED_NAMES
        if label.casefold() in taken:
            label = f"{label}-{digest[:4]}"
        if label.casefold() in taken:
            label = f"{clean_name(name)}-{digest[:8]}"

        current[digest] = label
        write_index(current, directory)
    return label


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
