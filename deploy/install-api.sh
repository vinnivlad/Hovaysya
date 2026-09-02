#!/bin/sh
# Set up the API on A, beside the watcher.
#
# It reads the database the watcher has just written, so there is nothing to
# replicate and nothing to be stale -- his constraint, and the reason for this
# shape: "якщо треба чекати поки щось запушиться, а потім поки застосунок
# опитає - то сенс застосунку губиться".
#
# TLS lives on B. Run `deploy/install-proxy.sh <host> <this machine's 10.x>`
# there afterwards.
#
#     sudo ./deploy/install-api.sh              # finds the private address
#     sudo ./deploy/install-api.sh 10.0.0.42    # or takes it
#
# Idempotent: running it again rewrites the unit and restarts the service.
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"

# The API binds to this machine's private VCN address -- the only place Caddy on
# B can reach it from, and the only place anything can. Never 0.0.0.0: that would
# put it on the public interface, which is the whole thing this arrangement
# avoids.
if [ -n "${1:-}" ]; then
	PRIVATE_IP="$1"
else
	PRIVATE_IP="$(hostname -I | tr ' ' '\012' | grep -E '^10\.' | head -1)"
fi
if [ -z "$PRIVATE_IP" ]; then
	echo "не знайшов приватної адреси 10.x — передай її аргументом" >&2
	exit 2
fi

echo "== окремий користувач для сервісу"
id -u hovaysya-api >/dev/null 2>&1 \
	|| useradd --system --no-create-home --shell /usr/sbin/nologin hovaysya-api

# The repo sits in somebody's home, and Ubuntu creates a home as 0750 -- owner
# and owning group only. Without this the service dies with 200/CHDIR: "Changing
# to the requested working directory failed: Permission denied", which reads like
# a systemd sandbox problem and is really a POSIX one.
OWNER="$(stat -c %U "$REPO")"
OWNER_GROUP="$(stat -c %G "$REPO")"
usermod -aG "$OWNER_GROUP" hovaysya-api
echo "  hovaysya-api додано в групу $OWNER_GROUP (власник: $OWNER)"

# Two parties write here and only one is the service: `tools.serve.token` is run
# by a person, and 0750 hovaysya-api:hovaysya-api locked that person out. Setgid
# keeps the group for whatever either of them creates later.
install -d -o hovaysya-api -g "$OWNER_GROUP" -m 2770 "$REPO/data/recipients"

echo "== сервіс на $PRIVATE_IP:8080"
sed "s#/home/ubuntu/hovaysya#$REPO#g; s#PRIVATE_IP#$PRIVATE_IP#" \
	"$REPO/deploy/api.service" > /etc/systemd/system/hovaysya-api.service

echo "== автооновлення"
# No timer of its own. `deploy/update.sh` with no arguments asks systemd which
# hovaysya services are enabled and restarts those, so the watcher's existing
# `hovaysya-update.timer` already covers this service once it is enabled.
#
# A second timer is what this replaced, and it was a fault rather than
# untidiness: two timers pulling and merging in the same working tree every
# ten minutes can collide, and one of them was needless.
systemctl disable --now hovaysya-api-update.timer 2>/dev/null || true
rm -f /etc/systemd/system/hovaysya-api-update.service \
      /etc/systemd/system/hovaysya-api-update.timer

# The update timer runs as the checkout's owner, who may not restart a system
# unit: systemd answers "Interactive authentication required". Nobody is at the
# keyboard at 3 a.m., so the grant is passwordless, and its narrowness is its
# safety -- one command, one unit. A malformed sudoers file locks the machine out
# of sudo entirely, so it is validated before being installed.
sudoers="$(mktemp)"
cat > "$sudoers" <<SUDO
# Installed by deploy/install-api.sh. Lets the update timer restart the API.
$OWNER ALL=(root) NOPASSWD: /usr/bin/systemctl restart hovaysya-api.service
SUDO
if visudo -cf "$sudoers" >/dev/null; then
	install -m 0440 -o root -g root "$sudoers" /etc/sudoers.d/hovaysya-api
else
	echo "не встановлюю sudoers, який не парситься" >&2
	rm -f "$sudoers"
	exit 1
fi
rm -f "$sudoers"

echo "== порт 8080, лише з приватної мережі"
# The VCN's own rules decide who may reach it; this only stops the host firewall
# from dropping what the VCN allowed. The source is deliberately the subnet
# rather than anywhere: an NSG on this instance should narrow it to B alone.
iptables -C INPUT -s 10.0.0.0/16 -p tcp --dport 8080 -j ACCEPT 2>/dev/null \
	|| iptables -I INPUT -s 10.0.0.0/16 -p tcp --dport 8080 -j ACCEPT
command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save || true

systemctl daemon-reload
systemctl enable hovaysya-api
# `restart`, not `enable --now`: a unit already stuck in a restart loop counts as
# starting, so `--now` does nothing and a second run of this script looks like it
# changed nothing at all.
systemctl restart hovaysya-api
sleep 2
if systemctl is-active --quiet hovaysya-api; then
	echo "  сервіс піднявся"
else
	echo "  ! сервіс не піднявся:"
	journalctl -u hovaysya-api -n 10 --no-pager
	exit 1
fi

echo
echo "готово: API слухає $PRIVATE_IP:8080 — приватну мережу, не інтернет."
echo
echo "далі:"
echo "  1. NSG на цьому інстансі: впустити 8080 з приватної адреси B"
echo "  2. python3 -m tools.serve.token --name <хто>   — показується один раз"
echo "  3. на B: sudo ./deploy/install-proxy.sh <хост> $PRIVATE_IP"
echo
echo "оновлюється саме, раз на 10 хвилин, як і вартовий."
echo "виняток — сам цей скрипт: зміна в api.service вимагає запустити його знову."
