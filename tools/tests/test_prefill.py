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


def test_prefilling_refuses_a_night_he_has_already_labelled(monkeypatch):
    """The one mistake that would destroy the only thing here that cannot be
    regenerated. A warning would not do: the output goes to a file, and nobody
    reads warnings from a command that appears to have worked."""
    from tools.labeler import prefill

    monkeypatch.setattr(prefill, "load_all",
                        lambda *a, **k: ([{"night": "2026-08-04"}], {}))
    monkeypatch.setattr("sys.argv", ["prefill", "--night", "2026-08-04"])
    with pytest.raises(SystemExit) as exc:
        prefill.main()
    assert "2026-08-04" in str(exc.value)


def test_prefilled_labels_never_override_a_labelled_night(tmp_path, capsys):
    """Two safeguards, and this is the second: even pointed at a labelled night
    by hand, the page keeps his."""
    scaffold = tmp_path / "prefill.jsonl"
    scaffold.write_text(
        json.dumps({"id": "x-01", "night": "2026-08-04", "prefilled": True})
        + chr(10)
        + json.dumps({"id": "y-01", "night": "1999-01-01", "prefilled": True})
        + chr(10), encoding="utf-8")

    labels = load_labels([scaffold])
    nights = {l["night"] for l in labels}
    assert "1999-01-01" in nights                       # the fresh night lands
    assert not any(l.get("prefilled") for l in labels
                   if l["night"] == "2026-08-04")       # ...his stays his
    assert "пропущено" in capsys.readouterr().out
