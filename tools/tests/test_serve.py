"""The service the app talks to.

Built because config editing needs it: "користувачі мають мати можливість
змінювати свій конфіг. Можливо навіть автоматично, при переміщенні містом." That
makes the port compulsory and writable, which is what most of these tests are
really about.
"""
import json
import sqlite3
import threading
import urllib.error
import urllib.request

import pytest

from tools.policy.recipients import hashed


def _quiet(*_a, **_k):
    pass
from tools.serve.api import decisions, messages, serve

TOKEN = "sekret"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "m.db"
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE messages (channel TEXT, message_id INTEGER, "
                "ts INTEGER, date_utc TEXT, text_raw TEXT, text_norm TEXT, "
                "fingerprint TEXT, edit_ts INTEGER, reply_to INTEGER, "
                "reply_text TEXT, media_type TEXT, fwd_from TEXT, "
                "PRIMARY KEY (channel, message_id))")
    rows = [("a", 2, 100, "", "", "друге", "", None, None, "", "", ""),
            ("a", 1, 100, "", "", "перше", "", None, None, "", "", ""),
            ("b", 9, 101, "", "", "третє", "", None, None, "", "", ""),
            ("b", 8, 99, "", "", "", "", None, None, "", "", "")]
    con.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


@pytest.fixture
def who(tmp_path):
    d = tmp_path / "recipients"
    d.mkdir()
    (d / "index.json").write_text(json.dumps({hashed(TOKEN): "vinni"}),
                                  encoding="utf-8")
    return d


