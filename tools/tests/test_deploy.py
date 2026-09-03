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

import pathlib
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
    server they came out 100644 and sudo said `command not found`.

    Every script, found rather than listed. This checked two names --
    `install.sh` and `update.sh` -- so the four added after it were never
    covered, and `update-proxy.sh` went in as 100644 for the third instance
    of the same fault. A test that has to be edited when a file is added is
    a test that will not be.
    """
    out = subprocess.run(["git", "ls-files", "-s", "deploy/"],
                         capture_output=True, text=True,
                         cwd=DEPLOY.parent).stdout
    modes = {line.split("\t")[1]: line.split()[0] for line in out.splitlines()}
    scripts = {name: mode for name, mode in modes.items()
               if name.endswith(".sh")}
    assert len(scripts) >= 6, f"expected the deploy scripts, found {scripts}"
    wrong = {name: mode for name, mode in scripts.items()
             if mode != "100755"}
    assert not wrong, wrong


def test_the_update_cannot_be_stopped_by_a_privilege_it_does_not_have():
    """The failure seen live on the first deploy: the pull succeeded, the
    restart did not, and the machine sat with new code and an old process."""
    update = _text("update.sh")
    # One script for both boxes, and with no arguments it asks systemd which
    # units are enabled rather than being told. That came from a real fault:
    # installing the API on A left two update timers on one working tree, both
    # pulling and merging every ten minutes.
    assert "systemctl list-unit-files 'hovaysya*.service'" in update
    assert "grep -v -- '-update'" in update, \
        "the update units must be excluded, or a deploy restarts its own timer"
    assert 'systemctl restart "$unit"' in update
    # ...but never unguarded. The restart may appear indented, inside the branch
    # that has already established this is root; at column zero it is the bug.
    for line in update.splitlines():
        assert not line.startswith("systemctl restart"), \
            "unguarded restart: the timer's user may not do that"
    assert 'sudo -n systemctl restart "$unit"' in update
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


def test_the_installers_do_not_refer_to_units_that_are_gone():
    """A `str.replace` I did not assert on left `install-api.sh` sed-ing a unit
    file that the same commit deleted: "sed: can't read
    .../hovaysya-api-update.service: No such file or directory", on his machine
    rather than on mine.

    The check is mechanical because the mistake was: every `deploy/*.service`
    and `deploy/*.timer` a script reads has to exist.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "deploy"
    for script in sorted(root.glob("*.sh")):
        # Comments stripped first, or the test trips over its own explanation --
        # which it did: the comment saying "there is no deploy/x.service" read as
        # a script reading deploy/x.service.
        body = "\n".join(
            line for line in script.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#"))
        for name in re.findall(r"hovaysya[\w-]*\.(?:service|timer)", body):
            if f'"$REPO/deploy/$unit"' in body or f"deploy/{name}" in body:
                assert (root / name).exists(), \
                    f"{script.name} reads deploy/{name}, which is not there"
        # ...and the loop form, where the name is only in the `for` list.
        for block in re.findall(r"for unit in ([^;]+); do(.*?)done", body, re.S):
            if "$REPO/deploy/$unit" not in block[1]:
                continue
            for name in block[0].split():
                assert (root / name).exists(), \
                    f"{script.name} loops over deploy/{name}, which is not there"


def test_the_lean_checkout_keeps_everything_the_backend_needs():
    """His requirement once the app joins the repository: "щоб тільки бекенд
    качався і деплоївся на серверах". The split is in the checkout rather than in
    the history -- one repository, because every decision and the API contract the
    app depends on live in the same `git log` as the code that implements them.

    The risk is the obvious one: excluding a directory the watcher imports would
    take the watch down at the next deploy. So the list is checked against what
    the code actually reaches for.
    """
    lean = _text("lean.sh")
    for needed in ("tools", "deploy", "docs", "labels"):
        assert needed in lean, f"{needed} must survive the sparse checkout"
    # `hovaysya.json` is a root file, and cone mode keeps those whatever happens
    # -- but the watcher will not start without it, so say so out loud.
    assert "hovaysya.json" in lean
    assert "--cone" in lean, "pattern mode is slower and harder to reason about"


def test_both_installers_thin_the_checkout():
    for script in ("install.sh", "install-api.sh"):
        body = _text(script)
        assert "lean.sh" in body, f"{script} must apply the sparse checkout"
        # As the owner, not as root: git would write .git/info/sparse-checkout
        # root-owned and the update timer, which runs as the owner, could not
        # read it.
        assert "SUDO_USER" in body
def test_the_phone_app_never_reaches_a_server():
    """The other half of "щоб тільки бекенд качався і деплоївся на серверах", and
    the half a test can actually hold.

    `lean.sh` names what survives, so a new top-level directory is excluded by
    saying nothing -- which is a guarantee that holds only as long as nobody adds
    it to the list for a reason that seemed good at the time. A box reachable
    from the internet has no business carrying the app's source, and one day its
    signing config.
    """
    lean = _text("lean.sh")
    kept = [line for line in lean.splitlines() if line.startswith("DIRS=")]
    assert len(kept) == 1, kept
    assert "app" not in kept[0].split("=", 1)[1], kept[0]

    root = pathlib.Path(__file__).resolve().parents[2]
    assert (root / "app" / "build.gradle.kts").exists(), (
        "the app is expected at the top level; move this test with it")
def test_the_proxy_lets_the_waiting_endpoint_wait():
    """The one place the proxy config and the code have to agree on a number.

    `/state?wait=30` exists in order not to answer until something changes -- it
    is what replaces a push service. Caddy's `response_header_timeout` was five
    seconds for every path, which was right while every request answered at
    once, and turned the long poll into a 504: the phone's permanent
    notification read "HTTP 504" under the word Ховайся.

    Raising it everywhere would have thrown away the property it was there for,
    so the waiting endpoint gets its own proxy. This pins both halves: that the
    split exists, and that its timeout is above what the API will actually hold.
    """
    import re

    from tools.serve.api import MAX_WAIT_S

    caddy = _text("Caddyfile")
    assert "@waiting path /state" in caddy, "the split is gone"

    # Comments first: the note above the split quotes the old value, and a
    # guard that reads its own explanation is measuring prose.
    directives = chr(10).join(line for line in caddy.splitlines()
                           if not line.strip().startswith("#"))
    timeouts = [int(m) for m in
                re.findall(r"response_header_timeout (\d+)s", directives)]
    assert len(timeouts) == 2, timeouts
    assert max(timeouts) > MAX_WAIT_S, (timeouts, MAX_WAIT_S)
    # ...and the other one still fails fast, which is what it is for.
    assert min(timeouts) <= 5, timeouts


def test_the_proxy_address_is_substituted_everywhere_it_appears():
    """It appears twice now. A `sed` without `g` would have left the second
    proxy pointing at the literal word `PRIVATE_IP`, which resolves to nothing
    and would have failed only on the paths that use it."""
    caddy = _text("Caddyfile")
    assert caddy.count("PRIVATE_IP:8080") == 2, caddy.count("PRIVATE_IP:8080")
    installer = _text("install-proxy.sh")
    assert "s/PRIVATE_IP/$TARGET/g" in installer, "substitution is not global"
