"""Tests for the labeling page builder.

The UI itself is exercised by hand; what is tested here is the logic that would
silently corrupt data — night bucketing, the Kyiv offset, and the stable
message key that labels anchor to.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.export import store
from tools.export.store import Msg
from tools.labeler import build


def ts(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


# --- Kyiv offset ----------------------------------------------------------


def test_summer_time_is_plus_three():
    assert build.kyiv_offset(ts(2026, 8, 27, 4)) == 3
    assert build.kyiv_offset(ts(2026, 4, 15, 12)) == 3


def test_winter_time_is_plus_two():
    assert build.kyiv_offset(ts(2026, 1, 10, 12)) == 2
    assert build.kyiv_offset(ts(2026, 12, 20, 12)) == 2


def test_offset_switches_at_the_last_sunday_of_march():
    assert build.kyiv_offset(ts(2026, 3, 28, 12)) == 2
    assert build.kyiv_offset(ts(2026, 3, 30, 12)) == 3


def test_offset_switches_back_at_the_last_sunday_of_october():
    assert build.kyiv_offset(ts(2026, 10, 24, 12)) == 3
    assert build.kyiv_offset(ts(2026, 10, 26, 12)) == 2


# --- night bucketing -----------------------------------------------------


def test_an_attack_spanning_midnight_stays_in_one_night():
    """Peak traffic is 00:00-04:00 Kyiv; splitting it across two nights would
    break the labeling flow exactly where the work is."""
    evening = ts(2026, 8, 26, 19)      # 22:00 Kyiv, 26 Aug
    after_midnight = ts(2026, 8, 27, 1)  # 04:00 Kyiv, 27 Aug
    assert build.night_id(evening) == build.night_id(after_midnight) == "2026-08-26"


def test_afternoon_starts_a_new_night():
    before = ts(2026, 8, 27, 11)  # 14:00 Kyiv
    after = ts(2026, 8, 27, 13)   # 16:00 Kyiv
    assert build.night_id(before) == "2026-08-26"
    assert build.night_id(after) == "2026-08-27"


# --- payload -------------------------------------------------------------


def make_db(tmp_path):
    conn = store.connect(tmp_path / "m.db")
    store.insert_messages(conn, [
        Msg("mon1tor_ua", 100, ts(2026, 8, 26, 21), "⚠️1 реактивний шахед на Жуляни."),
        Msg("kievinform_ua1", 200, ts(2026, 8, 27, 1), "Жуляни ✈️"),
        Msg("war_monitor", 300, ts(2026, 8, 27, 2), "5-7 Чернігівщина."),
    ])
    conn.close()
    return tmp_path / "m.db"


def load(tmp_path, db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    msgs = build.load_messages(conn, None)
    conn.close()
    return msgs


def test_messages_carry_a_stable_key_not_an_index(tmp_path):
    msgs = load(tmp_path, make_db(tmp_path))
    keys = [m["k"] for m in msgs]
    assert keys == ["mon1tor_ua/100", "kievinform_ua1/200", "war_monitor/300"]
    assert not any("i" in m for m in msgs)


def test_hints_are_prefilled(tmp_path):
    msgs = load(tmp_path, make_db(tmp_path))
    zh = next(m for m in msgs if m["id"] == 100)
    assert zh["s"] == "my-area"
    assert zh["th"] == "shahed-jet"
    assert zh["al"] == "drone-jet"
    assert zh["m"] == "live-threat"
    assert zh["st"] == "strong"


def test_bare_place_message_is_prefilled_as_live(tmp_path):
    msgs = load(tmp_path, make_db(tmp_path))
    bare = next(m for m in msgs if m["id"] == 200)
    assert bare["m"] == "live-threat"
    assert bare["th"] == "unknown"
    assert bare["s"] == "my-area"


def test_other_regions_are_marked_elsewhere(tmp_path):
    msgs = load(tmp_path, make_db(tmp_path))
    far = next(m for m in msgs if m["id"] == 300)
    assert far["s"] == "elsewhere"


def test_nights_group_and_count_correctly(tmp_path):
    msgs = load(tmp_path, make_db(tmp_path))
    nights = build.build_nights(msgs)
    assert [n["id"] for n in nights] == ["2026-08-26"]
    assert nights[0]["count"] == 3
    assert nights[0]["near"] == 2
    assert nights[0]["relevant"] == 2


def test_kyiv_time_is_shown_not_utc(tmp_path):
    msgs = load(tmp_path, make_db(tmp_path))
    zh = next(m for m in msgs if m["id"] == 100)
    assert zh["hm"] == "00:00"  # 21:00 UTC + 3


def test_payload_survives_a_script_tag_in_the_text(tmp_path):
    """A message containing </script> would otherwise close the data block."""
    conn = store.connect(tmp_path / "s.db")
    store.insert_messages(conn, [
        Msg("mon1tor_ua", 1, ts(2026, 8, 26, 21), "текст </script> далі"),
    ])
    conn.close()
    out = tmp_path / "page.html"
    assert build.main(["--db", str(tmp_path / "s.db"), "--out", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    body = html.split('type="application/json">')[1].split("</script>")[0]
    payload = json.loads(body.replace(chr(60) + chr(92) + chr(47), chr(60) + chr(47)))
    assert payload["messages"][0]["x"] == "текст </script> далі"


# --- page structure -------------------------------------------------------


def test_page_javascript_is_structurally_sound():
    """No JS engine here, so this is the closest thing to a syntax check.
    It catches the failure mode that renders the whole page blank."""
    from tools.labeler import checkjs

    js = checkjs.extract_js(checkjs.TEMPLATE.read_text(encoding="utf-8"))
    assert checkjs.problems(js) == []


def test_checkjs_detects_a_broken_structure():
    from tools.labeler import checkjs

    assert checkjs.problems("function f() { if (a) { return 1; }") != []
    assert checkjs.problems("const s = '}}}}'; function f() { return 1; }") == []


def test_every_threat_maps_to_an_alarm():
    """The form derives the sound from the type, so a gap would leave a
    notification with no channel to fire on."""
    from tools.nlp import hints

    for t in ("recon","shahed","shahed-jet","cruise","ballistic","kab",
              "aviation","mixed","unknown","none"):
        assert hints.alarm_for(t), t


def test_the_five_primary_types_have_five_distinct_sounds():
    """Knowing what is coming without opening your eyes only works if the
    reaction classes do not share a tone."""
    from tools.nlp import hints

    sounds = [hints.alarm_for(t) for t in
              ("recon", "shahed", "shahed-jet", "cruise", "ballistic")]
    assert len(set(sounds)) == 5, sounds
