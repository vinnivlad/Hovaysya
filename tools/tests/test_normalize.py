import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.export.normalize import (
    content_fingerprint,
    normalize_text,
    strip_footer,
)


def test_empty_and_none():
    assert normalize_text(None) == ""
    assert normalize_text("") == ""
    assert normalize_text("   \n\n  ") == ""


def test_collapses_whitespace_and_blank_lines():
    raw = "Київ\n\n\n  Загроза   БпЛА  \n"
    assert normalize_text(raw) == "Київ\nЗагроза БпЛА"


def test_preserves_line_structure_between_target_groups():
    raw = "БпЛА на півночі Київщини\nЩе група курсом на Бровари"
    out = normalize_text(raw)
    assert out.split("\n") == [
        "БпЛА на півночі Київщини",
        "Ще група курсом на Бровари",
    ]


def test_strips_invisible_characters():
    raw = "Київ​‎ — тривога﻿"
    assert normalize_text(raw) == "Київ — тривога"


def test_normalizes_nbsp():
    assert normalize_text("10 БпЛА") == "10 БпЛА"


def test_strips_subscribe_footer():
    raw = "Швидкісна ціль курсом на Київ!\n\n📢 Підписатися | Наш бот"
    assert normalize_text(raw) == "Швидкісна ціль курсом на Київ!"


def test_strips_bare_handle_and_link_footer():
    raw = "Вибухи в Києві\n@kievinform_ua1\nhttps://t.me/kievinform_ua1"
    assert normalize_text(raw) == "Вибухи в Києві"


def test_keeps_sentence_that_merely_mentions_a_bot():
    raw = "Інформація надійшла через бот для зв'язку від мешканця Позняків"
    assert "Позняків" in normalize_text(raw)


def test_footer_stripping_never_empties_a_content_only_message():
    raw = "Балістика на Київ, негайно в укриття"
    assert normalize_text(raw) == raw


def test_strip_footer_keeps_content_above_multiple_footer_lines():
    raw = "Загроза застосування балістики\n\nПідписатись\n@war_monitor\n"
    assert strip_footer(raw).strip() == "Загроза застосування балістики"


def test_fingerprint_ignores_emoji_punctuation_and_case():
    a = "🔴 Балістика на Київ!!!"
    b = "балістика на київ"
    assert content_fingerprint(a) == content_fingerprint(b)


def test_fingerprint_drops_urls():
    a = "Вибухи в Києві https://t.me/x/1"
    b = "Вибухи в Києві"
    assert content_fingerprint(a) == content_fingerprint(b)


def test_fingerprint_distinguishes_different_events():
    assert content_fingerprint("БпЛА на Обухів") != content_fingerprint(
        "БпЛА на Бровари"
    )
