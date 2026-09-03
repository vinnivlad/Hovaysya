"""Who the watcher is deciding for, and how to drop somebody who is gone.

    python -m tools.people                    # list
    python -m tools.people --forget 4f2a1c    # by the start of the digest
    python -m tools.people --forget test      # or by name, when it is unique

His question, from a startup log with four recipients in it: "тут ще питання чого
4? Має бути 2, ТГ канал і мій телефон. Тестових я наче всіх видаляв."

He had. From the app -- and that is the only broom there was, which is not
enough. `unregister` needs the device's own token, so a phone that reinstalled
the app cannot ask to be forgotten: reinstalling generates a fresh secret, and
the old row keeps its place in the index with nothing left anywhere that could
authorise removing it. `unregister`'s own comment anticipated this and named the
consequence -- "the only broom would be a terminal on the server" -- and then
the terminal never got one.

A forgotten recipient is not dangerous. It has the same home, so it decides the
same thing, and no phone is listening. It is expensive in the way that matters
least until it does not: a line per person in the journal, a decision per person
per message, a state file written per person per cycle. Four made the live feed
four times as long as the night it was describing.

Names can repeat -- his rule, "май на увазі що імена можуть повторюватись" -- so
the digest prefix is the address and the name is a convenience that refuses to
guess when it is ambiguous.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .policy import tokens
from .policy.recipients import config_of


def rows(directory: Path) -> list[tuple[str, str, bool]]:
    """(digest, name, has its own settings), in the index's own order."""
    entries = tokens.index(directory)
    out = []
    for digest, name in entries.items():
        settings = (directory / f"{Path(name).name}.json").exists()
        out.append((digest, name, settings))
    return out


def show(directory: Path) -> None:
    people = rows(directory)
    print(f"{tokens.TELEGRAM_NAME}  (завжди є, налаштування з hovaysya.json)")
    if not people:
        print("більше нікого")
        return
    for digest, name, settings in people:
        home = config_of(name, directory).home or "(газетир)"
        note = "" if settings else "  · без власних налаштувань"
        print(f"{digest[:8]}  {name:<20} {home}{note}")


def forget(directory: Path, wanted: str) -> int:
    """Drop one row from the index and its settings file with it.

    Refuses an ambiguous name rather than picking one, because two people called
    the same thing is a case he asked for explicitly and deleting the wrong one
    is not recoverable from here.
    """
    people = rows(directory)
    by_digest = [row for row in people if row[0].startswith(wanted)]
    by_name = [row for row in people if row[1] == wanted]
    found = by_digest or by_name

    if not found:
        print(f"нема такого: {wanted}", file=sys.stderr)
        return 1
    if len(found) > 1:
        print(f"неоднозначно, {len(found)} збігів — вкажи початок хешу:",
              file=sys.stderr)
        for digest, name, _ in found:
            print(f"  {digest[:8]}  {name}", file=sys.stderr)
        return 1

    digest, name, _ = found[0]
    current = tokens.index(directory)
    del current[digest]
    tokens.write_index(current, directory)
    try:
        (directory / f"{Path(name).name}.json").unlink()
    except OSError:
        pass
    print(f"забув {name} ({digest[:8]})")
    print("вартовий підхопить сам, перезапускати не треба")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--forget", metavar="ХЕШ-АБО-ІМʼЯ",
                        help="прибрати отримувача, який уже не існує")
    parser.add_argument("--dir", type=Path, default=tokens.DIR,
                        help="каталог отримувачів")
    args = parser.parse_args(argv)

    if args.forget:
        return forget(args.dir, args.forget)
    show(args.dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
