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
# --- appearing without a restart --------------------------------------------

RAID = (
    (0, "alarm_kyiv", "🛑 Повітряна тривога в м. Київ"),
    (60, "mon1tor_ua", "⚠️Реактивний шахед на Житомир."),
    (90, "mon1tor_ua", "⚠️2 реактивні шахеди на Жуляни та Вишневе."),
)


def _corpus(tmp_path, at):
    """A database holding one raid, timestamped to just before `at`."""
    import sqlite3

    from tools.export import store

    conn = store.connect(tmp_path / "messages.db")
    conn.row_factory = sqlite3.Row
    for offset, channel, text in RAID:
        conn.execute(
            "INSERT INTO messages (channel, message_id, ts, date_utc, "
            "text_raw, text_norm, fingerprint) VALUES (?,?,?,?,?,?,?)",
            (channel, offset, at - 300 + offset, "", text, text,
             f"f{offset}"))
    conn.commit()
    return conn


def _dir_with(tmp_path, **configs):
    """A recipients directory as the API would have written it."""
    import json

    from tools.policy import tokens as people

    directory = tmp_path / "recipients"
    directory.mkdir(exist_ok=True)
    index = {}
    for name, changes in configs.items():
        index[people.hashed(name)] = name
        (directory / f"{name}.json").write_text(
            json.dumps(changes, ensure_ascii=False), encoding="utf-8")
    people.write_index(index, directory)
    return directory


def test_somebody_who_registers_mid_raid_is_taken_on_next_poll(tmp_path):
    """His answer to needing a restart: "чому б спостерігачу не перевіряти, чи
    не зʼявився новий користувач, і просто не включати його в обробку на
    наступній ітерації? Безшовно і не треба нічого перезапускати."
    """
    import time

    from tools.live.run import Session, handle, refresh_recipients
    from tools.policy.config import load as load_config
    from tools.policy.recipients import TELEGRAM_NAME
    from tools.policy.status import ALERT, snapshot

    now = time.time()
    conn = _corpus(tmp_path, now)
    cfg = load_config(warn=lambda _m: None)

    session = Session()
    session.tracker.official_source = True
    for offset, channel, text in RAID:
        handle(session, channel, offset, int(now) - 300 + offset, text,
               False, now)
    assert snapshot(session.recipients[0], now=int(now))["state"] == ALERT

    directory = _dir_with(tmp_path, оля={"home": "Виноградар"})
    notes = refresh_recipients(session, conn, directory, cfg, now)

    # He is still there. The fallback recipient used to appear only when the
    # index was empty, so the first stranger to install the app would have
    # replaced him and the Telegram bell -- the only delivery there is today --
    # would have stopped with nothing in the log to say why.
    assert [who.name for who in session.recipients] == [TELEGRAM_NAME, "оля"], notes
    olya = session.recipients[1]
    assert olya.config.home == "Виноградар"
    # Warmed, so the screen tells the truth from the first moment rather than
    # saying "без загроз" into a running raid.
    assert snapshot(olya, now=int(now))["state"] == ALERT, notes

    # ...and the warm-up left its lines in the log, which is the half I had got
    # wrong twice. He found it both times -- "на мого користувача ховайся не
    # підтягнув повідомлень" -- because `warm_one` discarded its rows while the
    # watcher's own start-up warm keeps its own and marks them `warm`. With the
    # two paths disagreeing, every deploy restart left `telegram_channel` with
    # ninety minutes of lines and anybody who registered through the app with
    # none. `/decisions` is served from this log and `said` is filtered out of
    # it, so empty here means an empty screen and an empty feed.
    hers = [row for row in session.log if row.get("who") == olya.name]
    assert hers, notes
    assert all(row.get("warm") for row in hers), "replayed, not announced"
    assert any(row.get("said") for row in hers), hers[:3]
    # And her tracker knows the siren is being watched. Set on the first
    # recipient's tracker alone, everyone after the first would read a chat
    # channel's "ТРИВОГА" as the siren itself.
    assert olya.tracker.official_source is True


