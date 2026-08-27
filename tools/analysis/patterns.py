"""Mine the exported corpus for structure that can be exploited without a model.

The reply-chain pattern was spotted by eye on a single 20-message page, which
suggested more was hiding in the corpus. This produces a report covering the
axes the classifier and the episode state machine both need:

- toponym inventory, including slang and informal areas -> gazetteer input
- resolution vocabulary -> the state machine's episode-exit conditions
- reply-chain shape -> target identity across messages
- count and phase grammar -> classifier output schema
- cross-channel duplication -> sizing the dedup layer, and who reports first
- message rate -> realtime poll and batching budget

Usage:
    python -m tools.analysis.patterns                     # writes data/patterns.md
    python -m tools.analysis.patterns --out report.md
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "messages.db"

# Ukrainian word characters, apostrophe included (Солом'янський).
WORD = re.compile(r"[А-Яа-яЇїІіЄєҐґЁёA-Za-z][А-Яа-яЇїІіЄєҐґЁёA-Za-z'’\-]*")
UPPER_FIRST = re.compile(r"^[А-ЯЇІЄҐA-Z]")

# Spatial slots: whatever follows these is almost always a place.
SLOT_PATTERNS = [
    ("курсом на", r"курсом\s+на\s+"),
    ("в напрямку", r"[ву]\s+напрямку\s+"),
    ("в районі", r"[ву]\s+районі\s+"),
    ("з боку", r"з\s+боку\s+"),
    ("поблизу", r"поблизу\s+"),
    ("біля", r"біля\s+"),
    ("через", r"через\s+"),
    ("над", r"над\s+"),
    ("на", r"\bна\s+"),
]

# Candidate resolution / episode-exit markers, checked as substrings.
RESOLUTION_TERMS = [
    "збито", "збили", "збит", "відбій", "пішов далі", "пішли далі",
    "знизив", "знизили", "втрачено", "вийшов", "вийшли", "минув",
    "минули", "ліквідовано", "upd", "уточнення", "більше не",
]

THREAT_TERMS = [
    "балістик", "балістичн", "шахед", "бпла", "реактивн", "крилат",
    "калібр", "кинжал", "циркон", "іскандер", "кн-23", "х-101", "х-59",
    "каб", "розвідувальн", "розвід", "ракета", "ракети", "дрон",
    "мопед", "герань",
]

PHASE_TERMS = [
    "пуск", "пуски", "старт", "зліт", "курсом", "на підльоті", "підліт",
    "над", "вхід", "зайшл", "чути", "робота пво", "працює пво",
    "вибух", "влучан", "приліт", "загроза", "уваг",
]

COUNT_PATTERNS = [
    ("Nх (1х, 2х)", r"\b\d+\s*[хx]\b"),
    ("N-M (5-7)", r"\b\d+\s*[-–]\s*\d+\b"),
    ("+ N / + шахед", r"\+\s*\d*\s*[а-яіїєґ]"),
    ("N нових/нові", r"\b\d+\s+нов[а-яіїєґ]+"),
    ("до N", r"\bдо\s+\d+\b"),
    ("бare N + noun", r"\b\d+\s+[а-яіїєґ]{3,}"),
]


def load(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT channel, message_id, ts, date_utc, text_norm, reply_to, reply_text "
        "FROM messages WHERE text_norm <> '' ORDER BY ts"
    ).fetchall()


def tokens(text: str) -> list[str]:
    return WORD.findall(text)


def stem_key(word: str, n: int = 6) -> str:
    """Crude prefix stem, enough to cluster Ukrainian case endings.

    Борщагівка / Борщагівки / Борщагівці all collapse to the same key, which is
    what the gazetteer needs to see in order to enumerate variants.
    """
    return word.lower()[:n]


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def section_overview(rows) -> list[str]:
    out = ["## Corpus overview", ""]
    per = defaultdict(list)
    for r in rows:
        per[r["channel"]].append(r)
    out.append("| channel | messages | replies | reply % | median chars | span |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for ch, msgs in sorted(per.items()):
        rep = sum(1 for m in msgs if m["reply_to"])
        lens = sorted(len(m["text_norm"]) for m in msgs)
        med = lens[len(lens) // 2]
        span = f"{msgs[0]['date_utc'][:10]} .. {msgs[-1]['date_utc'][:10]}"
        out.append(
            f"| {ch} | {len(msgs)} | {rep} | {100 * rep / len(msgs):.0f}% | {med} | {span} |"
        )
    out.append("")
    return out


def section_toponyms(rows, top: int = 60) -> list[str]:
    """Rank place candidates from spatial slots and from standalone capitals."""
    slot_hits: Counter[str] = Counter()
    slot_by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    compiled = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in SLOT_PATTERNS]

    for r in rows:
        text = r["text_norm"]
        for name, rx in compiled:
            for m in rx.finditer(text):
                tail = text[m.end() : m.end() + 40]
                words = tokens(tail)
                if words and UPPER_FIRST.match(words[0]):
                    slot_hits[words[0]] += 1
                    slot_by_kind[name][words[0]] += 1

    caps: Counter[str] = Counter()
    for r in rows:
        for w in tokens(r["text_norm"]):
            if UPPER_FIRST.match(w) and len(w) > 3:
                caps[w] += 1

    # Cluster inflections so the gazetteer can see the variant families.
    families: dict[str, Counter[str]] = defaultdict(Counter)
    for word, n in caps.items():
        families[stem_key(word)][word] += n

    out = ["## Toponym candidates", ""]
    out.append(f"Extracted from {len(slot_hits)} distinct spatial-slot fillers and ")
    out.append(f"{len(caps)} distinct capitalised tokens.")
    out.append("")
    out.append("### Ranked by spatial-slot frequency (strongest place signal)")
    out.append("")
    out.append("| candidate | slot hits |")
    out.append("| --- | --- |")
    for word, n in slot_hits.most_common(top):
        out.append(f"| {word} | {n} |")
    out.append("")
    out.append("### Inflection families (gazetteer needs every variant)")
    out.append("")
    ranked = sorted(families.items(), key=lambda kv: -sum(kv[1].values()))
    out.append("| family | total | variants |")
    out.append("| --- | --- | --- |")
    for _key, variants in ranked[:top]:
        total = sum(variants.values())
        if total < 5 or len(variants) < 2:
            continue
        forms = ", ".join(f"{w} ({n})" for w, n in variants.most_common(6))
        out.append(f"| {variants.most_common(1)[0][0]} | {total} | {forms} |")
    out.append("")
    out.append("### Slot breakdown")
    out.append("")
    for name, counter in sorted(slot_by_kind.items(), key=lambda kv: -sum(kv[1].values())):
        head = ", ".join(f"{w}({n})" for w, n in counter.most_common(8))
        out.append(f"- **{name}** — {sum(counter.values())} hits: {head}")
    out.append("")
    return out


def section_resolution(rows) -> list[str]:
    """How episodes are closed — the state machine's exit conditions."""
    hits: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        low = r["text_norm"].lower()
        for term in RESOLUTION_TERMS:
            if term in low:
                hits[term] += 1
                if len(examples[term]) < 3:
                    examples[term].append(r["text_norm"].replace("\n", " / ")[:90])

    short_replies = [
        r for r in rows if r["reply_to"] and len(r["text_norm"]) <= 25
    ]
    short_counter = Counter(r["text_norm"].strip().lower() for r in short_replies)

    out = ["## Resolution vocabulary", ""]
    out.append(f"{len(short_replies)} replies are 25 characters or shorter — these are")
    out.append("the terse status updates whose meaning lives entirely in the quote.")
    out.append("")
    out.append("| term | messages | example |")
    out.append("| --- | --- | --- |")
    for term, n in hits.most_common():
        ex = examples[term][0] if examples[term] else ""
        out.append(f"| {term} | {n} | {ex} |")
    out.append("")
    out.append("### Most common short replies verbatim")
    out.append("")
    out.append("| text | count |")
    out.append("| --- | --- |")
    for text, n in short_counter.most_common(30):
        out.append(f"| {text} | {n} |")
    out.append("")
    return out


