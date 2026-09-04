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

    for t in ("recon","shahed","shahed-jet","drone-rocket","cruise","ballistic",
              "kab","aviation","mixed","unknown","none"):
        assert hints.alarm_for(t), t


def test_the_five_primary_types_have_five_distinct_sounds():
    """Knowing what is coming without opening your eyes only works if the
    reaction classes do not share a tone."""
    from tools.nlp import hints

    sounds = [hints.alarm_for(t) for t in
              ("recon", "shahed", "shahed-jet", "cruise", "ballistic")]
    assert len(set(sounds)) == 5, sounds


# --- context carried forward ---------------------------------------------


def ctx_msgs(items):
    """items: (offset_seconds, text). Returns messages with context filled."""
    base = ts(2026, 8, 26, 21)
    conn = store.connect(Path(__file__).parent / "_ctx_tmp.db") if False else None
    msgs = []
    for off, text in items:
        from tools.nlp import hints
        from tools.nlp.gazetteer import resolve_scope

        guess = hints.suggest(text)
        msgs.append({
            "k": f"c/{off}", "n": "2026-08-26", "c": "c", "ch": "c", "id": off,
            "t": base + off, "hm": f"{build.kyiv_dt(base + off):%H:%M}",
            "x": text, "q": "", "r": None,
            "s": resolve_scope(text), "m": guess["modality"], "th": guess["threat"],
            "al": guess["alarm"], "ce": guess["certainty"], "st": guess["strength"],
            "sh": guess["shapes"], "p": [], "inf": [],
            "ith": None, "isc": None, "ifrom": None,
        })
    build.carry_context(msgs)
    return msgs


def test_a_continuation_inherits_the_stated_type():
    """"Вибухи" and "1х Центр." name no type; judging them alone is the mistake
    the schema opens by warning about."""
    m = ctx_msgs([
        (0, "⚠️3 реактивні шахеди на Київ."),
        (120, "1х Центр. / 1х Троєщина."),
    ])
    assert m[1]["th"] == "unknown"
    assert m[1]["ith"] == "shahed-jet"
    assert m[1]["ifrom"] == m[0]["hm"]


def test_a_continuation_inherits_the_place_when_it_names_none():
    m = ctx_msgs([
        (0, "⚠️1 реактивний шахед на Жуляни."),
        (60, "Збито"),
    ])
    assert m[1]["s"] == "unknown"
    assert m[1]["isc"] == "my-area"


def test_context_expires_rather_than_being_guessed():
    m = ctx_msgs([
        (0, "⚠️3 реактивні шахеди на Київ."),
        (20 * 60, "Вибухи"),
    ])
    assert m[1]["ith"] is None


def test_an_all_clear_resets_the_carry():
    """After "відбій" nothing is known to be in the air; inheriting across it
    would invent a threat."""
    m = ctx_msgs([
        (0, "⚠️3 реактивні шахеди на Київ."),
        (60, "🛑 Відбій тривоги"),
        (120, "Вибухи"),
    ])
    assert m[2]["ith"] is None


def test_a_stated_type_wins_over_the_inherited_one():
    m = ctx_msgs([
        (0, "⚠️3 реактивні шахеди на Київ."),
        (60, "❗Група ракет Калібр на Київ."),
    ])
    assert m[1]["th"] == "cruise"


def test_social_messages_do_not_inherit():
    m = ctx_msgs([
        (0, "⚠️3 реактивні шахеди на Київ."),
        (60, "Дуже вам вдячний за підтримку ❤️"),
    ])
    assert m[1]["ith"] is None
    assert m[1]["m"] == "non-threat"


# --- the feed filters on the effective scope, not the stated one -----------


def test_a_placeless_message_inherits_the_night_s_scope():
    from tools.labeler.build import carry_context

    """"Падає.", "5х РАКЕТ", "На зараз без цілей" name no place and never will.
    The only thing that can place them is the feed around them."""
    msgs = [
        {"t": 1000, "s": "my-area", "th": "shahed-jet", "hm": "01:19",
         "x": "⚠️2 реактивні шахеди на Жуляни",
         "m": "live-threat", "as": None, "ith": None, "isc": None, "ifrom": None},
        {"t": 1120, "s": "unknown", "th": "none", "hm": "01:21", "x": "⚠️Падає.",
         "m": "live-threat", "as": None, "ith": None, "isc": None, "ifrom": None},
    ]
    carry_context(msgs)
    assert msgs[1]["isc"] == "my-area"


