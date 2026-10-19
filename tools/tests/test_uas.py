"""Tests for reading the city out of `UkraineAlarmSignal`.

The channel covers the whole country in a fixed format, and only the lines
about the city are ours. Every text below is a real post, trimmed only where
the list of other regions ran on.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.export.store import Msg
from tools.export.uas import CHANNEL, adapt, city_says

YELLOW = "🟡 Київ\nПовітряна тривога · жовтий рівень\nДронова загроза"
RED = "🔴 Київ\nПовітряна тривога · червоний рівень\nРакетна загроза"
LOWER = "🟡 Київ\nРівень знижено до жовтого\nДронова загроза"
CLEAR = "🟢 Київ\nВідбій повітряної тривоги"


def test_a_post_of_its_own_about_the_city():
    assert city_says("🟡 Київ\nЖовтий рівень тривоги. Прямуйте в укриття!") == YELLOW
    assert city_says("🔴 Київ\nЧервоний рівень тривоги. Прямуйте в укриття!") == RED
    assert city_says("🟢 Київ\nВідбій тривоги. Будьте обережні!") == CLEAR


def test_the_city_inside_a_list():
    assert city_says("🟡 Жовтий рівень тривоги\n• Київ\n"
                     "• Вишгородський район (Київська обл.)") == YELLOW
    assert city_says("🔴 Червоний рівень тривоги\n"
                     "• Бучанський район (Київська обл.)\n• Київ") == RED
    assert city_says("🟡 Відбій червоної тривоги\n• Київ\n"
                     "• Полтавський район (Полтавська обл.)") == LOWER
    assert city_says("🟢 Відбій тривоги\n• Київ\n"
                     "• Фастівський район (Київська обл.)") == CLEAR


def test_the_list_before_it_had_bullets():
    """Until about 2026-09-26 the places stood on bare lines."""
    assert city_says("🟡 Жовтий рівень тривоги\nКиїв\n"
                     "Вишгородський район (Київська обл.)") == YELLOW
    assert city_says("🟢 Відбій тривоги\nБучанський район (Київська обл.)\n"
                     "Ніжинський район (Чернігівська обл.)\nКиїв") == CLEAR


def test_the_section_decides_not_the_first_line():
    """Several events share a post, each under its own heading. Reading only
    the first one turned three city all-clears into sirens."""
    text = ("🔴 Червоний рівень тривоги\n• Чугуївський район (Харківська обл.)\n"
            "🟢 Відбій тривоги\n• Житомирський район (Житомирська обл.)\n"
            "• Київ\n• Бориспільський район (Київська обл.)")
    assert city_says(text) == CLEAR


def test_the_city_in_two_sections_is_the_siren():
    """The sections come in a fixed order -- lowered, raised, lifted -- and not
    in the order things happened, so a post that lifts the city and declares it
    again cannot say which came last. 2026-10-18 20:00:46 was the one such post
    in a month: the all-clear at 19:59:51, the next siren at 20:00:49."""
    text = ("🟡 Відбій червоної тривоги\n• Тульчинський район (Вінницька обл.)\n"
            "🟡 Жовтий рівень тривоги\n• Київ\n"
            "🟢 Відбій тривоги\n• Жмеринський район (Вінницька обл.)\n• Київ")
    assert city_says(text) == YELLOW


def test_the_oblast_is_not_the_city():
    assert city_says("🟡 Жовтий рівень тривоги\n"
                     "• Бориспільський район (Київська обл.)") is None
    assert city_says("🟢 Відбій тривоги\n• Київ (Київська обл.)") is None
    assert city_says("🟡 Бориспільський район (Київська обл.)\n"
                     "Жовтий рівень тривоги. Прямуйте в укриття!") is None


def test_threat_notices_are_not_sirens():
    """A drone threat, fast targets, explosions in the press: none of them is
    the siren, and the chats already carry what is flying."""
    for text in ("🛸 Київ\nЗагроза застосування БПЛА. Перейдіть в укриття!",
                 "🚀 Київ\nЗагроза застосування високошвидкісних цілей.",
                 "⚠️ Київ\nЗМІ повідомляють про вибухи. Будьте обережні!",
                 "Мапа тривог станом на 16:00 – 19 жовтня:"):
        assert city_says(text) is None


def _msg(i, text, channel=CHANNEL):
    return Msg(channel=channel, message_id=i, ts=1_760_000_000 + i,
               text_raw=text)


def test_only_the_city_goes_on():
    page = [_msg(1, "🟡 Полтавський район (Полтавська обл.)\n"
                    "Жовтий рівень тривоги. Прямуйте в укриття!"),
            _msg(2, "🟡 Київ\nЖовтий рівень тривоги. Прямуйте в укриття!"),
            _msg(3, "🛸 Київ\nЗагроза застосування БПЛА. Перейдіть в укриття!")]
    kept = adapt(page)
    assert [m.message_id for m in kept] == [2]
    assert kept[0].text_raw == YELLOW
    assert kept[0].ts == page[1].ts


def test_other_channels_pass_untouched():
    page = [_msg(1, "🛑 ТРИВОГА", channel="kievinform_ua1")]
    assert adapt(page) == page
