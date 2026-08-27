# Pattern mining findings

From 11 609 messages across the three channels, 2026-04-15 to 2026-08-27
(134 days). Regenerate the raw report with `python -m tools.analysis.patterns`.

Several findings contradict assumptions the project was being designed around,
including one from an earlier pass of this same analysis. Those are marked
**correction**.

## 0. Reference point

The user lives in **Zhuliany** (Solomianskyi district), next to Zhuliany
airport. Every relevance decision resolves against that point, so it is the
default subject for examples and eval cases.

Zhuliany appears in **115 messages (0.86/day)**, covered by all three channels
(mon1tor_ua 68, kievinform_ua1 30, war_monitor 17). A single night —
2026-08-27 — produced eight separate location-specific signals:

```
00:03  Жуляни
07:02  🅿️ Київ / 1х Жуляни
07:03  Через Оболонь в сторону Жулян
07:06  🅿️ Київ / 2х Вишневе Жуляни / 1х Труханів Поділ
07:15  1х Жуляни / 2х Велика Димерка/Бровари (вектор)
07:35  Жуляни ✈️
07:35  🅿️ 1х реактив Жуляни далі Центр.
07:36  Реактивний БпЛА курсом на Жуляни
```

The official app collapses all of that into one city-wide "increased danger".
This is the value of the project stated in data.

## 1. Almost two thirds of the corpus is irrelevant, and filtering it is free

| Slice | Messages | Share |
| --- | --- | --- |
| Mentions Kyiv city or a microdistrict | 3 026 | 26.1% |
| Mentions Kyiv oblast | 2 549 | 22.0% |
| **Kyiv city or oblast (either)** | **4 427** | **38.1%** |
| Only other regions — noise for this user | 2 515 | 21.7% |
| No geography at all | 4 667 | 40.2% |

These channels cover all of Ukraine. **A dictionary-only geographic filter
discards 55.7% of traffic before any model runs** — the highest-leverage
component in the pipeline, and it costs nothing.

The table above was produced by a crude stem list and implied ~62%. The real
gazetteer (`tools/nlp/gazetteer.py`) resolves more places, so fewer messages
land in the undroppable `unknown` bucket: **55.7% is the measured figure and
the one to quote.**

The 40% with no geography is not all noise: much of it continues a prior
message ("Збито", "Продовжує рух на Центр") whose location came earlier. That
is what the episode state machine is for.

## 2. District-level resolution is real: ~9 relevant messages per day

1 352 messages name a Kyiv microdistrict, raion, or informal area. Ranked:

```
троєщина 212  дарниця 202  оболонь 197  жуляни 100  святошин 91  позняки 87
лук'янівка 83  нивки 81  лісовий масив 70  борщагівка 65  русанівка 64
деснянський 59  солом'янський 54  голосіїв 52  печерськ 48  виноградар 38
теремки 33  сирець 32  шевченківський 28  поділ 24  осокорки 23
куренівка 17  коцюбинське 13  чоколівка 10  соцмісто 10
```

Found during analysis and missing from the initial gazetteer draft:
**Березняки, Воскресенка, Русанівські Сади, ДВРЗ, Погреби, Зазим'я, Бортничі,
Нижні Сади, Деміївка, Іподром, Труханів, Десна**, and the `X масив` family
(Лівобережний, Харківський, Дарницький, Лісовий). Slang forms appear too:
**Борщаги**, **Святошино**, **Троєща**.

**Channel roles differ sharply and should drive weighting:**

| channel | messages | Kyiv-relevant | names a district | live-threat share of its district posts |
| --- | --- | --- | --- | --- |
| kievinform_ua1 | 2 847 | 48.0% | 8.3% | terse toponym lists; 15% aftermath |
| mon1tor_ua | 5 709 | 36.8% | **13.5%** | **77.7%** live |
| war_monitor | 3 053 | 31.4% | 4.8% | 66.3% live |

`mon1tor_ua` is the primary source for district-level detection.
`kievinform_ua1` carries most of the aftermath reporting.

## 3. Correction: live threat is recognised by sentence shape, not by alarm words

A first pass keyed on words like `загроза`, `курсом`, `увага` and classified
78% of district messages as "unmarked". Inspecting them showed they were live
threats written telegraphically:

```
1х Центр. / 1х Троєщина.
⚠️1 реактивний шахед з Березняків на Русанівку, Лівобережний масив.
Жуляни ✈️
Дарниця, Чоколівка
Воскресенка, ДВРЗ ⚠️
```

Re-classifying on **structure** instead of vocabulary moved these into the live
bucket. The productive templates:

