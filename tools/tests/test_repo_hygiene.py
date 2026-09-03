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
def test_no_xml_comment_contains_a_double_hyphen():
    """`--` is illegal inside an XML comment, and it broke his build.

        Failed to compile resource file: network_security_config.xml
        The string "--" is not permitted within comments.

    I write `--` as a dash in prose, so it went into every resource file and
    manifest I wrote, and nothing here could catch it: the Python suite never
    parses those files, and only `aapt` does. He found it the way anybody would,
    by the build failing on him.

    Checked on the bytes rather than by parsing, so it holds for a manifest, a
    vector drawable and a values file alike, and it costs nothing.
    """
    import re

    offenders = []
    for path in sorted(REPO_ROOT.glob("app/src/**/*.xml")):
        text = path.read_text(encoding="utf-8")
        for comment in re.finditer(r"<!--(.*?)-->", text, re.S):
            if "--" in comment.group(1):
                line = text[:comment.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}")
    assert not offenders, offenders


def test_every_xml_the_build_reads_actually_parses():
    """The same class of fault, caught one level up: a resource file that is not
    well-formed fails at `aapt` and not before, which on this machine means it
    fails on him rather than on me. There is no Android SDK here, so parsing is
    the most the Python suite can do -- and it is enough for the mistakes that
    are made by hand."""
    import xml.etree.ElementTree as ET

    checked = 0
    for path in sorted(REPO_ROOT.glob("app/src/**/*.xml")):
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            raise AssertionError(f"{path.relative_to(REPO_ROOT)}: {exc}") from exc
        checked += 1
    assert checked >= 6, f"expected the app's resources, found {checked}"
# Compose symbols worth checking, and where each one comes from. Not the whole
# framework: only the widgets and modifiers this app uses, because the fault
# being guarded against is adding one to a file that did not use it before.
COMPOSE_IMPORTS = {
    "Box": "androidx.compose.foundation.layout.Box",
    "Row": "androidx.compose.foundation.layout.Row",
    "Column": "androidx.compose.foundation.layout.Column",
    "Spacer": "androidx.compose.foundation.layout.Spacer",
    "CircleShape": "androidx.compose.foundation.shape.CircleShape",
    "RoundedCornerShape": "androidx.compose.foundation.shape.RoundedCornerShape",
    "Alignment": "androidx.compose.ui.Alignment",
    "Arrangement": "androidx.compose.foundation.layout.Arrangement",
    "clickable": "androidx.compose.foundation.clickable",
    "clip": "androidx.compose.ui.draw.clip",
    "background": "androidx.compose.foundation.background",
    "verticalScroll": "androidx.compose.foundation.verticalScroll",
    "rememberScrollState": "androidx.compose.foundation.rememberScrollState",
    "rememberLazyListState": "androidx.compose.foundation.lazy.rememberLazyListState",
    "LazyColumn": "androidx.compose.foundation.lazy.LazyColumn",
    "items": "androidx.compose.foundation.lazy.items",
    "TextOverflow": "androidx.compose.ui.text.style.TextOverflow",
    "TextAlign": "androidx.compose.ui.text.style.TextAlign",
    "FontWeight": "androidx.compose.ui.text.font.FontWeight",
    "mutableIntStateOf": "androidx.compose.runtime.mutableIntStateOf",
    "mutableStateOf": "androidx.compose.runtime.mutableStateOf",
    "remember": "androidx.compose.runtime.remember",
    "LaunchedEffect": "androidx.compose.runtime.LaunchedEffect",
    "rememberCoroutineScope": "androidx.compose.runtime.rememberCoroutineScope",
    "LocalContext": "androidx.compose.ui.platform.LocalContext",
    "LocalSoftwareKeyboardController":
        "androidx.compose.ui.platform.LocalSoftwareKeyboardController",
    "Surface": "androidx.compose.material3.Surface",
    "MaterialTheme": "androidx.compose.material3.MaterialTheme",
    "Text": "androidx.compose.material3.Text",
    "Button": "androidx.compose.material3.Button",
    "OutlinedButton": "androidx.compose.material3.OutlinedButton",
    "OutlinedTextField": "androidx.compose.material3.OutlinedTextField",
    "TextButton": "androidx.compose.material3.TextButton",
    "Slider": "androidx.compose.material3.Slider",
    "Scaffold": "androidx.compose.material3.Scaffold",
    "NavigationBar": "androidx.compose.material3.NavigationBar",
    "NavigationBarItem": "androidx.compose.material3.NavigationBarItem",
    "CircularProgressIndicator":
        "androidx.compose.material3.CircularProgressIndicator",
    "KeyboardOptions": "androidx.compose.foundation.text.KeyboardOptions",
    "KeyboardActions": "androidx.compose.foundation.text.KeyboardActions",
    "FocusRequester": "androidx.compose.ui.focus.FocusRequester",
    "ImeAction": "androidx.compose.ui.text.input.ImeAction",
    "delay": "kotlinx.coroutines.delay",
    "launch": "kotlinx.coroutines.launch",
}

