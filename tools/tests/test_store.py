import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.export import store
from tools.export.store import Msg


def msg(channel: str, mid: int, ts: int, text: str = "Балістика на Київ") -> Msg:
    return Msg(channel=channel, message_id=mid, ts=ts, text_raw=text)


def open_db(tmp_path):
    return store.connect(tmp_path / "t.db")


def test_insert_and_count(tmp_path):
    conn = open_db(tmp_path)
    added = store.insert_messages(conn, [msg("a", 1, 1000), msg("a", 2, 2000)])
    assert added == 2


def test_reinserting_same_messages_is_a_noop(tmp_path):
    conn = open_db(tmp_path)
    rows = [msg("a", 1, 1000), msg("a", 2, 2000)]
    assert store.insert_messages(conn, rows) == 2
    assert store.insert_messages(conn, rows) == 0
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert total == 2


def test_same_message_id_in_different_channels_coexists(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(conn, [msg("a", 7, 1000), msg("b", 7, 1000)])
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert total == 2


def test_resume_id_is_zero_for_unknown_channel(tmp_path):
    conn = open_db(tmp_path)
    assert store.resume_id(conn, "nope") == 0


def test_resume_id_tracks_highest_id_per_channel(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(conn, [msg("a", 5, 1000), msg("a", 41, 2000), msg("b", 9, 1)])
    assert store.resume_id(conn, "a") == 41
    assert store.resume_id(conn, "b") == 9


def test_text_is_normalized_on_write(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(
        conn, [msg("a", 1, 1000, "Вибухи в Києві\n\n📢 Підписатися")]
    )
    row = conn.execute("SELECT text_raw, text_norm FROM messages").fetchone()
    assert "Підписатися" in row["text_raw"]
    assert row["text_norm"] == "Вибухи в Києві"


def test_fingerprint_matches_across_channels_for_same_event(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(
        conn,
        [
            msg("a", 1, 1000, "🔴 Балістика на Київ!"),
            msg("b", 1, 1005, "балістика на київ"),
        ],
    )
    fps = [r["fingerprint"] for r in conn.execute("SELECT fingerprint FROM messages")]
    assert fps[0] == fps[1]


def test_media_only_message_stores_null_fingerprint(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(conn, [msg("a", 1, 1000, "")])
    row = conn.execute("SELECT text_norm, fingerprint FROM messages").fetchone()
    assert row["text_norm"] == ""
    assert row["fingerprint"] is None


def test_update_channel_records_coverage(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(conn, [msg("a", 1, 1_700_000_000), msg("a", 4, 1_700_009_999)])
    store.update_channel(conn, "a", "Test Channel")
    row = conn.execute("SELECT * FROM channels WHERE channel='a'").fetchone()
    assert row["title"] == "Test Channel"
    assert row["max_id"] == 4
    assert row["first_ts"] == 1_700_000_000
    assert row["last_ts"] == 1_700_009_999


def test_update_channel_keeps_title_when_called_without_one(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(conn, [msg("a", 1, 1000)])
    store.update_channel(conn, "a", "Original")
    store.update_channel(conn, "a", None)
    row = conn.execute("SELECT title FROM channels WHERE channel='a'").fetchone()
    assert row["title"] == "Original"


def test_summary_reports_per_channel_text_counts(tmp_path):
    conn = open_db(tmp_path)
    store.insert_messages(
        conn,
        [
            msg("a", 1, 1_700_000_000, "Балістика"),
            msg("a", 2, 1_700_000_100, ""),
            msg("b", 1, 1_700_000_200, "БпЛА"),
        ],
    )
    rows = {r["channel"]: r for r in store.summary(conn)}
    assert rows["a"]["total"] == 2
    assert rows["a"]["with_text"] == 1
    assert rows["b"]["total"] == 1


def test_date_utc_is_derived_from_ts():
    assert msg("a", 1, 1_700_000_000).date_utc.startswith("2023-11-14T")
