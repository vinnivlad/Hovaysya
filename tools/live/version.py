"""Say, once and quietly, which version is watching.

A deploy here is a pull on a timer: a commit lands on `main`, the instance
fetches it, and systemd restarts the watcher. Nothing in that chain tells him
anything. `update.sh` could send the message itself, but it would be lying about
the interesting part — that git pulled says nothing about whether the process
came up, found its token, warmed its tracker and reached the live feed. So the
watcher announces itself, at the end of its own startup, and the message exists
only if all of that actually happened.

Which makes it two things at once, and he asked for both: "система покращена і
перезапущена", and — on a machine that has never run it before — proof that the
instance works at all.

Three cases, three openings:

    nothing recorded    ▶️ started     a fresh machine, the Oracle case
    a different commit  🔧 improved    a deploy
    the same commit     🔁 restarted   a crash, a reboot, a manual restart

The last one is rate-limited. `Restart=always` with `RestartSec=10` means a
watcher that cannot start sends six messages a minute forever, which would make
the deploy note itself the thing that wakes him. Once every half hour is still a
clear signal that something is wrong, and is not an alarm.

The record is only written when something was said. Writing it on every start
would let a crash loop keep pushing the timestamp forward, and the restart would
never be reported at all.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "data" / "live-version.json"

RESTART_COOLDOWN_S = 30 * 60

# How many commit subjects a deploy note carries before it stops listing them.
# It is read on a phone, possibly at three in the morning.
MAX_SUBJECTS = 3

GIT_TIMEOUT_S = 5


@dataclass(frozen=True)
class Version:
    """What is running. `commit` is empty when git cannot say."""

    commit: str = ""
    subject: str = ""

    def __str__(self) -> str:
        if not self.commit:
            return "невідома версія"
        return f"{self.commit} — {self.subject}" if self.subject else self.commit


def _git(root: Path, *args: str) -> str:
    """Never raises. A checkout without git is not a reason to stay silent."""
    try:
        out = subprocess.run(("git", "-C", str(root)) + args, capture_output=True,
                             text=True, encoding="utf-8", timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def describe(root: Path = REPO_ROOT) -> Version:
    line = _git(root, "log", "-1", "--format=%h\t%s")
    if not line:
        return Version()
    commit, _, subject = line.partition("\t")
    return Version(commit=commit, subject=subject)


def changes_since(previous: str, root: Path = REPO_ROOT) -> list[str]:
    """The subjects of the commits this deploy brought, newest first."""
    if not previous:
        return []
    out = _git(root, "log", "--format=%s", f"{previous}..HEAD")
    return [line for line in out.splitlines() if line.strip()]


def last_seen(path: Path = STATE_PATH) -> tuple[str, float]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", 0.0
    return str(state.get("commit") or ""), float(state.get("at") or 0.0)


def remember(path: Path, commit: str, at: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"commit": commit, "at": at}), encoding="utf-8")


def startup_note(status: str, version: Version | None = None, *,
                 changes: list[str] | None = None,
                 root: Path = REPO_ROOT, state_path: Path = STATE_PATH,
                 now: float | None = None,
                 cooldown: float = RESTART_COOLDOWN_S) -> str | None:
    """What to send at startup, or None to stay silent.

    Writes the record as a side effect, and only when it returns something.
    """
    version = version if version is not None else describe(root)
    now = time.time() if now is None else now
    previous, when = last_seen(state_path)

    if not previous:
        head = "▶️ Спостерігач запущено."
    elif previous != version.commit or not version.commit:
        head = "🔧 Оновлено і перезапущено."
        if changes is None:
            changes = changes_since(previous, root)
    elif now - when >= cooldown:
        head = "🔁 Перезапуск."
    else:
        return None

    lines = [head, f"версія: {version}"]

    # The newest subject is already on the version line, so only what came with
    # it below — and a count instead of the tail, because a deploy that carries
    # a week of work must not arrive as a wall of text.
    rest = [s for s in (changes or [])[1:] if s != version.subject]
    for subject in rest[:MAX_SUBJECTS]:
        lines.append("· " + subject)
    if len(rest) > MAX_SUBJECTS:
        lines.append(f"· ще {len(rest) - MAX_SUBJECTS}")

    lines.append("стан: " + status)
    remember(state_path, version.commit, now)
    return chr(10).join(lines)
