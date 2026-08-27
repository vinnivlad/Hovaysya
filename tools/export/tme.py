"""Read public Telegram channels through the t.me/s/ web preview.

Public channels expose their full feed as plain HTML at `t.me/s/<channel>`, with
no authentication, no account, and no phone number. Measured properties that
make this a viable source (2026-08-27, against the three Kyiv monitoring
channels):

- `?before=<id>` accepts an arbitrary id, so history is random-access, not just
  a sequential walk. That is what lets the backfill run in parallel blocks.
- `?after=<id>` returns only messages newer than `<id>` — about 5 KB when
  nothing is new, versus 9 KB gzipped for a full page. Cheap polling.
- No ETag or Last-Modified is offered, so conditional GET / 304 is impossible;
  `?after=` is the better mechanism anyway.
- A new post appears here roughly 2 s after being published.

Parsing notes that are easy to get wrong:

- A message's own text is `js-message_text`. A quoted reply is
  `js-message_reply_text` and appears FIRST in document order, so anchoring on
  the shared `tgme_widget_message_text` class silently captures the quoted
  older message instead of the real one.
- Telegram wraps emoji as `<i class="emoji"><b>X</b></i>`; stripping tags
  leaves the character, which is what we want.
- Promo footers live inside a trailing `<a>`; they are removed later by
  `normalize.normalize_text`, not here.
"""

from __future__ import annotations

import gzip
import html as htmlmod
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock

from .store import Msg

BASE = "https://t.me/s"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

_POST = re.compile(r'data-post="([^/"]+)/(\d+)"')
_DATE = re.compile(r'tgme_widget_message_date.*?datetime="([^"]+)"', re.S)
_ANY_DATETIME = re.compile(r'datetime="([^"]+)"')
_VIEWS = re.compile(r'tgme_widget_message_views"[^>]*>([^<]*)<')
_REPLY_HREF = re.compile(r'tgme_widget_message_reply[^"]*"\s+href="[^"]*/(\d+)"')
_FWD = re.compile(
    r'tgme_widget_message_forwarded_from_name[^>]*>(?:\s*<[^>]+>)*\s*([^<]+)'
)
_MORE_BEFORE = re.compile(r'data-before="(\d+)"')
_MORE_AFTER = re.compile(r'data-after="(\d+)"')
_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")

_MEDIA_CLASSES = (
    ("photo", "tgme_widget_message_photo"),
    ("video", "tgme_widget_message_video"),
    ("document", "tgme_widget_message_document"),
    ("voice", "tgme_widget_message_voice"),
    ("sticker", "tgme_widget_message_sticker"),
    ("poll", "tgme_widget_message_poll"),
    ("location", "tgme_widget_message_location"),
)


class FetchError(RuntimeError):
    """Raised when a page cannot be retrieved after retries."""


# --------------------------------------------------------------------------
# Parsing (pure functions — no I/O, so they are cheap to test on fixtures)
# --------------------------------------------------------------------------


def html_to_text(inner: str) -> str:
    """Convert the inner HTML of a message-text div into plain text.

    Line breaks are preserved because these channels put one target group per
    line, and that grouping is a real signal.
    """
    text = _BR.sub("\n", inner)
    text = re.sub(r"</(p|div)\s*>", "\n", text, flags=re.I)
    text = _TAG.sub("", text)
    return htmlmod.unescape(text)


def _div_inner(html: str, class_marker: str, start: int = 0) -> tuple[str, int] | None:
    """Return the inner HTML of the div carrying `class_marker`, plus its end.

    Depth-counted rather than regex-matched: message text contains nested divs
    and a non-greedy `</div>` match would truncate at the first inner close.
    """
    hit = html.find(class_marker, start)
    if hit == -1:
        return None
    open_tag = html.rfind("<div", 0, hit)
    if open_tag == -1:
        return None
    body_start = html.find(">", hit)
    if body_start == -1:
        return None
    body_start += 1

    depth = 1
    pos = body_start
    while depth > 0:
        nxt_open = html.find("<div", pos)
        nxt_close = html.find("</div", pos)
        if nxt_close == -1:
            return html[body_start:], len(html)
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            pos = nxt_open + 4
        else:
            depth -= 1
            close_end = html.find(">", nxt_close)
            pos = close_end + 1 if close_end != -1 else nxt_close + 5
            if depth == 0:
                return html[body_start : nxt_close], pos
    return None


def _media_type(chunk: str) -> str | None:
    for name, marker in _MEDIA_CLASSES:
        if marker in chunk:
            return name
    return None


def _parse_views(chunk: str) -> str | None:
    m = _VIEWS.search(chunk)
    return m.group(1).strip() or None if m else None


