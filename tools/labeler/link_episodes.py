"""Fill in episode links, and report where a label's reason contradicts its note.

Two jobs, kept apart on purpose.

**Mechanical**: `silent / already-notified` is a claim about an episode — "this
is the same thing that already woke me" — so the episode it refers to is the
most recent wake-up before it that night. That is derivable, and it was left
empty across a whole night of real labelling because the form only offered the
field on `notify` labels.

**Judgement**: the free-text `why` sometimes says something different from the
chosen `silent_reason`. "не в мою сторону летить" is `too-far`, not
`already-notified`. Those are reported, never rewritten — the note might be
loose while the label is right, and only the labeller knows which.

Usage:
    python -m tools.labeler.link_episodes            # report only
    python -m tools.labeler.link_episodes --apply    # write the links
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = REPO_ROOT / "labels"

# Reasons that are inherently about an episode.
EPISODE_REASONS = {"already-notified", "resolved"}

# Beyond this, "вже будив" stops being a statement about the same episode. A
# real link spanned 2.5 hours before this bound existed, which would have
# fabricated an episode joining two separate waves.
MAX_EPISODE_GAP_S = 60 * 60

ALARM_FOR_THREAT = {
    "recon": "recon", "mig": "mig", "shahed": "drone",
    "shahed-jet": "drone-jet", "drone-rocket": "drone-jet",
    "cruise": "cruise", "kab": "cruise",
    "ballistic": "ballistic", "aviation": "none", "mixed": "ballistic",
    "unknown": "drone", "none": "none",
}


def _ts(label: dict) -> float:
    return datetime.fromisoformat(label["at"].replace("Z", "+00:00")).timestamp()

# Phrases in `why` that point at a different reason than the one chosen.
CONTRADICTIONS = {
    "too-far": ("не в мою сторону", "не до мене", "інший район", "не моя зона",
                "далеко", "інша область", "не в мою"),
    "already-notified": ("ті самі", "той самий", "та сама", "уточнення",
                         "вже будив", "летять ті самі", "тої самої"),
    "insufficient": ("ще не зрозуміло", "ще рано", "не відомо", "роздуми",
                     "просто інформація", "загальний огляд"),
}

# Notes that argue for waking him, whatever the decision says. In 458 labels
# every «близько» was a wake-up except one, and the one was a slip: the note
# said «Близько» and the policy fired there while the label stayed silent.
WAKE_WORDS = ("близьк", "треба повідом", "треба буди", "дзвони", "прям близ")


def load(path: Path) -> list[dict]:
    if path.is_dir():
        from .load import load_all
        return load_all(path)[0]
    from .load import read_file
    return read_file(path)


def by_night(labels: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for l in labels:
        groups[l.get("night", "?")].append(l)
    for group in groups.values():
        group.sort(key=lambda l: l.get("at", ""))
    return groups


# Where the reason is not the labeller's to get wrong, the note cannot contradict
# it. Two such cases, both matching the order the policy actually decides in:
#
# - Geography outranks episode reasoning. `too-far` on a message about another
#   region is decided by the message alone, with no state at all — rule 4 fires
#   before any novelty rule. "не в мою сторону" is then a restatement of the
#   reason, not a disagreement with it.
# - A mechanically silent modality decides before any reason is consulted, so
#   whichever of the four was picked is moot. Flagging those trains the eye to
#   ignore the report.
GEOGRAPHY_DECIDES = {"elsewhere", "oblast"}
MECHANICALLY_SILENT = {"aftermath", "summary-news", "non-threat"}


def reason_is_moot(label: dict) -> bool:
    """Whether the chosen reason is not a judgement the note could contradict."""
    if label.get("modality") in MECHANICALLY_SILENT:
        return True
    return (label.get("silent_reason") == "too-far"
            and label.get("scope") in GEOGRAPHY_DECIDES)


def link(labels: list[dict]) -> tuple[list[tuple[str, str]], list[tuple[str, str, int]]]:
    """Fill episode links in place.

    Returns (filled, too_distant): links written, and links declined because the
    gap makes "the same episode" implausible — those need a human.
    """
    filled: list[tuple[str, str]] = []
    distant: list[tuple[str, str, int]] = []
    for group in by_night(labels).values():
        last_notify: dict | None = None
        for l in group:
            if l.get("decision") == "notify":
                # An all-clear ends the episode rather than continuing it.
                last_notify = None if l.get("alarm") == "clear" else l
                continue
            if l.get("silent_reason") in EPISODE_REASONS and not l.get("repeat_of"):
                if not last_notify or reason_is_moot(l):
                    # Nothing to link when the reason is not what silenced it.
                    # "Тривога триватиме ще 2 години" is commentary; it was
                    # filed as `already-notified` because none of the four fit,
                    # and asking which episode it repeats has no answer.
                    continue
                gap = int(_ts(l) - _ts(last_notify))
                if gap > MAX_EPISODE_GAP_S:
                    distant.append((l["id"], last_notify["id"], gap))
                    continue
                l["repeat_of"] = last_notify["id"]
                filled.append((l["id"], last_notify["id"]))
    return filled, distant


def fill_alarms(labels: list[dict]) -> list[tuple[str, str]]:
    """A notify with no alarm cannot fire on any channel. Derive it."""
    fixed = []
    for l in labels:
        if l.get("decision") == "notify" and not l.get("alarm"):
            alarm = ALARM_FOR_THREAT.get(l.get("threat"), "drone")
            l["alarm"] = alarm
            fixed.append((l.get("id", "?"), alarm))
    return fixed


def notes_arguing_for_a_wake_up(labels: list[dict]) -> list[tuple[str, str]]:
    """Silent labels whose own note says he should have been woken."""
    out = []
    for l in labels:
        if l.get("decision") != "silent":
            continue
        why = (l.get("why") or "").lower()
        if any(w in why for w in WAKE_WORDS):
            out.append((l.get("id", "?"), l.get("why", "")))
    return out


def contradictions(labels: list[dict]) -> list[tuple[str, str, str, str]]:
    """(label id, chosen reason, suggested reason, why) where the note disagrees."""
    out = []
    for l in labels:
        if l.get("decision") != "silent":
            continue
        if reason_is_moot(l):
            continue
        why = (l.get("why") or "").strip().lower()
        if not why:
            continue
        chosen = l.get("silent_reason")
        for reason, phrases in CONTRADICTIONS.items():
            if reason == chosen:
                continue
            if any(p in why for p in phrases):
                out.append((l.get("id", "?"), chosen, reason, l.get("why", "")))
                break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--labels", default=str(LABELS_PATH))
    ap.add_argument("--apply", action="store_true", help="Write the episode links.")
    args = ap.parse_args(argv)

    path = Path(args.labels)
    if not path.exists():
        print(f"No labels at {path}.")
        return 0

    labels = load(path)
    filled, distant = link(labels)
    alarms = fill_alarms(labels)
    clashes = contradictions(labels)

    print(f"{len(labels)} labels")
    print(f"  episode links to fill: {len(filled)}")
    if filled:
        for lid, target in filled[:6]:
            print(f"    {lid}  ->  {target}")
        if len(filled) > 6:
            print(f"    ... and {len(filled) - 6} more")
    if alarms:
        print(f"  missing alarms derived from the threat: {len(alarms)}")
        for lid, alarm in alarms:
            print(f"    {lid}  ->  {alarm}")
    print()

    if distant:
        print(f"Episode link declined — gap too large  ({len(distant)})")
        print("  \"вже будив\" across more than an hour is a different wave, not")
        print("  the same episode. Set these by hand, or leave them unlinked.")
        for lid, target, gap in distant:
            print(f"    {lid:<22} nearest wake-up {target} was {gap // 60} min earlier")
        print()

    wakes = notes_arguing_for_a_wake_up(labels)
    if wakes:
        print(f"Silent, but the note argues for waking  ({len(wakes)})")
        for lid, why in wakes:
            print(f"  {lid:<22} «{why}»")
        print()

    if clashes:
        print(f"Reason disagrees with the note  ({len(clashes)}) — not rewritten")
        for lid, chosen, suggested, why in clashes:
            print(f"  {lid:<22} {chosen} -> {suggested}?   «{why}»")
        print()

    if args.apply:
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for l in sorted(labels, key=lambda x: x.get("at", "")):
                fh.write(json.dumps(l, ensure_ascii=False) + "\n")
        print(f"Wrote {len(filled)} episode links to {path}.")
    elif filled or alarms:
        print("Re-run with --apply to write the changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