def test_the_page_filters_on_the_inherited_scope():
    """A regression guard on the template, not on Python: the page was already
    computing the inherited scope and then filtering on the stated one, which
    hid 31 live messages a night behind a field it had already filled. The user
    found it because a reply's quoted parent was missing from the feed."""
    src = (Path(__file__).resolve().parents[1] / "labeler" / "template.html"
           ).read_text(encoding="utf-8")
    assert 'const eff = m =>' in src
    block = src[src.index("const FILTERS = ["):]
    block = block[:block.index(chr(10) + "];")]
    assert "eff(m)" in block
    # The stated scope must not be consulted directly anywhere in the filters.
    assert "m.s ===" not in block, block


def test_every_class_the_hints_can_emit_has_a_button_and_a_word():
    """The page is where a night gets labelled, so a class the prefill can
    produce with no button to confirm it is a class nobody can label -- and the
    prefill would sit there stating something the page has no word for.

    Caught when `drone-rocket` arrived: `hints` began emitting it over 357
    messages while the page still knew eleven classes."""
    from tools.nlp import hints

    src = (Path(__file__).resolve().parents[1] / "labeler" / "template.html"
           ).read_text(encoding="utf-8")
    rows = src[src.index("const THREATS_MAIN = ["):src.index("const MODALITIES")]
    alarms = src[src.index("const ALARM_FOR = {"):]
    alarms = alarms[:alarms.index("};")]
    words = src[src.index("  threat: {"):]
    words = words[:words.index("},")]
    for kind, _pattern in hints.THREAT_RULES:
        assert f'"{kind}"' in rows, kind
        assert kind in alarms, kind
        assert kind in words, kind


def test_a_stated_scope_is_never_overridden_by_an_inherited_one():
    """"Реактивний шахед на Кривий Ріг" says elsewhere and means it."""
    src = (Path(__file__).resolve().parents[1] / "labeler" / "template.html"
           ).read_text(encoding="utf-8")
    assert 'const eff = m => (m.s === "unknown" && m.isc) ? m.isc : m.s;' in src


def test_the_feed_says_when_the_filter_dropped_something():
    """Twice the user found a filter bug by noticing a reply whose quoted parent
    was nowhere on the page, because a gap in the feed looks exactly like a quiet
    minute. Between 01:10 and 01:19 on 2026-08-04 the near view drops 34
    messages in a row."""
    src = (Path(__file__).resolve().parents[1] / "labeler" / "template.html"
           ).read_text(encoding="utf-8")
    assert "function hiddenRuns()" in src
    assert "if (runs.has(ix)) gapRow(runs.get(ix));" in src
    # A run at the very end of the night has no following row to hang on.
    assert "if (runs.has(msgs.length)) gapRow(runs.get(msgs.length));" in src


def test_the_labelling_default_is_the_kyiv_view_not_the_near_one():
    """The near filter shows where a target already is; judging a moment needs
    where it was. On 2026-08-04 the near view showed "загроза пуску" at 01:10
    and "Падає" on ТЕЦ-5 at 01:19 with nine minutes of approach across the left
    bank missing — "Ні пуску ні підльоту нема"."""
    src = (Path(__file__).resolve().parents[1] / "labeler" / "template.html"
           ).read_text(encoding="utf-8")
    assert "let filterIx = 1;" in src
    block = src[src.index("const FILTERS = ["):]
    block = block[:block.index(chr(10) + "];")]
    assert block.count("{ id:") == 3
    assert block.index('id: "relevant"') > block.index('id: "near"')


def test_whatever_a_visible_message_quotes_is_visible_too():
    """A `↳` pointing at nothing is what sent the user looking, twice."""
    src = (Path(__file__).resolve().parents[1] / "labeler" / "template.html"
           ).read_text(encoding="utf-8")
    assert "function ancestors()" in src
    assert "|| ancestors().has(m.k)" in src
