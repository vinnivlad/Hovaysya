#!/bin/sh
# Pull, and apply the Caddyfile only if it actually changed. Run on B.
#
#     sudo ./deploy/update-proxy.sh hovaysya.duckdns.org 10.0.0.75
#
# Why this exists at all, and it is a gap I left rather than a new feature: A has
# had `hovaysya-update.timer` since the first deploy, and B had nothing. Its
# checkout moved only when somebody typed `git pull` — and when that started
# asking for a password, B silently stopped receiving anything. The proxy change
# that fixes a 504 would have sat on disk indefinitely, and the only sign would
# have been the app still reading "HTTP 504".
#
# `update.sh` cannot do this job: it restarts units, and a Caddyfile has to be
# re-templated with the hostname and A's private address before it means
# anything. So this is the same idea with the apply step B needs.
set -eu

HOST="${1:-}"
TARGET="${2:-}"
if [ -z "$HOST" ] || [ -z "$TARGET" ]; then
	echo "потрібні хост і приватна адреса A:" >&2
	echo "  sudo ./deploy/update-proxy.sh hovaysya.duckdns.org 10.0.0.75" >&2
	exit 2
fi

REPO="$(cd "$(dirname "$0")/.." && pwd)"
# The checkout belongs to a person, not to root. Pulling as root would rewrite
# `.git` ownership and the next ordinary pull would fail on it — the same fault
# `install-api.sh` warns about.
OWNER="$(stat -c %U "$REPO/.git")"

as_owner() {
	if [ "$(id -un)" = "$OWNER" ]; then
		"$@"
	else
		runuser -u "$OWNER" -- "$@"
	fi
}

before="$(as_owner git -C "$REPO" rev-parse HEAD)"
# Never a prompt. A timer has no terminal, so a git that decides to ask for a
# password does not fail — it waits, holding the repository lock, until somebody
# notices days later. This is what turns that into an error in the journal.
GIT_TERMINAL_PROMPT=0 as_owner git -C "$REPO" fetch --quiet origin main
as_owner git -C "$REPO" merge --quiet --ff-only origin/main
after="$(as_owner git -C "$REPO" rev-parse HEAD)"

# Compared as a rendered config rather than by commit: almost nothing committed
# here touches the proxy, and reloading Caddy because the gazetteer gained a
# street would be noise in a log that has to stay readable.
rendered="$(mktemp)"
trap 'rm -f "$rendered"' EXIT
sed "s/hovaysya\\.duckdns\\.org/$HOST/g; s/PRIVATE_IP/$TARGET/g" \
	"$REPO/deploy/Caddyfile" > "$rendered"

if cmp -s "$rendered" /etc/caddy/Caddyfile; then
	exit 0
fi

echo "Caddyfile змінився: ${before%"${before#???????}"} -> ${after%"${after#???????}"}"
# Validated before it is installed. A config Caddy cannot parse would otherwise
# be found by the reload failing, with the old file already overwritten.
caddy validate --config "$rendered" --adapter caddyfile >/dev/null
install -m 0644 "$rendered" /etc/caddy/Caddyfile
systemctl reload caddy
sleep 2
if systemctl is-active --quiet caddy; then
	echo "  Caddy перечитав конфіг"
else
	echo "  ! Caddy не піднявся:"
	journalctl -u caddy -n 12 --no-pager
	exit 1
fi
