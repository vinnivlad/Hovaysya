#!/bin/sh
# Set up TLS on B, proxying to the API on A over the private network.
#
# Run on **B**, the box with the open port. It installs Caddy, gets a Let's
# Encrypt certificate for the DuckDNS name, and points it at A's private VCN
# address -- so the app reads the database the watcher has just written, with
# nothing replicated and nothing stale.
#
#     sudo ./deploy/install-proxy.sh hovaysya.duckdns.org 10.0.0.42
#
# Idempotent: running it again rewrites the config and reloads Caddy.
set -eu

HOST="${1:-}"
TARGET="${2:-}"
if [ -z "$HOST" ] || [ -z "$TARGET" ]; then
	echo "потрібні хост і приватна адреса A:" >&2
	echo "  sudo ./deploy/install-proxy.sh hovaysya.duckdns.org 10.0.0.42" >&2
	exit 2
fi

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OWNER_GROUP="$(stat -c %G "$REPO")"

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

echo "== Caddyfile: $HOST -> $TARGET:8080"
sed "s/hovaysya\.duckdns\.org/$HOST/; s/PRIVATE_IP/$TARGET/" \
	"$REPO/deploy/Caddyfile" > /etc/caddy/Caddyfile
install -d -o caddy -g caddy /var/log/caddy
caddy validate --config /etc/caddy/Caddyfile >/dev/null

echo "== порти 80 і 443"
# Caddy needs 80 for the ACME challenge and 443 to serve. Oracle's security list
# or an NSG has to allow them too, and that is a click in the dashboard -- iptables
# alone will look like it worked and then time out.
for port in 80 443; do
	iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
		|| iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
done
command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save || true

echo "== оновлювач DuckDNS"
case "$HOST" in
*.duckdns.org)
	DUCK_NAME="${HOST%%.duckdns.org}"
	if [ -r "$REPO/data/duckdns.token" ]; then
		# Written inline: there is no `deploy/hovaysya-duckdns.service` to copy,
		# and the `sed ... || cat` form that used to be here meant the first half
		# never ran. A test now checks that no script reads a unit file which is
		# not in the repository, because that is how this was found.
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
	else
		echo "  пропускаю: нема $REPO/data/duckdns.token"
	fi
	;;
*) echo "  пропускаю: $HOST не з duckdns.org" ;;
esac

systemctl enable caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy
sleep 2
systemctl is-active --quiet caddy && echo "  Caddy працює" \
	|| { echo "  ! Caddy не піднявся:"; journalctl -u caddy -n 12 --no-pager; }

echo
echo "готово. Далі:"
echo "  1. NSG на A має впускати 8080 з приватної адреси цієї машини"
echo "  2. на A: sudo ./deploy/install-api.sh (він слухатиме приватну адресу)"
echo "  3. curl https://$HOST/health"
echo
echo "B більше не тримає ні бази, ні токенів — тільки сертифікат."