def test_a_settings_change_is_picked_up_without_forgetting_the_raid(tmp_path):
    """"Користувачі мають мати можливість змінювати свій конфіг. Можливо навіть
    автоматично, при переміщенні містом." A watcher holding the old home would
    ring for the old ring until a deploy.

    The tracker survives it: the episode is about the sky, not about them, and
    dropping it because somebody moved would forget the alert that is running.
    """
    import time

    from tools.live.run import Session, handle, refresh_recipients
    from tools.policy.config import load as load_config

    now = time.time()
    conn = _corpus(tmp_path, now)
    cfg = load_config(warn=lambda _m: None)

    directory = _dir_with(tmp_path, оля={"home": "Виноградар"})
    session = Session()
    refresh_recipients(session, conn, directory, cfg, now)
    olya = [who for who in session.recipients if who.name == "оля"][0]
    for offset, channel, text in RAID:
        handle(session, channel, offset, int(now) - 300 + offset, text,
               False, now)
    episode = olya.tracker.episode
    assert episode is not None

    _dir_with(tmp_path, оля={"home": "Жуляни", "radius_km": 3})
    notes = refresh_recipients(session, conn, directory, cfg, now)

    assert "~оля" in notes, notes
    assert olya in session.recipients, "the same person, not a new one"
    assert olya.config.home == "Жуляни"
    assert olya.tracker.config.home == "Жуляни"
    assert olya.announcer.config.home == "Жуляни"
    assert olya.tracker.episode is episode, "the raid was forgotten"


def test_the_directory_is_only_read_when_it_changes(tmp_path):
    """One `scandir` a poll is nothing beside seven HTTP fetches, but reloading
    every poll would rebuild trackers for no reason."""
    from tools.live.run import recipients_signature

    directory = _dir_with(tmp_path, оля={"home": "Виноградар"})
    first = recipients_signature(directory)
    assert first == recipients_signature(directory)

    _dir_with(tmp_path, оля={"home": "Виноградар"}, петро={"home": "Жуляни"})
    assert recipients_signature(directory) != first
    # A directory that is not there yet is not an error.
    assert recipients_signature(tmp_path / "absent") == ()
def test_the_telegram_recipient_is_a_user_that_always_exists(tmp_path):
    """His call, and it settles what I had made conditional: "телеграм - нехай
    буде користувач за замовченням який завжди вже створений в системі."

    It is not a fallback for an empty index. `from_dir` used to return it only
    when there were no names, which was invisible for as long as nobody could
    register -- and open registration would have made it a silent fault: the
    first stranger to install the app takes its place, and the Telegram bell,
    the only delivery there is today, stops with nothing anywhere to say why.
    """
    from tools.policy.config import DEFAULTS
    from tools.policy.recipients import TELEGRAM_NAME, from_dir

    for configs in ({}, {"оля": {"home": "Виноградар"}},
                    {"оля": {"home": "Виноградар"},
                     "петро": {"home": "Жуляни"}}):
        directory = _dir_with(tmp_path, **configs)
        names = [who.name for who in from_dir(directory, fallback=DEFAULTS)]
        assert names[0] == TELEGRAM_NAME, names
        assert names.count(TELEGRAM_NAME) == 1, names
        assert len(names) == len(configs) + 1, names
        for path in directory.glob("*.json"):
            if path.name != "index.json":
                path.unlink()

    # Its settings come from `hovaysya.json` and never from this directory, so
    # there is nothing here for anybody to layer over his ring.
    assert not (directory / f"{TELEGRAM_NAME}.json").exists()

    # And the plain reading of the index is still available.
    directory = _dir_with(tmp_path, оля={"home": "Виноградар"})
    plain = [who.name for who in from_dir(directory, fallback=DEFAULTS,
                                          telegram=None)]
    assert plain == ["оля"], plain


def test_nobody_can_register_as_the_telegram_recipient(tmp_path):
    """A stranger under that name would have had their own settings file layered
    over his ring, because that is where `config_of` looks."""
    from tools.policy import tokens as people

    for chosen in (people.TELEGRAM_NAME, people.TELEGRAM_NAME.upper()):
        name = people.register(people.hashed(chosen), chosen, tmp_path)
        assert name.casefold() != people.TELEGRAM_NAME.casefold(), name
