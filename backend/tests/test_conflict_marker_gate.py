"""Gate: no conflict marker survives a merge into a template, script or style.

The merge of `master` (CR-11's roll-out) into CR-17's branch left the line
`>>>>>>> origin/master` in `app/ui/templates/design_system.html`, and the kit
page drew it as a line of text — 182 x 20 px between the person card and
section 8, at every width. Every suite stood green on it, because no gate read
a template for markers (review A1 of 11 October 2026).

This gate reads every Jinja template of the kit and the domains, and every
script and style under `app/static`, and fails on a conflict marker on a line
of her own: `<<<<<<<`, `=======` or `>>>>>>>`. Vendor files are read too: they
carry none today, and a vendor that grows one is exactly as broken.

Proven red while building: one temporary template holding the three markers
made the gate fall naming the file and the line; the file removed, the gate
stood green again. The violation was additive — nothing that existed was
broken to prove her (the lesson of CR-12's gate that renamed a member and
laid the import flat).
"""

import re

import pytest

from tests._bestanden import APP, bestanden

# Via the shared helper (#678): a gate that looks nowhere stands green without
# guarding anything. The floor lies high enough to catch a glob that still
# finds something but misses most of her.
BESTANDEN = bestanden(
    (APP / "ui" / "templates").rglob("*.html"),
    (p for d in (APP / "domains").glob("*/templates") for p in d.rglob("*.html")),
    (APP / "static").rglob("*.js"),
    (APP / "static").rglob("*.css"),
    wat="every Jinja template of the kit and the domains, and every script and style under app/static",
    minstens=200,
)

# The marker on a line of her own — 7 times the same character, how git writes
# a conflict. Not `=======` as a word inside a line: that is text, not a merge.
MARKER = re.compile(r"^(<{7}|={7}|>{7})")

pytestmark = pytest.mark.ui_agnostisch


def test_no_template_script_or_style_holds_a_conflict_marker():
    overtredingen = [
        f"{pad.relative_to(APP.parent)}:{nr}: {regel[:60]}"
        for pad in BESTANDEN
        for nr, regel in enumerate(pad.read_text().splitlines(), 1)
        if MARKER.match(regel)
    ]
    assert not overtredingen, (
        "a conflict marker survived a merge (the run would ship her):\n" + "\n".join(overtredingen)
    )
