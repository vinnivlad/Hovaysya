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
    row = {"at": "2026-09-01T02:30:08+00:00", "anchor": "a/1", "who": "оля",
           "level": "alert", "said": "Загроза: балістика. Жуляни."}
    (d / "1.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (d / "2.jsonl").write_text(json.dumps(row) + "\n"
                               + json.dumps({**row, "anchor": "b/2"}) + "\n",
                               encoding="utf-8")
    page = decisions(d, "оля", None, 10, days=10 ** 6)
    assert [x["anchor"] for x in page["decisions"]] == ["a/1", "b/2"]


def test_a_broken_line_in_the_log_does_not_take_the_endpoint_down(tmp_path):
    d = tmp_path / "live"
    d.mkdir()
    (d / "1.jsonl").write_text(
        "{oops\n" + json.dumps({"at": "2026-09-01T00:00:00+00:00",
                                "anchor": "a/1", "who": "оля"}) + "\n", encoding="utf-8")
    assert len(decisions(d, "оля", None, 10, days=10 ** 6)["decisions"]) == 1


def test_a_missing_log_directory_is_an_empty_answer(tmp_path):
    assert decisions(tmp_path / "absent", "оля", None, 10)["decisions"] == []


def test_one_persons_decisions_never_reach_another(tmp_path):
    """His call, made from intuition rather than from the code: "decisions думаю
    теж приватне, воно ж персональне".

    It is worse than private. `reason` reads "new target heading into my area",
    where *my* is whoever the line was decided for, and the sentence names their
    ring -- 47 lines of 3907 named the watcher's own district. Unfiltered, every
    token holder got his address, and an answer computed from his home rather
    than from their own, which is simply the wrong answer for them.
    """
    d = tmp_path / "live"
    d.mkdir()
    lines = [
        {"at": "2026-09-01T02:30:08+00:00", "anchor": "a/1", "who": "я",
         "level": "alarm", "reason": "my place, and ballistic is up",
         "said": "Тривога. Балістика. Жуляни."},
        {"at": "2026-09-01T02:30:08+00:00", "anchor": "a/1", "who": "оля",
         "level": "info", "reason": "far from me",
         "said": "Загроза: балістика."},
    ]
    (d / "1.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + chr(10) for x in lines),
        encoding="utf-8")

    for name, said in (("я", "Тривога. Балістика. Жуляни."),
                       ("оля", "Загроза: балістика.")):
        page = decisions(d, name, None, 10, days=10 ** 6)
        assert [x["said"] for x in page["decisions"]] == [said], name

    # A line decided before the owner was recorded belongs to nobody at all.
    (d / "2.jsonl").write_text(
        json.dumps({"at": "2026-09-01T03:00:00+00:00", "anchor": "c/3",
                    "said": "Тривога. Жуляни."}, ensure_ascii=False) + chr(10),
        encoding="utf-8")
    for name in ("я", "оля", None):
        got = decisions(d, name, None, 10, days=10 ** 6)["decisions"]
        assert "c/3" not in [x["anchor"] for x in got], name


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
# --- the home picker --------------------------------------------------------


def test_every_name_offered_as_a_home_can_actually_be_one():
    """The invariant the first screen rests on, and the reason `/places` reads the
    gazetteer instead of a generated copy.

    A home with no coordinate is not an error anyone sees: `Config.centre()`
    returns None, the radius contributes nothing, and the ring quietly falls back
    to the hand list -- so the person gets somebody else's ring and no message
    says so. Offering only names that survive `centre()` is what stops that, and
    it has to be checked against the real gazetteer rather than a fixture,
    because the failure arrives when the two drift.
    """
    from dataclasses import replace

    from tools.policy.config import DEFAULTS
    from tools.serve.api import places

    page = places()
    offered = [p for p in page["places"] if p["home"]]
    assert len(offered) > 100, len(offered)

    for p in offered:
        centre = replace(DEFAULTS, home=p["name"]).centre()
        assert centre is not None, p["name"]
        assert centre == (p["lat"], p["lon"]), p["name"]


def test_a_name_that_cannot_be_a_point_is_not_offered_as_a_home():
    """Правий берег is half a city and Київщина is the oblast. Both are real
    threats to report and neither is a place to live, which is why `coords.py`
    leaves them out on purpose rather than substituting a centre."""
    from tools.serve.api import places

    by_name = {p["name"]: p for p in places()["places"]}
    for name in ("Правий берег", "Київщина"):
        assert by_name[name]["home"] is False, name
        assert by_name[name]["lat"] is None, name


