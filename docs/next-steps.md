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

### ...but a moving reference point needs geometry, not a deciding model

He pushed back on the above, and rightly: the original idea was an app he could
carry around the city, with the predictions following him into a new district.
That is a real requirement and the section above skated past it.

It does not change where the decision lives. What it exposes is a thing this
project deliberately does not have: **coordinates.** The ring is a list of
names, so it cannot move with him. From `gazetteer.py`, in his own words:

> "не завжди питання в відстані, а також якою дорогою найчастіше воно летить і
> які топоніми мелькають в чаті" — Gatne is in and neighbouring Chabany is out;
> Solomianka is in and Chokolivka is not. Do not "tidy" this into a geometric
> rule.

So the ring is an approach corridor plus the names that actually recur, hand-
ruled by him over a labelled night. Three ways to make that follow him:

- **Coordinates and a radius.** Works from anywhere, and throws away the thing
  he said in the quote above: a radius cannot put Gatne in and Chabany out.
- **Coordinates and a bearing.** The corridor *is* geometry — the places on the
  vector between where a threat came from and where he is. A drone from the
  south-east through Gatne is heading at him; Chabany off that axis is not.
  This generalises his rule instead of discarding it, and it moves with him.
- A model taking position as an input. No data: all 458 labels are from one
  place.

Which gives a test worth running before any of it is built. **Does "distance
plus bearing from Zhuliany" reproduce his own rulings?** If the geometry puts
Gatne inside and Chabany outside on its own, the reference point really can
become a parameter. If it does not, the corridor is idiosyncratic and a moving
reference point will be an approximation — worth knowing before it is promised
rather than after. His labels are usable as that test precisely because they all
come from one point.

**First result, 2026-08-29** — on approximate coordinates, so indicative rather
than settled. Two radii, an inner one for his own microdistrict and an outer one
for the neighbours, cannot reproduce his rulings. Distances from Zhuliany:

    1.8 km  ring   Іподром          7.1 km  ring   Гатне
    2.2 km  OUT    Чоколівка        7.3 km  ring   Борщагівка
    3.2 km  ring   Солом'янка       7.4 km  OUT    Чабани
    4.2 km  OUT    Караваєві Дачі
    5.7 km  OUT    Мишоловка

Chokolivka is the nearest place to him of all, and he ruled it out. No radius
excludes it while keeping Solomianka, Teremky or Gatne, which are farther.
Karavaievi Dachi and Myshalovka are the same shape of counterexample. Gatne and
Chabany a radius separates only by 300 m, which is coincidence, not a rule.

So the cost of radii is three of his explicit rulings — which is exactly what he
warned about in the gazetteer. Radius plus bearing is the candidate that might
survive: Chokolivka lies north-east, toward the centre and behind him relative
to the usual approach, while Gatne is south-west and on it. Proving that needs
real coordinates and a run against every label, not three examples.

Parked on his call: "з моделлю по іншому думаю не вийде. Потім розберемося."

### A smaller, safer use for coordinates — his idea, 2026-08-30

Separate from the ring question above, and much cheaper. Coordinates would not
decide anything; they would only choose **which of several named places to say**.
The ring stays the hand-ruled list. A wrong choice costs a worse sentence, not a
missed wake-up, which is the whole difference from redefining the ring.

The case that prompted it: the siren said Obolon and the explanation said
Vyshhorod, both true, and the pair read as a contradiction. Obolon is nearer, so
"say the nearest" would have produced one answer instead of two.

Two things to get right before building it:

- **"Nearest" is not always the right one.** With two threats up -- one over
  Obolon, one coming at the city from Vasylkiv in the south -- the nearest name
  is the harmless one. The choice has to be the nearest *of what this message is
  about*, not of everything remembered.
- **Coverage is a smaller problem than it looks.** The worry was that the
  channels' informal names would not geocode -- but the gazetteer already *is*
  the synonym dictionary, and it resolves them: "Троя" to Троєщина, "Голос" to
  Голосіїв, "КарДачі" to Караваєві Дачі. What needs coordinates is the 122
  canonical names in the near tiers, every one a real place. The failure mode is
  therefore a *missing synonym* rather than an ungeocodable name, and that shows
  up as a place going unrecognised today, long before any coordinate work.

The second reason is the one that matters at 3 a.m. anyway. A rule that fires
wrongly can be read, argued with, and corrected in one line with a comment
saying why — which is what most of `rules.py` is. A model that fires wrongly
can only be retrained. The part worth replacing with a model is the part that
is already guesswork: `hints.py`, where a regex over Ukrainian morphology
decides what is flying, and where every fault this project has hit so far has
lived.

