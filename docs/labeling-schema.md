# Labeling schema

Frozen before labeling starts. Changing it halfway invalidates the work done so
far, and labeling is the only part of this project that cannot be delegated.

## What a label is

The system's output is a **decision at a moment in time**: notify or not, and
how loudly. So labels attach to moments, not to messages.

A label answers one question:

> Given everything visible in the merged feed up to this timestamp, and my
> location, should the app have notified me — and at what level?

This has two consequences worth stating plainly:

1. **A single message is often unlabelable.** `Збито` means nothing without its
   quote; `Продовжує рух на Центр` means nothing without the preceding message.
   The moment carries the context, the message does not.
2. **Negative labels matter as much as positive ones.** The headline metric is
   false wake-ups per night, so moments where the app must stay silent are
   first-class data — especially aftermath posts that name your district.

## Storage

`labels/moments.jsonl` — one JSON object per line, appended in timestamp order.

This lives in `labels/`, **not** in `data/`. `data/` is git-ignored because it
holds re-derivable scraped content; labels are irreplaceable human judgement and
are committed and versioned.

JSONL rather than a single JSON array so the labeler can append without
rewriting, and so a diff shows exactly which labels changed.

## Fields

| field | type | required | meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable id, `YYYY-MM-DDTHH:MM-nn`. Never reused. |
| `at` | ISO 8601 UTC | yes | The decision moment. |
| `decision` | enum | yes | `notify` \| `silent` |
| `level` | enum | if `notify` | `info` \| `alert` \| `shelter` |
| `silent_reason` | enum | if `silent` | why no notification was warranted |
| `threat` | enum | yes | what is flying |
| `modality` | enum | yes | live threat, aftermath, summary, or social |
| `scope` | enum | yes | how close it is to me |
| `certainty` | enum | yes | how well its position is known |
| `repeat_of` | string \| null | yes | id of the earlier label this repeats, or `null` |
| `evidence` | array | yes | the messages that justify this label |
| `why` | string | yes | one line, in your own words |
| `open_question` | string \| null | no | anything you were unsure about |

### `level` — the notification ladder

Three levels, mapped to what the phone actually does. Deliberately few: more
levels sound precise but produce inconsistent labeling.

| level | phone behaviour | use when |
| --- | --- | --- |
| `info` | silent; the persistent status notification updates only | something changed worth knowing, nothing to act on — alert declared, all-clear, threat far away |
| `alert` | sound, wakes you, does not repeat | a real threat to the city that is not near you yet — the signal the official app collapses into one city-wide "increased danger" |
| `shelter` | loud, repeating, full-screen | act now — threat near you, or ballistic launched at Kyiv regardless of where in the city you are |

Ballistic is always at least `shelter` city-wide: flight time is minutes, so
there is no room for geography.

### `silent_reason`

| value | meaning |
| --- | --- |
| `aftermath` | describes consequences of a strike that already happened |
| `too-far` | real live threat, but not near enough to matter to me |
| `already-notified` | same episode, nothing escalated, no new wave |
| `not-a-threat` | news, summary, auction, thanks, politics |
| `resolved` | episode closed, area clear |
| `insufficient` | something is happening but the feed does not yet say enough |

`insufficient` is important: it distinguishes "the app was right to wait" from
"the app missed it", and those must not be scored the same way.

### `threat`

`shahed` · `shahed-jet` · `cruise` · `ballistic` · `kab` · `aviation` ·
`recon` · `mixed` · `unknown` · `none`

`shahed` and `shahed-jet` are separate on purpose. A jet-powered Shahed
(`реактивний`) is several times faster than a propeller one and appears in 1 511
messages — more than every ballistic term — so it is neither the slow case nor
the ballistic case.

`mixed` is for a combined attack where naming one type would misrepresent it.

### `modality`

`live-threat` · `aftermath` · `summary-news` · `non-threat`

Aftermath posts are the trap: they name districts and use alarming words
(`пожежа`, `постраждалі`, `уламки`) while carrying no live threat. They must be
labelable as such so the veto can be measured.

Note the boundary that measurement established: `вибух` and `влучання` are
**not** aftermath. They arrive a median of 1.8–2.2 minutes from live danger, and
88% of `вибух` messages land within ten minutes of a live threat. An explosion
report usually means the wave is still in progress.

### `scope`

| value | meaning |
| --- | --- |
| `my-area` | Zhuliany, or immediately adjacent — Teremky, Demiivka, Solomianka |
| `my-district` | Solomianskyi district generally |
| `city` | Kyiv, no district resolution given |
| `oblast` | Kyiv oblast, outside the city |
| `elsewhere` | another region entirely |
| `unknown` | a threat is stated with no usable location |

