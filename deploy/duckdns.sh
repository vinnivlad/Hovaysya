#!/bin/sh
# Keep the DuckDNS name pointing at this machine.
#
# Needed because there is no own domain -- his call, and a reasonable one -- so
# the name comes from DuckDNS and nothing else keeps it current. Oracle hands out
# an *ephemeral* public IP by default: stop and start the instance and it changes,
# and a reclaimed instance is replaced by one with a different address entirely.
# The name would then point at nothing and the app would simply stop reaching us,
# which looks exactly like a quiet night.
#
# Reserving the IP in the dashboard is the other half of this and is free. Do
# both: the reservation stops it changing, this notices if it changed anyway.
#
#     echo <duckdns-token> > data/duckdns.token
#     chmod 600 data/duckdns.token
#     ./deploy/duckdns.sh hovaysya
set -eu

NAME="${1:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_FILE="${DUCKDNS_TOKEN_FILE:-$REPO/data/duckdns.token}"

if [ -z "$NAME" ]; then
	echo "потрібне ім'я, напр. ./deploy/duckdns.sh hovaysya" >&2
	exit 2
fi
if [ ! -r "$TOKEN_FILE" ]; then
	echo "нема $TOKEN_FILE" >&2
	exit 2
fi

TOKEN="$(tr -d ' \t\n\r' < "$TOKEN_FILE")"

# DuckDNS works out the address from the request itself when `ip` is empty, which
# is what we want: whatever this machine looks like from outside is the answer.
REPLY="$(curl -fsS --max-time 20 \
	"https://www.duckdns.org/update?domains=$NAME&token=$TOKEN&ip=" || echo FAIL)"

case "$REPLY" in
	OK) exit 0 ;;                       # a healthy run says nothing at all
	*)
		echo "duckdns: $NAME не оновився — відповідь: $REPLY" >&2
		exit 1
		;;
esac
