"""Mint a token for one recipient, print it once, and store only its hash.

The token is what an app sends; the hash is all this machine keeps. That matters
because the machine also holds the bot token, and a leak of one file should not be
a leak of both.

Printed once and never recoverable: if it is lost, mint another. Which is also
how a token is revoked -- minting for the same name replaces the old hash.

    python -m tools.serve.token --name vinni
    python -m tools.serve.token --list
    python -m tools.serve.token --revoke vinni
"""

from __future__ import annotations

import argparse
import json
import secrets

from ..policy import recipients as people


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="whose token to mint")
    ap.add_argument("--revoke", metavar="NAME")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dir", default=str(people.DIR))
    args = ap.parse_args()

    from pathlib import Path

    directory = Path(args.dir)
    index = people.index(directory)

    if args.list:
        if not index:
            print("токенів нема")
        for digest, name in sorted(index.items(), key=lambda kv: kv[1]):
            has = (directory / f"{name}.json").exists()
            print(f"  {name:16} {digest[:12]}…  "
                  f"{'налаштування є' if has else 'налаштувань ще нема'}")
        return

    if args.revoke:
        index = {d: n for d, n in index.items() if n != args.revoke}
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        # The settings stay: a revoked token is usually a lost phone, and
        # throwing away where somebody lives would be a poor answer to that.
        print(f"{args.revoke}: токен відкликано, налаштування лишились")
        return

    if not args.name:
        raise SystemExit("потрібен --name, --revoke або --list")

    token = secrets.token_urlsafe(32)
    index = {d: n for d, n in index.items() if n != args.name}
    index[people.hashed(token)] = args.name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{args.name}: {token}")
    print("  показано один раз — зберігай зараз. Тут лишається тільки хеш.")


if __name__ == "__main__":
    main()