@pytest.fixture
def api(db, who, tmp_path):
    # A log directory with something in it, because that is the running state:
    # the watcher rewrites its log after every poll, so an empty directory means
    # a watcher that has never polled -- which `poll_age_s` reports as None and
    # which a separate test covers.
    live = tmp_path / "live"
    live.mkdir()
    (live / "now.jsonl").write_text("", encoding="utf-8")
    httpd = serve("127.0.0.1", 0, db, live, who)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(base, path, token=TOKEN, method="GET", body=None):
    req = urllib.request.Request(base + path, method=method)
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as reply:
            return reply.status, json.loads(reply.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


# --- what may be reached without a token ------------------------------------


def test_health_says_whether_the_watch_is_alive(api, tmp_path):
    """His question decides what this endpoint is for: "реально, якщо А не
    працює, то який взагалі сенс?" An endpoint that answers `{"ok": true}` while
    the watcher is dead is worse than one that does not answer -- the app would
    show a calm sky and the phone would stay silent, which is what a quiet night
    looks like.

    `poll_age_s` is the one to act on: the watcher rewrites its log after every
    poll cycle whether or not anything arrived. `message_age_s` is information --
    silences over ten minutes happen twenty-two times a day."""
    code, body = call(api, "/health", token=None)
    assert code == 200 and body["ok"] is True and body["corpus"] is True
    # The channels are never quiet for long, so age is the signal.
    assert isinstance(body["message_age_s"], int)
    assert isinstance(body["poll_age_s"], int)


def test_health_reports_a_dead_watcher_rather_than_hiding_it(tmp_path, db, who):
    """No decision log at all, and a corpus that stops: both have to be visible
    as numbers the app can act on."""
    import threading

    from tools.serve.api import health, serve

    httpd = serve("127.0.0.1", 0, db, tmp_path / "no-logs", who)
    try:
        out = health(httpd.db, tmp_path / "no-logs", now=2_000_000_000)
        assert out["poll_age_s"] is None              # never polled
        assert out["message_age_s"] > 10_000          # the corpus is ancient
    finally:
        httpd.server_close()


def test_an_empty_corpus_does_not_stop_the_service(tmp_path, who):
    """A missing database once killed the service outright, and that cost an
    hour: `mode=ro` on a file that is not there raises, and B is a fresh box
    until A hands something over -- while `/config`, the reason the port exists
    at all, needs no corpus.

    B now creates the file so it can receive a push, so the state to survive is
    an *empty* corpus rather than an absent one."""
    import threading

    httpd = serve("127.0.0.1", 0, tmp_path / "fresh.db", tmp_path / "live", who)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert call(base, "/health", token=None)[1]["corpus"] is False
        assert call(base, "/messages")[1]["messages"] == []
        assert call(base, "/config", method="PUT",
                    body={"home": "Оболонь"})[0] == 200
    finally:
        httpd.shutdown()


@pytest.mark.parametrize("path", ["/messages", "/decisions", "/config"])
def test_everything_else_refuses_without_a_token(api, path):
    assert call(api, path, token=None)[0] == 401
    assert call(api, path, token="wrong")[0] == 401


def test_an_unknown_path_says_so_and_nothing_more(api):
    assert call(api, "/nope")[0] == 404
    assert call(api, "/../hovaysya.json")[0] == 404


# --- the feed ---------------------------------------------------------------


def test_the_feed_is_ordered_by_time_not_by_insert_order(db):
    """`rowid` would hand the app a feed that jumps backwards: the export is
    resumable, so backfilling an old channel writes high rowids for old
    messages. Here row 2 was inserted before row 1 and must come second."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    page = messages(conn, None, 10)
    assert [m["text"] for m in page["messages"]] == ["перше", "друге", "третє"]


def test_a_cursor_continues_without_repeating_or_skipping(db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    first = messages(conn, None, 2)
    second = messages(conn, first["next"], 2)
    assert [m["text"] for m in first["messages"]] == ["перше", "друге"]
    assert [m["text"] for m in second["messages"]] == ["третє"]
    # ...and the end of the feed keeps the cursor rather than resetting it, so
    # an app polling a quiet night does not replay the whole corpus.
    assert messages(conn, second["next"], 2)["messages"] == []
    assert messages(conn, second["next"], 2)["next"] == second["next"]


def test_a_cursor_we_never_issued_means_the_beginning(db):
    """Never an error: a stale app, a truncated string, a hand-typed URL."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    assert len(messages(conn, "лапки", 10)["messages"]) == 3
    assert len(messages(conn, "", 10)["messages"]) == 3


def test_a_message_with_no_text_is_not_in_the_feed(db):
    """A photo with no caption decides nothing and says nothing."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    assert all(m["text"] for m in messages(conn, None, 10)["messages"])


def test_the_limit_cannot_be_talked_into_reading_everything(api):
    for query in ("limit=100000", "limit=-5", "limit=nonsense"):
        code, body = call(api, f"/messages?{query}")
        assert code == 200 and len(body["messages"]) <= 500


# --- the decisions ----------------------------------------------------------


def test_the_decision_log_is_deduplicated_across_files(tmp_path):
    """Logs overlap by design: a restart replays the last ninety minutes and the
    catch-up pass writes those lines again."""
    d = tmp_path / "live"
    d.mkdir()
    row = {"at": "2026-09-01T02:30:08+00:00", "anchor": "a/1",
           "level": "alert", "said": "Загроза: балістика. Жуляни."}
    (d / "1.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (d / "2.jsonl").write_text(json.dumps(row) + "\n"
                               + json.dumps({**row, "anchor": "b/2"}) + "\n",
                               encoding="utf-8")
    page = decisions(d, None, 10, days=10 ** 6)
    assert [x["anchor"] for x in page["decisions"]] == ["a/1", "b/2"]


def test_a_broken_line_in_the_log_does_not_take_the_endpoint_down(tmp_path):
    d = tmp_path / "live"
    d.mkdir()
    (d / "1.jsonl").write_text(
        "{oops\n" + json.dumps({"at": "2026-09-01T00:00:00+00:00",
                                "anchor": "a/1"}) + "\n", encoding="utf-8")
    assert len(decisions(d, None, 10, days=10 ** 6)["decisions"]) == 1


def test_a_missing_log_directory_is_an_empty_answer(tmp_path):
    assert decisions(tmp_path / "absent", None, 10)["decisions"] == []


# --- the settings -----------------------------------------------------------


def test_settings_come_back_effective_not_bare(api):
    """GET answers with what actually applies to this person, which is the shipped
    configuration plus whatever they changed -- not the contents of their file.

    It used to answer `{}` for a recipient with no file of their own, and that was
    the visible end of a real defect: the watcher built such a recipient from bare
    defaults, so the first token minted on its own machine would have silently
    emptied his ring and zeroed the radius. A name in the index with no file beside
    it means "changed nothing", never "configured nothing".
    """
    from tools.policy.config import load as load_config

    shipped = load_config(warn=_quiet)
    got = call(api, "/config")[1]["config"]
    assert got["home"] == shipped.home
    assert got["radius_km"] == shipped.radius_km

    call(api, "/config", method="PUT", body={"radius_km": 4})
    after = call(api, "/config")[1]["config"]
    assert after["radius_km"] == 4                 # theirs wins
    assert after["home"] == shipped.home           # ...and the rest still applies


def test_a_hostile_body_is_clamped_before_it_reaches_disk(api, who):
    """The loader was written so a typo could not take the watch down at 3 a.m.
    With a config arriving over the network it is the trust boundary, and what
    lands on disk must be what it accepted -- not the body as sent, or the next
    read would treat unvalidated input as already checked."""
    code, body = call(api, "/config", method="PUT",
                      body={"radius_km": 999, "refractory_s": 0,
                            # 200 names, not 5000: Cyrillic escapes to six
                            # bytes a character, so a bigger list hits the size
                            # limit first -- which is the test below.
                            "ring": ["х" * 20] * 200, "жарт": True})
    assert code == 200
    assert body["config"]["radius_km"] == 50          # clamped
    assert body["config"]["refractory_s"] == 60       # clamped
    assert len(body["config"]["ring"]) == 128         # bounded
    assert "жарт" not in body["config"]               # dropped

    stored = json.loads((who / "vinni.json").read_text(encoding="utf-8"))
    assert stored["radius_km"] == 50 and "жарт" not in stored


def test_only_the_difference_is_stored(api, who):
    """Their file holds deviations, so a later change to the shipped settings
    reaches everyone who did not override that particular thing."""
    call(api, "/config", method="PUT", body={"radius_km": 4})
    stored = json.loads((who / "vinni.json").read_text(encoding="utf-8"))
    assert stored == {"radius_km": 4}


def test_a_body_that_is_not_an_object_is_refused(api):
    assert call(api, "/config", method="PUT", body=[1, 2, 3])[0] == 400


def test_an_enormous_body_is_refused_before_it_is_read(api):
    code, _body = call(api, "/config", method="PUT",
                       body={"home": "х" * 100_000})
    assert code == 413


def test_only_config_accepts_a_write(api):
    assert call(api, "/messages", method="PUT", body={})[0] == 404


def test_one_persons_settings_are_not_anothers(api, who):
    (who / "index.json").write_text(
        json.dumps({hashed(TOKEN): "vinni", hashed("other"): "hanna"}),
        encoding="utf-8")
    call(api, "/config", method="PUT", body={"home": "Оболонь"})
    call(api, "/config", token="other", method="PUT", body={"home": "Троєщина"})
    assert call(api, "/config")[1]["config"]["home"] == "Оболонь"
    assert call(api, "/config", token="other")[1]["config"]["home"] == "Троєщина"


def test_the_database_handle_cannot_write(db, who, tmp_path):
    """Stated in the connection URI rather than left to the code: this process
    has no business touching the corpus."""
    httpd = serve("127.0.0.1", 0, db, tmp_path / "live", who)
    try:
        with pytest.raises(sqlite3.OperationalError):
            httpd.db.execute("DELETE FROM messages")
    finally:
        httpd.server_close()


# --- opening the screen cold -------------------------------------------------


def test_a_window_returns_the_newest_of_it_not_the_oldest(db):
    """His case: "коли я відкриваю скрін, я хочу бачити останні повідомлення за
    30хв". A screen is not an archive -- half an hour during an attack is three
    hundred messages, and the last two hundred are the ones worth showing.
    """
    from tools.serve.api import messages

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # The fixture's rows sit at ts 99..101; `now` is set just past them.
    page = messages(conn, None, 2, back=3600, now=200)
    # Newest two, but handed over oldest-first so the app can append.
    assert [m["text"] for m in page["messages"]] == ["друге", "третє"]
    # ...and the cursor points at the newest, ready for the next poll.
    assert page["next"].startswith("101.")


def test_an_empty_window_still_says_where_to_poll_from(db):
    """The defect his question found, and he restated it more plainly than I
    had: "якщо за минулі 30хв нічого не було, то курсора нема."

    That is exactly what happened. `?back=30m` on a quiet stretch returned no
    messages *and* an empty cursor, so an app opened during one -- which is about
    twenty-two times a day -- had no way forward except replaying the corpus from
    January 2024. An empty window is a normal answer; an empty cursor is a dead
    end.

    It is also why there is no `?since=head` any more. That existed to fetch a
    bare cursor, and he asked what it was for: "воно ж ніколи не поверне нічого,
    хіба ні?" It never did, and once this answers with a cursor of its own there
    was nothing left for it to do.
    """
    from tools.serve.api import messages

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    quiet = messages(conn, None, 10, back=60, now=10_000)
    assert quiet["messages"] == []
    assert quiet["next"].startswith("101."), "an empty window must still give a cursor"
    # ...and polling from it returns nothing until something new arrives.
    assert messages(conn, quiet["next"], 10)["messages"] == []


@pytest.mark.parametrize("given,seconds", [
    ("1800", 1800), ("30m", 1800), ("2h", 7200),
    # Clamped up to a minute: anything shorter is a poll, and a poll has a
    # cursor. Clamped down at a day: past that it is an archive request.
    ("45s", 60), ("0", 60), ("999h", 86400),
    ("нонсенс", None), ("", None), (None, None),
])
def test_a_window_is_parsed_or_ignored_never_an_error(given, seconds):
    from tools.serve.api import _parse_back

    assert _parse_back(given) == seconds


def test_the_window_reaches_the_endpoint(api):
    code, body = call(api, "/messages?back=30m")
    assert code == 200 and isinstance(body["messages"], list)
    # Percent-encoding, because a hand-typed URL is exactly where this arrives.
    assert call(api, "/messages?back=%D0%BD%D0%BE%D0%BD%D1%81%D0%B5%D0%BD%D1%81")[0] == 200
    assert call(api, "/messages?back=-5")[0] == 200