def test_the_picker_is_offered_the_gazetteers_own_tier_order():
    """So the app groups "мій район / поруч / місто / область" the way the policy
    ranks them, rather than inventing an order that disagrees with the rules."""
    from tools.nlp.gazetteer import PLACES, TIERS
    from tools.serve.api import places

    page = places()
    assert page["tiers"] == list(TIERS)
    assert {p["name"] for p in page["places"]} == {p.name for p in PLACES}
    assert {p["tier"] for p in page["places"]} <= set(TIERS)
# --- taking yourself in -----------------------------------------------------


def _reg(tmp_path, secret, name):
    from tools.policy import tokens as people

    return people.register(people.hashed(secret), name, tmp_path)


def test_a_phone_takes_itself_in_and_the_token_it_made_works(tmp_path):
    """Open registration, on his instruction: "нащо ти намагаєшся робити так щоб
    я адміністрував всіх користувачів? Нехай собі ставлять застосунок, самі
    вибирають дім і все."

    The phone generates the secret and sends only its sha256, so this machine
    never holds anything that could impersonate a phone -- the property
    `token.py` has always had, kept when the minting moved off the terminal.
    """
    from tools.policy import tokens as people

    assert _reg(tmp_path, "s3cret", "Оля") == "Оля"
    assert people.name_for("s3cret", tmp_path) == "Оля"
    assert people.name_for("s3cre", tmp_path) is None
    # And the secret itself is nowhere on disk.
    stored = (tmp_path / "index.json").read_text(encoding="utf-8")
    assert "s3cret" not in stored


def test_a_hash_already_registered_cannot_be_claimed_again(tmp_path):
    """Two names on one hash would make `name_for` answer with whichever the
    dict happened to yield first -- an identity takeover for anyone who learned
    a hash, which is the one thing this file is allowed to leak."""
    from tools.policy import tokens as people

    _reg(tmp_path, "s3cret", "Оля")
    with pytest.raises(people.Refused) as caught:
        _reg(tmp_path, "s3cret", "не Оля")
    assert caught.value.code == 409
    assert people.name_for("s3cret", tmp_path) == "Оля"


def test_a_recipient_cannot_be_called_the_index(tmp_path):
    """The hole open registration made, and it locks everybody out at once.

    A person's name is a filename here, so a device registering as "index" would
    be handed `index.json` as its settings file and its first `PUT /config`
    would overwrite the index -- with no error anywhere, and no way back short of
    re-registering every phone.
    """
    from tools.policy import tokens as people

    for chosen in ("index", "INDEX", "  index  "):
        name = _reg(tmp_path, chosen, chosen)
        assert name.casefold() != "index", chosen
        assert people._config_path(name, tmp_path).name != "index.json", chosen
    # Three devices in, and the index still knows all three.
    assert len(people.index(tmp_path)) == 3


def test_a_chosen_name_cannot_reach_out_of_the_directory(tmp_path):
    """The name arrives from the network now, not from a person at a terminal."""
    from tools.policy import tokens as people

    name = _reg(tmp_path, "s", "../../etc/passwd")
    path = people._config_path(name, tmp_path)
    assert path.parent == tmp_path, path
    assert ".." not in name and "/" not in name, name


def test_two_people_who_pick_one_name_get_two(tmp_path):
    """His warning: "май на увазі що імена можуть повторюватись". The suffix is
    visible on purpose -- it is what lets him say "глянь олю" when there are two
    and mean one of them."""
    from tools.policy import tokens as people

    assert _reg(tmp_path, "a", "Оля") == "Оля"
    second = _reg(tmp_path, "b", "оля")
    assert second != "Оля" and second.startswith("оля-"), second
    assert len(people.index(tmp_path)) == 2


def test_the_ceiling_refuses_rather_than_growing(tmp_path):
    """The push sender walks every registration on every alert, so unbounded
    growth costs delivery time to the people who are really there."""
    from tools.policy import tokens as people

    for i in range(3):
        people.register(people.hashed(str(i)), f"p{i}", tmp_path, ceiling=3)
    with pytest.raises(people.Refused) as caught:
        people.register(people.hashed("x"), "ще один", tmp_path, ceiling=3)
    assert caught.value.code == 507


def test_a_malformed_hash_is_refused_before_anything_is_written(tmp_path):
    from tools.policy import tokens as people

    for bad in (None, "", "деде", "z" * 64, "AB" * 32, "a" * 63):
        with pytest.raises(people.Refused) as caught:
            people.register(bad, "x", tmp_path)
        assert caught.value.code == 400, bad
    assert not (tmp_path / "index.json").exists()