# Modifiers, which are used as `.name(` and so need their own pattern.
COMPOSE_MODIFIERS = {
    "size": "androidx.compose.foundation.layout.size",
    "width": "androidx.compose.foundation.layout.width",
    "height": "androidx.compose.foundation.layout.height",
    "padding": "androidx.compose.foundation.layout.padding",
    "fillMaxSize": "androidx.compose.foundation.layout.fillMaxSize",
    "fillMaxWidth": "androidx.compose.foundation.layout.fillMaxWidth",
    "imePadding": "androidx.compose.foundation.layout.imePadding",
    "focusRequester": "androidx.compose.ui.focus.focusRequester",
}


def test_every_compose_symbol_the_app_uses_is_imported():
    """Kotlin's compiler is the right tool for this and it is not here.

    There is no Android SDK on this machine, so the first thing that reads these
    files is his Gradle build -- which means a missing import fails on him
    rather than on me. It did: `Settings.kt:98:13 Unresolved reference 'Box'`,
    after I moved settings out of the tab bar and gave it a back button in a
    file that had never used a `Box`.

    That is the exact shape of the mistake this catches: a widget added to a
    file that did not use it before. It cannot type-check Kotlin and does not
    try. It reads the bytes, which is all the Python suite can do, and it is
    enough for the one error I keep making.
    """
    import re

    offenders = []
    for path in sorted(REPO_ROOT.glob("app/src/main/java/**/*.kt")):
        text = path.read_text(encoding="utf-8")
        # Comments carry symbol names as prose; only real code counts.
        code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        imported = {line.rsplit(".", 1)[-1]
                    for line in re.findall(r"^import (\S+)", text, re.M)}
        for name, full in COMPOSE_IMPORTS.items():
            if name in imported:
                continue
            if re.search(r"(?<![\w.])" + re.escape(name) + r"\s*[({<.]", code):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}: import {full}")
        for name, full in COMPOSE_MODIFIERS.items():
            if name in imported:
                continue
            if re.search(r"\.\s*" + re.escape(name) + r"\s*\(", code):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}: import {full}")
    assert not offenders, offenders
# Addresses that say nothing about anybody: loopback, the private ranges, the
# emulator's route to its host, and the two wildcards.
ALLOWED_ADDRESSES = ("127.", "10.", "192.168.", "0.0.0.0", "255.255.255.255",
                     *[f"172.{n}." for n in range(16, 32)])


def test_nothing_tracked_carries_an_address_or_a_key():
    """The repository is public and its history is not reversible.

    That is the whole reason `data/runbook.md` sits outside git -- and the reason
    is only as good as the discipline. Splitting the runbook into `docs/servers.md`
    moved two hundred lines of procedure into a public file by hand, and a hand
    is exactly what puts a public IP in the one paragraph nobody re-reads.

    So this reads every tracked text file. A private address is fine: `10.0.0.75`
    is meaningless without a way in, and naming it is what makes the two-box
    arrangement explicable. A routable one is not, and neither is a key path or a
    fingerprint.
    """
    import re
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True).stdout.split()

    address = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    keyish = re.compile(
        r"(?:BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"
        r"|SHA256:[A-Za-z0-9+/]{20,}"
        r"|[/\\]\.ssh[/\\])")

    offenders = []
    for name in tracked:
        path = REPO_ROOT / name
        if path.suffix.lower() in (".png", ".jpg", ".zip", ".jar", ".keystore"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for found in address.findall(line):
                if not found.startswith(ALLOWED_ADDRESSES):
                    offenders.append(f"{name}:{number} address {found}")
            if keyish.search(line):
                offenders.append(f"{name}:{number} key material or path")
    assert not offenders, offenders
def test_the_drawn_rhythm_matches_the_pattern_it_names():
    """The screen is the only place the alphabet is written down, so a screen
    that draws it wrong teaches it wrong -- and is believed, which is worse than
    teaching nothing.

    It did. `NEAR` was `longArrayOf(0, 250, 180, 250)`, two pulses, and Settings
    had always drawn `·· ··`, four. He noticed by feel: "наче має бути 2
    коротких + 2 коротких, а гуде 1 короткий + 1 короткий." The drawing won,
    because a single pair is what every other app does for an ordinary
    notification and this one has to read as deliberate.

    Comparable because the convention was made comparable: one glyph per pulse,
    `·` short and `▬` long. A vibration pattern is `{wait, buzz, wait, buzz, ...}`
    so the buzzes are the entries at odd positions.
    """
    import re

    bell = (REPO_ROOT / "app/src/main/java/ua/hovaysya/Bell.kt").read_text(
        encoding="utf-8")
    settings = (REPO_ROOT / "app/src/main/java/ua/hovaysya/ui/Settings.kt"
                ).read_text(encoding="utf-8")

    pulses = {}
    for name, body in re.findall(
            r"private val ([A-Z]+) = longArrayOf\(([^)]*)\)", bell, re.S):
        numbers = [n for n in re.findall(r"\d+", body)]
        # Odd positions are the buzzes; the evens are the waits between them.
        pulses[name] = len(numbers[1::2])

    assert set(pulses) >= {"SOS", "SHELTER", "NEAR", "CLEAR"}, pulses

    drawn = re.findall(r'Bells\(\s*"[^"]+",\s*"([·▬ —]*)"', settings)
    counts = [sum(1 for c in row if c in "·▬") for row in drawn]
    # Settings lists them in the order of the alphabet, the silent one last.
    expected = [pulses["SOS"], pulses["SHELTER"], pulses["NEAR"],
                pulses["CLEAR"], 0]
    assert counts == expected, (drawn, counts, expected)
