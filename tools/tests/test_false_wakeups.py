"""Every audible decision the rules got wrong, kept as a set.

Built 2026-09-24 by replaying the whole corpus through the policy and reading
every audible decision it produced -- 770 of them, once the official siren and
all-clear templates are set aside. 58 were wrong, and every one is the same
fault: a message *about* a threat read as a report *of* one. His plan, in his
words: "полатаємо регулярками що знайшли в якості швидкого фіксу, а далі будемо
намагатися фіксити по нормальному".

The fixture is the quick fix's definition of done, and it outlives it: whatever
replaces the regexes one day has to pass this too.

Two expectations, because two different things went wrong:

  not-live   the text is not a report of something in the air, so `modality_hint`
             must not call it `live-threat`
  no-alert   the text does not declare a siren, whatever else it says, so
             `alert_state` must not return one

These are my labels, not his -- the eight cases where the call was genuinely his
to make are deliberately absent, and `labels/` stays his alone.
"""

import json
import pathlib

import pytest

from tools.nlp import hints

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "false_wakeups.jsonl"


def cases():
    out = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.append(pytest.param(r, id=f"{r['category']}-{r['anchor']}"))
    return out


@pytest.mark.parametrize("case", cases())
def test_a_message_about_a_threat_does_not_ring(case):
    if case["expect"] == "no-alert":
        assert hints.alert_state(case["text"]) is None, case["text"]
    else:
        assert hints.modality_hint(case["text"]) != "live-threat", case["text"]