def parse_message(chunk: str, channel: str, message_id: int) -> Msg | None:
    """Parse one message wrapper chunk. Returns None if it carries no date."""
    m = _DATE.search(chunk) or _ANY_DATETIME.search(chunk)
    if not m:
        return None
    ts = int(datetime.fromisoformat(m.group(1)).timestamp())

    # Anchor on js-message_text: js-message_reply_text is the quoted message
    # and appears earlier in the chunk.
    parts: list[str] = []
    pos = 0
    while (found := _div_inner(chunk, "js-message_text", pos)) is not None:
        inner, pos = found
        parts.append(html_to_text(inner))
    text = "\n".join(p for p in parts if p.strip())

    reply = _REPLY_HREF.search(chunk)
    # The quoted text is already in this HTML. Keep it: a bare "Збили" is
    # noise, while "Збили" + quoted "Дрон на Жуляни" closes an episode.
    quoted = _div_inner(chunk, "js-message_reply_text")
    reply_text = html_to_text(quoted[0]) if quoted else None
    fwd = _FWD.search(chunk)
    return Msg(
        channel=channel,
        message_id=message_id,
        ts=ts,
        text_raw=text,
        reply_to=int(reply.group(1)) if reply else None,
        reply_text=reply_text,
        media_type=_media_type(chunk),
        fwd_from=fwd.group(1).strip() if fwd else None,
    )


@dataclass
class Page:
    """One t.me/s page: its messages and the cursors to walk further."""

    messages: list[Msg] = field(default_factory=list)
    before: int | None = None  # cursor for older messages
    after: int | None = None  # cursor for newer messages

    @property
    def ids(self) -> list[int]:
        return [m.message_id for m in self.messages]


def parse_page(html: str, channel: str) -> Page:
    """Parse a full t.me/s page into messages, oldest first."""
    hits = list(_POST.finditer(html))
    messages: list[Msg] = []
    for i, hit in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(html)
        chunk = html[hit.start() : end]
        msg = parse_message(chunk, channel, int(hit.group(2)))
        if msg is not None:
            messages.append(msg)
    messages.sort(key=lambda m: m.message_id)

    before = _MORE_BEFORE.search(html)
    after = _MORE_AFTER.search(html)
    return Page(
        messages=messages,
        before=int(before.group(1)) if before else None,
        after=int(after.group(1)) if after else None,
    )


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket limiter shared across worker threads."""

    def __init__(self, rps: float) -> None:
        self._interval = 1.0 / rps if rps > 0 else 0.0
        self._lock = Lock()
        self._next = 0.0

    def penalize(self, seconds: float) -> None:
        """Delay every waiter by `seconds`. Used when the server returns 429."""
        with self._lock:
            self._next = max(self._next, time.monotonic()) + seconds

    def wait(self) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next - now)
            self._next = max(now, self._next) + self._interval
        if sleep_for:
            time.sleep(sleep_for)


class Client:
    """Fetches t.me/s pages with rate limiting, retries and 429 backoff."""

    def __init__(self, rps: float = 2.0, retries: int = 4, timeout: int = 25) -> None:
        self.limiter = RateLimiter(rps)
        self.retries = retries
        self.timeout = timeout
        self.requests = 0
        self.bytes = 0
        self.throttled = 0
        self._lock = Lock()

    def url(self, channel: str, before: int | None = None, after: int | None = None) -> str:
        url = f"{BASE}/{channel}"
        if before is not None:
            url += f"?before={before}"
        elif after is not None:
            url += f"?after={after}"
        return url

    def get(self, channel: str, before: int | None = None, after: int | None = None) -> str:
        url = self.url(channel, before, after)
        last: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.wait()
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept-Language": "uk,en",
                        "Accept-Encoding": "gzip",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    with self._lock:
                        self.requests += 1
                        self.bytes += len(raw)
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return raw.decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code == 429:
                    delay = float(exc.headers.get("Retry-After") or 2 ** (attempt + 2))
                    with self._lock:
                        self.throttled += 1
                    self.limiter.penalize(delay)
                    continue
                if 500 <= exc.code < 600:
                    time.sleep(2 ** attempt)
                    continue
                raise FetchError(f"{url}: HTTP {exc.code}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                time.sleep(2 ** attempt)
        raise FetchError(f"{url}: giving up after {self.retries} attempts ({last})")

    def page(self, channel: str, before: int | None = None, after: int | None = None) -> Page:
        return parse_page(self.get(channel, before, after), channel)

    def newest_id(self, channel: str) -> int:
        page = self.page(channel)
        if not page.messages:
            raise FetchError(f"{channel}: no messages on the front page")
        return max(page.ids)

    def find_id_at_date(
        self, channel: str, cutoff: datetime, newest: int, max_iters: int = 64
    ) -> int:
        """Binary search a floor id for messages posted at or after `cutoff`.

        Random access on `?before=` turns "only the last month" from a full
        history walk into roughly log2(newest) requests.

        The result is a floor to page granularity, never above the true
        boundary, so no wanted message is excluded.

        Both bounds must be forced past `mid`. `before=mid` only ever returns
        ids strictly below `mid`, so `max(page.ids) + 1` can equal the current
        `lo` and the search then repeats the same probe forever — this hung a
        real export before `max(mid + 1, ...)` was added.
        """
        cutoff_ts = int(
            cutoff.replace(tzinfo=cutoff.tzinfo or timezone.utc).timestamp()
        )
        lo, hi = 1, newest
        answer = newest
        for _ in range(max_iters):
            if lo > hi:
                break
            mid = (lo + hi) // 2
            page = self.page(channel, before=mid)
            if not page.messages:
                lo = mid + 1
                continue
            if max(m.ts for m in page.messages) >= cutoff_ts:
                answer = min(page.ids)
                hi = min(min(page.ids) - 1, mid - 1)
            else:
                lo = max(mid + 1, max(page.ids) + 1)
        return answer
