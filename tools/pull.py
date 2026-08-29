"""Bring the server's night logs home, and complain when it cannot.

`tools/backup.py` copies what is on this machine. This is its mirror: it copies
what is on the instance, which since 2026-08-29 is where the watching actually
happens.

The reason it exists is a hole we opened by moving to a server. Oracle reclaims
an idle Always Free instance and does not promise notice, so the machine is
replaceable on purpose — `data/runbook.md` rebuilds it in half an hour. But
`data/live/*.jsonl` are not replaceable by anything: one file per night, every
decision and the rule that made it, and they are now accumulating somewhere that
can vanish.

**Two failures, and neither may be silent.**

The copy not happening is the obvious one. The other is worse and is the reason
this checks more than its own exit code: the copy can succeed and bring nothing
fresh, which means the watcher on the far end is dead. That failure is otherwise
invisible — a watcher that died at 3 a.m. shows up as a phone that stops
beeping, which is exactly what a quiet night looks like.

A healthy run says nothing at all. It runs every day, and a message every day is
a message he learns to ignore.

Usage:
    python -m tools.pull
    python -m tools.pull --host 130.110.250.164 --to D:/Work/Hovaysya-data
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "data" / "pull-state.json"

DEFAULT_DEST = Path("D:/Work/Hovaysya-data")
DEFAULT_KEY = Path.home() / ".ssh" / "hovaysya"
DEFAULT_USER = "ubuntu"
DEFAULT_REMOTE = "/home/ubuntu/hovaysya/data/live"

# Older than this and the watcher is not writing. It rewrites the current
# night's log on every poll, so a healthy file is seconds old, never hours —
# the margin is for the machine being asleep or the pull running early, not for
# any normal quiet.
STALE_AFTER_S = 6 * 3600

SCP_TIMEOUT_S = 300


@dataclass
class Outcome:
    ok: bool
    files: int
    newest: float | None = None
    error: str = ""


def plan(key: Path, user: str, host: str, remote: str, dest: Path) -> list[str]:
    """The copy, built to fail rather than hang.

    It runs from a scheduler with nobody watching, so a password prompt or an
    unknown host key must be an error and not a wait. `-p` keeps the mtimes,
    which are the whole liveness signal.
    """
    return [
        "scp", "-p", "-r",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=20",
        "-i", str(key),
        f"{user}@{host}:{remote}",
        str(dest),
    ]


def newest_log(dest: Path) -> tuple[str, float] | None:
    """By mtime, not by name: a restart opens a new file, so the names do not
    sort into the order the nights actually happened in."""
    files = [p for p in (dest / "live").glob("*.jsonl") if p.is_file()]
    if not files:
        return None
    best = max(files, key=lambda p: p.stat().st_mtime)
    return best.name, best.stat().st_mtime


def read_state(path: Path = STATE_PATH) -> bool:
    """Did the previous run have trouble?"""
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("trouble"))
    except (OSError, ValueError):
        return False


def write_state(path: Path, trouble: bool, at: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"trouble": trouble, "at": at}), encoding="utf-8")


def _ago(seconds: float) -> str:
    hours = seconds / 3600
    if hours < 48:
        return f"{hours:.0f} год тому"
    return f"{hours / 24:.0f} дн тому"


def is_trouble(outcome: Outcome, now: float | None = None,
               stale_after: float = STALE_AFTER_S) -> bool:
    """Healthy means all three: the copy ran, it brought logs, and the newest
    one is recent enough that the watcher must still be writing."""
    now = time.time() if now is None else now
    if not outcome.ok or outcome.newest is None:
        return True
    return now - outcome.newest > stale_after


def verdict(outcome: Outcome, previous_trouble: bool, now: float | None = None,
            stale_after: float = STALE_AFTER_S) -> str | None:
    """What to say, or None for a healthy run."""
    now = time.time() if now is None else now

    if not outcome.ok:
        return "⚠️ Копія з сервера не вдалася." + chr(10) + outcome.error

    if outcome.newest is None:
        return "⚠️ Копія з сервера порожня: жодного нічного логу."

    age = now - outcome.newest
    if age > stale_after:
        when = datetime.fromtimestamp(outcome.newest).strftime("%d.%m %H:%M")
        return (f"⚠️ Сервер мовчить: найсвіжіший лог від {when}, "
                f"{_ago(age)}." + chr(10) +
                "Копія пройшла, але вартовий, схоже, не пише.")

    if previous_trouble:
        return f"✅ Копія з сервера відновилася. {outcome.files} логів."

    return None


def pull(argv: list[str], dest: Path) -> Outcome:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=SCP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return Outcome(ok=False, files=0, error=f"scp не вклався у {SCP_TIMEOUT_S}s")
    except OSError as exc:
        return Outcome(ok=False, files=0, error=str(exc))

    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip().splitlines()
        return Outcome(ok=False, files=0,
                       error=detail[-1] if detail else f"scp вийшов з {done.returncode}")

    found = newest_log(dest)
    files = len(list((dest / "live").glob("*.jsonl")))
    return Outcome(ok=True, files=files, newest=found[1] if found else None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    ap.add_argument("--host", required=True, help="The instance's public IP.")
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--key", default=str(DEFAULT_KEY))
    ap.add_argument("--remote", default=DEFAULT_REMOTE)
    ap.add_argument("--to", dest="dest", default=str(DEFAULT_DEST))
    ap.add_argument("--state", default=str(STATE_PATH))
    ap.add_argument("--quiet", action="store_true",
                    help="Do not send anything to Telegram, only print.")
    args = ap.parse_args(argv)

    dest = Path(args.dest)
    outcome = pull(plan(Path(args.key), args.user, args.host, args.remote, dest),
                   dest)
    previous = read_state(Path(args.state))
    said = verdict(outcome, previous)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if outcome.ok:
        newest = newest_log(dest)
        when = (datetime.fromtimestamp(newest[1]).strftime("%d.%m %H:%M")
                if newest else "—")
        print(f"{stamp}  {outcome.files} логів у {dest / 'live'}, "
              f"найсвіжіший {when}")
    else:
        print(f"{stamp}  не вдалося: {outcome.error}")

    if said:
        print(chr(10).join("  " + line for line in said.splitlines()))
        if not args.quiet:
            # The same bot as everything else, and silent: a backup is never
            # worth a sound, even when it is the bad news.
            from .live.notify import Notifier

            Notifier().send(said, audible=False)

    write_state(Path(args.state), trouble=is_trouble(outcome), at=time.time())
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
