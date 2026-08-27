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
| `alarm` | enum | if `notify` | `alert` \| `ballistic` \| `mig` \| `cruise` \| `drone-jet` \| `drone` \| `recon` \| `clear` \| `none` — which sound |
| `silent_reason` | enum | if `silent` | why no notification was warranted |
| `threat` | enum | yes | what is flying |
| `modality` | enum | yes | live threat, aftermath, summary, or social |
| `scope` | enum | yes | how close it is to me |
| `certainty` | enum | yes | how well its position is known |
| `heading` | enum | yes | which way it is going, relative to me |
| `cleared` | enum \| null | no | which class a partial all-clear lifts |
| `repeat_of` | string \| null | yes | the earlier label whose episode this one continues or closes, or `null` |
| `evidence` | array | yes | the messages that justify this label |
| `why` | string | for `notify` | one line, in your own words |
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

**`level` — audible or not:**

| level | phone behaviour | use when |
| --- | --- | --- |
| `info` | silent; the persistent status notification updates only | something changed worth knowing, nothing to act on |
| `alert` | sound — and the tone says what to do | anything worth waking for |

There were three levels at first, with `shelter` for "loud, repeating, full
screen". It was dropped after the first labelled night, where it was used three
times out of twenty-three and every one was ballistic — it was saying what the
ballistic tone already said.

**Insistence is now a property of the tone, not a separate axis.** The ballistic
tone repeats and takes the screen; the drone tone rings once; the recon tone is
barely there. In the user's words: "у нас же різні звуки на різні загрози, цього
достатньо" — the sound tells you what to do, so a second axis for how urgently
only adds a way to disagree with it.

Why `shelter` existed at all is the same reason it is not needed: "я там поставив
шелтер бо на балістику ховатись треба завжди і зразу". That is now the definition
of the ballistic tone rather than a level layered on top of it, and it fixes two
rules in the policy:

- **Ballistic always notifies audibly, immediately, and city-wide.** No
  proximity qualification — flight time is minutes, so there is no room for
  geography. Only a target stated in another region takes it out of scope.
- **The ballistic tone is never used for anything else.** If it sounds, hiding is
  the correct response every time, which is only true if nothing quieter borrows
  it.

**`alarm` — which sound:** `alert` · `ballistic` · `mig` · `cruise` · `drone-jet` · `drone` · `recon` · `clear-partial` · `clear` · `none`

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

### When a new sound fires — and when it must not

From labelling a real sequence, 2026-08-27 20:55-20:56:

```
20:55  ⚠️❗️КИЇВ - ТРИВОГА. В укриття!                      alert sound, type unknown
20:56  ❗️❗❗Загроза пуску балістичних ракет з Курської      NO new sound
20:56  ❗️❗Є інформація про пуск балістичної ракети         new sound: ballistic
```

The middle message is the one that matters. It warns that a launch *may* happen;
nothing is in the air. Re-alarming there spends the user's attention on an
anticipation, and the sound that should mean "ballistic is coming" gets worn out
before it is true.

The rule this gives:

> **A new sound fires when the threat class changes and the new information is
> confirmed.** An anticipatory warning updates the status and does not re-alarm.

No new field is needed — `certainty` already carries it. `загроза пуску` is
`probable`, `є інформація про пуск` is `confirmed`. The implementation
consequence is that `загроза\s+(пуску|застосування)` must be detected *before*
any other certainty rule, because the phrase contains the same words an actual
launch does.

This is also the precise form of the original complaint about repeat signals:
not "notify more often", but "notify again exactly when something new and real
happens".

### `alert` — the sound of a declaration with no type yet

`КИЇВ - ТРИВОГА. В укриття!` states that something is coming without saying
what. It must be audible, and it must not borrow a threat tone: sounding like a
drone when nobody said drone is how the tones stop meaning anything. So a siren
declaration gets its own generic `alert` tone, and the labeler pre-fills it.

### `clear` — the all-clear is a notification too

Knowing the alert ended matters as much as knowing it began: after taking
shelter you need to be told you can come out. The all-clear has its own sound —
calm and unmistakable, nothing like a threat tone — and the labeler pre-fills a
`clear` alert-state message as `notify / alert / clear`.

**It is unconditional, and that follows from a policy rule worth stating
outright: an alert declaration always notifies.** So by the time an all-clear
arrives, the user has already been woken by the declaration; there is no case
where the all-clear is the thing that disturbs them.

