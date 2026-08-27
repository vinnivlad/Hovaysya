# Hovaysya

A personal air-threat notification system for Kyiv. It merges several Telegram
monitoring channels and the official air-alert API into one feed, resolves
threats to district / neighborhood level, and pushes notifications that account
for where the user actually is.

It is an **augmentation of** the official "Тривога" app, never a replacement.
When the backend is unreachable, the client must say so loudly and point the
user back to official sources.

## Why it exists

The official alert covers a 3-million-person city with a binary signal. The
useful detail — what is flying, how many, and toward which part of the city —
lives in unstructured Telegram text. The gap this project closes:

1. City-wide "increased danger" for a drone approaching the far side of Kyiv.
2. No repeat signal for a second ballistic wave during an ongoing alert.
3. Drone danger scoped to the whole city rather than a neighborhood.
4. Several channels to watch manually instead of one merged feed.

## Design in one picture

```
Telegram channels ─┐
                   ├─> ingest ─> gazetteer ─> classifier ─> situation state
alert API ─────────┘                                              │
                                                                  v
                                        per-user policy (location, thresholds)
                                                                  │
                                                                  v
                                                         FCM push -> Android
```

Three principles worth stating up front:

- **The model classifies; hand-written policy decides.** The model outputs
  `{threat type, phase, location, confidence}`. Whether that wakes someone up is
  a config file, so it can be tuned per user without retraining and audited
  after a false alarm.
- **Threat type determines which axis matters.** Ballistic threats are a time
  problem — react at launch, city-wide, no geometry. Drones are a space problem
  — there is time, so precision is what matters.
- **The gazetteer comes before the model.** These channels write in terse local
  shorthand (`1х Борщагівки`, `Солома/Центр`, `2х над Києвом - Оболонь`).
  A closed dictionary — currently ~150 places and ~230 stems, mined from the
  corpus — resolves most of it deterministically and explainably; the model
  handles what is genuinely ambiguous.

## Repository layout

| Path | Purpose |
| --- | --- |
| `tools/export/tme.py` | t.me/s web-preview source: fetch + parse |
| `tools/export/backfill.py` | Parallel, resumable history walker |
| `tools/export/store.py` | SQLite schema, idempotent writes, progress |
| `tools/export/normalize.py` | Text normalization, promo-footer stripping |
| `tools/export/export.py` | Export CLI |
| `tools/export/mtproto.py` | Deferred MTProto path (unwired, see below) |
| `tools/nlp/` | Gazetteer with morphology, and threat/modality hints |
| `tools/analysis/` | Pattern mining and typo mining over the corpus |
| `tools/labeler/` | Builds the self-contained labeling page |
| `labels/` | Ground truth — **committed**, unlike `data/` |
| `tools/tests/` | Tests, with real captured HTML fixtures |
| `docs/` | Setup and design documentation |
| `data/` | Database and logs — **git-ignored** |

## Data source

Public channels expose their whole feed as plain HTML at `t.me/s/<channel>` —
**no account, no phone number, no API key**. Measured on 2026-08-27 against the
three Kyiv monitoring channels:

| Property | Measured |
| --- | --- |
| `?before=<id>` with an arbitrary id | works — history is random-access |
| `?after=<id>` when nothing is new | ~5 KB (vs ~9 KB gzipped for a full page) |
| Full page, gzipped / uncompressed | 9.4 KB / 113 KB |
| ETag / Last-Modified | not offered — conditional GET impossible |
| New post visible after | ~2 s |
| Sustained 1.25 req/s, 12 requests | no rate limiting |
| Full history, all three channels | ~6 900 requests |

The page does not update itself; a refresh is one HTTP request, which is what
the poller does. At a 5 s poll the feed runs 2-6 s behind the channel.

### Why not MTProto

MTProto would push instead of poll and would report edits and deletions, which
the HTML source cannot see. It needs a user session, therefore a phone number,
therefore either an anonymous Telegram number or an SMS rental — and a rented
number is a poor fit for long-lived infrastructure, because re-verification
(triggered by, say, moving the session to a server in another country) would
lose the account permanently.

That decision is deferred, not rejected: `mtproto.py` keeps a working
implementation, unwired and untested. Even after a switch, the HTML source stays
useful as a cross-check for messages the ingest missed.

## Setup

```bash
python -m pip install -r requirements.txt
```

No credentials are required for the export.

## Exporting channel history

```bash
# One channel, recent days — smoke test
python -m tools.export.export --channel mon1tor_ua --since 2026-08-26

# Last month, all channels — the labeling set
python -m tools.export.export --since 2026-07-27

# Full history from channel creation (~6900 requests, ~1 h at 2 req/s)
python -m tools.export.export

# What is left to do
python -m tools.export.export --status
```

The export is **resumable and idempotent**. History is split into id blocks,
each with its own cursor; interrupt it and re-run the same command to continue.
Re-running a finished export adds nothing.

`--rps` bounds the global request rate and is the real throughput limit;
`--workers` only keeps that many block walks in flight. A 429 slows every
worker, not just the one that hit it.

### Two parsing traps worth knowing about

- A message's own text is `js-message_text`; a **quoted reply** is
  `js-message_reply_text` and appears *first* in document order. Anchoring on
  the shared `tgme_widget_message_text` class silently replaces every reply's
  text with the older quoted message. `test_own_text_is_never_the_quoted_text`
  guards this.
- Message ids are **not contiguous** — deleted messages leave gaps — so the
  backfill must follow the cursor the server returns rather than stepping the id
  by a page size.

### Quoted replies are stored, and they matter

Roughly 28% of messages in `mon1tor_ua` are replies, and the channel uses them
to track one target through its life:

```
39981  Шахед над Позняками
39983  Шахед над Голосієвом   → reply_to=39981   (same drone, moved)
39984  Шахед на Троєщину
39986  Збито                  → reply_to=39984   (episode closed)
```

`"Збито"` on its own is noise; with the quoted text it closes an episode. Both
`reply_to` and the quoted text are stored, so the reply chain gives target
identity across messages for free.

Reactions are deliberately not parsed.

## Labeling

```bash
python -m tools.labeler.build --since 2026-07-27
```

Writes `data/labeler.html` — a self-contained page, no server and no
dependencies. Open it, work a night, press **Експорт JSONL**, and save the
download over `labels/moments.jsonl`.

Keys: `j`/`k` move, `n` notify, `s` silent, `1`/`2`/`3` level, `Enter` save,
`x` delete, `f` cycle filter, `[`/`]` change night.

Each message is pre-filled by `tools/nlp/` — scope, threat, alarm sound,
modality, certainty, and whether the live-threat evidence is strong or only an
emoji. The same module runs in the baseline, so correcting a pre-fill while
labeling is also feedback on the baseline.

See [docs/labeling-schema.md](docs/labeling-schema.md) for what the fields mean
and how the harness scores them.

## Tests

```bash
python -m pytest tools/tests -q
```

Parser tests run against real HTML captured from deep history
(`tools/tests/fixtures/`), so their content is stable.

## Documentation

- [Oracle Cloud Free Tier setup (zero-charge guide)](docs/oracle-cloud-setup.md)
- [Next steps](docs/next-steps.md)