| template | messages | note |
| --- | --- | --- |
| `Nх <toponym>` | 1 783 | the count marker *is* the threat report |
| `<threat> (на\|над\|з\|через\|курсом) <toponym>` | — | most common full form |
| bare `<toponym>[, <toponym>] <emoji>` | — | kievinform_ua1's house style |
| `з <A> на <B>` | 146 | movement, direction stated by the channel |
| `🅿️ Київ / …` | — | war_monitor section header, a useful parse anchor |

**Emoji carry meaning, but they are not reliable evidence.** An earlier draft of
this document claimed they are the predicate of a bare report. Measured, the
claim is too strong:

| marker | messages | share of corpus | already matched another shape |
| --- | --- | --- | --- |
| ⚠️ | 3 024 | 26.0% | 93% |
| ❗ | 2 290 | 19.7% | 83% |
| 🔴 | 707 | 6.1% | 93% |
| 💥 | 425 | 3.7% | 40% |
| 🅿️ | 366 | 3.2% | 98% |
| ✈️ | 289 | 2.5% | 52% |

⚠️ sits on one message in four and nearly always duplicates what the text
already says, so as a feature it discriminates almost nothing. Where an emoji
plus a place name is the *only* live evidence — 593 messages, 5.1% — it is right
about 95% of the time: 563 live threats, but also 24 aftermath posts and 6
summaries, including a fundraising drive (`🚨Терміновий збір для ГУР МОУ на
далекобійні FPV дрони🚨`).

So emoji are kept as a **weak** signal (`hints.live_strength` returns `weak`),
useful for recall in the labeler's pre-fill, and the baseline must never let
weak-only evidence raise a `shelter`. Waking someone at full volume on an emoji
is not acceptable at 3 a.m.

