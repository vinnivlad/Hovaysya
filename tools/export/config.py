"""Static configuration for the export tool."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Telegram monitoring channels, by username (no @).
# Adding one? Put it above `alarm_kyiv`, or anywhere except after it.
#
# **The official channel must stay last.** The page timestamps carry seconds and
# nothing finer, and three messages sharing a second is ordinary, so at equal
# times the order is decided by the order the channels were asked -- the sort is
# stable. Asking the siren last means a chat message from the same second is
# folded in first, and the siren then arrives already knowing what it is about.
# `tools/live/run.py` re-sorts to enforce this, so a mistake here is corrected
# rather than fatal; keeping the order right anyway means the two agree.
CHANNELS = (
    "kievinform_ua1",
    "war_monitor",
    "mon1tor_ua",
    # The official siren state for the city, and nothing else: this channel
    # relays the "Повітряна тривога" app's bot and posts exactly two forms,
    # "🚨 м. Київ / Повітряна тривога" and "🟢 м. Київ / Відбій повітряної
    # тривоги". He found it, and it closes the one gap the chat channels could
    # never fill — they report sirens, they do not declare them.
    #
    # Checked against the official app on 2026-08-28: the app declared Kyiv at
    # 08:04 and this channel posted at 08:04:15, while `kievinform_ua1` had
    # already said a bare "🛑 ТРИВОГА" at 07:50 for a district.
    "alarm_kyiv",
    # A live tracker in conversational Ukrainian, and the only channel measured
    # to be *first* about his own ring: 26 times in three days, against 41 live
    # ring mentions total. One of those firsts put a ballistic warning five
    # minutes ahead of every other source.
    #
    # `kyivalarm` and `kyivnow` were measured the same way and left out — see
    # docs/pattern-findings.md.
    "monitoring_kyiv",
    # Added 2026-09-02, after `tools/bench/channel.py` on the 46 nights where all
    # five of the above exist. Before that window the comparison is meaningless:
    # `kievinform_ua1` only starts on 19.07, so anything earlier "leads" us
    # merely because we were not watching.
    #
    # The most useful source about his own ring after `monitoring_kyiv`: 561 ring
    # mentions, and 276 of them arrived when our five had said nothing about the
    # ring for ten minutes. Replayed through the policy it moves 29 wake-ups
    # earlier -- 8 of them by more than a minute -- and adds 20 bells across 46
    # nights, which is 0.4 a night. Almost every added bell names Жуляни, so by
    # his own rule they are coverage rather than noise.
    "nebo_raketa",
    # Two messages a day, and the cleanest source measured: 248 of them state a
    # class about here and 244 arrive while a Kyiv alert is actually on. Zero
    # noise in a year, which none of the other five manages.
    #
    # It names his ring once a year, so it is not a monitor -- it is a second
    # clock on ballistic, and it costs nothing at all: **+0 bells** across the 46
    # nights, because its bells replace ours rather than adding to them, while
    # moving seven of them earlier.
    #
    # `KyivPolitic` was measured beside these two and left out. It does lead, but
    # with aftermath -- "В Соломенском районе повреждено здание школы", "Жуляны,
    # момент прилета «Шахеда»" -- which the policy vetoes by design, and it would
    # have cost a second language in the gazetteer for it.
    "rocketskyiv",
)

DB_PATH = REPO_ROOT / "data" / "messages.db"
SESSION_PATH = REPO_ROOT / "data" / "session" / "hovaysya"
