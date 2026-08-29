#!/usr/bin/env bash
# Pull main and restart the watcher only if something actually changed.
#
# Restarting unconditionally would drop the episode state every ten minutes,
# and the watcher rebuilds it from the last 90 minutes of the database on every
# start — cheap, but not free, and it prints a warm-up line each time. Silence
# when nothing changed is what makes the log readable in the morning.
set -euo pipefail
cd "$(dirname "$0")/.."

before=$(git rev-parse HEAD)
git fetch --quiet origin main
git checkout --quiet main
git merge --quiet --ff-only origin/main
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ]; then
    exit 0
fi

echo "hovaysya: ${before:0:7} -> ${after:0:7}"
git log --oneline "$before..$after" | sed 's/^/  /'

# The timer runs this as the checkout's owner, and an ordinary user may not
# restart a system unit: systemd answers "Interactive authentication required",
# which is exactly what the first real deploy hit. The pull had already
# succeeded, so the machine sat with new code on disk and the old process still
# running — worse than either failing outright.
#
# install.sh grants this one command, passwordless, through sudo. Run as root by
# hand it needs none of that.
if [ "$(id -u)" -eq 0 ]; then
    systemctl restart hovaysya
else
    sudo -n systemctl restart hovaysya
fi
