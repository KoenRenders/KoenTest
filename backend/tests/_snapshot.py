"""Rendered screens compared with a snapshot taken before a conversion (CR-13 B8 test 12).

A gate that looks for a member *in* the output cannot see a missing or empty
rendering (CR-12 phase 4). So a phase that puts a method or an enum where a screen
read a string renders the screens on the code BEFORE it, keeps the output, and the
converted code must render the same. One helper for every such test, so the way a
screen is normalised is the same everywhere.

`SNAPSHOT_UPDATE=1` rewrites the files — and a snapshot rewritten on the new code
proves nothing: record on the old code, read the diff before committing it.
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

import pytest


def main_region(html: str) -> str:
    """The page's own content: `<main>`, so the chrome around it does not count."""
    match = re.search(r"<main\b.*?</main>", html, re.S)
    assert match, "the screen has no <main> — is this test still looking?"
    return match.group(0)


def normalise(fragment: str, names: dict[int, str], literals: dict[str, str]) -> str:
    """Fixed ids and strings replaced by names, tokens masked, whitespace collapsed."""
    text = fragment
    for literal, name in literals.items():
        text = text.replace(literal, name)
    for number, name in sorted(names.items(), key=lambda kv: -kv[0]):
        text = re.sub(rf"(?<!\d){number}(?!\d)", name, text)
    text = re.sub(r"[A-Za-z0-9_\-.]{40,}", "<TOKEN>", text)
    text = re.sub(r'(name="csrf_token" value=")[^"]*', r"\1<CSRF>", text)
    text = re.sub(r'("X-CSRF-Token"\s*:\s*")[^"]*', r"\1<CSRF>", text)
    text = re.sub(r">\s+<", ">\n<", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip() + "\n"


def compare(folder: Path, screen: str, got: str, before: str) -> None:
    """Compare a normalised rendering with `folder/screen.html`; `before` names the
    change the snapshot guards, for the failure message."""
    path = folder / f"{screen}.html"
    if os.environ.get("SNAPSHOT_UPDATE") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(got, encoding="utf-8")
    assert path.exists(), f"no snapshot for {screen}; record it on the old code (SNAPSHOT_UPDATE=1)"
    want = path.read_text(encoding="utf-8")
    if got != want:
        diff = "".join(
            difflib.unified_diff(
                want.splitlines(True), got.splitlines(True), "snapshot", "rendered", n=2
            )
        )
        pytest.fail(f"{screen} renders differently from before {before}:\n{diff}")