def section_reply_chains(rows) -> list[str]:
    """Chain shape: how far a single target is tracked."""
    by_key = {(r["channel"], r["message_id"]): r for r in rows}
    parent = {
        (r["channel"], r["message_id"]): (r["channel"], r["reply_to"])
        for r in rows
        if r["reply_to"]
    }
    children: dict[tuple, list[tuple]] = defaultdict(list)
    for child, par in parent.items():
        children[par].append(child)

    roots = [k for k in by_key if k not in parent and k in children]

    def depth(node) -> int:
        best = 1
        for c in children.get(node, ()):
            best = max(best, 1 + depth(c))
        return best

    lengths = Counter()
    longest = None
    for root in roots:
        d = depth(root)
        lengths[d] += 1
        if longest is None or d > longest[0]:
            longest = (d, root)

    out = ["## Reply chains", ""]
    out.append(f"{len(parent)} replies form {len(roots)} chains.")
    out.append("")
    out.append("| chain length | chains |")
    out.append("| --- | --- |")
    for d, n in sorted(lengths.items()):
        out.append(f"| {d} | {n} |")
    out.append("")

    if longest:
        out.append(f"### Longest chain ({longest[0]} messages)")
        out.append("")
        node = longest[1]
        while node:
            r = by_key.get(node)
            if r is None:
                break
            out.append(
                f"- `{r['date_utc'][11:19]}` **{r['message_id']}** "
                f"{r['text_norm'].replace(chr(10), ' / ')[:110]}"
            )
            kids = children.get(node, [])
            node = min(kids, key=lambda k: k[1]) if kids else None
        out.append("")

    # Does a chain end in an explicit resolution?
    def terminal_nodes(root):
        stack, ends = [root], []
        while stack:
            n = stack.pop()
            kids = children.get(n, [])
            if kids:
                stack.extend(kids)
            else:
                ends.append(n)
        return ends

    resolved = unresolved = 0
    for root in roots:
        for end in terminal_nodes(root):
            r = by_key.get(end)
            if r is None:
                continue
            low = r["text_norm"].lower()
            if any(t in low for t in RESOLUTION_TERMS):
                resolved += 1
            else:
                unresolved += 1
    total = resolved + unresolved or 1
    out.append(
        f"Chain endings carrying an explicit resolution marker: "
        f"**{resolved}/{total} ({100 * resolved / total:.0f}%)**; "
        f"the rest simply stop."
    )
    out.append("")
    return out