def test_registration_is_throttled_by_attempts_not_by_successes():
    """`MAX_RECIPIENTS` being a ceiling makes the ceiling itself the denial --
    fill it and the next real person is locked out. This is what makes filling it
    slow and visible in the journal instead of instant and quiet. It counts
    attempts, because a flood of malformed bodies is the thing being slowed."""
    from tools.serve.api import may_register

    now = 1_000_000.0
    assert all(may_register(now, per_min=3) for _ in range(3))
    assert not may_register(now, per_min=3)
    # And it is a window, not a quota.
    assert may_register(now + 61, per_min=3)
def test_a_device_can_take_itself_out(tmp_path):
    """His workflow: "може зробимо тестового користувача і будемо тестити завжди
    зпід нього на реальному сервері?"

    Which is the right way round -- real data, real timing, and the emulator sees
    exactly what a phone will. It needs this to stay sustainable: every reinstall
    generates a fresh secret, so each cycle would otherwise leave a recipient
    behind, and the only broom would be a terminal on the server.

    The settings go with it, and that is the difference from `--revoke`. A revoke
    is usually a lost phone, where throwing away where somebody lives would be a
    poor answer. A device asking to be forgotten is saying it is done.
    """
    from tools.policy import tokens as people

    people.register(people.hashed("mine"), "тест", tmp_path)
    people.register(people.hashed("theirs"), "оля", tmp_path)
    people.save_config("тест", {"home": "Виноградар"}, tmp_path)
    assert people._config_path("тест", tmp_path).exists()

    assert people.unregister("mine", tmp_path) == "тест"
    assert people.name_for("mine", tmp_path) is None
    assert not people._config_path("тест", tmp_path).exists()

    # ...and nobody else's row was touched.
    assert people.name_for("theirs", tmp_path) == "оля"
    assert sorted(people.index(tmp_path).values()) == ["оля"]

    # A token that is already gone, or was never there, removes nothing.
    assert people.unregister("mine", tmp_path) is None
    assert people.unregister("never", tmp_path) is None
    assert sorted(people.index(tmp_path).values()) == ["оля"]


def test_unregistering_without_settings_is_not_an_error(tmp_path):
    """The normal case for somebody who registered and never chose a home."""
    from tools.policy import tokens as people

    people.register(people.hashed("bare"), "хтось", tmp_path)
    assert people.unregister("bare", tmp_path) == "хтось"
    assert people.index(tmp_path) == {}
def test_a_cold_screen_gets_the_newest_decisions_and_paging_gets_the_oldest(tmp_path):
    """Two questions that look like one. Opening a feed asks "what happened
    lately"; a cursor asks "what have I not seen yet", and they want opposite
    ends of the same window.

    It served the oldest either way, so an app opening on a three-day log met the
    lines from three days ago. Invisible while the feed drew newest-first from
    whatever it was given, and immediate once he asked for Telegram's order:
    "зроби новіші повідомлення внизу, а не згори."
    """
    d = tmp_path / "live"
    d.mkdir()
    rows = [{"at": f"2026-09-0{1 + i // 10}T0{i % 10}:00:00+00:00",
             "anchor": f"a/{i}", "who": "оля", "said": f"line {i}"}
            for i in range(30)]
    (d / "1.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + chr(10) for r in rows),
        encoding="utf-8")

    fresh = decisions(d, "оля", None, 5, days=10 ** 6)["decisions"]
    assert [r["said"] for r in fresh] == [f"line {i}" for i in range(25, 30)], fresh

    # ...and from a cursor, what follows it rather than the last few. Four here
    # and not five, because the window ends: the log has thirty lines.
    page = decisions(d, "оля", fresh[0]["cursor"], 5, days=10 ** 6)["decisions"]
    assert [r["said"] for r in page] == [f"line {i}" for i in range(26, 30)], page

    # Ascending either way, so the app can append.
    for served in (fresh, page):
        assert served == sorted(served, key=lambda r: r["cursor"])
# --- what stands in for a push ----------------------------------------------


