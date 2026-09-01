"""Pre-labelling a night, and the one thing it must never do.

His instruction was "спочатку розміть все по вже існуючим правилам. Я буду тільки
коригувати". The danger that comes with it is that machine-made labels look
exactly like his, and labels scored against the policy that made them report a
perfect night while measuring nothing.
"""
import json

import pytest

from tools.labeler.build import load_labels
from tools.labeler.prefill import SILENT_REASONS, silent_reason


def test_a_rule_names_its_silent_reason_and_the_rest_are_left_blank():
    """The reason strings were written against the schema's four, which is why
    the front of them can be trusted -- and why anything else must stay empty
    rather than be guessed into a category he would then have to undo."""
    assert silent_reason("too-far: another oblast") == "too-far"
    assert silent_reason("already-notified: same ballistic wave") == "already-notified"
    assert silent_reason("not a threat") is None
    assert set(SILENT_REASONS) == {"too-far", "already-notified",
                                  "resolved", "insufficient"}


def test_prefilling_leaves_his_own_labels_alone(monkeypatch, tmp_path, capsys):
    """Per label, not per night. The first version refused any night that had a
    hand label, and three corrections then blocked the scaffolding for the other
    693 messages -- which is how a 696-message night actually gets reviewed, in
    more than one sitting."""
    from tools.labeler import prefill

    monkeypatch.setattr(prefill, "load_all", lambda *a, **k: (
        [{"night": "2026-08-31", "id": "keep-me"}], {}))
    monkeypatch.setattr(prefill, "build", lambda night, db: [
        {"id": "keep-me", "night": night, "prefilled": True},
        {"id": "fresh", "night": night, "prefilled": True, "decision": "silent"},
    ])
    out = tmp_path / "p.jsonl"
    monkeypatch.setattr("sys.argv", ["prefill", "--night", "2026-08-31",
                                     "--out", str(out)])
    prefill.main()

    written = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in written] == ["fresh"]
    assert "не торкаюсь" in capsys.readouterr().out


def test_the_page_keeps_his_label_over_a_prefilled_one(tmp_path, capsys):
    """The second safeguard, also by id: scaffolding for a message he has not
    reached is welcome, scaffolding over one he has decided is not."""
    from tools.labeler.load import load_all

    taken = next(l["id"] for l in load_all()[0])
    scaffold = tmp_path / "prefill.jsonl"
    scaffold.write_text(
        json.dumps({"id": taken, "night": "2026-08-04", "prefilled": True})
        + chr(10)
        + json.dumps({"id": "y-01", "night": "1999-01-01", "prefilled": True})
        + chr(10), encoding="utf-8")

    labels = load_labels([scaffold])
    assert any(l["id"] == "y-01" for l in labels)        # the untouched one lands
    assert not any(l["id"] == taken and l.get("prefilled") for l in labels)
    assert "пропущено" in capsys.readouterr().out
