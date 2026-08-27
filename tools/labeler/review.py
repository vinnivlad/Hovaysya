"""Check labels for schema validity and internal consistency.

Reviewing labels by eye is how a labelled set quietly drifts: the twentieth
night gets judged by a slightly different standard than the first, and nothing
notices. This reports two kinds of finding:

- **errors** — the label cannot be used: a missing field, an unknown enum value,
  a `repeat_of` pointing nowhere.
- **warnings** — the label is usable but looks inconsistent with a rule the
  schema states, e.g. a new alarm sound raised on an anticipatory warning rather
  than a confirmed event.

A warning is not necessarily wrong. It is a question, and the answer may be that
the rule needs changing — which is exactly the sort of thing worth catching
early rather than after a hundred labels.

Usage:
    python -m tools.labeler.review
    python -m tools.labeler.review --labels labels/moments.jsonl
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from ..nlp import hints

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = REPO_ROOT / "labels" / "moments.jsonl"
DB_PATH = REPO_ROOT / "data" / "messages.db"

DECISIONS = {"notify", "silent"}
LEVELS = {"info", "alert"}
ALARMS = {"alert", "ballistic", "mig", "cruise", "drone-jet", "drone",
          "recon", "clear-partial", "clear", "none"}
SILENT_REASONS = {"too-far", "already-notified", "resolved", "insufficient"}
THREATS = {"none", "unknown", "recon", "mig", "shahed", "shahed-jet", "cruise",
           "ballistic", "kab", "aviation", "mixed"}
MODALITIES = {"live-threat", "aftermath", "summary-news", "non-threat"}
SCOPES = {"my-area", "my-district", "city", "oblast", "elsewhere", "unknown"}
CERTAINTIES = {"confirmed", "probable", "lost", "clear"}
HEADINGS = {"toward", "away", "loitering", "position", "unknown"}

LEVEL_RANK = {"info": 0, "alert": 1}

REQUIRED = ("id", "at", "decision", "threat", "modality", "scope", "certainty",
            "night", "anchor")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            out.append({"_broken": f"line {n}: {exc}"})
    return out


def load_messages(db: Path) -> dict[str, dict]:
    if not db.exists():
        return {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT channel, message_id, text_norm FROM messages WHERE text_norm <> ''"
    ).fetchall()
    conn.close()
    return {
        f"{r['channel']}/{r['message_id']}": {"text": r["text_norm"]} for r in rows
    }


def check(labels: list[dict], messages: dict[str, dict]) -> list[tuple[str, str, str]]:
    """Returns (severity, label id, message) triples."""
    found: list[tuple[str, str, str]] = []

    def err(lid, msg):
        found.append(("error", lid, msg))

    def warn(lid, msg):
        found.append(("warning", lid, msg))

    seen_ids: set[str] = set()
    by_id = {l.get("id"): l for l in labels if l.get("id")}
    by_night: dict[str, list[dict]] = defaultdict(list)
    for l in labels:
        if l.get("night"):
            by_night[l["night"]].append(l)
    for night in by_night.values():
        night.sort(key=lambda l: l.get("at", ""))

    for l in labels:
        if "_broken" in l:
            err("?", l["_broken"])
            continue
        lid = l.get("id", "<no id>")

        for field in REQUIRED:
            if not l.get(field):
                err(lid, f"missing required field `{field}`")
        if lid in seen_ids:
            err(lid, "duplicate id")
        seen_ids.add(lid)

        for field, allowed in (("decision", DECISIONS), ("threat", THREATS),
                               ("modality", MODALITIES), ("scope", SCOPES),
                               ("certainty", CERTAINTIES), ("heading", HEADINGS)):
            v = l.get(field)
            if v is not None and v not in allowed:
                err(lid, f"`{field}` has unknown value {v!r}")

        decision = l.get("decision")
        if decision == "notify":
            if l.get("level") not in LEVELS:
                err(lid, f"notify needs a valid level, got {l.get('level')!r}")
            if l.get("alarm") not in ALARMS:
                err(lid, f"notify needs a valid alarm, got {l.get('alarm')!r}")
            if not (l.get("why") or "").strip():
                err(lid, "notify needs `why` — a wake-up has to be justified")
        elif decision == "silent":
            if l.get("silent_reason") not in SILENT_REASONS:
                err(lid, f"silent needs a valid reason, got {l.get('silent_reason')!r}")

        ref = l.get("repeat_of")
        if ref:
            target = by_id.get(ref)
            if target is None:
                err(lid, f"`repeat_of` points at {ref!r}, which does not exist")
            elif target.get("at", "") >= l.get("at", ""):
                err(lid, f"`repeat_of` points at {ref!r}, which is not earlier")
            elif target.get("night") != l.get("night"):
                warn(lid, f"`repeat_of` crosses into another night ({ref})")

        anchor = l.get("anchor")
        if anchor and messages and anchor not in messages:
            err(lid, f"anchor {anchor!r} is not a message in the database")

        # --- consistency, not validity ---
        if decision == "notify":
            if l.get("scope") == "elsewhere":
                warn(lid, "notify on a threat resolved to another region")
            if l.get("threat") == "none" and l.get("level") != "info":
                warn(lid, "audible notify while nothing is flying — `info`?")
            if l.get("certainty") == "clear" and l.get("alarm") != "clear":
                warn(lid, "a threat tone on an all-clear")
            if l.get("modality") in ("aftermath", "summary-news", "non-threat") \
                    and l.get("level") != "info":
                warn(lid, f"audible notify on modality {l.get('modality')}")
            if anchor and anchor in messages:
                text = messages[anchor]["text"]
                if l.get("level") == "alert" and hints.live_strength(text) == "weak":
                    warn(lid, "a wake-up where the only evidence is an emoji")

        if decision == "silent" and l.get("silent_reason") == "already-notified":
            earlier = [
                x for x in by_night.get(l.get("night"), [])
                if x.get("decision") == "notify" and x.get("at", "") < l.get("at", "")
            ]
            if not earlier:
                warn(lid, "`already-notified` but nothing woke you earlier this night")

    # --- the new-sound rule, across each night ---
    for night, group in by_night.items():
        last_alarm: str | None = None
        for l in group:
            if l.get("decision") != "notify" or l.get("level") == "info":
                continue
            alarm = l.get("alarm")
            if alarm and alarm != last_alarm and l.get("certainty") == "probable":
                warn(l.get("id", "?"),
                     "new sound raised on an anticipated threat — the schema "
                     "reserves a new sound for confirmed events")
            last_alarm = alarm or last_alarm

    return found


def inconsistencies(labels: list[dict], messages: dict[str, dict]) -> list[str]:
    """Moments that look alike but were decided differently.

    This is the half of "are the labels consistent" that a machine can answer.
    Whether a label makes *sense* is a reading task; whether the same situation
    got two different answers is a grouping task, and drift shows up here long
    before it shows up in a metric.

    The signature is deliberately coarse — threat class, distance, certainty,
    modality — because that is the tuple the policy is supposed to be a function
    of. If two moments share it and got different decisions, either one of them
    is wrong or the policy needs a distinction the signature is missing. Both
    are worth knowing.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for l in labels:
        if "_broken" in l:
            continue
        # Heading is part of the signature because the decision genuinely
        # depends on it: two labels on Kriukivshchyna looked like a
        # contradiction until direction was separated from position.
        sig = (l.get("threat"), l.get("scope"), l.get("certainty"),
               l.get("modality"), l.get("heading") or "unknown")
        if all(sig):
            groups[sig].append(l)

    out: list[str] = []
    for sig, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(group) < 2:
            continue
        outcomes = {
            (l.get("decision"), l.get("level"), l.get("silent_reason"))
            for l in group
        }
        if len(outcomes) < 2:
            continue
        threat, scope, certainty, modality, head = sig
        out.append(f"{threat} · {scope} · {head} · {certainty} · {modality}  "
                   f"— {len(group)} moments, {len(outcomes)} different answers")
        for l in sorted(group, key=lambda x: x.get("at", "")):
            verdict = (f"{l.get('level')} · {l.get('alarm')}"
                       if l.get("decision") == "notify"
                       else f"silent · {l.get('silent_reason')}")
            text = messages.get(l.get("anchor"), {}).get("text", "")
            text = text.replace(chr(10), " / ")[:64]
            why = (l.get("why") or "").strip()
            out.append(f"    {l.get('id', '?'):<22} {verdict:<26} {text}")
            if why:
                out.append(f"    {'':<22} «{why}»")
        out.append("")
    return out


