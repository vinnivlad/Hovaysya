"""Faults that live in the bytes of a source file rather than in its logic."""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Tab and newline are the only control characters a source file has any business
# containing. Carriage return is allowed because the working tree is Windows.
ALLOWED = {"\t", "\n", "\r"}


def test_no_control_characters_hide_in_the_source():
    """A literal backspace shipped inside a regex and nothing noticed for weeks.

    `_SPECIFIC_CRUISE` was written as `\bкр\b` and stored as `\x08кр\x08`, so
    the channels' own abbreviation for a cruise missile could not match: 247 of
    the 388 messages that say "КР" as a word counted as a bare "ракета", and
    during a ballistic episode the rules relabelled them ballistic.

    Every part of it conspired to stay hidden. The edit went through a shell
    heredoc, which collapses `\\b` to `\b`; `"\b"` in a non-raw Python string is
    a *valid* escape for backspace, so there was no SyntaxWarning; and a terminal
    renders a backspace by erasing the character before it, so reading the file
    back showed exactly what was intended. Three of these were found in one
    afternoon, in two files.

    So the guard is on the bytes. It costs nothing and it cannot be fooled by
    however the character got there.
    """
    offenders = []
    for path in sorted(REPO_ROOT.glob("tools/**/*.py")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            bad = {ch for ch in line if ord(ch) < 32 and ch not in ALLOWED}
            if bad:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{number} "
                    f"{sorted(hex(ord(c)) for c in bad)}")
    assert not offenders, offenders
