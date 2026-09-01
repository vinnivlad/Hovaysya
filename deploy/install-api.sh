#!/bin/sh
# Set up the API and the TLS in front of it, on the box that has the open port.
#
# Run on the *second* instance, not the one running the watcher. The reason is in
# deploy/README.md: the machine reachable from the internet is not the machine
# holding the bot token, and the bell must not travel through anything that can
# be attacked from outside.
#
#     sudo ./deploy/install-api.sh hovaysya.duckdns.org
#
# Idempotent. Running it again re-reads the unit and reloads Caddy.
set -eu

HOST="${1:-}"
if [ -z "$HOST" ]; then
	echo "потрібне ім'я хоста, напр. ./deploy/install-api.sh hovaysya.duckdns.org" >&2
	echo "Let's Encrypt не видає сертифікат на голий IP." >&2
	exit 2
fi

REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "== окремий користувач для сервісу"
id -u hovaysya-api >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin hovaysya-api

# The repo sits in somebody's home, and Ubuntu creates a home as 0750 -- owner and
# owning group only. Without this the service dies with 200/CHDIR: "Changing to
# the requested working directory failed: Permission denied", which reads like a
# systemd sandbox problem and is really a POSIX one.
#
# Joining the group rather than `chmod o+x` on the home directory: the group is
# already the boundary the files were created with, and widening the home to
# everyone would be a broader change than this needs.
OWNER="$(stat -c %U "$REPO")"
OWNER_GROUP="$(stat -c %G "$REPO")"
usermod -aG "$OWNER_GROUP" hovaysya-api
echo "  hovaysya-api додано в групу $OWNER_GROUP (власник репозиторію: $OWNER)"

install -d -o hovaysya-api -g hovaysya-api -m 0750 "$REPO/data/recipients"

echo "== Caddy"
if ! command -v caddy >/dev/null 2>&1; then
	apt-get update
	apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
	curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
		| gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
	echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" \
		> /etc/apt/sources.list.d/caddy-stable.list
	apt-get update
	apt-get install -y caddy
fi

echo "== Caddyfile для $HOST"
sed "s/hovaysya\.duckdns\.org/$HOST/" "$REPO/deploy/Caddyfile" > /etc/caddy/Caddyfile
install -d -o caddy -g caddy /var/log/caddy

echo "== сервіс"
sed "s#/home/ubuntu/hovaysya#$REPO#g" "$REPO/deploy/api.service" > /etc/systemd/system/hovaysya-api.service
systemctl daemon-reload
systemctl enable --now hovaysya-api

# Caddy needs 80 for the ACME challenge and 443 to serve. Oracle's own security
# list has to allow them too, and that is a click in the dashboard rather than a
# command here -- iptables alone will look like it worked and time out.
echo "== порти"
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 80 -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 443 -j ACCEPT
command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save || true

echo "== оновлювач DuckDNS"
# Only if the hostname is a DuckDNS one and the token has been placed. Without
# this the name silently stops pointing here the first time the address changes,
# and that failure looks exactly like a quiet night.
case "$HOST" in
*.duckdns.org)
	DUCK_NAME="${HOST%%.duckdns.org}"
	if [ -r "$REPO/data/duckdns.token" ]; then
		cat > /etc/systemd/system/hovaysya-duckdns.service <<UNIT
[Unit]
Description=Keep the DuckDNS name pointing here
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=$REPO/deploy/duckdns.sh $DUCK_NAME
UNIT
		cat > /etc/systemd/system/hovaysya-duckdns.timer <<UNIT
[Unit]
Description=Keep the DuckDNS name pointing here

[Timer]
OnBootSec=1min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
UNIT
		systemctl daemon-reload
		systemctl enable --now hovaysya-duckdns.timer
		systemctl start hovaysya-duckdns.service || echo "  ! перший апдейт не вдався — перевір токен"
	else
		echo "  пропускаю: нема $REPO/data/duckdns.token"
	fi
	;;
*)
	echo "  пропускаю: $HOST не з duckdns.org"
	;;
esac

systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo
echo "готово. Далі:"
echo "  1. у дашборді Oracle дозволь 80 і 443 у security list цього інстанса"
echo "  2. python3 -m tools.serve.token --name <хто>   — і збережи токен"
echo "  3. curl https://$HOST/health"
echo
echo "і окремо, один раз у дашборді: зарезервуй публічний IP цього інстанса,"
echo "бо ephemeral змінюється при зупинці — оновлювач це підхопить, але з паузою"
