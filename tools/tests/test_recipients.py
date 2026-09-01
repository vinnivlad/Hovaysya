"""Deciding for more than one person from one reading.

His question is what this answers: "як сервер може вирішити що варте звуку?
Локація і коло у кожного користувача своя". The reading is shared, the last step
is personal, and the last step is what costs almost nothing.
"""
import dataclasses
import time

from tools.policy.config import load
from tools.policy.episodes import Tracker, observe, read
from tools.policy.recipients import Recipient, decide_all, only


def _quiet(*_a, **_k):
    pass


ZHULIANY = load(warn=_quiet)
OBOLON = dataclasses.replace(
    ZHULIANY, home="Оболонь",
    ring=("Оболонь", "Пуща-Водиця", "Мінський масив"))


def _two():
    return [Recipient("Жуляни", ZHULIANY), Recipient("Оболонь", OBOLON)]


def test_the_same_message_means_different_things_to_two_people():
    """The whole point. One drone, two districts, opposite answers."""
    got = {}
    for who, obs, dec in decide_all(
            read(0, "⚠️Реактивний шахед на Жуляни.", False, "mon1tor_ua"),
            _two()):
        got[who.name] = (obs.scope, dec.audible)
    assert got["Жуляни"] == ("my-area", True)
    assert got["Оболонь"] == ("city", False)


def test_the_city_wide_threat_reaches_everyone():
    """A ring is not a filter on everything: minutes of ballistic flight leave no
    room to find out whose street, so the city is near enough for both."""
    for _who, _obs, dec in decide_all(
            read(0, "❗Балістика на Київ.", False, "mon1tor_ua"), _two()):
        assert dec.audible


def test_nobody_inherits_anybody_else_s_episode():
    """The subtle one. Episode state is what makes a repeat a repeat, so sharing
    it would silence one person because another had already been told."""
    people = _two()
    for text in ("❗Балістика на Київ.", "Жуляни"):
        decide_all(read(0, text, False, "mon1tor_ua"), people)
    a, b = (p.tracker.episode for p in people)
    assert a is not b
    assert a.ring_seen != b.ring_seen        # his place seen, hers not


def test_one_reading_serves_all_of_them():
    """Not a style point: re-reading per person is 0.052 ms of gazetteer and
    0.579 ms of hints each time, and it is the same answer every time."""
    calls = []
    from tools.nlp import hints as h

    real = h.suggest
    h.suggest = lambda text: (calls.append(text), real(text))[1]
    try:
        reading = read(0, "❗Балістика на Київ.", False, "mon1tor_ua")
        decide_all(reading, [Recipient(f"n{i}", ZHULIANY) for i in range(10)])
    finally:
        h.suggest = real
    assert len(calls) == 1


def test_a_hundred_recipients_cost_about_twice_one():
    """Measured rather than asserted in prose, because the whole design of
    keeping the decision on the server rests on this number. Generous bound: the
    measurement is ~2.1x, and CI on a cold box is not a benchmark rig."""
    text = "❗2 балістичні ракети на Жуляни, Чабани."

    def run(n):
        people = [Recipient(f"n{i}", ZHULIANY) for i in range(n)]
        start = time.perf_counter()
        for _ in range(200):
            decide_all(read(0, text, False, "mon1tor_ua"), people)
        return time.perf_counter() - start

    one, many = run(1), run(100)
    assert many < one * 12, (one, many)


def test_the_old_single_person_call_still_works():
    """`observe()` is the two halves together, and almost everything wants that
    -- the tests, the eval, the replay. Only the watcher has N above one."""
    a = observe(0, "Жуляни", False, "mon1tor_ua", config=ZHULIANY)
    b = decide_all(read(0, "Жуляни", False, "mon1tor_ua"),
                   [Recipient("я", ZHULIANY)])[0][1]
    assert (a.scope, a.ring_places, a.home) == (b.scope, b.ring_places, b.home)


def test_only_builds_the_world_as_it_is_today():
    people = only(ZHULIANY)
    assert len(people) == 1 and people[0].config is ZHULIANY
    assert isinstance(people[0].tracker, Tracker)
