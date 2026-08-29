"""Tests for the deploy scripts, which nothing else covers.

They are shell, so what can be checked here is their text — but the two faults
they have actually produced were both visible in the text, and both only showed
up on a real server:

- the scripts were committed without the executable bit, so `./deploy/install.sh`
  answered `command not found`
- the update timer runs as the checkout's owner, who may not restart a system
  unit, so the first real deploy pulled the commit and then failed with
  "Interactive authentication required" — leaving new code on disk and the old
  process running, which is the worst of both
"""

import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _text(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_the_scripts_are_executable_in_git():
    """Authored on Windows, where the mode bit is not tracked. Cloned onto the
    server they came out 100644 and sudo said `command not found`."""
    out = subprocess.run(["git", "ls-files", "-s", "deploy/"],
                         capture_output=True, text=True,
                         cwd=DEPLOY.parent).stdout
    modes = {line.split("\t")[1]: line.split()[0] for line in out.splitlines()}
    for script in ("deploy/install.sh", "deploy/update.sh"):
        assert modes.get(script) == "100755", f"{script} is {modes.get(script)}"


def test_the_update_cannot_be_stopped_by_a_privilege_it_does_not_have():
    """The failure seen live on the first deploy: the pull succeeded, the
    restart did not, and the machine sat with new code and an old process."""
    update = _text("update.sh")
    assert "systemctl restart hovaysya" in update
    # ...but never unguarded. The restart may appear indented, inside the branch
    # that has already established this is root; at column zero it is the bug.
    for line in update.splitlines():
        assert not line.startswith("systemctl restart"), \
            "unguarded restart: the timer's user may not do that"
    assert "sudo -n systemctl restart hovaysya" in update
    assert 'id -u' in update, "must still work when run as root by hand"


def test_the_installer_grants_exactly_that_one_command():
    """A password prompt is not an option — nobody is at the keyboard at 3 a.m.
    — so the grant is passwordless, which makes its narrowness the whole of its
    safety."""
    install = _text("install.sh")
    assert "/etc/sudoers.d/hovaysya" in install
    assert "NOPASSWD" in install
    assert "systemctl restart hovaysya.service" in install
    # A malformed sudoers file locks the machine out of sudo entirely, so it is
    # never written into place unvalidated.
    assert "visudo -c" in install
    assert "0440" in install or "440" in install


def test_the_watcher_unit_still_holds_the_ballast():
    """It is what keeps the instance from being reclaimed, and it lives in the
    unit rather than in the code because it is a property of where this runs."""
    assert "--memory-floor-mb 260" in _text("hovaysya.service")
