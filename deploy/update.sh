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
systemctl restart hovaysya
