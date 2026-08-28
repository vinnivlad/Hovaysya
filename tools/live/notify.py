"""Send what the app would say to a Telegram bot, so the phone actually beeps.

Not a substitute for the Android client — there is no persistent status line and
no sound that overrides silent mode. What it is for is the comparison he wants
tonight: our notification and the official "Тривога" app side by side on one
screen, both beeping, and afterwards it is obvious which one was worth waking up
for.

The two levels map onto Telegram exactly:

    alert  ->  a normal message, which beeps
    info   ->  `disable_notification`, which appears without a sound

Credentials live in `data/`, which is gitignored:

    data/telegram-bot.token    from @BotFather, one line
    data/telegram-chat.id      written automatically after he messages the bot

Nothing here may take the watcher down. A network failure, a revoked token, a
bot he has not yet written to — all of them log a line and the watch continues,
because a missing notification is a bad night and a crashed watcher is no night
at all.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = REPO_ROOT / "data" / "telegram-bot.token"
CHAT_PATH = REPO_ROOT / "data" / "telegram-chat.id"

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_S = 10


class Notifier:
    """Sends utterances to one Telegram chat, or quietly does nothing."""

    def __init__(self, token_path: Path = TOKEN_PATH,
                 chat_path: Path = CHAT_PATH) -> None:
        self.token = self._read(token_path)
        self.chat_id = self._read(chat_path)
        self.failures = 0
        self.sent = 0

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _call(self, method: str, **params) -> dict | None:
        url = API.format(token=self.token, method=method)
        data = urllib.parse.urlencode(params).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=TIMEOUT_S) as fh:
                return json.loads(fh.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.failures += 1
            if self.failures <= 3:
                print(f"  ! telegram: {exc}", flush=True)
            return None

    def find_chat(self) -> str | None:
        """Pick up the chat id from whatever he has written to the bot.

        Only messages he sent count, and only a private chat: a bot added to a
        group would otherwise capture the id of the group.
        """
        if self.chat_id or not self.enabled:
            return self.chat_id
        reply = self._call("getUpdates", limit=20, timeout=0)
        if not reply or not reply.get("ok"):
            return None
        for update in reversed(reply.get("result", [])):
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            if chat.get("type") == "private" and chat.get("id"):
                self.chat_id = str(chat["id"])
                CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
                CHAT_PATH.write_text(self.chat_id, encoding="utf-8")
                print(f"  telegram: чат {self.chat_id} — напиши боту ще раз,"
                      f" якщо це не той", flush=True)
                return self.chat_id
        return None

    def send(self, text: str, audible: bool = True) -> bool:
        if not self.enabled:
            return False
        if not self.chat_id and not self.find_chat():
            return False
        reply = self._call("sendMessage", chat_id=self.chat_id, text=text,
                           disable_notification="false" if audible else "true")
        if reply and reply.get("ok"):
            self.sent += 1
            return True
        if reply and not reply.get("ok"):
            self.failures += 1
            if self.failures <= 3:
                print(f"  ! telegram: {reply.get('description')}", flush=True)
        return False