An earlier draft of this section made the all-clear's level conditional on
whether the episode had produced a notification, which would have required the
labeler to track episode state. The premise above removes the case entirely, and
with it that complexity.

The two siren messages are therefore both audible: the declaration because it
needs a reaction, the all-clear because coming out of shelter needs one too.

### `clear-partial` — one class lifted, the alert continuing

`⚪️ Відбій загрози МіГ-31К` and `⚪️По балістиці відбій` say one threat is over
while the siren still runs. The user asked to be told: "якщо відомо що відбій по
мігам чи балістиці — висилати повідомлення". They are audible.

They have **their own tone**, at his instruction — "повний відбій звучить по
іншому". Hearing "you can come out" when only one class was lifted would be
worse than hearing nothing, so the two cannot share a sound.

They also do not close the episode, which is what makes the distinction matter:
everything the night established stays in place.

**Which class was lifted goes in `cleared`, not in `threat`.** `threat` means
what is in the air, and the whole point of a partial clear is that this class no
longer is — so putting it there would have the message announcing a MiG is up in
the very sentence saying it is not. For the same reason a pure partial clear
reports `threat: none`.

Nothing has to be typed: the class named next to the all-clear word is the one
being lifted, which is the same positional reading that finds what is *still*
flying. The labeler pre-fills it and shows a "по чому відбій" row so it can be
corrected.

The tracker keeps the set of lifted classes on the open episode, and drops one
as soon as that class is named flying again. That set is what the persistent
status notification needs in order to answer the thing the user actually asked
for — "було б гарно знати що нема загрози балістики чи мігів".

`war_monitor` is where most of these come from — 12 to 33 a month against
almost no declarations. For the policy that makes it the more informative
channel of the two: a general all-clear says the siren stopped, a partial one
says *what* ended.

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

**When two of them are both true, the one that needs no state wins.** A message
about another city is often *also* a continuation of the wave that already woke
you — "☄ Балістика на Кременчук" during a Kyiv alert is both `too-far` and
`already-notified`. Pick `too-far`: it is decided by the message alone, it is the
order the policy actually decides in (geography is rule 4, novelty is rule 6),
and labelling it `already-notified` would credit the episode state for silence
that the geographic filter produces on its own — hiding the fact that a filter
dropping 55.7% of all traffic is doing the work.

Near you the precedence reverses, because geography no longer decides anything.
A drone announced over your district and then reported drifting away is
`already-notified`: the first message woke you and nothing new happened. That is
the case where `already-notified` is the whole answer.

`aftermath` and `not-a-threat` are **not** hand-labeled — see the negative set
below. Whether a post describes consequences is a mechanical property of its
text, not a judgement about your situation, so spending your evenings on it
would be waste.

### `threat`

`recon` · `mig` · `shahed` · `shahed-jet` · `cruise` · `ballistic` · `kab` ·
`aviation` · `mixed` · `unknown` · `none`

The labeler's primary row is `none`, `unknown`, `recon`, `mig`, `shahed`,
`shahed-jet`, `cruise`, `ballistic`. `kab`, `aviation` and `mixed` stay
secondary.

The two "no type stated" cases lead, because they are the most common and
because confusing them is the easiest mistake available:

| | meaning | example |
| --- | --- | --- |
| `none` | nothing is flying | aftermath, a summary, channel commentary |
| `unknown` | something is, and nobody said what | a bare `Тривога`, a bare `Вибухи` |

Both were behind the collapsed secondary row at first, which is why they were
hard to find — the same friction, twice. `none` alone accounts for 4 148 of the
corpus's 11 609 messages.

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

### `heading` — position is not enough

| value | meaning |
| --- | --- |
| `toward` | a destination in my ring is stated |
| `away` | it was in my ring and the stated destination is not |
| `loitering` | circling near me, no direction given |
| `position` | named near me, nothing said about direction |
| `unknown` | not about my area at all |

This axis exists because two labels on the same place looked like a
contradiction and were not. From the user, after a night of labelling:

> якщо видно, що воно летить з Крюківщини в мою сторону — то краще б
> зреагувати, а якщо просто літає в тій стороні, то і не обов'язково, якщо то
> дрон