### `certainty`

| value | meaning |
| --- | --- |
| `confirmed` | position stated and current |
| `probable` | inferred from direction or a previous position |
| `lost` | was tracked, no longer is — `локаційно втрачено`, `без фіксації` |
| `clear` | actively reported clear — `чисто`, `збито` |

`lost` and `clear` must never collapse into one value. `Локаційно втрачено`
means *we no longer know*, which is not safety; treating it as safety would
silence the app at the worst possible time.

### `evidence`

```json
"evidence": [
  {"channel": "war_monitor",   "message_id": 43201},
  {"channel": "kievinform_ua1","message_id": 22981}
]
```

The messages that justify the label. The eval harness replays exactly the feed
visible at `at`, so evidence makes each label auditable and lets a
disagreement be examined rather than argued about.

### `repeat_of`

Set when this is a *repeat* notification during an alert that is already
running — the second ballistic wave, a new group after a lull. This is the field
that encodes the original complaint that repeat signals either never arrive or
arrive unpredictably. `null` for the first notification of an episode.

## Worked examples

Real messages, from the night of 2026-08-27, at the reference location.

**A `shelter` label — a jet drone on a course to Zhuliany:**

```json
{
  "id": "2026-08-27T07:36-01",
  "at": "2026-08-27T07:36:00Z",
  "decision": "notify",
  "level": "shelter",
  "threat": "shahed-jet",
  "modality": "live-threat",
  "scope": "my-area",
  "certainty": "confirmed",
  "repeat_of": "2026-08-27T07:02-01",
  "evidence": [
    {"channel": "kievinform_ua1", "message_id": 22981},
    {"channel": "war_monitor", "message_id": 43210}
  ],
  "why": "Named course onto Zhuliany, jet-powered so minutes not tens of minutes. Third approach of the morning, so a repeat is warranted.",
  "open_question": "Does 'Жуляни ✈️' mean the airport specifically or aviation overhead? Treated as the airport here."
}
```

**A `silent` label — aftermath naming a district:**

```json
{
  "id": "2026-08-27T09:14-01",
  "at": "2026-08-27T09:14:00Z",
  "decision": "silent",
  "silent_reason": "aftermath",
  "threat": "shahed",
  "modality": "aftermath",
  "scope": "my-district",
  "certainty": "clear",
  "repeat_of": null,
  "evidence": [{"channel": "kievinform_ua1", "message_id": 22994}],
  "why": "Debris removal and damage assessment in Holosiiv. Names a district and reads alarming, but nothing is flying. This is the false-wake-up case."
}
```

**A `silent` label — the app was right to wait:**

```json
{
  "id": "2026-08-27T07:02-02",
  "at": "2026-08-27T07:02:30Z",
  "decision": "silent",
  "silent_reason": "insufficient",
  "threat": "unknown",
  "modality": "live-threat",
  "scope": "city",
  "certainty": "probable",
  "repeat_of": null,
  "evidence": [{"channel": "war_monitor", "message_id": 43201}],
  "why": "One target over Kyiv with no direction yet. Not enough to wake me; the direction arrived a minute later."
}
```

## How to label

Work night by night, not message by message.

For each night with an alert, place roughly **three to six** labels:

1. The first moment you would have wanted waking — and at what level.
2. Each subsequent wave or escalation, with `repeat_of` set.
3. The moment the episode closed for you.
4. **At least one `silent` label per night**, ideally an aftermath post or a
   threat that stayed on the far side of the city.

Around 25–30 alert nights in a month gives 150–200 labels: two evenings of
work, not weeks.

Two rules that keep the data honest:

- **Label from the feed, not from memory.** If the feed at that moment does not
  support the label, that is itself the finding — the app could not have known
  either.
- **When torn, write it in `open_question` and pick anyway.** An unlabeled
  moment teaches nothing; a labeled one with a recorded doubt teaches twice.

## How the harness scores this

- A predicted notification counts as a **hit** when it lands within the
  tolerance window of a `notify` label at the same level or higher.
  Tolerance: **±3 minutes** for `shelter`, **±10 minutes** for `alert`.
- A notification with no `notify` label nearby, or one landing on a `silent`
  label, is a **false wake-up**. This is the number that matters.
- A `notify` label with no prediction nearby is a **miss**.
- Predictions at `insufficient` moments are scored separately and reported, not
  counted as false wake-ups — waiting for more information is a legitimate
  behaviour, and the report should show how often it happens.

Reported per night, not aggregated: a single terrible night matters more than a
good average, because that is the night you stop trusting the app.
