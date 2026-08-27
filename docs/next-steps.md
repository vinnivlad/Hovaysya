# Next steps

Ordered by dependency. Stages 1-4 are done; stage 5 is yours.

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

## 5. Your labeling pass — next

Open `data/labeler.html`, work night by night, export, save over
`labels/moments.jsonl`. Filter defaults to "near me", which is what makes a
76-message hour scannable.

## 6. Baseline without ML, then evaluate

Gazetteer + phase rules + the episode state machine, measured against the labels
from step 4. Build order follows the findings: geographic pre-filter (removes
55.7% of traffic, measured), then the structural templates from §3, then the two-tier veto,
then episode closure. Adjacency can start from co-mention statistics rather than
polygons. This produces the number that decides how much model is actually
needed, and for which parts. The headline metric is not accuracy but
**false wake-ups per night** — an app that wakes you twice for nothing gets
deleted in a week regardless of recall.

## 7. Model, by distillation

Label a large historical sample with an LLM once, fine-tune a small multilingual
classifier on those labels, deploy the small model. The user's own labels stay
as the test set and are never mixed into training — LLM labels train, human
labels judge.

## Deferred, with the trigger that un-defers them

| Item | Deferred until |
| --- | --- |
| Alert API token (`alerts.in.ua` / `api.ukrainealarm.com`) | needed for the realtime gate and for retrospective ground truth — can be requested at any time |
| Oracle Cloud account | production deployment; see `oracle-cloud-setup.md` |
| Phone number + MTProto | polling latency or invisible edits become a real problem |
| Android client | after the baseline produces decisions worth pushing |
