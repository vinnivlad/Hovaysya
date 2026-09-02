#!/usr/bin/env bash
# Provision this machine to run the watcher. Idempotent: run it again after a
# change to any unit file.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo" >&2
    exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"
# Only the backend on a server: the app source has no business on a box that
# is reachable from the internet. Runs as the checkout owner rather than
# root, or git writes its config as root and the update timer cannot read it.
if [ -n "${SUDO_USER:-}" ]; then
	sudo -u "$SUDO_USER" "$(dirname "$0")/lean.sh" || true
else
	"$(dirname "$0")/lean.sh" || true
fi

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

# The update timer runs as $user, who may not restart a system unit. A password
# prompt is not an option — nobody is at the keyboard at 3 a.m. — so the grant
# is passwordless, and its narrowness is the whole of its safety: one command,
# one unit, nothing else. A malformed sudoers file locks the machine out of sudo
# entirely, so it is validated before being put in place.
sudoers=$(mktemp)
cat > "$sudoers" <<SUDO
# Installed by deploy/install.sh. Lets the update timer restart the watcher
# after it pulls a new commit.
$user ALL=(root) NOPASSWD: /usr/bin/systemctl restart hovaysya.service
SUDO
if visudo -cf "$sudoers" >/dev/null; then
    install -m 0440 -o root -g root "$sudoers" /etc/sudoers.d/hovaysya
else
    echo "refusing to install a sudoers file that does not parse" >&2
    rm -f "$sudoers"
    exit 1
fi
rm -f "$sudoers"

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