```
🅿️ 1х реактив на Крюківщину / Борщагівки.   toward     → woke him
Крюківщина                                   position   → he marked it far
```

Same threat, same place, same certainty — different answer, because a drone
*heading into* the ring and a drone merely *in* it are different decisions. The
reviewer's split-decision check would have flagged that pair as an
inconsistency; it is now part of the signature instead, which is what the
reviewer's own note anticipated: a split means either a label is off or the
policy needs a distinction the signature does not carry.

**This is parsing, not inference.** The channels state direction outright — 146
`з A на B` statements in the corpus — and the marker before a place name says
which role it plays: `курсом на`, `в сторону`, `у бік`, `далі` mark a
destination; `з`, `від`, `повз` mark an origin; `кружляє`, `намотує`,
`довкола` mark loitering. `Жуляни далі Центр` needs one extra rule — the first
place is the implicit origin — and that is the whole of it.

Inference earns its place only where direction has to be recovered from a
sequence of positions, and even there the reply chains supply most of it.

**And it is narrow.** Measured against the first night's 124 labels, `heading`
explains far less than expected: only 6 labels are `toward` and 16 `position`,
against 99 `unknown` — because most of the night was ballistic traffic about
other regions and city-wide alerts that name the ring not at all. Over the whole
corpus, `toward` is 1.0% of messages.

What the same check did reveal is the axis that actually drives the decision:

- Every `toward` label that stayed silent is `already-notified`. The heading was
  right; the episode logic is what silenced it.
- Every `position` label that woke him says the same thing in the note —
  "новий дрон", "ще один дрон", "виліз поруч з районом".

So the decision is **proximity x novelty**, and direction only refines it. A new
target near the ring wakes him with no stated course; a target heading toward
him that already woke him does not wake him again. `already-notified` carries 78
of the 101 silent labels.

That is the original complaint about repeat signals, restated from data: the
thing to build first is episode and novelty tracking, not geometry.

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

## Alert declarations and all-clears are never hidden

The siren is the frame of the night: without it there is no telling when a
threat passed. These messages routinely name no place at all —
`Відбій, усім солодких снів та тихої ночі💕` — so the geographic filter dropped
them, hiding **245 of the corpus's 658** alert-state messages, including exactly
the ones that close an episode.

They now pass every filter unless they resolve to another region, and render
with their own colour: red for a declaration, teal for an all-clear.

Treating a place-less one as local is not a guess. Measured over the corpus,
of 323 scope-less alert messages **68.4% come from `kievinform_ua1`**, the
Kyiv-focused channel, 28.2% from `war_monitor`, and only 3.4% from
`mon1tor_ua` — which covers all of Ukraine but names the region when it means
another one. Only **10** alert messages in 4.5 months name a region explicitly
other than Kyiv's, so the cost of showing the unaddressed ones is negligible and
the cost of hiding them was the episode-closing signal.

An all-clear is detected before a declaration, because `Відбій тривоги` contains
both words and reading it as a declaration would invert the meaning.

**This is a proxy, not the real thing.** The authoritative alert timeline comes
from the official API (`alerts.in.ua` / `api.ukrainealarm.com`), which is free
and listed as a stage-8 dependency. Labeling would be easier with it now: the
frame would be exact rather than inferred from channel chatter.

## Why a moment is picked by clicking a message

Labels are moments, so it is fair to ask why the labeler makes you click a
message rather than a point on a clock.

Because the app never decides at an arbitrary instant — it has nothing to decide
from. It wakes when new data arrives, so the set of possible decision moments
*is* the set of message arrival times. Clicking a message means "at the instant
this arrived, the app should have…", and `anchor` records which arrival, not
which post is being judged.

Allowing a free-floating time would invent a coordinate no system could ever
satisfy, because at that instant the feed held nothing new. The one meaningful
case — "I should have been woken at 02:30 and the channels only said it at
02:34" — is a finding about the data source rather than a label; put it in
`open_question`.

The interface has to carry that distinction, because the opposite reading
produces bad labels: it is what makes a bare `Вибухи` look like `threat: none`.
So a saved label draws as a bar **between** rows rather than a badge inside one,
the form is headed by the moment's time, and it lists the messages visible
before it under "що було видно до цього". The message is the trigger and the
context, not the subject.

## Judging a moment, not a post

The schema opens by saying a label attaches to a moment, and that has a
consequence for the tooling: **the pre-fill must read the feed, not one
message.** Most messages state neither type nor place —

