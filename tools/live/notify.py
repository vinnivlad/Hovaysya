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
    data/telegram-chat.id      where to send — one id per line

**A bot cannot be made private.** Its username is public and anyone who knows it
can write to it; that is how Telegram works and there is no setting for it. What
can be controlled is who receives anything, and there are two ways:

- **A private channel.** He creates one, adds the bot as an administrator, and
  puts the channel's id in the file. People he invites see the alerts; nobody
  else can even find the channel. This is also how a few other people get the
  app without a store, which was the original distribution plan.
- **Direct chats**, one id per line. Each person has to write to the bot first,
  because a bot may not open a conversation.

Discovery is deliberately a handshake rather than "whoever wrote last": the
watcher prints a code and accepts the chat only from a message containing it.
Without that, a stranger who found the bot and wrote to it before he did would
have been cached as the recipient — and would have received his alerts.

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
                 chat_path: Path = CHAT_PATH, code: str | None = None) -> None:
        self.token = self._read(token_path)
        self.chat_path = chat_path
        raw = self._read(chat_path) or ""
        self.chats = [line.strip() for line in raw.splitlines() if line.strip()]
        self.code = code or "hovaysya"
        self.failures = 0
        self.sent = 0

    @property
    def chat_id(self) -> str | None:
        return self.chats[0] if self.chats else None

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
        """Add a chat that has said the code word, and only such a chat.

        "Whoever wrote last" was the first version, and it is a hole: the bot's
        username is public, so a stranger who found it and wrote first would
        have been cached as the recipient of his alerts.
        """
        if self.chats or not self.enabled:
            return self.chat_id
        reply = self._call("getUpdates", limit=40, timeout=0)
        if not reply or not reply.get("ok"):
            return None
        for update in reversed(reply.get("result", [])):
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            text = (message.get("text") or "").lower()
            if not chat.get("id") or self.code not in text:
                continue
            self.chats = [str(chat["id"])]
            self.chat_path.parent.mkdir(parents=True, exist_ok=True)
            self.chat_path.write_text(self.chats[0] + chr(10), encoding="utf-8")
            name = chat.get("username") or chat.get("title") or chat.get("first_name")
            print(f"  telegram: додано {name or self.chats[0]}", flush=True)
            return self.chat_id
        return None

    def send(self, text: str, audible: bool = True) -> bool:
        """To every recipient. One failing must not stop the others."""
        if not self.enabled:
            return False
        if not self.chats and not self.find_chat():
            return False
        delivered = False
        for chat in self.chats:
            reply = self._call("sendMessage", chat_id=chat, text=text,
                               disable_notification="false" if audible else "true")
            if reply and reply.get("ok"):
                self.sent += 1
                delivered = True
            elif reply:
                self.failures += 1
                if self.failures <= 3:
                    print(f"  ! telegram {chat}: {reply.get('description')}",
                          flush=True)
        return delivered


# Every label the policy assigned, in the schema's own words rather than
# translated: these are the values the labels use, so a post can be compared
# against `labels/*.jsonl` directly. His reason for wanting them — "так легше
# потім аналізувати".
# `летить` and `де` are named because they are the two he reads first, and
# because dropping an empty one shifted everything left — with `threat` unknown
# the first value became the scope, and he read the rule name as the class. The
# rest keep the schema's bare values, which is what makes a post comparable to
# `labels/*.jsonl` by eye.
NAMED_FIELDS = (("летить", "threat"), ("де", "scope"))
TAG_FIELDS = ("modality", "certainty", "heading", "alarm")


def format_message(utterance, obs, decision) -> str:
    """What goes to the channel: the sentence, the labels, and the source.

    The bell marks a message that made a sound. In a Telegram channel every post
    looks alike afterwards, and telling a wake-up from a status line by scrolling
    back is exactly the analysis he wants to do.
    """
    head = ("🔔 " if decision.audible else "") + utterance.text

    tags = []
    for label, field in NAMED_FIELDS:
        value = getattr(obs, field, None)
        if field == "threat":
            value = obs.effective_threat or value
        tags.append(f"{label}={value or '?'}")
    for field in TAG_FIELDS:
        value = decision.alarm if field == "alarm" else getattr(obs, field, None)
        if value and value not in ("none", "unknown", "position"):
            tags.append(str(value))
    if getattr(obs, "official", False):
        tags.append("official")
    line = " · ".join(tags)

    source = (obs.text or "").replace(chr(10), " / ")
    if len(source) > 220:
        source = source[:217] + "..."

    # Both lines are labelled. Unlabelled, they read as one list, and he took
    # the rule name for the threat class — "це в тексті drone near me but not my
    # street?" The order inside `мітки` is fixed and the class is always first.
    parts = [head]
    if line:
        parts.append("мітки: " + line)
    parts.append("правило: " + decision.reason)
    if source and source not in utterance.text:
        parts.append("— " + source)
    return chr(10).join(parts)