def section_grammar(rows) -> list[str]:
    out = ["## Count and phase grammar", ""]
    out.append("| count form | messages | example |")
    out.append("| --- | --- | --- |")
    for name, pat in COUNT_PATTERNS:
        rx = re.compile(pat, re.IGNORECASE)
        hits = [r for r in rows if rx.search(r["text_norm"])]
        ex = hits[0]["text_norm"].replace("\n", " / ")[:70] if hits else ""
        out.append(f"| {name} | {len(hits)} | {ex} |")
    out.append("")

    for title, terms in (("Threat type", THREAT_TERMS), ("Phase", PHASE_TERMS)):
        counter = Counter()
        for r in rows:
            low = r["text_norm"].lower()
            for t in terms:
                if t in low:
                    counter[t] += 1
        out.append(f"### {title} vocabulary")
        out.append("")
        out.append("| term | messages |")
        out.append("| --- | --- |")
        for t, n in counter.most_common():
            out.append(f"| {t} | {n} |")
        out.append("")
    return out


def section_cross_channel(rows, window_s: int = 300, thresh: float = 0.5) -> list[str]:
    """How often the channels report the same event, and who is first."""
    sets = [
        (r, set(w.lower() for w in tokens(r["text_norm"]) if len(w) > 3)) for r in rows
    ]
    pairs = 0
    first_counter: Counter[str] = Counter()
    lags: list[float] = []
    examples: list[str] = []

    for i, (a, sa) in enumerate(sets):
        if not sa:
            continue
        for j in range(i + 1, len(sets)):
            b, sb = sets[j]
            if b["ts"] - a["ts"] > window_s:
                break
            if a["channel"] == b["channel"] or not sb:
                continue
            inter = len(sa & sb)
            if not inter:
                continue
            jac = inter / len(sa | sb)
            if jac >= thresh:
                pairs += 1
                first_counter[a["channel"]] += 1
                lags.append(b["ts"] - a["ts"])
                if len(examples) < 6:
                    examples.append(
                        f"`{a['channel']}` {a['text_norm'][:55]} → "
                        f"`{b['channel']}` (+{b['ts'] - a['ts']}s) {b['text_norm'][:55]}"
                    )

    out = ["## Cross-channel duplication", ""]
    out.append(
        f"Token-set Jaccard >= {thresh} within {window_s // 60} minutes: "
        f"**{pairs} duplicate pairs**."
    )
    out.append("")
    if lags:
        lags.sort()
        out.append(
            f"Lag between the two reports: median **{lags[len(lags) // 2]:.0f}s**, "
            f"p90 {lags[int(0.9 * len(lags))]:.0f}s, max {lags[-1]:.0f}s."
        )
        out.append("")
        out.append("| channel | times it reported first |")
        out.append("| --- | --- |")
        for ch, n in first_counter.most_common():
            out.append(f"| {ch} | {n} |")
        out.append("")
    if examples:
        out.append("### Examples")
        out.append("")
        for e in examples:
            out.append(f"- {e}")
        out.append("")
    return out