```
1х Центр. / 1х Троєщина.      Вибухи      Збито      Продовжує рух на Центр
```

— and in isolation the honest answer for every one of them is "unknown", which
is useless as a starting point. In context the answer is usually obvious,
because a message minutes earlier said `3 реактивні шахеди на Київ`.

So the labeler carries the last stated type and place forward for up to
**15 minutes**, shows which message it came from, and asks you to confirm. Over
the sampled month this fills in **3 760 of 5 167 messages (73%)**.

Three rules keep it from inventing things:

- **An explicit `відбій` resets it.** After an all-clear nothing is known to be
  in the air, and carrying across that would manufacture a threat.
- **It expires.** Beyond 15 minutes the situation has probably moved on, and a
  blank field is better than a stale guess.
- **A stated value always wins.** If the message names a type, that is the type,
  even when the inherited one seemed more specific.

Resolutions (`Збито`, `чисто`, `мінус`, `локаційно втрачено`) count as
live-situation events rather than chatter, precisely because they are the
messages that most need the earlier context.

The pre-fill is a starting point, not an answer. Correcting it is useful twice:
it fixes the label, and the same module runs in the stage-6 baseline, so the
correction is also a report about the baseline.

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

Either way of working is fine, and the second turns out to be easier in
practice.

**Dense — a label after every post.** More labels, but no decision about *which*
moments deserve one, and that decision is the tiring part. It also produces
strictly better data: every message becomes a test case, and episode boundaries
are pinned exactly ("silent at 10:06 because already woken, notify at 10:35
because a new wave"), which is precisely what the repeat logic needs. Nothing
needs cleaning up afterwards — dense labels are a superset of sparse ones.

Three things make it viable:

- **Sticky defaults.** A new label starts from the night's most recent label of
  the same decision, so a run of `молчати · вже будив` is one click each.
- **One-click from the feed.** Each unlabelled row carries a `не буди` button
  that saves with the previous silent settings without opening the form.
- **`why` is required only for a wake-up.** A decision to wake someone has to be
  justified; "nothing here" does not. Requiring a sentence on every silent label
  would make a whole night unbearable, and most of a night is silent.

**Sparse — only the moments that matter.** Fewer labels, but each one is a
judgement call about significance as well as about the decision.

If you label densely, the harness gets an explicit answer at every arrival and
scoring becomes stricter rather than harder: there is no longer any moment where
"no label nearby" has to be interpreted.

### Sparse guidance

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

## What he hears

The notification is a **queue of spoken Ukrainian sentences**, not a set of
tones. His design:

> Повідомлення ставляться в чергу. Якщо прилітають "Загроза балістики" і слідом
> "Вихід на Київ", то я хочу почути що почалась тривога по балістиці і потім що
> був пуск. Скоріше за все, ці звуки будуть не просто звуки, а слова.

Three properties follow, and `tools/policy/announce.py` implements them.

**An utterance says what changed.** The second sentence in each of his examples
is shorter than the first, because the siren has already been announced by then.
Reading the whole situation aloud every time is how a voice channel becomes
noise — the failure the tone channel had when every message rang.

**Nothing is dropped.** A tone arriving while another plays is lost; a sentence
waits its turn. So it is a queue, and the queue is deliberately not
de-duplicated: the policy has already decided what is worth saying, and making
that judgement twice in two places is how the two drift apart.

**`alarm` still names the class**, because the lead-in sound plays before the
words and has to say what is coming before he is properly awake.

    🔔 Тривога.
    💬 Загроза: балістика.
    🔔 Пуск: балістика.
    🔔 Жуляни.
    🔔 Відбій по балістиці.
    🔔 Відбій тривоги.

The 💬 line is the reason `info` exists. An anticipated launch writes a sentence
and rings nothing: he asked to hear the class named after the siren, and of
eleven anticipated threats in the labels exactly one is a wake-up — sounding
every episode's first one costs three false wake-ups.

That change is also what made **long-range forecasts** matter. "Загроза
балістичного удару по Києву протягом 48 годин" is `live-threat`, `probable`,
`ballistic` — identical in every field to an imminent launch threat — and once
anticipation writes a status line, a two-day forecast would sit there saying
"Загроза: балістика" all night. Sixty-five such messages are now read as
summaries.
