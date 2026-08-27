"""Build a self-contained labeling page from the exported corpus.

Produces one HTML file with the merged feed embedded, plus any labels already in
`labels/moments.jsonl`. No server and no dependencies: open the file, label a
night, export, save the result back over `labels/moments.jsonl`.

Each message arrives pre-filled with the gazetteer and hint layer's guesses
(`tools/nlp/`), so a night is a scroll and a few keystrokes rather than a
data-entry exercise. The same module runs in the stage-6 baseline, which is why
the pre-fill is worth trusting as a starting point and worth correcting when
wrong — a correction here is a signal about the baseline too.

Usage:
    python -m tools.labeler.build
    python -m tools.labeler.build --since 2026-07-27 --out data/labeler.html
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..nlp import hints
from ..nlp.gazetteer import find_infrastructure, find_places, resolve_scope

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "messages.db"
LABELS_PATH = REPO_ROOT / "labels" / "moments.jsonl"
TEMPLATE = Path(__file__).with_name("template.html")
OUT_PATH = REPO_ROOT / "data" / "labeler.html"

# A "night" runs 15:00 to 15:00 Kyiv time, so an attack spanning midnight stays
# in one night. Peak traffic is 00:00-04:00 Kyiv, right in the middle of that.
NIGHT_START_HOUR = 15

CHANNEL_SHORT = {
    "mon1tor_ua": "mon1tor",
    "war_monitor": "war_mon",
    "kievinform_ua1": "kievinfo",
}


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month, 31)  # both March and October have 31 days
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def kyiv_offset(ts: int) -> int:
    """Hours to add to UTC for Kyiv. EU rule, so no tzdata dependency.

    Summer time runs from the last Sunday of March to the last Sunday of
    October. The corpus is April to August, i.e. entirely +3, but the realtime
    ingest will cross the boundary.
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    start = datetime.combine(_last_sunday(dt.year, 3), datetime.min.time(), timezone.utc)
    end = datetime.combine(_last_sunday(dt.year, 10), datetime.min.time(), timezone.utc)
    return 3 if start <= dt < end else 2


def kyiv_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(hours=kyiv_offset(ts))


def night_id(ts: int) -> str:
    """The night a timestamp belongs to, named by its evening date."""
    local = kyiv_dt(ts)
    if local.hour < NIGHT_START_HOUR:
        local -= timedelta(days=1)
    return local.date().isoformat()


def load_messages(conn: sqlite3.Connection, since: str | None) -> list[dict]:
    sql = (
        "SELECT channel, message_id, ts, text_norm, reply_to, reply_text, media_type "
        "FROM messages WHERE text_norm <> '' "
    )
    params: list[object] = []
    if since:
        cutoff = int(
            datetime.strptime(since, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        sql += "AND ts >= ? "
        params.append(cutoff)
    sql += "ORDER BY ts"

    out: list[dict] = []
    for row in conn.execute(sql, params):
        text = row["text_norm"]
        guess = hints.suggest(text)
        places = [p.name for p in find_places(text)]
        out.append(
            {
                # Stable key, NOT the array index: rebuilding with a different
                # --since shifts indices and would detach every stored label.
                "k": f"{row['channel']}/{row['message_id']}",
                "n": night_id(row["ts"]),
                "c": CHANNEL_SHORT.get(row["channel"], row["channel"]),
                "ch": row["channel"],
                "id": row["message_id"],
                "t": row["ts"],
                "hm": f"{kyiv_dt(row['ts']):%H:%M}",
                "x": text,
                "q": row["reply_text"] or "",
                "r": row["reply_to"],
                "s": resolve_scope(text),
                # A MiG-31K takeoff names a Russian airfield and no Ukrainian
                # target, so the geographic filter alone would hide it.
                "nw": hints.nationwide(text),
                "m": guess["modality"],
                "th": guess["threat"],
                "al": guess["alarm"],
                "ce": guess["certainty"],
                "st": guess["strength"],
                "sh": guess["shapes"],
                "p": places,
                "inf": find_infrastructure(text),
                # Filled by carry_context: the best answer available from the
                # feed when the message itself states none.
                "ith": None,
                "isc": None,
                "ifrom": None,
            }
        )
    return out


# How long a stated threat type or location stays the best available answer for
# a message that gives none of its own. Beyond this the situation has probably
# moved on and guessing does more harm than leaving it blank.
CARRY_WINDOW_S = 15 * 60


def carry_context(messages: list[dict]) -> None:
    """Fill each message's inherited threat and scope, in place.

    A label answers "what is flying at this moment", not "what does this post
    say". Continuation messages — `Вибухи`, `Збито`, `Продовжує рух на Центр` —
    carry no type or place of their own, and judging them in isolation is
    exactly the mistake the schema warns about. So the pre-fill inherits from
    the most recent message that did state one.

    An explicit all-clear resets the carry: after `відбій` nothing is known to
    be in the air, and inheriting across it would invent a threat.
    """
    last_threat: tuple[str, int, str] | None = None  # value, ts, hh:mm
    last_scope: tuple[str, int, str] | None = None

    for m in messages:
        if m["m"] == "live-threat":
            if last_threat and m["t"] - last_threat[1] <= CARRY_WINDOW_S:
                m["ith"], m["ifrom"] = last_threat[0], last_threat[2]
            if last_scope and m["t"] - last_scope[1] <= CARRY_WINDOW_S:
                m["isc"] = last_scope[0]

        if "відбій" in m["x"].lower():
            last_threat = last_scope = None
            continue

        if m["th"] not in ("none", "unknown"):
            last_threat = (m["th"], m["t"], m["hm"])
        if m["s"] != "unknown":
            last_scope = (m["s"], m["t"], m["hm"])


def build_nights(messages: list[dict]) -> list[dict]:
    by_night: dict[str, list[dict]] = {}
    for m in messages:
        by_night.setdefault(m["n"], []).append(m)

    nights = []
    for nid, msgs in sorted(by_night.items(), reverse=True):
        relevant = [m for m in msgs if m["s"] in ("my-area", "my-district", "city", "oblast")]
        near = [m for m in msgs if m["s"] in ("my-area", "my-district")]
        nights.append(
            {
                "id": nid,
                "count": len(msgs),
                "relevant": len(relevant),
                "near": len(near),
                "from": msgs[0]["t"],
                "to": msgs[-1]["t"],
            }
        )
    return nights


def load_labels() -> list[dict]:
    if not LABELS_PATH.exists():
        return []
    labels = []
    for line in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            labels.append(json.loads(line))
    return labels


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="Only include this date onward.")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    messages = load_messages(conn, args.since)
    conn.close()
    carry_context(messages)

    if not messages:
        print("No messages matched — nothing to label.")
        return 1

    payload = {
        "generated": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "reference": "Жуляни",
        "nights": build_nights(messages),
        "messages": messages,
        "labels": load_labels(),
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # </script> inside the data would end the tag early.
    blob = blob.replace("</", "<\\/")
    html = template.replace("__PAYLOAD__", blob)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8", newline="\n")

    inherited = sum(1 for m in messages if m["ith"] or m["isc"])
    near = sum(n["near"] for n in payload["nights"])
    print(f"Wrote {out}  ({out.stat().st_size / 1048576:.1f} MB)")
    print(f"  {len(messages)} messages across {len(payload['nights'])} nights")
    print(f"  {near} mention your area or district")
    print(f"  {inherited} take their type or place from earlier in the feed")
    print(f"  {len(payload['labels'])} existing labels loaded")
    print(f"\nOpen it in a browser: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