def section_rate(rows) -> list[str]:
    per_min: Counter[int] = Counter()
    per_hour: Counter[int] = Counter()
    for r in rows:
        per_min[r["ts"] // 60] += 1
        per_hour[
            datetime.fromtimestamp(r["ts"], tz=timezone.utc).hour
        ] += 1

    busiest = per_min.most_common(5)
    out = ["## Message rate", ""]
    out.append("| busiest minute (UTC) | messages |")
    out.append("| --- | --- |")
    for minute, n in busiest:
        stamp = datetime.fromtimestamp(minute * 60, tz=timezone.utc)
        out.append(f"| {stamp:%Y-%m-%d %H:%M} | {n} |")
    out.append("")
    out.append("Messages by hour of day (UTC):")
    out.append("")
    peak = max(per_hour.values()) or 1
    for h in range(24):
        n = per_hour.get(h, 0)
        bar = "#" * round(40 * n / peak)
        out.append(f"    {h:02d}  {bar} {n}")
    out.append("")
    return out


def build_report(rows) -> str:
    parts = [
        f"# Pattern mining report",
        "",
        f"{len(rows)} messages with text, "
        f"{rows[0]['date_utc'][:10]} .. {rows[-1]['date_utc'][:10]}.",
        "",
    ]
    for fn in (
        section_overview,
        section_toponyms,
        section_resolution,
        section_reply_chains,
        section_grammar,
        section_cross_channel,
        section_rate,
    ):
        parts += fn(rows)
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--out", default=str(REPO_ROOT / "data" / "patterns.md"))
    args = p.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = load(conn)
    conn.close()
    if not rows:
        print("No messages in the database.")
        return 1

    report = build_report(rows)
    Path(args.out).write_text(report, encoding="utf-8", newline="\n")
    print(f"Wrote {args.out} ({len(report.splitlines())} lines) from {len(rows)} messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