### Which launches should ring — open, 2026-08-30

Today two labels were corrected because launches ring: "☄ Вихід у напрямку
Києва" and the ballistic warning before it. Six other launch labels were left
silent, because ringing on all of them would contradict rules he made earlier:
the second launch of a wave ("☄ Другий вихід"), a cruise launch, bare "☄ Вихід
Курськ" inside a wave that had already rung, a past-tense mention, and aviation.

His own reading of it, and it is not settled: "може б мали дзвонити всі, крім
авіації. А може і ні. Треба глянути на реальній ситуації."

Two specific candidates he raised, both worth keeping:

- **A launch with no destination.** It says nothing about where it is going,
  which is an argument for ringing rather than against: nobody knows yet whether
  it is coming here.
- **A probable launch.** "А якщо пуск таки був реальний?" The asymmetry is
  obvious once stated -- a warning that turns out to be nothing costs a
  wake-up, and a launch treated as a warning costs the minutes.

### Waiting for the arrival reads as waiting for the launch

Measured properly on 2026-08-31, after a first note blamed the wrong mechanism.
It is not `AWAITING_TERMS`, which only gates `alert_state` and `partial_clear`.
The word sits in a list inside `certainty_hint`, among the markers that mean "a
takeoff is a possibility, not a fact" -- and it vetoes the whole message:

    Був вихід з Брянська.             -> certainty = confirmed
    Був вихід з Брянська. Очікуємо.   -> certainty = probable

That is expensive because `certainty == "confirmed"` is the door into the
ballistic launch rule. Demoted, the message takes the anticipation path instead,
which is silent by design. So: a launch happened, the channel added that it is
waiting for the arrival, and we read that as the launch not having happened yet.

Twenty messages, not the one the first note assumed. Split by word order:

- waiting **before** the launch word -- 18, genuine anticipation: "Очікуємо на
  пуски ракет з Криму по Одещині"
- waiting **after** -- 20, the launch already happened: "Проведено пуски КР
  «Калібр» з акваторії Чорного моря. Очікуємо у повітряному просторі", "Пуски
  Х-101 з Ту-95МС. Підліт ракет до України очікується", "Був вихід з Брянська.
  Очікуємо."

So order is the discriminator, and it divides the corpus almost cleanly. Not
perfectly: "Є інформація про **можливий** пуск балістичної ракети, очікуємо" is
in the second group and genuinely is probable -- which is the right outcome, an
explicit ймовірн/можлив should stay stronger than word position.

Nothing to do until a real ballistic night is watched live. The whole area has
been tuned against recordings only.

### Deduplicate by event, not by clock — his framing, 2026-08-31

"Якби у нас було єдине джерело даних, то дзвонили б на кожну згадку, а так 4
канали шлють повідомлення коли їм заманеться." That reframes the whole
refractory machinery: it is not about how a drone behaves, it is about source
multiplicity. The single authoritative picture would be Віраж-планшет, which is
not available to anyone outside the military; what *is* available downstream of
it is `alarm_kyiv` -- and only the binary siren state, never the detail.

Measured cross-channel lag for the same target (same class, overlapping places,
different channel): median 74 s, p90 4 min, p99 5 min. Which means the existing
`REFRACTORY_NEAR_S` of five minutes is exactly the ceiling of "whenever they feel
like it" -- not fitted to that, but justified by it after the fact.

`RING_MEMORY_S` of ten minutes is longer than any cross-channel lag, so it is
doing a different job: deciding whether a drone that circled and came back
deserves a second sound. That is a judgement, not a measurement.

**The two are tangled in one number today, which is why arguing about minutes has
no answer.** Deduplicating on event identity -- class, place, and a window sized
from the measured channel lag -- would separate them: the first becomes exact and
data-driven, the second becomes an explicit choice. And his sentence becomes
literally true, because after grouping there is one message per event and every
genuinely new event rings.

Not worth building yet: the measurement rests on 31 pairs, because matching
identity by hand is strict. Event grouping is close to free once the LLM
labelling exists.

### The rolling feed, considered and dropped — 2026-09-01

He asked for every ballistic and cruise detail message, silent, during a wave:
"Спокійніше відразу знати що не до тебе, чим не знати взагалі." Then for the
shape it would take -- one message rewritten in place holding the last five or
ten lines, a new *type* of notification, closing on an all-clear or a recheck.

Measured on the night of 2026-08-31 before building any of it, and the
measurement is what settled it:

    02:23-02:33 (густіше нема)   94 повідомлень, 91 у стрічку -> лишає 96%
    02:20-02:47 (уся хвиля)     155,            137           -> 88%
    за півдоби                  369,            176           -> 47%