def _state_dir(tmp_path, payload):
    directory = tmp_path / "state"
    directory.mkdir(exist_ok=True)
    (directory / "оля.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def test_the_version_ignores_when_the_state_was_written():
    """Which is the whole reason a long poll can wait at all.

    The watcher rewrites the state file after every poll whether or not anything
    happened, so `at` changes about six times a minute. A version that included
    it would make every held request return within ten seconds, the phone would
    be back to polling, and the battery this exists to save would be spent on
    learning that nothing had changed.
    """
    from tools.serve.api import _version

    quiet = {"at": 1, "state": "quiet", "said": []}
    later = {"at": 999, "state": "quiet", "said": []}
    assert _version(quiet) == _version(later)

    alert = {"at": 1, "state": "alert", "said": []}
    assert _version(quiet) != _version(alert)


def test_a_held_request_returns_the_moment_the_answer_changes(tmp_path):
    """This is what replaces Firebase, so it is worth pinning what it promises.

    He asked whether a push provider was really compulsory, and it is not: it is
    compulsory only to use Google's channel. A request held open against the
    watcher delivers the same thing with nothing in between -- no account, no
    `google-services.json`, no service key on the server.
    """
    import threading
    import time

    from tools.serve.api import _version, state_after

    directory = _state_dir(tmp_path, {"at": 1, "state": "quiet", "said": []})
    have = _version({"state": "quiet", "said": []})

    def change():
        time.sleep(0.5)
        _state_dir(tmp_path, {"at": 2, "state": "alert", "said": []})

    threading.Thread(target=change, daemon=True).start()
    started = time.monotonic()
    answer = state_after(directory, "оля", have, wait=20)
    took = time.monotonic() - started

    assert answer["state"] == "alert"
    assert answer["v"] != have
    assert took < 5, f"waited {took:.1f}s for a change half a second away"


def test_a_timeout_is_an_answer_and_not_a_failure(tmp_path):
    """It comes back with the state and its version, which is how the phone asks
    again -- and how it learns the service is still there. A held request that
    simply died would be indistinguishable from a server that had."""
    import time

    from tools.serve.api import _version, state_after

    directory = _state_dir(tmp_path, {"at": 1, "state": "quiet", "said": []})
    have = _version({"state": "quiet", "said": []})

    started = time.monotonic()
    answer = state_after(directory, "оля", have, wait=2)
    took = time.monotonic() - started

    assert answer["v"] == have
    assert answer["state"] == "quiet"
    assert 1.5 <= took < 6, f"{took:.1f}s"


def test_the_wait_is_bounded(tmp_path):
    """A phone asking for an hour would hold a thread for an hour, and every
    proxy in the way would drop it long before that."""
    import time

    from tools.serve.api import MAX_WAIT_S, _version, state_after

    directory = _state_dir(tmp_path, {"at": 1, "state": "quiet", "said": []})
    have = _version({"state": "quiet", "said": []})
    fake = iter([0.0] + [MAX_WAIT_S + 1] * 10)

    answer = state_after(directory, "оля", have, wait=10 ** 6,
                         now=lambda: next(fake))
    assert answer["v"] == have


def test_asking_without_a_version_answers_at_once(tmp_path):
    """A cold screen has nothing to compare against and should not be made to
    wait for a change that may be hours away."""
    import time

    from tools.serve.api import state_after

    directory = _state_dir(tmp_path, {"at": 1, "state": "quiet", "said": []})
    started = time.monotonic()
    answer = state_after(directory, "оля", None, wait=20)
    assert answer["state"] == "quiet"
    assert answer["v"]
    assert time.monotonic() - started < 2
def test_the_feed_survives_a_quiet_stretch_longer_than_its_window(tmp_path):
    """The fault he reported twice, and the numbers say why it was not obvious.

    Only one row in seven carries an utterance, and the corpus has silent runs
    of up to seventy-two. The feed asked for the last sixty *rows* and filtered
    them in the app -- so any quiet stretch longer than the window emptied the
    screen, while the first screen kept showing his lines because `write_state`
    filters before taking the last three rather than after.

    Filtering after a limit is not a filter. It is a lottery on how talkative
    the channels have been.
    """
    d = tmp_path / "live"
    d.mkdir()
    rows = []
    # One thing said, then a hundred silent decisions after it.
    rows.append({"at": "2026-09-03T00:00:00+00:00", "anchor": "a/0",
                 "who": "Володимир", "level": "alert", "alarm": "alert",
                 "said": "Тривога."})
    for i in range(1, 101):
        rows.append({"at": f"2026-09-03T{i // 60:02d}:{i % 60:02d}:00+00:00",
                     "anchor": f"a/{i}", "who": "Володимир",
                     "reason": "too-far: oblast, not the city"})
    (d / "1.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + chr(10) for r in rows),
        encoding="utf-8")

    # What the app used to do: the newest sixty rows, filtered afterwards.
    raw = decisions(d, "Володимир", None, 60, days=10 ** 6)["decisions"]
    assert [r for r in raw if r["said"]] == [], "the old shape, for the record"

    # What it asks for now.
    page = decisions(d, "Володимир", None, 60, days=10 ** 6,
                     said_only=True)["decisions"]
    assert [r["said"] for r in page] == ["Тривога."], page


def test_asking_for_said_lines_still_pages_forward(tmp_path):
    """A cursor has to skip the silent rows in between rather than replay them,
    or the phone walks the same quiet stretch on every request."""
    d = tmp_path / "live"
    d.mkdir()
    rows = []
    for i in range(6):
        rows.append({"at": f"2026-09-03T0{i}:00:00+00:00", "anchor": f"a/{i}",
                     "who": "Володимир", "level": "alert", "alarm": "alert",
                     "said": f"line {i}"})
        rows.append({"at": f"2026-09-03T0{i}:30:00+00:00", "anchor": f"b/{i}",
                     "who": "Володимир", "reason": "silent"})
    (d / "1.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + chr(10) for r in rows),
        encoding="utf-8")

    first = decisions(d, "Володимир", None, 2, days=10 ** 6,
                      said_only=True)["decisions"]
    assert [r["said"] for r in first] == ["line 4", "line 5"], first

    older = decisions(d, "Володимир", "2026-09-03T00:00:00+00:00.a/0", 3,
                      days=10 ** 6, said_only=True)["decisions"]
    assert [r["said"] for r in older] == ["line 1", "line 2", "line 3"], older
def test_the_feed_carries_exactly_what_the_chat_carries(tmp_path):
    """What he asked screen two to be: "рахуй те саме, що показує Ховайся ТГ
    канал... неважливо тиша там чи ні."

    The equality is structural rather than a coincidence worth maintaining by
    hand. `_say` sends to the chat when there is an utterance, and writes that
    same utterance into the log as `said` -- so a silent decision reaches neither.
    `?said=1` therefore returns the chat's contents for whoever asks, computed
    against their own ring instead of his.

    Pinned because the two could drift apart in either direction: a notifier that
    learned to send something unsaid, or a log that stopped recording something
    sent.
    """
    import time

    from tools.live.run import Session, handle, write_log
    from tools.policy.config import load as load_config
    from tools.policy.recipients import TELEGRAM_NAME, Recipient

    class Chat:
        enabled = True
        failures = 0

        def __init__(self):
            self.messages = []

        @property
        def sent(self):
            return len(self.messages)

        def send(self, text, audible=False):
            self.messages.append(text)
            return True

    cfg = load_config(warn=lambda _m: None)
    chat = Chat()
    who = Recipient(name=TELEGRAM_NAME, config=cfg)
    who.tracker.official_source = True
    session = Session(recipients=[who], tracker=who.tracker,
                      announcer=who.announcer, notifier=chat)

    now = int(time.time())
    # A raid with plenty of silence in it: the oblast, the city at large, and
    # somewhere far away, none of which is his business.
    script = [
        ("🚨 м. Київ\nПовітряна тривога", "alarm_kyiv"),
        ("⚠️Реактивний шахед на Сумщині.", "mon1tor_ua"),
        ("⚠️Реактивний шахед на Жуляни.", "mon1tor_ua"),
        ("⚠️БпЛА на Київщині, курс західний.", "mon1tor_ua"),
        ("⚠️2 реактивні шахеди на Вишневе.", "mon1tor_ua"),
        ("💥Вибух у Дніпрі.", "mon1tor_ua"),
        ("🟢 м. Київ\nВідбій повітряної тривоги", "alarm_kyiv"),
    ]
    for offset, (text, channel) in enumerate(script):
        handle(session, channel, offset, now - 600 + offset * 60, text,
               False, now)

    live = tmp_path / "live"
    live.mkdir()
    write_log(session, live / "20260903T120000.jsonl")

    served = decisions(live, TELEGRAM_NAME, None, 60, days=10 ** 6,
                       said_only=True)["decisions"]

    # The chat got a message for every utterance; the feed serves every `said`.
    assert chat.sent > 0, "the script must produce something"
    assert len(served) == chat.sent, (len(served), chat.sent)
    # ...and the same sentences, in the same order.
    for row, message in zip(served, chat.messages):
        assert row["said"] in message, (row["said"], message[:80])

    # The silence is in the log and not in either of them.
    everything = decisions(live, TELEGRAM_NAME, None, 60,
                           days=10 ** 6)["decisions"]
    assert len(everything) > len(served), "the script must include silence"
