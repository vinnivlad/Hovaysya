#!/usr/bin/env bash
# Pull main and restart the named units only if something actually changed.
#
#     ./deploy/update.sh                 # every enabled hovaysya unit
#     ./deploy/update.sh hovaysya-api    # or just the named ones
#
# One script for both boxes rather than a copy per box: what it has to get right
# -- pull only, restart only on a real change, sudo without a prompt -- is the
# same on either, and a copy would drift.
#
# With no arguments it *asks systemd* which units to restart rather than being
# told. That is not cleverness, it is the fix for a real fault: installing the
# API on A left two update timers on one working tree, both pulling and merging
# every ten minutes, which can collide and is needless either way. Discovery
# means one timer, and neither installer can undo the other's arrangement.
#
# Restarting unconditionally would drop the episode state every ten minutes,
# and the watcher rebuilds it from the database on every start — cheap, but not
# free, and it prints a warm-up line each time. Silence when nothing changed is
# what makes the log readable in the morning.
#
# "Nothing changed" used to mean "HEAD did not move", and that was too coarse.
# An Android-only commit moves HEAD, so shipping a sound for the phone restarted
# the watcher on the server and cost a live episode. Nothing under `app/` is even
# checked out here. So the question is not whether the repository moved, it is
# whether anything these units read moved.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -gt 0 ]; then
    units=("$@")
else
    # Enabled hovaysya services, minus the update machinery itself: restarting
    # the timer that is running us would be a fine way to lose a deploy.
    mapfile -t units < <(
        systemctl list-unit-files 'hovaysya*.service' --state=enabled --no-legend             | awk '{print $1}' | grep -v -- '-update' | sed 's/\.service$//')
fi
if [ "${#units[@]}" -eq 0 ]; then
    units=()
fi

before=$(git rev-parse HEAD)
# Never a prompt. A timer has no terminal, so a git that decides to ask for a
# password does not fail -- it waits, holding the repository lock, until somebody
# notices days later. B spent a day in exactly that state for a different
# reason, and this is one line against the same shape of silence.
export GIT_TERMINAL_PROMPT=0
git fetch --quiet origin main
git checkout --quiet main
git merge --quiet --ff-only origin/main
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ]; then
    exit 0
fi

echo "${units[*]:-нічого перезапускати}: ${before:0:7} -> ${after:0:7}"
git log --oneline "$before..$after" | sed 's/^/  /'

# Paths no running unit reads: the Android app, prose, and the label files the
# eval uses. Everything else counts, including anything new -- an unknown path
# restarts, because being one deploy late is a smaller fault than running old
# code without knowing it.
if ! git diff --name-only "$before..$after" \
        | grep -qvE '^(app/|docs/|labels/|README\.md$|\.gitignore$)'; then
    echo "  — служб не торкається, не перезапускаю"
    exit 0
fi

# The timer runs this as the checkout's owner, and an ordinary user may not
# restart a system unit: systemd answers "Interactive authentication required",
# which is exactly what the first real deploy hit. The pull had already
# succeeded, so the machine sat with new code on disk and the old process still
# running — worse than either failing outright.
#
# install.sh grants this one command, passwordless, through sudo. Run as root by
# hand it needs none of that.
#
# The Caddyfile is *not* applied here. It is generated into /etc/caddy by
# install-api.sh, so a change to it in git needs that script run again -- which
# also reloads Caddy. Restarting Caddy from a timer that never rewrote its config
# would look like a deploy and change nothing.
for unit in "${units[@]}"; do
    if [ "$(id -u)" -eq 0 ]; then
        systemctl restart "$unit"
    else
        sudo -n systemctl restart "$unit"
    fi
done