**During the wave the filter leaves 96% of the raw traffic.** So the feed would
be the five channels he is already subscribed to, reproduced inside Ховайся
exactly when it matters most -- and 94 edits in ten minutes, against Telegram's
rate limits, for the privilege. His own conclusion arrived at the same place from
the other side: "спам повідомленнями на основному екрані це таки може бути
незручно. Для спаму повідомленнями буде свій спеціальний екран."

So the raw detail belongs to the app's own screen (stage 9), not to the
notification channel. Two things survive the decision:

- **The picture, not the feed.** One silent message per wave, edited in place,
  holding only what the raw channels cannot give: what is up, since when, how
  many launches, whether his own place has been named. One edit every ten or
  fifteen seconds, no rate-limit exposure. Not built -- offered and not yet
  taken.
- **`info` does not mean what the schema says it means.** The schema has said
  from the start that `info` is "the persistent status notification updates
  only", and `notify.py` sends a fresh silent message per line instead. Nothing
  is wrong today, at 72 silent lines a night; anything of the shape above needs
  the transport fixed first.

### At night, vibration rather than sound — his idea, 2026-08-31

"Дзвінки залишимо вдень, а вночі залишиться тільки різні вібросигнали. Зпросоння
вони краще читаються. Не треба навіть брати телефон, щоб розуміти що і де
відбувається." Also for a phone in a pocket somewhere loud.

The part to decide before building it is not the interface but **the size of the
alphabet.** There are nine tones today -- alert, ballistic, mig, cruise,
drone-jet, drone, recon, clear-partial, clear -- which an ear separates by timbre.
Vibration carries far less: half-asleep a person reliably tells three or four
patterns apart, not nine, and nine would blur into something worse than one.

So the natural grouping for vibration is **by action, not by class**:

- **shelter now** -- ballistic, KAB, Kinzhal: minutes, and one decision
- **look and be ready** -- a jet drone over the ring, cruise over the city
- **over** -- the all-clear

Three patterns nothing confuses: a sharp burst of short pulses, one long, two
calm ones. The class stays in the text on screen, for whoever does pick the
phone up.

One constraint worth knowing now: at night the phone is in Do Not Disturb, so the
notification channel needs priority with explicit permission to bypass it.
Android allows that, and the user must grant it -- meaning the app has a setup
step without which the whole idea does not work at all.

## 9. The Android client — what it needs from this side, decided 2026-09-01

Not started, and this section is only the seam: what the watcher has to grow
before an app has anything to connect to. Asked what stood in the way, the answer
turned out to include a defect — `observe()` had taken a `config` for days and no
caller passed it, so `ring` in the settings file changed nothing. Fixed in
134186f. Worth naming because of *why* it hid: the list in the file is identical
to the gazetteer's, and the test guarding that identity stood in for the wiring.
A setting that changes nothing when changed has no symptom.

### The transport is FCM

Firebase Cloud Messaging, on his confirmation that everyone will have an ordinary
Android. What it costs and what it does not:

- an ordinary **free Google account** and a Firebase project. **No Play Developer
  account** — that is only for publishing — and no payment method: FCM has no
  send quota on the free plan.
- it does require **Google Play Services on the device**, not the store listing.
  A sideloaded APK is fine; a de-Googled ROM or a recent Huawei is not. That was
  the only real wall here and he has closed it: "у всіх нормальний Андроїд буде".
- updates outside the store are explicitly not a worry yet, on his call. The
  keystore still is: lose it and an installed app cannot be updated at all, only
  removed and reinstalled, so it belongs in `tools/backup.py` the day it exists.

The alternative was ntfy/UnifiedPush — no Google anywhere, could live on the same
box — and it loses on the one axis that is the product: it keeps its own
connection, which Android's Doze kills more readily than the system's own push
channel. Chosen with the dependency stated rather than by default.

**FCM needs no inbound port.** The server calls Google outbound, exactly like the
channel polling it already does. That matters more than it sounds — see below.

### The push carries the decision, not the observation

Two shapes were possible and only one of them is cheap.

*Send the observation* — "ballistic, my area, launch" — and let the phone decide.
That means the ordered rules and the episode state reimplemented in Kotlin: two
copies of the one thing in this project whose whole design is that order is
semantics and every rule carries its reason. They would diverge on the first fix.

*Send the decision.* One implementation, and a rule fix reaches every phone in
ten minutes through the pull deploy that already exists, with no app release. The
phone stays dumb, which also means one that was offline does not replay a
finished wave.

