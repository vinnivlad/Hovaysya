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
   first-class data. But only the ones needing judgement are labeled by hand —
   "was I glad to be woken", "would a second alert have annoyed me". Mechanical
   negatives are generated instead; see the negative set below.

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
| `level` | enum | if `notify` | `info` \| `alert` \| `shelter` — how insistent |
| `alarm` | enum | if `notify` | `ballistic` \| `mig` \| `cruise` \| `drone-jet` \| `drone` \| `recon` \| `none` — which sound |
| `silent_reason` | enum | if `silent` | why no notification was warranted |
| `threat` | enum | yes | what is flying |
| `modality` | enum | yes | live threat, aftermath, summary, or social |
| `scope` | enum | yes | how close it is to me |
| `certainty` | enum | yes | how well its position is known |
| `repeat_of` | string \| null | yes | id of the earlier label this repeats, or `null` |
| `evidence` | array | yes | the messages that justify this label |
| `why` | string | yes | one line, in your own words |
| `open_question` | string \| null | no | anything you were unsure about |
| `night` | string | yes | the night this belongs to, `YYYY-MM-DD` of the evening |
| `anchor` | string | yes | `channel/message_id` of the message the label was placed on |

`night` and `anchor` are written by the labeler. A night runs 15:00 to 15:00
Kyiv time so an attack spanning midnight stays in one night — peak traffic is
00:00-04:00 Kyiv, and splitting it would break the flow exactly where the work
is. `anchor` is a channel and id rather than a row index on purpose: indices
shift when the page is rebuilt over a different date range, which would silently
detach every stored label.

### `level` and `alarm` — two independent axes

Nine levels (3 loudness x 3 threat types) would be unlabelable: they blur into
each other and get applied inconsistently. So insistence and sound are separate.

**`level` — how insistent:**

| level | phone behaviour | use when |
| --- | --- | --- |
| `info` | silent; the persistent status notification updates only | something changed worth knowing, nothing to act on |
| `alert` | sound, wakes you, does not repeat | a real threat to the city that is not near you yet |
| `shelter` | loud, repeating, full-screen | act now — near you, or ballistic anywhere over Kyiv |

**`alarm` — which sound:** `ballistic` · `mig` · `cruise` · `drone-jet` · `drone` · `recon` · `none`

The point of separating sound from loudness is that **you should know what is
coming without opening your eyes.** Ballistic must not sound like a drone: woken
by the first, you get up immediately; by the second, you can look at the screen
first. That is the real difference in response, and it is not a difference of
volume.

On Android this is 6 sounds x 2 audible levels = 12 notification channels, plus
one silent channel for the persistent status. Volume is adjustable per channel,
so a barely-there recon tone and a maximum-volume ballistic tone are one setting
each.

Mapping from `threat` to `alarm`:

| threat | alarm |
| --- | --- |
| `ballistic` | `ballistic` |
| `mig` | `mig` |
| `cruise`, `kab` | `cruise` |
| `shahed-jet` | `drone-jet` |
| `shahed` | `drone` |
| `recon` | `recon` |
| `aviation` | `none` |
| `mixed` | the most severe class present |

Six sounds map one-to-one onto the six reaction classes, which is how the
labeler presents them, ordered by how little time each leaves:

**розвідник → МіГ-31К → дрон → реактивний дрон → ракета → балістика**

Each gets its own tone because each implies a different response. A recon drone
is information; a MiG-31K in the air means the whole country is alerted but the
launch may be an hour away, or may never come; a propeller Shahed leaves
minutes; a jet Shahed far less; ballistic none. Sharing a tone across those
would defeat the point of separate sounds, which is knowing what is coming
before opening your eyes.

### `mig` — a carrier, not a missile

A MiG-31K carries the Kinzhal, an aeroballistic missile it can release anywhere
along its route, so its takeoff alone triggers a country-wide alert. It also
sometimes lands without launching — the corpus has
`Борти МіГ-31К розвернулись на аеродром базування` about as often as it has a
launch. That combination — nationwide, uncertain, potentially ballistic — is
unlike anything else, which is why it is a class of its own.

Two consequences the implementation has to respect:

