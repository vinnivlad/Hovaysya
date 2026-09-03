"""The broom for recipients nobody can unregister any more."""

from __future__ import annotations

import json

from tools import people
from tools.policy import tokens


def _index(directory, entries):
    directory.mkdir(parents=True, exist_ok=True)
    tokens.write_index(entries, directory)


def test_it_lists_who_the_watcher_decides_for(tmp_path, capsys):
    _index(tmp_path, {"aaaa1111": "Володимир", "bbbb2222": "test"})
    (tmp_path / "Володимир.json").write_text(
        json.dumps({"home": "Жуляни"}), encoding="utf-8")

    people.show(tmp_path)
    out = capsys.readouterr().out

    assert tokens.TELEGRAM_NAME in out
    assert "Володимир" in out and "Жуляни" in out
    assert "test" in out


def test_forgetting_by_digest_prefix(tmp_path):
    _index(tmp_path, {"aaaa1111": "Володимир", "bbbb2222": "test"})
    (tmp_path / "test.json").write_text(json.dumps({"home": "Жуляни"}),
                                        encoding="utf-8")

    assert people.forget(tmp_path, "bbbb") == 0
    assert tokens.index(tmp_path) == {"aaaa1111": "Володимир"}
    assert not (tmp_path / "test.json").exists(), "settings go with the person"


def test_forgetting_by_name_when_it_is_unique(tmp_path):
    _index(tmp_path, {"aaaa1111": "Володимир", "bbbb2222": "test"})

    assert people.forget(tmp_path, "test") == 0
    assert list(tokens.index(tmp_path).values()) == ["Володимир"]


def test_a_repeated_name_is_refused_rather_than_guessed(tmp_path, capsys):
    """His rule: "май на увазі що імена можуть повторюватись". Deleting the
    wrong one is not recoverable from here."""
    _index(tmp_path, {"aaaa1111": "оля", "bbbb2222": "оля"})

    assert people.forget(tmp_path, "оля") == 1
    assert len(tokens.index(tmp_path)) == 2, "nothing removed"
    assert "неоднозначно" in capsys.readouterr().err


def test_an_unknown_name_changes_nothing(tmp_path):
    _index(tmp_path, {"aaaa1111": "Володимир"})

    assert people.forget(tmp_path, "нікого") == 1
    assert len(tokens.index(tmp_path)) == 1


def test_the_telegram_recipient_cannot_be_forgotten(tmp_path, capsys):
    """It is not in the index -- it exists unconditionally, by his decision --
    so there is nothing here that could remove it. Worth a test because the
    alternative is a watcher with no way to ring his phone."""
    _index(tmp_path, {"aaaa1111": "Володимир"})

    assert people.forget(tmp_path, tokens.TELEGRAM_NAME) == 1
    assert len(tokens.index(tmp_path)) == 1
