# Next steps

Ordered by dependency. Stages 1-6 are done. **Nothing runs live yet** — that is
the whole of what stage 7 is about.

Visual status board: <https://claude.ai/code/artifact/a7a19c52-e4c8-4bad-9bf8-1c480dd8434c>

## 1. History export — done

`tools/export/` reads `t.me/s/` and stores normalized messages in SQLite,
resumably and idempotently. See the README for usage and measured properties.

## 2. Pattern mining over the exported dataset — done

Results in [pattern-findings.md](pattern-findings.md); regenerate with
`python -m tools.analysis.patterns`. It overturned four assumptions: live threat
is recognised by sentence shape rather than alarm words, jet Shaheds need their
own class, reply chains are weaker evidence than they looked, and outcome
vocabulary splits into a safe veto tier and an unsafe one.

## 3. Label schema — done

Frozen in [labeling-schema.md](labeling-schema.md). Labels land in
`labels/moments.jsonl`, which is committed — unlike `data/`, human judgement is
not re-derivable.

What it settles:

The decision the system makes is *notify or not, at a moment in time*, so labels
are anchored to **moments, not messages**. A month is roughly 25-30 alert nights
× 3-6 decision points, i.e. 150-200 labels — a couple of evenings, not weeks.

Minimum fields: timestamp, notification level, threat type, geographic scope,
and a free-text "why". Changing the schema mid-labeling wastes the work, so it
gets written down and reviewed first.

The findings add required dimensions the first draft lacked:

- **modality** — `live-threat` / `aftermath` / `summary-news` / `non-threat`.
  Aftermath posts name districts and use alarming words while carrying no
  threat, so they must be labelable as such.
- **threat type** must separate `shahed` from `shahed-jet`.
- **certainty** — `clear` and `unknown` are different outcomes
  (`чисто` versus `локаційно втрачено`), and conflating them is unsafe.
- **the ✈️ question** — whether `Жуляни ✈️` means the airport or aviation
  overhead is something only the user can settle, so the schema needs a place
  to record it.

## 4. Timeline labeler — done

`python -m tools.labeler.build` writes a self-contained page: the merged feed as
a scrollable timeline, keyboard navigation, click a moment to label it, export
JSONL. Every message arrives pre-filled from `tools/nlp/`, and the same module
runs in the stage-6 baseline — so a correction made while labeling is also a
signal about the baseline.

## 5. Labeling pass — done, twice

458 labels across two nights: 2026-08-04 densely (334, every post) and
2026-08-26 sparsely (124). Drop a fresh export into `labels/` and it counts —
each file is a complete snapshot and the newest one per night wins, see
`labels/README.md`.

The dense night is what made the baseline arguable. It opened at 11 false
wake-ups and 7 misses where the sparse set had shown 2 and 0.

Four questions the labels raised and could not settle, all recorded with their
measurements in [pattern-findings.md](pattern-findings.md):

- a repeat ballistic alert over the ring — settled by a sentence from him, not a
  threshold: "якщо був пуск балістики... я і так не сплю"
- drone waves — the channels' own roll-call count is the only signal that
  separates them, and no time threshold exists
- Крюківщина — one wake-up against one "далеко"
- a propeller Shahed near home never woke him, 0 of 5. Left as is on his
  instruction.

## 6. Baseline without ML — done

`tools/policy/` plus `tools/eval/`. Replay a whole night, score against the
labels, headline metric false wake-ups.

    2026-08-04   4 false wake-ups, 2 misses, 15 hits   (334 labels of 465 messages)
    2026-08-26   2 false wake-ups, 3 misses, 19 hits   (124 labels of 544)

From 20 false wake-ups at the first run. `tools/policy/announce.py` turns each
decision into a queued Ukrainian sentence — his design, see the schema doc.

Two of the six remaining false wake-ups are the same thing and cannot be fixed
from the chats: an all-clear for another district reads as ours. That is what the
alert API token is for.

## 6. Baseline without ML, then evaluate

Gazetteer + phase rules + the episode state machine, measured against the labels
from step 4. Build order follows the findings: geographic pre-filter (removes
55.7% of traffic, measured), then the structural templates from §3, then the two-tier veto,
then episode closure. Adjacency can start from co-mention statistics rather than
polygons. This produces the number that decides how much model is actually
needed, and for which parts. The headline metric is not accuracy but
**false wake-ups per night** — an app that wakes you twice for nothing gets
deleted in a week regardless of recall.

## 7. Make it run — in progress

`python -m tools.live.run` — see [running-overnight.md](running-overnight.md) for
the Windows settings that stop the machine sleeping.

Everything above is a batch tool. The next stage is the smallest thing that
turns it into a system that is actually watching:

1. a poll loop over `t.me/s/<channel>?after=<id>` — measured at ~5 KB per poll,
   so once every 20-30 s during an alert and rarely otherwise
2. feed each new message through `observe` -> `decide` -> `announce`
3. print the utterance queue, and log every decision with its reason

No server, no phone, no account. Run it on the laptop through one real night and
compare what it says against what he would have wanted — which is his own test
of the concept: "подивимося чи взагалі працює цей концепт". The log of that night
is also the next labelling pass, already aligned to real decisions.

Only after that does the Android client have anything to deliver.

## 8. Model, by distillation

Label a large historical sample with an LLM once, fine-tune a small multilingual
classifier on those labels, deploy the small model. The user's own labels stay
as the test set and are never mixed into training — LLM labels train, human
labels judge.

## Adding a channel

Two steps, and skipping the second costs a blind spot. He caught it within
minutes: the new channel had named Zhuliany at 18:32 and the app said nothing.

1. `tools/export/config.py` — add the username to `CHANNELS`.
2. **Backfill it**: `python -m tools.export.export --channel <name> --since ...`

Without the backfill a new channel starts blind. `resume_id` is 0, so the watcher
takes `newest_id` and begins there rather than replaying the whole history — which
is right for a cold start and wrong for a new source, because the 90-minute
warm-up then has nothing in the database to warm from either. The channel is
watched from the restart forward and everything before it is invisible.

Before adding one at all, measure it. `KyivPolitic`, `kyivalarm`, `kyivnow` and
`monitoring_kyiv` were each exported into a scratch copy of the database and
scored on one question — **how often is it first to name the near ring, against
the channels already in place** — see docs/pattern-findings.md. Three of the four
were left out on the numbers.

## Deferred, with the trigger that un-defers them

| Item | Deferred until |
| --- | --- |
| ~~Alert API token~~ | **Not needed.** He found the official app's Telegram bot, and `alarm_kyiv` relays it: two forms, city only, `🚨 м. Київ / Повітряна тривога` and `🟢 м. Київ / Відбій`. Читається через `t.me/s/` без жодних облікових даних, історія з 2024-01-08. Checked against the official app to the second. |
| Oracle Cloud account | production deployment; see `oracle-cloud-setup.md` |
| Phone number + MTProto | polling latency or invisible edits become a real problem |
| Android client | after stage 7 shows the decisions are worth pushing |
