# Next steps

Ordered by dependency. Item 1 is done; everything below it is not started.

## 1. History export — done

`tools/export/` reads `t.me/s/` and stores normalized messages in SQLite,
resumably and idempotently. See the README for usage and measured properties.

## 2. Pattern mining over the exported dataset

Before designing the label schema or the gazetteer, mine the corpus for
structure that can be exploited deterministically. The reply-chain pattern
(`Шахед над Позняками` → `Шахед над Голосієвом` → `Збито`) was found by eye in a
single 20-message page, which strongly suggests more is there.

Specifically worth counting:

- **Resolution vocabulary.** How does each channel close an episode? (`Збито`,
  `Відбій`, `Пішов далі`, `UPD: відбій`, `Знизив`.) A closed set here gives the
  state machine its exit conditions for free.
- **Reply-chain shape.** Chain length distribution, how often a chain crosses
  districts, how often it ends in an explicit resolution versus just stopping.
  Chains are candidate ground truth for target identity.
- **Count grammar.** `1х`, `2х`, `5-7`, `+ шахед`, `3 нові` — how many distinct
  forms express quantity, and how reliably.
- **Toponym inventory.** Every capitalized token that is not a known word,
  ranked by frequency. This *is* the gazetteer's raw material, including slang
  (`Солома`, `Троєща`, `Виноград`) and informal areas (`Соцмісто`,
  `Лісовий масив`, `Харківський масив`).
- **Threat-type vocabulary.** How ballistic, cruise, jet-powered drone, Shahed,
  and recon drone are each named, and how consistently.
- **Cross-channel duplicates.** Using `fingerprint` and a time window: how often
  do the three channels report the same event, and with what lag? This sizes the
  cross-channel dedup layer and reveals which channel is usually first.
- **Phase markers.** `пуск`, `курсом на`, `на підльоті`, `над`, `чути роботу`,
  `вибухи` — the phase axis of the classifier.
- **Message rate over time.** Messages per minute during known attacks, which
  sets the realtime poll and batching budget.

Output: a short findings note plus a first-cut gazetteer and phase/threat
vocabulary, both as data files the runtime and the eval harness share.

## 3. Label schema — fix before any labeling happens

The decision the system makes is *notify or not, at a moment in time*, so labels
are anchored to **moments, not messages**. A month is roughly 25-30 alert nights
× 3-6 decision points, i.e. 150-200 labels — a couple of evenings, not weeks.

Minimum fields: timestamp, notification level, threat type, geographic scope,
and a free-text "why". Changing the schema mid-labeling wastes the work, so it
gets written down and reviewed first.

## 4. Timeline labeler

A local page showing the merged feed as a scrollable timeline, click to insert a
label, export to JSON. Labeling a timeline in a spreadsheet is painful enough
that it would not get done.

## 5. Baseline without ML, then evaluate

Gazetteer + phase rules + the episode state machine, measured against the labels
from step 4. This produces the number that decides how much model is actually
needed, and for which parts. The headline metric is not accuracy but
**false wake-ups per night** — an app that wakes you twice for nothing gets
deleted in a week regardless of recall.

## 6. Model, by distillation

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