def summarise(labels: list[dict]) -> list[str]:
    good = [l for l in labels if "_broken" not in l]
    if not good:
        return ["No usable labels."]
    nights = sorted({l.get("night") for l in good if l.get("night")})
    notify = [l for l in good if l.get("decision") == "notify"]
    out = [
        f"{len(good)} labels across {len(nights)} night(s): "
        f"{len(notify)} notify, {len(good) - len(notify)} silent",
    ]
    for field in ("level", "alarm", "silent_reason", "threat", "scope", "certainty"):
        c = Counter(l.get(field) for l in good if l.get(field))
        if c:
            body = "  ".join(f"{k}={v}" for k, v in c.most_common())
            out.append(f"  {field:<14}{body}")
    if nights:
        per = Counter(l.get("night") for l in good)
        out.append("  per night     " + "  ".join(
            f"{n}={per[n]}" for n in nights))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--labels", default=str(LABELS_PATH))
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args(argv)

    path = Path(args.labels)
    labels = load(path)
    if not labels:
        print(f"No labels in {path}. Export from the labeler and save them there.")
        return 0

    messages = load_messages(Path(args.db))
    findings = check(labels, messages)

    for line in summarise(labels):
        print(line)
    print()

    errors = [f for f in findings if f[0] == "error"]
    warnings = [f for f in findings if f[0] == "warning"]

    for title, group in (("Errors — these labels cannot be used", errors),
                         ("Warnings — questions, not necessarily mistakes", warnings)):
        if not group:
            continue
        print(f"{title}  ({len(group)})")
        for _sev, lid, msg in group:
            print(f"  {lid:<22} {msg}")
        print()

    pairs = inconsistencies(labels, messages)
    if pairs:
        print("Same situation, different answer — worth a second look")
        print("  (the signature is what the policy is meant to be a function of;")
        print("   a split here means either a label is off or the policy needs a")
        print("   distinction this signature does not carry)")
        print()
        for line in pairs:
            print(line)

    if not findings and not pairs:
        print("No findings. Schema-valid, internally consistent, no split decisions.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
