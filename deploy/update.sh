#!/usr/bin/env bash
# Pull main and restart the named units only if something actually changed.
#
#     ./deploy/update.sh                 # the watcher, on A
#     ./deploy/update.sh hovaysya-api    # the API, on B
#
# One script for both boxes rather than a copy per box: what it has to get right
# -- pull only, restart only on a real change, sudo without a prompt -- is the
# same on either, and a copy would drift.
#
# Restarting unconditionally would drop the episode state every ten minutes,
# and the watcher rebuilds it from the last 90 minutes of the database on every
# start — cheap, but not free, and it prints a warm-up line each time. Silence
# when nothing changed is what makes the log readable in the morning.
set -euo pipefail
cd "$(dirname "$0")/.."

units=("${@:-hovaysya}")

before=$(git rev-parse HEAD)
git fetch --quiet origin main
git checkout --quiet main
git merge --quiet --ff-only origin/main
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ]; then
    exit 0
fi

echo "${units[*]}: ${before:0:7} -> ${after:0:7}"
git log --oneline "$before..$after" | sed 's/^/  /'

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