The log row is already almost the payload:

    { "seq": 10482, "at": "2026-09-01T02:30:08Z", "level": "alert",
      "alarm": "ballistic", "said": "Загроза: балістика. Жуляни.",
      "episode": "2026-09-01T02:22", "reason": "my place, and ballistic is up",
      "anchor": "kievinform_ua1/24620" }

Around 200 bytes against a 4 KB limit. Every field earns its place: `level`
decides ring or status line, `alarm` picks the tone or the vibration pattern,
`said` is the sentence `announce.py` already produces, `episode` lets the app
update one notification instead of stacking eleven, `reason` is the screen that
let eight faults be found in a week, and **`at` plus `seq` exist because FCM does
not promise delivery time** — a phone must be able to discard a ballistic ring
that arrives four minutes late, which is worse than none.

So a recipient is `{FCM token, config}`, and that is where the two prerequisites
meet: the per-recipient decision loop is what the transport needs, not a separate
piece of work.

### Where each layer lives, since this reads backwards easily

He read the section above as the gazetteer staying on the server and the decision
tree moving to the phone. It is the other way round, and one constraint settles it
rather than any preference:

**the decision needs every message, and every message cannot be pushed.** Rules
that decide are stateful -- an episode, a wave, what was already said -- so they
have to see the whole stream, all 1175 messages of a busy night. Pushing that
stream is exactly what the section above rules out. So the decision lives where
the messages arrive.

    server   the gazetteer and hints        reading Ukrainian
    server   the ordered rules + episodes   whether this is worth a sound
    server   each recipient's config        home, ring, switches, quiet hours
    phone    rendering                      which tone, which vibration pattern,
                                            bypassing Do Not Disturb
    phone    the two screens                the filtered one and the raw feed

The phone is deliberately dumb about *whether*, and the only authority it keeps is
*how* -- which is also where its own hardware knowledge belongs. The cost of the
split is that the server knows where each recipient lives; the answer to that is
that the configs sit on the box with no inbound port, which is the reason the
previous section puts the open port somewhere else.

### The raw feed is fetched, not pushed

He remembered what the design above forgot: the app has a second screen with
every chat message on it. That cannot be pushed. Each push wakes the app, and the
busiest night in the corpus is 1175 messages — 149 KB of JSON, one message every
six seconds at the peak. A thousand wake-ups would empty the battery.

It also does not need to be. A feed nobody is looking at has nowhere to arrive:
when the app is open he is reading it, and when it is closed he is asleep and only
the bell matters. So:

    GET /messages?since=<seq>     the merged raw feed
    GET /decisions?since=<seq>    what Ховайся decided, for this recipient

Cursor-based, which is the pattern the watcher already uses against `t.me/s/`
with `?after=<id>`, and an app that was offline closes the gap in one request.
Thin reading over the SQLite that exists.

### ...and the open port goes on a second box, not this one

**Today the instance has no inbound service at all** — it only polls outward,
which is half the reason it is safe to keep a bot token there. Serving the feed
means the first inbound door on a public IP.

His instinct was to move the *bot* to a second instance so the token leaves the
exposed box. Right instinct, wrong direction, and the reason is the critical path:
the bell would then travel watcher → write → second box polls → Telegram, and a
dead second box or a lagging poll looks exactly like a quiet night. That is paid
in the one thing that is the product, to protect the cheapest secret in the system
— a bot token is not account access, it can only post to his own channel, and
@BotFather revokes it in seconds.

So the exposed thing moves out instead:

| | A, the instance that exists | B, new and small |
| --- | --- | --- |
| inbound | SSH only, as now | 443 |
| holds | watcher, decisions, bot token, recipient configs, FCM sender | a copy of the raw feed |
| worth stealing | everything | public messages |
| in the path to the bell | yes, one process, as now | no |

**A pushes to B, never the reverse.** If B pulled over SSH it would hold a key to
A, and compromising the public box would then hand over the private one — far
worse than the token this started from. Pushing outward means a compromised B
yields a copy of public data and the ability to lie to a feed screen, while the
bell still comes from A and cannot be forged. The recipient configs — which is to
say where each person lives, the only genuinely private data here — stay behind
the closed door.

B is free within Always Free (the ARM allowance is 4 OCPU / 24 GB across up to
four instances and 1/1 is in use), and the binding constraint is disk: 200 GB per
account against a 47 GB boot volume, so two fit and a third is tight.

**Not built until an app exists to read it.** It costs a second runtime — its own
deploy, restart and runbook entry — and the push path needs no port at all, so the
order is: the per-recipient decision loop, then FCM, then B when the feed screen
is real.

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
