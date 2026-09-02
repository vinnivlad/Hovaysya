#!/bin/sh
# Keep only the backend in this checkout.
#
# His requirement once the Android client joins the repository: "щоб тільки
# бекенд качався і деплоївся на серверах". A server should carry what it runs and
# nothing else -- the app's source, and one day its signing config, have no
# business on a box that is reachable from the internet.
#
# One repository rather than two, because this project's value is in one history:
# every decision, every measurement and the reason it was taken sit in the same
# `git log`, and the API contract the app depends on is documented beside the code
# that implements it. Two repositories would let those drift, which is the class
# of fault this whole codebase is arranged against.
#
# So the split is in the checkout, not in the history. `git pull` is unchanged and
# needs no flags: sparse configuration is stored in the repository and every later
# pull respects it.
#
#     ./deploy/lean.sh          # from inside the checkout
#
# Idempotent, and safe to run on a checkout that has no app directory yet.
set -eu
cd "$(dirname "$0")/.."

# Cone mode: whole directories rather than patterns, which is the form that stays
# fast and that `git pull` can reason about. Root files come along regardless --
# `hovaysya.json` is needed and the rest is a README.
DIRS="tools deploy docs labels"

if ! git sparse-checkout list >/dev/null 2>&1; then
	git sparse-checkout init --cone
fi
git sparse-checkout set $DIRS

echo "у робочій теці лишається: $DIRS (плюс файли в корені)"
git sparse-checkout list | sed 's/^/  /'
