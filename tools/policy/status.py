"""What one person's screen shows right now, as facts rather than as a sentence.

The first screen, as he described it: "Показує теперішню максимальну загрозу
(знижує коли дали частковий відбій). Показує що без загроз коли тривоги нема.
Показує що дорозвідка і яка + нижча загроза (наприклад: Дрони, Балістика
Дорозвідка)".

So this answers three questions and stops: what is the worst thing in the air,
what is only being scouted, and what has been lifted. It hands over the facts and
the Ukrainian words for them, and not the finished line.

That split is deliberate. The vocabulary belongs here because a class the server
knows and the app does not would render as a blank label -- a threat with no name
on the one screen that exists to name it. The layout belongs to the app, because
it is visual, and a file that cannot see the screen has no business deciding how
two threats sit next to each other.

`top` is the one computed answer, and it is computed here for the same reason:
"теперішня максимальна загроза" is a question about which classes are still live,
which needs `cleared`, `launched` and the severity ladder together. Left to the
app it would be three fields the app has to combine correctly, forever, in
Kotlin.

    data/live/state/<name>.json     rewritten every poll, read by `serve.api`

A file per person rather than one file for everybody: the API serves the one the
token names and never opens the others, which is the same property `/decisions`
gained when it started filtering.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .announce import CLASS_WORD
from .episodes import THREAT_LEVEL

# `тихо` | `стежу` | `ТРИВОГА` in the watcher's own words, and the distinction
# matters on a screen more than in a log. An episode opens on any live threat --
# a drone launched three regions away opens one -- so "watching" is not "alert",
# and calling it one would be the overstatement `state_word` was fixed to avoid:
# "an app that overstates once is discounted afterwards".
QUIET, WATCHING, ALERT = "quiet", "watching", "alert"

# How many of the last Ховайся lines the first screen carries. His number:
# "останні 1-3 повідомлення від ховайся внизу".
SAID_ON_SCREEN = 3

# How recently a class must have been called "дорозвідка" to still be on the
# screen as such. `Episode.rechecked` deliberately has no age -- it answers "have
# we said this already in this episode", which stays true -- so reading it as
# "what is being scouted now" was wrong: measured over the corpus, 41% of 417
# entries sit there past ten minutes, 14% past thirty, and one stood for three
# hours. Ten minutes, the same number and the same measurement the announcer's
# own memory uses: where the channels speak before a siren, ten covers 77%.
RECON_FRESH_S = 10 * 60


def _named(classes) -> list[dict]:
    """Classes worst first, each with the word the announcer would use."""
    live = sorted((c for c in classes if c),
                  key=lambda c: (-THREAT_LEVEL.get(c, 0), c))
    return [{"class": c, "word": CLASS_WORD.get(c, c)} for c in live]


def snapshot(recipient, said=(), now: int | None = None) -> dict:
    """One person's current state, from their own tracker.

    `said` is their last few lines, newest last, as the log recorded them --
    passed in rather than fetched, because the watcher already has them in memory
    and this module has no business knowing what a Session is.
    """
    ep = recipient.tracker.episode
    at = int(now if now is not None else 0)

    if ep is None:
        # No episode is exactly "без загроз", and it is also how a full all-clear
        # is recognised -- there is nothing left to describe.
        return {"at": at, "state": QUIET, "since": None, "top": None,
                "threat": None, "recon": [], "cleared": [], "launched": [],
                "peak": 0, "said": list(said)[-SAID_ON_SCREEN:]}

    cleared = set(ep.cleared)
    # Reconnaissance is not the threat -- it is the thing his example puts on the
    # second line: "Дрони, Балістика Дорозвідка" is drones in the air with
    # ballistic only being scouted. So it stays out of `top` on purpose.
    airborne = ({ep.threat} | set(ep.launched)) - cleared
    fresh = {c for c, when in ep.recon_at.items()
             if at - when <= RECON_FRESH_S}
    recon = (set(ep.rechecked) & fresh) - cleared - airborne
    top = _named(airborne)

    return {
        "at": at,
        "state": ALERT if ep.official_alert else WATCHING,
        "since": ep.opened_at,
        # The worst thing still in the air, or None when everything named has
        # been lifted and the siren has not been called off yet.
        "top": top[0] if top else None,
        "threat": _named([ep.threat])[0] if ep.threat else None,
        "recon": _named(recon),
        "cleared": _named(cleared),
        "launched": _named(ep.launched),
        # The rung reached since the siren. A partial all-clear moves it down by
        # one, which is the only thing that lowers it -- his exception.
        "peak": ep.threat_peak,
        "said": list(said)[-SAID_ON_SCREEN:],
    }


def write(directory: Path, recipient, said=(), now: int | None = None) -> Path:
    """Replace one person's state file in a single step.

    Atomically, because a phone reading a half-written file is a crash on the
    screen whose whole job is to be trusted at three in the morning. 0640: the
    watcher writes, the API's group reads, nobody else.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{Path(recipient.name).name}.json"
    payload = snapshot(recipient, said=said, now=now)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