- **The carrier and the missile are two states, and that is deliberate.**
  `mig` while the aircraft is up, `ballistic` the moment a launch is mentioned —
  after which nothing about the aircraft matters. The takeoff boilerplate reads
  `МіГ-31К — носій аеробалістичної ракети`, which any ballistic pattern matches
  even though nothing is flying, so the carrier state has to win until a launch
  actually appears. Do not fold this into the ordered rule list to "simplify"
  it; the two-state transition is the behaviour that is wanted.
- **It is nationwide with no local geography.** A takeoff names a Russian
  airfield and no Ukrainian target, so the geographic filter alone would hide
  it. `hints.nationwide()` keeps `mig` and `ballistic` visible regardless of
  scope.

### `aviation` — deliberately no sound

Bombers taking off (Ту-95, Ту-160, Ту-22М3) trigger no alert. It happens long
before one, from airfields thousands of kilometres away, and the channels say so
themselves: `В повітрі є 2 бомбардувальники Ту-22М3, зараз прямої загрози немає`.
The alert arrives with the cruise missiles they launch, and those are already
their own class.

So `aviation` exists only so such a message can be typed while labeling the
moment `silent / insufficient` — "the app was right to wait". It maps to no
sound, because an audible channel for it would only train the user to ignore the
app.

Ballistic is always at least `shelter` city-wide: flight time is minutes, so
there is no room for geography.

### Impact reports — the question is not "is it about a hit"

`threat` means **what is flying at this moment**, so an impact report is labeled
by whether the wave is still running, not by the fact that something landed.
Two cases that read alike and mean the opposite:

**During a wave — the peak-danger moment, not `none`:**

```
💥Вибухи у Дніпрі, над містом чисто. / ⚠️Але на місто летить ще 1 реактивний шахед.
```

`вибух` messages sit a median of **1.8 minutes** from a live threat and 88% of
them arrive within ten minutes of one. The wave is usually still in progress,
often stated in the same message. `threat` is whatever is flying, and the
decision is frequently `notify` — this is exactly when someone should be in
shelter. Labeling it `none` would hide the most important moment of the night
from the evaluation.

**After the wave — genuinely `none`:**

```
У Голосіївському районі уламки БпЛА, пожежу ліквідовано
```

Consequence vocabulary sits **20-56 minutes** from a live threat. Nothing is
flying: `threat: none`, `modality: aftermath`, `decision: silent`.

So the question to ask is **"is anything still in the air?"** — and the channels
answer it themselves: `над містом чисто` versus `Але летить ще 1`.

**A third case: the bare impact report.** `Вибухи 💥💥💥`, `Чутно було вибух` —
no place, no type, and no word about whether anything remains. There the honest
label is `threat: unknown` and `certainty: lost`: something arrived, we do not
know what, and we do not know the current state.

Not `none`, and never `clear`. `none` would say nothing is flying and `clear`
would say it is safe, when in fact nobody has said either — and impact reports
sit 1.8 minutes from live danger. The decision itself is usually
`silent / already-notified` if this episode already woke you, or
`silent / insufficient` if it did not and there is still nothing to act on.

In practice you rarely label aftermath at all: it is in the generated negative
set, and your contribution there is five checks, once. When a post about fire
crews or casualties comes up, skip it.

### `silent_reason`

Only reasons that require **your judgement** are labeled by hand:

| value | meaning |
| --- | --- |
| `too-far` | real live threat, but not near enough to matter to me |
| `already-notified` | same episode, nothing escalated, no new wave |
| `resolved` | episode closed, area clear |
| `insufficient` | something is happening but the feed does not yet say enough |

`insufficient` distinguishes "the app was right to wait" from "the app missed
it", and those must not be scored the same way.

`aftermath` and `not-a-threat` are **not** hand-labeled — see the negative set
below. Whether a post describes consequences is a mechanical property of its
text, not a judgement about your situation, so spending your evenings on it
would be waste.

### `threat`

`recon` · `mig` · `shahed` · `shahed-jet` · `cruise` · `ballistic` · `kab` ·
`aviation` · `mixed` · `unknown` · `none`

