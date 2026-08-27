"""Parser tests against real captured t.me/s pages.

Fixtures come from deep history (`?before=40000` / `?before=5000`), so their
content is stable and the assertions below will not drift.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from tools.export.normalize import normalize_text
from tools.export.store import Msg
from tools.export.tme import (
    Client,
    Page,
    RateLimiter,
    _div_inner,
    html_to_text,
    parse_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def page():
    html = (FIXTURES / "tme_mon1tor_before40000.html").read_text("utf-8")
    return parse_page(html, "mon1tor_ua")


@pytest.fixture(scope="module")
def media_page():
    html = (FIXTURES / "tme_media.html").read_text("utf-8")
    return parse_page(html, "kievinform_ua1")


def by_id(page, mid):
    return next(m for m in page.messages if m.message_id == mid)


# --- page structure -------------------------------------------------------


def test_page_yields_twenty_messages(page):
    assert len(page.messages) == 20


def test_messages_are_sorted_ascending(page):
    assert page.ids == sorted(page.ids)


def test_cursors_are_extracted(page):
    assert page.before == 39979
    assert page.after == 39999


def test_ids_are_not_contiguous(page):
    """Deleted messages leave gaps, so a backfill must follow the returned
    cursor rather than stepping the id by a fixed page size."""
    assert 39994 not in page.ids
    assert max(page.ids) - min(page.ids) + 1 > len(page.ids)


def test_every_message_has_a_timestamp(page):
    assert all(m.ts > 0 for m in page.messages)


def test_timestamps_increase_with_id(page):
    ts = [m.ts for m in sorted(page.messages, key=lambda m: m.message_id)]
    assert ts == sorted(ts)


def test_channel_is_recorded_on_each_message(page):
    assert {m.channel for m in page.messages} == {"mon1tor_ua"}


# --- quoted replies -------------------------------------------------------


def test_reply_captures_both_own_text_and_quoted_text(page):
    """The case that makes replies worth storing: "Збито" alone is noise."""
    m = by_id(page, 39986)
    assert normalize_text(m.text_raw) == "Збито"
    assert m.reply_to == 39984
    assert "Троєщ" in m.reply_text


def test_own_text_is_never_the_quoted_text(page):
    """Regression guard for the js-message_text vs js-message_reply_text trap.

    The quoted block appears FIRST in document order and shares the
    tgme_widget_message_text class, so anchoring on that class silently
    replaces every reply's text with the older quoted message.
    """
    replies = [m for m in page.messages if m.reply_to]
    assert replies, "fixture must contain replies for this to test anything"
    for m in replies:
        assert m.text_raw.strip()
        assert normalize_text(m.text_raw) != normalize_text(m.reply_text)


def test_reply_chain_links_the_same_target_across_districts(page):
    """39981 Pozniaky -> 39983 Holosiiv is one drone moving, not two."""
    m = by_id(page, 39983)
    assert m.reply_to == 39981
    assert "Позн" in m.reply_text


def test_non_reply_messages_have_no_reply_fields(page):
    m = by_id(page, 39980)
    assert m.reply_to is None
    assert not m.reply_text


# --- media ----------------------------------------------------------------


def test_photo_is_detected(media_page):
    photos = [m for m in media_page.messages if m.media_type == "photo"]
    assert [m.message_id for m in photos] == [4999]


def test_text_only_messages_report_no_media(page):
    assert all(m.media_type is None for m in page.messages)


def test_media_message_keeps_its_caption(media_page):
    m = by_id(media_page, 4999)
    assert normalize_text(m.text_raw)


# --- html_to_text ---------------------------------------------------------


def test_br_becomes_newline():
    assert html_to_text("Шахеди:<br/>10 з півдня") == "Шахеди:\n10 з півдня"


def test_self_closing_and_plain_br_both_handled():
    assert html_to_text("a<br>b<br />c") == "a\nb\nc"


def test_entities_are_unescaped():
    assert html_to_text("&quot;Шахед&quot; &amp; ракета") == '"Шахед" & ракета'


def test_emoji_wrapper_leaves_the_character():
    inner = (
        '<i class="emoji" style="background-image:url(\'//telegram.org/x.png\')">'
        "<b>🚨</b></i>Загроза"
    )
    assert html_to_text(inner) == "🚨Загроза"


def test_links_keep_their_text():
    inner = '<a href="https://t.me/x" target="_blank">Підписатись</a>'
    assert html_to_text(inner) == "Підписатись"


# --- _div_inner -----------------------------------------------------------


def test_div_inner_handles_nesting():
    html = '<div class="target">a<div>b</div>c</div>tail'
    inner, end = _div_inner(html, "target")
    assert inner == "a<div>b</div>c"
    assert html[end:].startswith("tail")


def test_div_inner_returns_none_when_marker_absent():
    assert _div_inner("<div>nothing</div>", "target") is None


def test_div_inner_can_resume_from_offset():
    html = '<div class="t">one</div><div class="t">two</div>'
    first, end = _div_inner(html, 'class="t"')
    second, _ = _div_inner(html, 'class="t"', end)
    assert (first, second) == ("one", "two")


# --- client plumbing ------------------------------------------------------


def test_url_without_cursor():
    assert Client().url("war_monitor") == "https://t.me/s/war_monitor"


def test_url_with_before_and_after():
    c = Client()
    assert c.url("war_monitor", before=100) == "https://t.me/s/war_monitor?before=100"
    assert c.url("war_monitor", after=100) == "https://t.me/s/war_monitor?after=100"


def test_before_wins_when_both_given():
    assert "before=1" in Client().url("c", before=1, after=2)


def test_rate_limiter_spaces_calls():
    limiter = RateLimiter(rps=20)  # 50 ms apart
    start = time.monotonic()
    for _ in range(4):
        limiter.wait()
    assert time.monotonic() - start >= 0.10


def test_rate_limiter_zero_rps_does_not_block():
    limiter = RateLimiter(rps=0)
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start < 0.05


# --- find_id_at_date ------------------------------------------------------


class _Corpus(Client):
    """Client backed by a synthetic id->timestamp corpus.

    Raises after a call budget so a non-terminating search fails the test
    instead of hanging it.
    """

    def __init__(self, first_ts, count, step=600, page_size=20, budget=80):
        super().__init__(rps=0)
        self.ts_of = {i: first_ts + i * step for i in range(1, count + 1)}
        self.page_size = page_size
        self.budget = budget
        self.calls = 0

    def page(self, channel, before=None, after=None):
        self.calls += 1
        if self.calls > self.budget:
            raise AssertionError(f"search did not converge in {self.budget} probes")
        pool = [i for i in sorted(self.ts_of) if before is None or i < before]
        chosen = pool[-self.page_size :]
        msgs = [
            Msg(channel=channel, message_id=i, ts=self.ts_of[i], text_raw="x")
            for i in chosen
        ]
        return Page(messages=msgs, before=min(chosen) if chosen else None)


BASE_TS = 1_750_000_000


def _cutoff(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def test_find_id_at_date_terminates_and_is_logarithmic():
    c = _Corpus(BASE_TS, 43_000)
    target = 41_944
    c.find_id_at_date("ch", _cutoff(c.ts_of[target]), 43_000)
    assert c.calls < 40, f"took {c.calls} probes — not a binary search"


def test_find_id_at_date_never_returns_a_floor_above_the_boundary():
    """A floor above the boundary would silently drop wanted messages."""
    c = _Corpus(BASE_TS, 43_000)
    for target in (2_000, 21_568, 41_944, 42_999):
        c.calls = 0
        got = c.find_id_at_date("ch", _cutoff(c.ts_of[target]), 43_000)
        assert got <= target, f"floor {got} is above boundary {target}"


def test_find_id_at_date_is_close_to_the_boundary():
    c = _Corpus(BASE_TS, 43_000)
    target = 30_000
    got = c.find_id_at_date("ch", _cutoff(c.ts_of[target]), 43_000)
    assert target - got <= c.page_size


def test_find_id_at_date_handles_cutoff_before_all_history():
    c = _Corpus(BASE_TS, 500)
    assert c.find_id_at_date("ch", _cutoff(BASE_TS - 10_000), 500) <= 20


def test_find_id_at_date_handles_cutoff_after_all_history():
    c = _Corpus(BASE_TS, 500)
    got = c.find_id_at_date("ch", _cutoff(BASE_TS + 10_000_000), 500)
    assert got == 500


def test_find_id_at_date_respects_the_iteration_cap():
    """Even a source that never converges must return rather than hang."""

    class Pathological(_Corpus):
        def page(self, channel, before=None, after=None):
            self.calls += 1
            if self.calls > self.budget:
                raise AssertionError("iteration cap not honoured")
            return Page(
                messages=[Msg(channel=channel, message_id=1, ts=BASE_TS, text_raw="x")],
                before=1,
            )

    c = Pathological(BASE_TS, 100, budget=20)
    c.find_id_at_date("ch", _cutoff(BASE_TS + 5000), 100, max_iters=10)
    assert c.calls <= 10
