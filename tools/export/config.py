"""Static configuration for the export tool."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Telegram monitoring channels, by username (no @).
CHANNELS = (
    "kievinform_ua1",
    "war_monitor",
    "mon1tor_ua",
)

DB_PATH = REPO_ROOT / "data" / "messages.db"
SESSION_PATH = REPO_ROOT / "data" / "session" / "hovaysya"
