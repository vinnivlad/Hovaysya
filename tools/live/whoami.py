"""Show every chat the bot can currently see, with its id.

Finding a channel's id by hand means opening an API URL with the token in it and
reading raw JSON. This does it instead: add the bot to the channel as an
administrator, post anything there, and run this.

    python -m tools.live.whoami
    python -m tools.live.whoami --save -1001234567890

Telegram keeps undelivered updates for 24 hours and drops them once read, so if
nothing appears, post in the channel again and re-run. A channel only produces
updates at all once the bot is an administrator — that is the usual reason for
an empty list.
"""

from __future__ import annotations

import argparse

from .notify import CHAT_PATH, Notifier

KIND = {
    "private": "особистий чат",
    "channel": "канал",
    "group": "група",
    "supergroup": "супергрупа",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--save", metavar="ID", action="append",
                    help="Write these ids to the recipient file (repeatable).")
    args = ap.parse_args(argv)

    if args.save:
        CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHAT_PATH.write_text("\n".join(args.save) + "\n", encoding="utf-8")
        print(f"Записано {len(args.save)} отримувач(ів) у {CHAT_PATH}")
        return 0

    bot = Notifier()
    if not bot.enabled:
        print("Нема токена. Поклади його в data/telegram-bot.token")
        return 1

    me = bot._call("getMe")
    if me and me.get("ok"):
        print(f"Бот: @{me['result'].get('username')}")
    print(f"Зараз надсилає до: {bot.chats or '(нікого)'}")
    print()

    reply = bot._call("getUpdates", limit=100, timeout=0)
    if not reply or not reply.get("ok"):
        print("Не вдалося отримати оновлення.")
        return 1

    seen: dict[str, tuple[str, str]] = {}
    for update in reply.get("result", []):
        message = (update.get("message") or update.get("channel_post")
                   or update.get("edited_channel_post") or {})
        chat = message.get("chat") or {}
        if not chat.get("id"):
            continue
        name = (chat.get("title") or chat.get("username")
                or chat.get("first_name") or "?")
        seen[str(chat["id"])] = (KIND.get(chat.get("type"), chat.get("type", "?")),
                                 name)

    if not seen:
        print("Порожньо. Або бот ще не адміністратор каналу, або нічого не")
        print("написано після того, як він ним став, або оновлення вже прочитані")
        print("(Telegram віддає їх один раз). Напиши в канал ще раз і повтори.")
        return 0

    print("Кого бачить:")
    for chat_id, (kind, name) in seen.items():
        print(f"  {chat_id:<18} {kind:<16} {name}")
    print()
    print("Обери потрібний і виконай:")
    first = next(iter(seen))
    print(f"  python -m tools.live.whoami --save {first}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
