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

## Where this stands, as of 2026-08-29

Читається українською; код, коміти й документи — англійською.

**Що працює просто зараз.** Вартовий живе **на сервері** — Oracle Always Free,
Марсель, Ubuntu 24.04 aarch64 — і слухає пʼять каналів цілодобово, незалежно від
того, чи ввімкнений компʼютер. Рішення ухвалює тією ж політикою, що й оцінка, і
шле їх у приватний телеграм-канал через бота. Затримка виявлення виміряна:
медіана 6 с, p90 9 с.

Деплой — тільки притягуванням: коміт у `main`, інстанс сам забирає його раз на
десять хвилин і перезапускається, а на старті шле тихе повідомлення з версією.
Ключів від сервера нікому зайвому не треба. Нічні логи щодня о 13:00 їдуть на
`D:\Work\Hovaysya-data` і скаржаться, якщо перестануть. Усі реквізити сервера —
у `data/runbook.md`, поза git, бо репозиторій публічний.

    2026-08-04   4 хибні побудки, 1 пропуск,  17 влучань   (334 мітки)
    2026-08-26   0 хибних побудок, 4 пропуски, 19 влучань  (124 мітки)

За всі 737 ночей корпусу: 3283 побудки, медіана 4 за ніч, p90 8.

**Чим це керується.** `tools/policy/rules.py` — впорядкований список правил,
кожне з причиною в тексті. Найважливіші, і всі вони з його слів:

- дрон дзвонить, лише якщо назване саме **Жуляни**; коло — надто широко
- `падає` + Жуляни дзвонить завжди, що б уже не сказали
- сходинка **дрон → крилата → балістика**: кожен підйом зі звуком, падіння не
  скидає, частковий відбій знижує
- балістика дзвонить **на пуск**, крилаті — **на позицію** (крилата летить
  години, балістика хвилини)
- офіційний канал `alarm_kyiv` оголошує тривогу й відбій; чати пояснюють причину
- вибух — це інформація, не попередження; поза колом не показується взагалі

**Що відкрито.**

- Крюківщина — **вирішено 2026-08-29**: не в колі. Вона там сиділа за здогадом,
  а не за рішенням.
- Звичайний (не реактивний) шахед біля дому не будив жодного разу, 0 з 5 —
  лишено як є на його вказівку.
- Модель (стадія 8) не почата. Даних уже вистачає: 458 ручних міток і 2000+
  рішень політики в `data/live/*.jsonl`.

**Чого не забути.** `python -m tools.backup` — усе поза git живе в одній теці, і
логи ночей не відтворити нізвідки.

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

### What the model decides, and what it must not

**It labels; the rules decide.** Settled 2026-08-29, and by an argument that
came from renaming the channel to "Ховайся Жуляни": he wanted the reference
point to be a parameter one day, and that wish turns out to rule out the other
design rather than support it.

Two shapes were possible.

*The model reads the message.* It says "shahed-jet, Solomianka, inbound" and
nothing else; whether that is worth waking anyone stays with `rules.py` and the
gazetteer. The reference point is then already a parameter — it lives in `HOME`
and the ring — and moving it needs no new labels at all.

*The model decides.* Then "wake the person at X" makes X an input, and training
it needs labelled nights from several different X. Every one of his 458 labels
was made from Zhuliany. There is nothing to train that on, and there will not
be until somebody else uses this.

His original expectation was the second one, and he changed it himself: "може
просто розставляти мітки".

The second reason is the one that matters at 3 a.m. anyway. A rule that fires
wrongly can be read, argued with, and corrected in one line with a comment
saying why — which is what most of `rules.py` is. A model that fires wrongly
can only be retrained. The part worth replacing with a model is the part that
is already guesswork: `hints.py`, where a regex over Ukrainian morphology
decides what is flying, and where every fault this project has hit so far has
lived.

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
| ~~Oracle Cloud account~~ | **Done 2026-08-29.** Running there; `data/runbook.md` has everything. |
| Phone number + MTProto | **Deferred on the measurement, 2026-08-29**, and see below |
| Android client | after stage 7 shows the decisions are worth pushing |

### Why MTProto is not happening yet, and how it would arrive

The lag it would remove has been measured rather than guessed: median 6 s, p90
9 s. Against a ballistic flight of four or five minutes that is about 2% of the
warning; against a drone it is invisible. It buys less than the model does.

The price is not the work, it is the credential. **An MTProto session file is
full access to the Telegram account that created it** — not a bot token, not a
channel key: whoever takes it from the machine signs in as him. The machine is
a free VM in France that the provider may reclaim without notice, and today the
worst it holds is a bot token. So the condition is not "when there is time" but
**a separate account on a separate number that does nothing else**; his own
account does not go on that box.

His call on the shape, and the right one: an alternative to polling with an
easy switch, not a rewrite. The seam already exists and does not need building
in advance — `poll_once` is the only thing that knows how messages arrive.
Everything downstream of `handle(session, channel, id, ts, text, ...)` is
transport-agnostic already, and a push-based source would call exactly that.
What would need care is the two things polling gives for free: the catch-up
pass after downtime, and `lag_s`, which is the number that justified this
decision in the first place.