The labeler's primary row is `none`, `recon`, `mig`, `shahed`, `shahed-jet`,
`cruise`, `ballistic` — ordered by how little time each leaves, starting from
nothing at all. `none` is there rather than behind the secondary row because
purely informational messages are the most common case in the corpus (4 148 of
11 609), and reaching for a collapsed row that often is friction. `kab`,
`aviation`, `mixed` and `unknown` stay secondary.

`shahed` and `shahed-jet` are separate on purpose. A jet-powered Shahed
(`реактивний`) is several times faster than a propeller one and appears in 1 511
messages — more than every ballistic term — so it is neither the slow case nor
the ballistic case.

`mixed` is for a combined attack where naming one type would misrepresent it.

### `modality`

`live-threat` · `aftermath` · `summary-news` · `non-threat`

Aftermath posts are the trap: they name districts and use alarming words
(`пожежа`, `постраждалі`, `уламки`) while carrying no live threat. `modality` is
assigned automatically for the negative set and is only set by hand when you are
labeling a moment for another reason and the classification looks wrong.

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
| `lost` | the state is unknown — tracked and lost (`локаційно втрачено`, `без фіксації`), or never known at all |
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

## The negative set — built, not labeled

The headline metric is false wake-ups, so inputs that must produce **no**
notification are as important as the ones that must. But most of them do not
need human judgement:

| class | how it is built | size |
| --- | --- | --- |
| `aftermath` | consequence-management vocabulary — `пожеж`, `рятувальн`, `ДСНС`, `постраждал`, `загинул`, `пошкодж`, `уламк`, `наслідк`, `ліквідовано`, official quotes | 56 district-naming messages |
| `other-region` | gazetteer resolves the location outside Kyiv and its oblast | ~2 515 messages |
| `not-a-threat` | auctions, donation links, thanks, politics, channel commentary | several hundred |

These are generated from the corpus and checked into `labels/negative.jsonl`
with the rule that produced each one, so any disagreement is inspectable.

The aftermath class is the dangerous one and the reason it is scored at all:

```
У Голосіївському районі фіксується загоряння автомобіля
внаслідок ворожої атаки. Пожежу ліквідовано.
```

A district name, "ворожої атаки", and "пожежа" — a geographic filter plus
keywords fires on this every time, and nothing is flying. It is a negative test
case in the ordinary sense: an input that looks like it should produce output and
must not.

**What you do contribute:** five aftermath moments, once, to confirm the
automatic classification agrees with your judgement. Not fifty-six, and never
again after that.

The boundary this rests on was measured, not assumed: consequence vocabulary
sits 20-56 minutes from the nearest live threat, while `вибух` and `влучання`
sit 1.8-2.2 minutes from it, and 88% of `вибух` messages arrive within ten
minutes of one. **Impact reports are not aftermath** and must never be vetoed.

## Worked examples

Real messages, from the night of 2026-08-27, at the reference location.

**A `shelter` label — a jet drone on a course to Zhuliany:**

```json
{
  "id": "2026-08-27T07:36-01",
  "at": "2026-08-27T07:36:00Z",
  "decision": "notify",
  "level": "shelter",
  "alarm": "drone",
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

**A `silent` label — a threat that stayed on the far side of the city:**

```json
{
  "id": "2026-08-27T10:24-01",
  "at": "2026-08-27T10:24:00Z",
  "decision": "silent",
  "silent_reason": "too-far",
  "threat": "shahed-jet",
  "modality": "live-threat",
  "scope": "city",
  "certainty": "confirmed",
  "repeat_of": null,
  "evidence": [{"channel": "mon1tor_ua", "message_id": 71204}],
  "why": "Academmistechko and Holosiiv — real and live, but the other side of the city from me. Status update at most."
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

For each night with an alert, place roughly **four to six** labels (a heavy
night like 2026-08-27 warrants more; a quiet one, one or two):

1. The first moment you would have wanted waking — and at what level.
2. Each subsequent wave or escalation, with `repeat_of` set.
3. The moment the episode closed for you.
4. **At least one `silent` label per night** — a threat that stayed on the far
   side of the city, a second report of an episode you were already woken for,
   or a moment where waiting was right. Aftermath posts are handled by the
   negative set; do not spend labels on them.

Around 25-30 alert nights in a month gives 120-180 labels: two evenings of
work, not weeks. Plus the one-off five aftermath checks.

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
