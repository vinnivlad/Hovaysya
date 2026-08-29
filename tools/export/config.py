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
    # `kyivalarm`, `kyivnow` and `KyivPolitic` were measured the same way and
    # left out — see docs/pattern-findings.md.
    "monitoring_kyiv",
)

DB_PATH = REPO_ROOT / "data" / "messages.db"
SESSION_PATH = REPO_ROOT / "data" / "session" / "hovaysya"
