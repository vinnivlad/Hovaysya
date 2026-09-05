"""What the watcher must not forget when it restarts.

The episode is the answer to "is there a raid", and for a long time a restart
threw it away and tried to work it out again from the last ninety minutes of the
database. That failed exactly the way re-deriving state always fails: 20% of
official raids in the corpus run longer than ninety minutes, so one restart in
five during an alert reported a calm sky over a city under attack. It happened
to him -- "після оновлення не витягло активний статус тривоги" -- when an
Android-only commit restarted the watcher.

His objection to my first fix was the right one, and it is the reason this file
exists rather than a bigger number: "тягнути історію щоб знайти старт тривоги це
все одно не варіант". Reading further back makes the window larger; it does not
make the approach correct. The state was known -- the previous run computed it,
labelled every message with it, and served it to the phone -- and then dropped
it on the floor. So save it and read it back.

Which is the same lesson as the two before it, in a third costume: state takes
what the decision threw out. A rule that decides correctly and a process that
forgets the decision are one bug.

Written as one file per recipient, beside the state files, and never served over
the API: this is the tracker's insides, and `/state` is a contract with a phone.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import fields
from pathlib import Path

from .episodes import Episode, Sent

# Tracker state that outlives a single message and does not live in the episode.
# `official_seen` is the important one: without it a restart mid-raid does not
# know the authoritative channel is present in this stream, and every chat
# all-clear becomes evidence again.
CARRIED = ("official_seen", "said_clear_at", "home_rang_at", "home_said_at",
           # How long the last raid ran is drawn for an hour after it ends, and
           # deploys are frequent enough that an hour reliably contains one.
           "alert_began")

# Refuse a file older than this rather than trust it. A watcher that has been
# off for a day has missed the all-clear along with everything else, and an
# episode restored from before then would hold the screen red until the next
# official message. The tracker's own idle-close would sort it out eventually;
# this makes "eventually" unnecessary.
STALE_S = 12 * 3600

# `Episode.last_silent` is keyed by tuples, which JSON cannot use as object
# keys, so it travels as pairs. Named rather than special-cased inline: the next
# tuple-keyed field should be added here and nowhere else.
PAIRED = ("last_silent",)


def _tuples(value):
    """Lists back into tuples, all the way down.

    `silent_signature` nests one: `(reason, threat, (places...), scope)`. JSON
    flattens both levels to lists, and a list inside a key is unhashable -- so
    converting only the outer one raises on the first restore of an episode that
    ever suppressed a silent line, which is most of them.
    """
    if isinstance(value, list):
        return tuple(_tuples(item) for item in value)
    return value


def _blank() -> Episode:
    """A default episode, used only to read each field's runtime type from."""
    return Episode(opened_at=0)


def encode(episode: Episode | None) -> dict | None:
    """An episode as JSON-safe data.

    Driven by `dataclasses.fields` rather than by a hand-written list, because
    `Episode` gains a field roughly every time a rule gets sharper -- and a
    hand-written encoder would keep working while quietly dropping the new one.
    """
    if episode is None:
        return None
    blank = _blank()
    out: dict = {}
    for spec in fields(Episode):
        value = getattr(episode, spec.name)
        default = getattr(blank, spec.name)
        if spec.name in PAIRED:
            out[spec.name] = [[list(key), when] for key, when in value.items()]
        elif isinstance(default, set):
            out[spec.name] = sorted(value)
        elif isinstance(default, list):
            out[spec.name] = [
                {f.name: getattr(item, f.name) for f in fields(Sent)}
                for item in value]
        else:
            out[spec.name] = value
    return out


def decode(data: dict | None) -> Episode | None:
    """The inverse, tolerant in both directions.

    A key the file does not have keeps the field's default, and a key the code
    no longer knows is ignored. Both matter because this file survives deploys:
    it is written by the version that is stopping and read by the version that
    is starting, and those differ precisely when something has changed.
    """
    if not data:
        return None
    blank = _blank()
    episode = _blank()
    for spec in fields(Episode):
        if spec.name not in data:
            continue
        raw = data[spec.name]
        default = getattr(blank, spec.name)
        if spec.name in PAIRED:
            setattr(episode, spec.name,
                    {_tuples(key): when for key, when in raw})
        elif isinstance(default, set):
            setattr(episode, spec.name, set(raw))
        elif isinstance(default, list):
            setattr(episode, spec.name, [Sent(**item) for item in raw])
        else:
            setattr(episode, spec.name, raw)
    return episode


def state_of(tracker) -> dict:
    """Everything about a tracker that should survive the process."""
    carried = {name: getattr(tracker, name, None) for name in CARRIED}
    return {"episode": encode(tracker.episode), "carried": carried}


def restore(tracker, data: dict, now: int) -> bool:
    """Put a saved state back, unless it is too old to believe.

    Returns whether an open episode came back, which is the only part worth
    printing at startup.
    """
    if not isinstance(data, dict):
        return False
    for name, value in (data.get("carried") or {}).items():
        if name in CARRIED:
            setattr(tracker, name, value)
    episode = decode(data.get("episode"))
    if episode is None:
        return False
    # Age from the last sign of life rather than from the opening, so a raid
    # that has been running for ten hours is still restored while a file left
    # behind by a watcher that stopped yesterday is not.
    seen = max(episode.last_live, episode.opened_at, episode.threat_at)
    if now - seen > STALE_S:
        return False
    tracker.episode = episode
    return True


def path_for(directory: Path, recipient) -> Path:
    return directory / f"{Path(recipient.name).name}.json"


def save(directory: Path, recipient, tracker, now: int) -> Path:
    """Replace one tracker's saved state in a single step.

    Atomically, and 0600: unlike the state files this is nobody's business but
    the watcher's -- not the API's, and certainly not a phone's.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(directory, recipient)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".carry-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"at": int(now), **state_of(tracker)}, handle,
                      ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def load(directory: Path, recipient, tracker, now: int) -> bool:
    """Restore one tracker from disk. Absent or unreadable is not an error.

    A corrupt file must not stop the watcher starting: the cost of ignoring it
    is one lost episode, and the cost of raising is a service that will not come
    up at all. Which of those is worse does not need arguing at three in the
    morning.
    """
    path = path_for(directory, recipient)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return restore(tracker, data, now)
