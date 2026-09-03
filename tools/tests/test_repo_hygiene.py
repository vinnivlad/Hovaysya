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
