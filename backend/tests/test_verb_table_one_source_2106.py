"""Refuses a verb → glyph table that differs between the code and the design-system document · hard · since #2106.

The table lives once as data (`app/ui/kit/verbs.py`): the design-system page renders
it and the UI gate reads it. `docs/design-system.md` §1.4 carries the same rows as
prose for a reader of the document — a process document this issue does not edit —
so a test ties the two: the glyphs of the document's two tables are the glyphs of the
code, no more and no fewer. Neither side can gain or lose a row alone.

Proven additively (18 October 2026): a row added to `VERBS` that §1.4 does not carry
→ red, with the glyph named.
"""

import re
from pathlib import Path

from app.ui.kit.icons import icon_names
from app.ui.kit.verbs import VERBS, glyphs, verb_of, verbs_in

DOC = Path(__file__).resolve().parents[2] / "docs" / "design-system.md"


def _section_glyphs() -> set[str]:
    text = DOC.read_text()
    section = text[text.index("### 1.4 Icons") : text.index("### 1.6")]
    names = set(icon_names())
    return {name for name in re.findall(r"`([a-z0-9-]+)`", section) if name in names}


def test_the_document_and_the_code_carry_the_same_glyphs():
    document, code = _section_glyphs(), set(glyphs())
    assert len(document) >= 12, f"the section's table was not read: {sorted(document)}"
    assert document == code, (
        f"only in the document: {sorted(document - code)}; only in the code: {sorted(code - document)}"
    )


def test_every_glyph_of_the_table_is_a_glyph_of_the_kit():
    unknown = [v.glyph for v in VERBS if v.glyph not in icon_names()]
    assert not unknown, f"`ui.icon()` fails silently on an unknown name: {unknown}"


def test_a_label_is_read_by_its_first_word():
    assert verb_of("+ Nieuwe pagina").glyph == "plus"
    assert verb_of("Toevoegen aan de kring").glyph == "plus"
    assert verb_of("Verwijderen").variant == "danger"
    assert verb_of("Annuleren") is None and verb_of("Openen") is None
    assert verbs_in("Gast verwijderen") == {"trash-2"}


def test_the_design_system_page_renders_the_table(client, platform_workspace):
    from tests.integration.test_records_lijsten_ui import _login

    _login(client)
    page = client.get("/admin/design-system").text
    table = page[page.index("data-verb-table") :]
    table = table[: table.index("</table>")]
    assert table.count("<code>") == len(VERBS), "one row per verb of the code"
    assert "<code>trash-2</code>" in table
