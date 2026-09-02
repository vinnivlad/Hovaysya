"""What the app talks to: the raw feed, the decisions, and one person's settings.

Four endpoints and no framework, because the watcher's whole deployment property
is that nothing has to be installed:

    GET  /messages?since=<cursor>     the merged raw feed of every channel
    GET  /messages?back=30m           ...or just the last half hour, newest end
    GET  /decisions?since=<cursor>    what Ховайся decided, for this recipient
                                      -- and for nobody else: the sentence names
                                      their ring and the reason says "my area"
    GET  /places                      every name the policy knows, for the
                                      first screen's home picker
    GET  /config                      their settings
    PUT  /config                      change them
    GET  /health                      no token needed

**This process must never be the reason the watch stops.** It shares nothing with
the watcher but a read-only handle on the database, runs as its own service, and
is meant for a second machine -- see `docs/next-steps.md` on why the box with the
open port is not the box with the bot token.

TLS is deliberately not here. Caddy terminates it in front and talks to this over
localhost, so there is no certificate, no private key and no renewal in this file.
Bound to 127.0.0.1 it cannot be reached any other way at all.

    python -m tools.serve.api                     # 127.0.0.1:8080

Cursors are opaque and ordered by time rather than by insert order: a backfill of
an old channel writes high rowids for old messages, so `rowid` would hand the app
a feed that jumps backwards.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Deliberately `tokens` and not `recipients`: the second pulls in the ordered
# rules, the episode machinery and `hints`, and this process needs a hash
# comparison and a database. The service facing the internet carries the least
# code that can do its job.
from ..policy import tokens as people

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "messages.db"
LOG_DIR = REPO_ROOT / "data" / "live"

MAX_LIMIT = 500
DEFAULT_LIMIT = 200
MAX_BODY = 64 * 1024
# How far back the decision log is read. A night is a couple of thousand lines,
# and an app away longer than this has nothing useful to catch up on -- whatever
# was flying has landed.
LOG_DAYS = 3


def _cursor(ts: int, channel: str, message_id: int) -> str:
    return f"{ts}.{channel}.{message_id}"


def _parse_back(raw: str | None) -> int | None:
    """A window in seconds, from `1800`, `30m` or `2h`. None if not asked for.

    Opening the screen with nothing loaded is the case this exists for: "коли я
    відкриваю скрін, я хочу бачити останні повідомлення за 30хв". Without it the
    only way in was a cursor, and a cursor the app has never had means the
    beginning of the corpus -- January 2024, and 27 000 messages to walk before
    reaching tonight.
    """
    if not raw:
        return None
    raw = raw.strip().lower()
    unit = 1
    if raw.endswith("m"):
        unit, raw = 60, raw[:-1]
    elif raw.endswith("h"):
        unit, raw = 3600, raw[:-1]
    elif raw.endswith("s"):
        raw = raw[:-1]
    try:
        seconds = int(float(raw)) * unit
    except ValueError:
        return None
    # A day is the ceiling: past that it is an archive request, and the cursor is
    # the honest way to ask for one.
    return max(60, min(86400, seconds))


def _parse_cursor(raw: str | None) -> tuple[int, str, int]:
    """A cursor we did not issue means "from the beginning", never an error."""
    if not raw:
        return (0, "", 0)
    try:
        ts, channel, mid = raw.split(".", 2)
        return (int(ts), channel, int(mid))
    except ValueError:
        return (0, "", 0)


def messages(conn: sqlite3.Connection | None, since: str | None,
             limit: int, back: int | None = None,
             now: float | None = None) -> dict:
    """The feed, or an empty one when there is no corpus on this machine.

    Two ways in, and the app needs both:

    `since=<cursor>`  everything after what it already has. The ordinary poll.
    `back=30m`        the last half hour, for a screen opened cold. Returns the
                      *newest* messages in the window rather than the oldest,
                      because a screen is not an archive: half an hour during an
                      attack is 300 messages and the last 200 are the ones worth
                      showing.

    A cursor the app has never had means the beginning, which is January 2024 --
    so without `back` a fresh screen had to walk 27 000 messages to reach tonight.

    `back` always answers with a cursor, including when the window is empty, and
    that is what makes it enough on its own. There was a third way in briefly --
    `since=head`, a bare cursor and no messages -- and it went when he asked what
    it was for: nothing, once this one carries a cursor too.

    B is a fresh box with no database until something copies one there, and the
    settings endpoint has nothing to do with the corpus. A service that refuses to
    start because the feed is missing takes the useful half down with the absent
    half -- which is exactly what it did on the first deploy.
    """
    if conn is None:
        return {"messages": [], "next": since or "", "corpus": False}

    if back is not None:
        floor = int((time.time() if now is None else now) - back)
        rows = conn.execute(
            "SELECT channel, message_id, ts, text_norm, reply_to FROM messages "
            "WHERE text_norm <> '' AND ts >= ? "
            "ORDER BY ts DESC, channel DESC, message_id DESC LIMIT ?",
            (floor, limit)).fetchall()
        rows = list(reversed(rows))
        if not rows:
            # An empty window is normal -- ten minutes of silence happens about
            # twenty-two times a day -- but it must still hand over somewhere to
            # poll from, or an app that opened during one of those has no way
            # forward at all except replaying the corpus from January 2024.
            #
            # This is also what made `?since=head` unnecessary. It existed to
            # fetch a bare cursor, and he asked what it was for: "воно ж ніколи
            # не поверне нічого, хіба ні?" It never did, and once `back` answers
            # with a cursor of its own there is nothing left for it to do.
            newest = conn.execute(
                "SELECT ts, channel, message_id FROM messages "
                "WHERE text_norm <> '' "
                "ORDER BY ts DESC, channel DESC, message_id DESC "
                "LIMIT 1").fetchone()
            return {"messages": [],
                    "next": _cursor(newest[0], newest[1], newest[2])
                            if newest else ""}
    else:
        ts, channel, mid = _parse_cursor(since)
        rows = conn.execute(
            "SELECT channel, message_id, ts, text_norm, reply_to FROM messages "
            "WHERE text_norm <> '' AND (ts, channel, message_id) > (?, ?, ?) "
            "ORDER BY ts, channel, message_id LIMIT ?",
            (ts, channel, mid, limit)).fetchall()

    out = [{"channel": r["channel"], "id": r["message_id"], "ts": r["ts"],
            "text": r["text_norm"], "reply": r["reply_to"]} for r in rows]
    return {"messages": out,
            "next": _cursor(rows[-1]["ts"], rows[-1]["channel"],
                            rows[-1]["message_id"]) if rows else (since or "")}


def health(conn: sqlite3.Connection | None, log_dir: Path,
           now: float | None = None) -> dict:
    """Whether the watch is running, not whether this process is up.

    His question, and it settles the whole design: "реально, якщо А не працює, то
    який взагалі сенс?" A service that answers `{"ok": true}` while the watcher is
    dead is worse than one that does not answer at all -- the app would show a
    calm sky and the phone would stay silent, which is exactly what a quiet night
    looks like.

    `poll_age_s` is the signal to act on. The watcher rewrites its decision log
    after every poll cycle, whether or not anything arrived, so this is the age of
    the poll loop itself: seconds while it runs, unbounded when it stops. Nothing
    is shared or agreed -- it is read off the file the watcher writes.

    `message_age_s` is information, not health, and the corpus says why. Measured
    over two weeks of seven channels: the median gap between messages is 23 s,
    but silences longer than ten minutes happen 307 times -- about twenty-two a
    day -- and the longest was six hours. An app treating minutes here as a fault
    would cry wolf daily. I had documented the opposite; the data corrected it.

    Numbers rather than a verdict, because the threshold is the app's business and
    it is the only part that knows whether anyone is looking.
    """
    now = time.time() if now is None else now
    newest = None
    if conn is not None:
        row = conn.execute("SELECT max(ts) FROM messages").fetchone()
        newest = row[0] if row and row[0] else None
    try:
        polled = max((p.stat().st_mtime for p in log_dir.glob("*.jsonl")),
                     default=None)
    except OSError:
        polled = None
    return {
        "ok": True,
        "corpus": newest is not None,
        "poll_age_s": round(now - polled) if polled else None,
        "message_age_s": round(now - newest) if newest else None,
    }


def decisions(log_dir: Path, who: str | None, since: str | None, limit: int,
              days: int = LOG_DAYS, now: float | None = None) -> dict:
    """What Ховайся decided **for this recipient**, from the newest logs only.

    The filter is the whole point, and for a while it was missing -- his call,
    from intuition rather than from the code: "decisions думаю теж приватне, воно
    ж персональне". It is worse than private. `reason` reads "new target heading
    into my area", where *my* is whoever the line was decided for, and the
    sentence names their ring: 47 lines of 3907 named the watcher's own district.
    Served unfiltered, every token holder got his address -- and an answer
    computed from his home rather than from their own, which is simply wrong for
    them.

    Read from the log rather than recomputed, because the app must see what
    actually happened -- including on a version of the policy that has since been
    corrected. A decision cannot be recomputed alone in any case: the episode it
    belongs to is sequential.

    A line with no owner belongs to nobody and reaches nobody. Those are the ones
    written before the owner was recorded, and `LOG_DAYS` clears them on its own.
    """
    if who is None:
        return {"decisions": [], "next": since or ""}
    horizon = (now if now is not None else time.time()) - days * 86400
    try:
        files = sorted((p for p in log_dir.glob("*.jsonl")
                        if p.stat().st_mtime >= horizon), key=lambda p: p.name)
    except OSError:
        files = []
    seen: set[str] = set()
    out = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            at, anchor = row.get("at") or "", row.get("anchor") or ""
            key = f"{at}.{anchor}"
            # Logs overlap: a restart replays the last ninety minutes and the
            # catch-up pass writes those lines again.
            if (not at or key in seen or (since and key <= since)
                    or row.get("who") != who):
                continue
            seen.add(key)
            out.append({"cursor": key, "at": at, "anchor": anchor,
                        "level": row.get("level"), "alarm": row.get("alarm"),
                        "said": row.get("said"), "reason": row.get("reason"),
                        "text": row.get("text")})
    out.sort(key=lambda r: r["cursor"])
    out = out[:limit]
    return {"decisions": out, "next": out[-1]["cursor"] if out else (since or "")}


def places() -> dict:
    """Every name the policy knows, so the picker can only offer names it parses.

    Read from the gazetteer itself rather than from a generated copy of it. A copy
    would be one more thing to keep in step and its failure would be quiet: a
    picker offering a district the rules no longer recognise, or a home with no
    coordinate, which leaves `Config.centre()` returning None and the radius
    silently empty while the ring falls back to the hand list.

    `home` is the flag the first screen needs. 230 names are known and 162 have a
    point, because some deliberately cannot have one -- Правий берег is half a
    city, Київщина is the oblast -- and those can be reported as a threat but not
    lived in. `tiers` is the gazetteer's own order, so the picker groups by it
    rather than inventing an order of its own.

    Two modules join the process here, `gazetteer` and `coords`, and both are
    data: neither pulls in `hints`, which is where every fault in this project has
    lived. Imported inside the function so a service nobody asks for a picker
    stays at six modules -- but after the first request they are resident, and
    this is a lazy import rather than a smaller service.
    """
    from ..nlp.coords import POINTS
    from ..nlp.gazetteer import PLACES, TIERS

    out = []
    for place in PLACES:
        point = POINTS.get(place.name)
        out.append({"name": place.name, "tier": place.tier,
                    "lat": point[0] if point else None,
                    "lon": point[1] if point else None,
                    "home": point is not None,
                    "landmark": place.landmark or None})
    out.sort(key=lambda r: r["name"])
    return {"places": out, "tiers": list(TIERS)}


class Handler(BaseHTTPRequestHandler):
    server_version = "hovaysya"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # One line per request on stdout, so journalctl is the access log.
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _token(self) -> str | None:
        auth = self.headers.get("Authorization") or ""
        return auth[7:].strip() if auth.startswith("Bearer ") else None

    def _who(self) -> str | None:
        token = self._token()
        return people.name_for(token, self.server.recipients_dir) if token else None


    def _limit(self, query: dict) -> int:
        try:
            n = int((query.get("limit") or [DEFAULT_LIMIT])[0])
        except ValueError:
            return DEFAULT_LIMIT
        return max(1, min(MAX_LIMIT, n))

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)

        if url.path == "/health":
            self._send(200, health(self.server.db, self.server.log_dir))
            return

        who = self._who()
        if who is None:
            self._send(401, {"error": "потрібен токен"})
            return

        since = (query.get("since") or [None])[0]
        limit = self._limit(query)
        if url.path == "/messages":
            self._send(200, messages(self.server.db, since, limit,
                                     _parse_back((query.get("back") or [None])[0])))
        elif url.path == "/decisions":
            self._send(200, decisions(self.server.log_dir, who, since, limit))
        elif url.path == "/places":
            self._send(200, places())
        elif url.path == "/config":
            from ..policy.config import changed_from_default

            cfg = people.config_of(who, self.server.recipients_dir)
            self._send(200, {"config": changed_from_default(cfg)})
        else:
            self._send(404, {"error": "нема такого"})

    do_HEAD = do_GET

    def do_PUT(self) -> None:
        if urlparse(self.path).path != "/config":
            self._send(404, {"error": "нема такого"})
            return
        who = self._who()
        if who is None:
            self._send(401, {"error": "потрібен токен"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._send(413, {"error": f"тіло більше за {MAX_BODY} байт"})
            return
        try:
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "не JSON"})
            return
        if not isinstance(raw, dict):
            self._send(400, {"error": "очікував обʼєкт"})
            return

        from ..policy.config import changed_from_default

        # What lands on disk is what the loader accepted, never the body as sent.
        cfg = people.save_config(who, raw, self.server.recipients_dir)
        self._send(200, {"config": changed_from_default(cfg)})


def serve(host: str, port: int, db: Path, log_dir: Path,
          recipients_dir: Path) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    # Read-only, said in the URI rather than left to the code: this process has
    # no business writing to the corpus and cannot be talked into it.
    #
    # Missing is not fatal. `mode=ro` on an absent file raises, and letting that
    # reach systemd cost an hour: the service died with 1/FAILURE on a machine
    # whose only job at that moment was to serve settings.
    try:
        httpd.db = sqlite3.connect(f"file:{db}?mode=ro", uri=True,
                                   check_same_thread=False)
        httpd.db.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        print(f"  ! бази {db} немає ({exc}) — /messages віддає порожньо")
        httpd.db = None
    httpd.log_dir = log_dir
    httpd.recipients_dir = recipients_dir
    return httpd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1",
                    help="On A this is the private VCN address, so Caddy on B "
                         "can reach it and nothing else can. 127.0.0.1 is the "
                         "safe default and means only this machine.")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--logs", default=str(LOG_DIR))
    ap.add_argument("--recipients", default=str(people.DIR))
    args = ap.parse_args()

    httpd = serve(args.host, args.port, Path(args.db), Path(args.logs),
                  Path(args.recipients))
    print(f"Слухаю http://{args.host}:{args.port} · "
          f"{len(people.index(Path(args.recipients)))} токен(и)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