`✈️` specifically marks aviation activity (in war_monitor usually "Активність
тактичної авіації"), and per the user `Жуляни ✈️` refers to the airport — an
ambiguity only he can settle during labeling. Normalization keeps emoji in the
message text; only the dedup fingerprint strips them.

## 4. The outcome-word anti-filter works — but only for the right tier

Posts describing consequences ("влучання, пожежа, вибухи") name districts and
use alarming vocabulary while carrying no live threat. Using them to *suppress*
a notification is the right instinct, and it is measurable: for each marker,
the median gap to the most recent live-threat message.

| marker | messages | median gap to live threat | verdict |
| --- | --- | --- | --- |
| `вибух` | 242 | **1.8 min** | **never veto** |
| `влучан` | 139 | **2.2 min** | **never veto** |
| `детонац` | 3 | 3.9 min | never veto |
| `Кличко` | 22 | 7.4 min | safe |
| `уламк` | 21 | 12.6 min | safe |
| `медик / швидка` | 14 | 15.7 min | safe |
| `пожеж` | 59 | 20.8 min | safe |
| `рятувальн / ДСНС` | 32 | 21.6 min | safe |
| `пошкодж / вибило` | 50 | 23.8 min | safe |
| `загинул / загибл` | 64 | 25.1 min | safe |
| `постраждал / поранен` | 87 | 27.1 min | safe |
| `наслідк` | 33 | 27.8 min | safe |
| `ліквідовано` | 5 | 56.0 min | safe |

The split is an order of magnitude wide and therefore defensible:

- **Impact vocabulary is simultaneous with danger, not after it.** 88% of
  `вибух` messages arrive within 10 minutes of a live-threat message. One of
  them makes the point by itself:
  `💥Вибухи у Дніпрі, над містом чисто. / ⚠️Але на місто з півдня летить ще 1 реактивний шахед.`
  Vetoing on `вибухи` would silence the app at peak danger.
- **Consequence-management vocabulary is genuinely retrospective** — fire
  crews, casualties, damage assessment, official quotes. 56 district-naming
  messages, 0.42/day. Small, but they are the false-wake-up risk, and they are
  concentrated in `kievinform_ua1` (15% of its district posts versus 0.8% for
  `mon1tor_ua`).

So: hard veto on the consequence tier, never on the impact tier.

## 5. Correction: jet-powered Shaheds break the two-axis model

The design assumed two classes — ballistic (a time problem, city-wide) and
drones (a space problem, with time to be precise). The corpus disagrees:

| term | messages | | term | messages |
| --- | --- | --- | --- | --- |
| шахед | 2 302 | | циркон | 244 |
| бпла | 1 658 | | бандероль | 241 |
| **реактивн** | **1 511** | | х-101 | 130 |
| балістик / балістичн | 784 / 748 | | герань | 107 |
| ракети / ракета | 673 / 481 | | калібр | 93 |
| крилат | 386 | | х-59 | 71 |
| іскандер | 374 | | каб | 52 |

"Реактивний" outranks every ballistic term. A jet Shahed is several times
faster than a propeller one — neither the slow-space case nor the ballistic
time case. **The policy matrix needs a third row**, and the taxonomy must
separate `shahed` from `shahed-jet`.

Threat names the hand-written list missed entirely: **Бандероль** (241 — S8000
cruise missile), **Циркон**, **Іскандер-К**, **Кинджал**, **Гербера**,
**Герань-2**, **КН-23**, **Х-59**, and the slang **мопед**.

## 6. Correction: reply chains are weaker evidence than they first looked

The chain `Шахед над Позняками → Шахед над Голосієвом → Збито` looked like free
target identity. At corpus scale it is thinner:

- 1 886 replies form 1 214 chains, but **900 (74%) are only 2 messages**.
- Only **7% of chain endings carry an explicit resolution marker**.
- The longest chain (13 messages) is a **charity auction**, not a threat.

Reply chains remain valuable as *local* context — a bare "Збито" is resolvable
because its quote is attached — but they are not a reliable episode-closure
signal, and chain length says nothing about significance.

Movement, however, *is* directly parseable: 146 explicit `з X на Y` statements
at district granularity, and they chain into real tracks:

```
Дарниця → Дарницький масив → Лісовий масив → Воскресенка → Русанівські Сади → Поділ
```

The earlier decision not to *compute* trajectories still holds. But the
channels state direction themselves, and that should be parsed rather than
discarded.

## 7. The real resolution vocabulary is slang and phrase-shaped

None of these were in the hand-written guess list. From the 562 replies of 25
characters or fewer:

| phrase | count | meaning |
| --- | --- | --- |
| `чисто.` / `локаційно чисто.` / `📡 чисто.` | 28 | area clear |
| `мінус` / `мінус.` | 11 | shot down (slang) |
| `без фіксації` / `без подальшої фіксації.` | 14 | no longer tracked |
| `локаційно втрачено.` | 10 | lost from radar |
| `дорозвідка.` / `дорозвідка по шахедах.` | 9 | re-scouting, still active |
| `💥збито.` / `збито!` / `💥ще збиття.` | 7 | shot down |

`відбій` is the most frequent term overall (296) but usually refers to the
official all-clear rather than a single target.

The distinction that matters: `чисто` and `збито` **close** an episode, while
`локаційно втрачено`, `без фіксації`, and `дорозвідка` mean *we no longer
know*. Treating the second group as safety would produce exactly the wrong
notification, so `unknown` must stay a distinct state from `clear`.

## 8. Adjacency can be derived from the corpus instead of drawn by hand

Areas co-mentioned with Zhuliany in the same message, by frequency:

```
солом'янка 19  теремки 18  оболонь 17  дарниця 14  борщагівка 13
деміївка 12  святошин 11  нивки 11  голосіїв 10  центр 9  троєщина 8  дврз 7
```

Solomianka is Zhuliany's own raion; Teremky, Demiivka, and Borshchahivka are
its geographic neighbours. **Co-mention frequency is a usable soft adjacency
measure**, which means a first-cut "is this near me" can ship before any
polygon work — and can later be used to sanity-check the polygons.

Named infrastructure appearing as targets: `ТЕЦ` 114, `вокзал` 29, `метро` 11,
`аеропорт` 10, `залізнич` 6, `мост` 7. These need to be in the gazetteer as
points, not just districts.

## 9. The merged feed is the core value, not a convenience

Token-set Jaccard >= 0.5 within 5 minutes finds only **206 duplicate pairs**
across 11 609 messages — the channels are **~98% non-overlapping**. Merging
them multiplies coverage rather than removing redundancy.

Who reports first is not settled either: mon1tor_ua 88, war_monitor 71,
kievinform_ua1 47. No channel can be dropped.

Dedup sizing: median lag between the two reports **39 s**, p90 **167 s**, max
297 s. A 5-minute window is right; a 1-minute one would miss a tenth.

## 10. Volume makes cost a non-issue, and sets the real requirement

Busiest minute in four months: **17 messages**. Peak hours are 21:00-01:00 UTC
(00:00-04:00 Kyiv) — 1 395 messages in the 22:00 UTC hour versus 185 at 05:00.

Per-message inference is affordable at any model tier. And **the app's hardest
requirement is being reliable while the user is asleep**, because that is when
nearly all the traffic happens.

## What this changes

1. **Geographic pre-filter first.** Removes 55.7% of traffic with a dictionary.
2. **Classify on structure, not vocabulary.** The templates in §3 carry the
   threat report; alarm words are optional and often absent.
3. **Two-tier veto.** Hard-suppress on the consequence tier (§4); never on
   `вибух` / `влучан`.
4. **Four modality classes:** `live-threat`, `aftermath`, `summary/news`,
   `non-threat social` (auctions, donations, thanks, politics — a real and
   sizeable class).
5. **Split `shahed` and `shahed-jet`**; add the intermediate row to the policy
   matrix.
6. **Episode closure from §7 vocabulary plus timeouts**, not from reply chains.
   Keep `unknown` distinct from `clear`.
7. **Parse stated movement** (`з X на Y`), do not compute trajectories.
8. **Weight `mon1tor_ua` highest** for district detection; treat
   `kievinform_ua1` as the aftermath-heavy channel.
9. **Gazetteer as stem plus suffix matching.** Every toponym has 4-6 inflected
   forms (`Київщину/Київщини/Київщина/Київщині/Київщиною`,
   `Бровари/Броварський/Броварів/Броварському/Броварами`) and case is
   inconsistent (`КИЇВ`, `ТРОЄЩИНА`, `БпЛА/БПЛА/БпЛа/Бпла`). Exact matching is
   useless; a 6-character prefix stem clustered every family correctly here.
10. **Keep emoji in the text.** They are predicates and disambiguators.
11. **Start adjacency from co-mention statistics**, not from polygons.

## What the geographic filter was hiding

Found because the user noticed a reply on the page quoting a post that was not
on the page: `↳ ⚠️На ТЕЦ-5! Падає`, with no parent row anywhere. The parent was
in the database all along.

Three separate causes, measured on the two labelled nights:

| cause | effect |
| --- | --- |
| a place named 44 times was not in the gazetteer (`ТЕЦ-5`) | every mention resolved `unknown` |
| the page computed an inherited scope and then filtered on the stated one | 31 live messages a night hidden behind a field it had already filled |
| a launch report names only where it came from | the beginning of every wave hidden |

The Kyiv view went from 346 to 388 of 465 messages on 2026-08-04, and the count
of live messages hidden while naming no region at all went from 24 to 2 — one
commentary post and one about Odesa.

A sweep for capitalised words in live messages that resolved to no place at all
turned up 34 more toponyms, most of them Kyiv-oblast towns the channels track
routinely: Кагарлик, Ржищів, Козин, Березань, Бородянка, Яготин, Іванків,
Білогородка, Вишеньки. Adding `oblast` entries carries no wake-up risk — the
policy silences the tier outright — so the only thing that was ever at stake was
whether the user gets to see them.

Two structural bugs came out of the same sweep:

- **A hyphen counted as a word character**, so the second half of every joined
  pair was mid-word and invisible. Згурівка was in the gazetteer and had never
  once matched, because the channels always write "Яготин-Згурівка".
- **Fixing that exposed Kyiv district names inside distant towns.** `подільськ`
  is Podil; Кам'янець-Подільський read as Kyiv nine times. Longest match already
  handles it, but only once the full hyphenated name is an entry of its own.

And a rule that had no home before: **a settlement named beside a landmark
outranks it.** Nearly every city has a ТЕЦ-5, so "Залітає у Черкаси курсом на
ТЕЦ-5" is about theirs. One message in 4.5 months — and exactly the shape that
wakes somebody at 3 a.m. for another city.

## Fitting the ring re-arm (334 dense labels, 2026-08-04)

A ballistic salvo arriving over the user's own area: seconds since the previous
alert, split by what he decided.

| | gaps |
| --- | --- |
| woke him | 78, 108, 448, 633 |
| called it a repeat | 4, 5, 6, 13, 26, 28, 34, 39, 48, 59 |

The boundary is between **59 and 78 s**, and it needs a second condition — a
launch announced inside the gap — or the same missiles being re-listed would
re-fire. `RING_REARM_S = 60`.

The same measurement for a jet Shahed near him gives a boundary between **142 and
194 s**, and for a propeller Shahed there is no wake-up at all in the set (five
moments, gaps up to 1346 s, all silent).

But **sweeping the near refractory against the labels does not confirm 180 s**:

| `REFRACTORY_NEAR_S` | false wake-ups | misses |
| --- | --- | --- |
| 360 (current) | 8 | 6 |
| 240 | 9 | 6 |
| 180 | 9 | 5 |
| 150 | 9 | 5 |

Total error is flat, and false wake-ups are the headline metric, so 360 stays.
The label-to-label gaps and the policy's own alert timeline are not the same
series — which is the reason to sweep rather than to trust a fit.
