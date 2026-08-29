#!/usr/bin/env bash
# Provision this machine to run the watcher. Idempotent: run it again after a
# change to any unit file.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
user="${SUDO_USER:-ubuntu}"

python3 --version
chmod +x "$here/update.sh"

# The units name /home/ubuntu/hovaysya; if the checkout is somewhere else, say
# so rather than installing something that silently will not start.
if [ "$root" != "/home/$user/hovaysya" ]; then
    echo "checkout is at $root but the units expect /home/$user/hovaysya" >&2
    echo "either move it there or edit deploy/*.service" >&2
    exit 1
fi

for unit in hovaysya.service hovaysya-update.service hovaysya-update.timer; do
    sed "s|/home/ubuntu|/home/$user|g; s|User=ubuntu|User=$user|" \
        "$here/$unit" > "/etc/systemd/system/$unit"
done

systemctl daemon-reload
systemctl enable hovaysya.service hovaysya-update.timer
systemctl start hovaysya-update.timer

cat <<TXT

Installed. Before starting the watcher:

  1. data/telegram-bot.token   and   data/telegram-chat.id
  2. python3 -m tools.export.export --since 2026-07-01
     (a channel with no history starts blind — it begins at the newest message)

Then:  sudo systemctl start hovaysya
       journalctl -u hovaysya -f
TXT
