"""Fail when the built page is older than what it was built from.

The page is generated, git-ignored, and opened by hand — so a stale one looks
exactly like a fresh one. That already cost real work twice: once when the night
list did not contain the nights I had just recommended, and once when label
corrections in the file were not in the page and the next export undid them.

Remembering to rebuild is not a mechanism. This is: the test suite runs on every
change, so staleness surfaces immediately instead of during labelling.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

PAGE = REPO / "data" / "labeler.html"

# Everything whose change alters what the page shows or how it behaves.
SOURCES = (
    REPO / "tools" / "labeler" / "template.html",
    REPO / "tools" / "labeler" / "build.py",
    REPO / "tools" / "nlp" / "gazetteer.py",
    REPO / "tools" / "nlp" / "hints.py",
    REPO / "labels" / "moments.jsonl",
)


def test_every_source_the_page_depends_on_exists():
    """A renamed or moved module would make the freshness check vacuous."""
    missing = [p.relative_to(REPO).as_posix() for p in SOURCES if not p.exists()]
    assert not missing, f"freshness check is watching files that are gone: {missing}"


def test_the_built_page_is_not_stale():
    if not PAGE.exists():
        pytest.skip("no page built yet — run python -m tools.labeler.build")

    page_mtime = PAGE.stat().st_mtime
    newer = [
        p.relative_to(REPO).as_posix()
        for p in SOURCES
        if p.exists() and p.stat().st_mtime > page_mtime
    ]
    assert not newer, (
        "data/labeler.html is older than "
        + ", ".join(newer)
        + " — run: python -m tools.labeler.build"
    )
