"""Structural check for the labeler page's inline JavaScript.

There is no JS engine on the development machine, so this is the closest thing
to a syntax check: strip strings, template literals, regex literals and
comments, then verify that braces, parentheses and brackets balance and nest.

It cannot catch a typo in a property name — only a broken structure, which is
the failure mode that turns the whole page blank. Run it after editing the
template; the tests call it too.

Usage:
    python -m tools.labeler.checkjs
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")
BACKSLASH = chr(92)
QUOTES = ('"', "'", "`")
OPENERS = {"}": "{", ")": "(", "]": "["}


def extract_js(html: str) -> str:
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not blocks:
        raise ValueError("no inline <script> block found")
    return blocks[-1]


def strip_literals(js: str) -> str:
    """Replace strings, regexes and comments with placeholders."""
    out: list[str] = []
    i, n = 0, len(js)
    while i < n:
        ch = js[i]
        if ch in QUOTES:
            quote = ch
            i += 1
            while i < n and js[i] != quote:
                if js[i] == BACKSLASH:
                    i += 1
                i += 1
            i += 1
            out.append("S")
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "/":
            while i < n and js[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "*":
            i = js.find("*/", i) + 2
            continue
        if ch == "/":
            prev = next((c for c in reversed(out) if not c.isspace()), "")
            if prev in "(,=:[!&|?{;" or prev == "":
                i += 1
                while i < n and js[i] != "/":
                    if js[i] == BACKSLASH:
                        i += 1
                    elif js[i] == "[":
                        while i < n and js[i] != "]":
                            if js[i] == BACKSLASH:
                                i += 1
                            i += 1
                    i += 1
                i += 1
                out.append("R")
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def problems(js: str) -> list[str]:
    code = strip_literals(js)
    found: list[str] = []
    for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
        a, b = code.count(opener), code.count(closer)
        if a != b:
            found.append(f"{opener}{closer} unbalanced: {a} vs {b}")

    stack: list[str] = []
    for pos, ch in enumerate(code):
        if ch in "{([":
            stack.append(ch)
        elif ch in "})]":
            if not stack or stack[-1] != OPENERS[ch]:
                top = stack[-1] if stack else None
                found.append(f"nesting error at offset {pos}: {ch!r} closes {top!r}")
                break
            stack.pop()
    if stack:
        found.append(f"unclosed: {''.join(stack)}")
    return found


def main(argv: list[str] | None = None) -> int:
    path = Path(argv[0]) if argv else TEMPLATE
    js = extract_js(path.read_text(encoding="utf-8"))
    found = problems(js)
    if found:
        print(f"{path}: {len(found)} problem(s)")
        for f in found:
            print(f"  {f}")
        return 1
    print(f"{path}: {len(js)} chars of JS, structure balanced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
