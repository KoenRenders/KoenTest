"""The renderer's fontconfig is never seen half-written (#1810).

Inkscape finds the poster's fonts through a private fontconfig file that the
renderer writes on one fixed path. It wrote that file in place, once per
process: truncate, then write. An Inkscape another process started in the
instant between the two read an empty configuration and set every text in
DejaVu Sans — measured on 9 October 2026: with an empty file `fc-match` answers
"DejaVu Sans" for both poster faces, and the authority check then reports the
five overflows of the red master run to the decimal (t-title-1 222.6 mm against
201.0, t-bar 125.3 / 118.0, …). The suite runs in four processes, each
rewriting that one file at its own first render.

So the rule: the file that exists is left alone when it already says the right
thing, and otherwise replaced as a whole — never the same file emptied and
filled again. Held here without timing: an untouched file keeps the moment it
was last written, and a replaced file is another file.

Proven red (9 October 2026): the function as it stood (`conf.write_text(...)`
on the path itself) → the first assertion fails, the file was rewritten.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.domains.designstudio import render

pytestmark = pytest.mark.ui_agnostisch

LONG_AGO = 1_000_000_000  # a moment no rewrite can land on


@pytest.fixture
def written(tmp_path, monkeypatch):
    """The function without its per-process cache, writing under a folder of this test."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return render._fontconfig_file.__wrapped__


def test_a_configuration_that_is_right_is_left_alone(written):
    conf = Path(written())
    assert str(render.FONTS_DIR) in conf.read_text(encoding="utf-8")
    os.utime(conf, (LONG_AGO, LONG_AGO))
    before = conf.stat()

    again = Path(written())

    assert again == conf
    after = conf.stat()
    assert (after.st_ino, int(after.st_mtime)) == (before.st_ino, LONG_AGO), (
        "the file was written again although it held exactly this — another process's "
        "Inkscape can read it empty in between"
    )


def test_a_configuration_that_is_wrong_is_replaced_as_a_whole(written):
    conf = Path(written())
    right = conf.read_text(encoding="utf-8")
    conf.write_text("<fontconfig></fontconfig>", encoding="utf-8")  # what an older release left
    stale = conf.stat()

    written()

    assert conf.read_text(encoding="utf-8") == right
    assert conf.stat().st_ino != stale.st_ino, (
        "the same file was emptied and filled again — a reader in between sees it empty"
    )
    assert [p.name for p in conf.parent.iterdir() if p.is_file()] == ["fonts.conf"], (
        "the file it was written to first stays behind"
    )
