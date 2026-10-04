"""CR-11 pilot A, K8 (#1562): one trigger, one panel — what a template may not
bring back (B7 tests 13 and 14).

Block 10 (Koen, 4 October 2026; `docs/design-system-end-state.md` §3.15): the
Assistent is the panel behind the one trigger in the shell's chrome. The
assistant page and the per-screen `AI ·` buttons do not exist.

1. **an AI button of its own** — in any template but the trigger's: a button or
   a link whose label starts with `AI ·`, one that carries the `sparkles` glyph,
   or the old overlay macro (`raakje.overlay(`, `_raakje_overlay.html`);
2. **a link to the assistant page** — `/admin/rapporten/raakje` as an `href`;
   the address only answers a redirect now;
3. **a second panel** — the frame (`_raakje_frame.html`) is called by the two
   shells and by nothing else: `admin_base.html` and the public
   `_raakje_widget.html`;
4. **a selector in the panel** — a select, a checkbox or a radio inside
   `_raakje_panel.html` or the back office's panel body: the screen owns its
   selection, the panel reads it;
5. **an admin address in the public component** — the public bell posts to the
   public route only; which tools that route may use is
   `test_public_tool_boundary_gate.py`'s to guard.

The newsletter's own drafting panel (`_nb_raakje.html`) stays a column of the
newsletter page until PR 2 puts it on the proposal mechanism; it carries no AI
button and no frame, so no rule here names it.

Proven red, additively — each rule on a throwaway text that adds one violation
to a clean one — and the gate counts what it read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

#: The one template that draws the trigger.
TRIGGER = "_assistant_trigger.html"
#: The two shells that carry a panel.
SHELLS = {"admin_base.html", "_raakje_widget.html"}
#: What stands in a panel.
PANEL_BODIES = {"_raakje_panel.html", "_assistant_panel.html"}

_COMMENT = re.compile(r"{#.*?#}", re.S)


def _templates() -> dict[str, str]:
    return {p.name: _COMMENT.sub("", p.read_text()) for p in APP.rglob("templates/*.html")}


def own_ai_button(text: str) -> list[str]:
    found = []
    if "raakje.overlay(" in text or "_raakje_overlay.html" in text:
        found.append("the per-screen overlay")
    if re.search(r"""_\(\s*["']AI · """, text):
        found.append("a label that starts with `AI ·`")
    if re.search(r"""lead_icon\s*=\s*["']sparkles["']|icon\(\s*["']sparkles["']""", text):
        found.append("the assistant's glyph on a control of its own")
    return found


def links_to_the_page(text: str) -> bool:
    return bool(re.search(r"""href\s*=\s*["']/admin/rapporten/raakje["']""", text))


def has_selector(text: str) -> bool:
    return bool(
        re.search(r"<select\b|select_control\(|multiselect\(|type=\"(checkbox|radio)\"", text)
    )


def test_the_gate_reads_the_assistants_templates():
    templates = _templates()
    assert len(templates) > 100, "the gate found no templates"
    for name in {TRIGGER} | SHELLS | PANEL_BODIES | {"_raakje_frame.html"}:
        assert name in templates, name
    # The trigger is what rule 1 would refuse anywhere else.
    assert own_ai_button(templates[TRIGGER])


def test_no_template_brings_its_own_ai_button():
    wrong = {
        name: found
        for name, text in _templates().items()
        if name != TRIGGER and (found := own_ai_button(text))
    }
    assert not wrong, f"an AI button of its own — the Assistent has one trigger (rule 1): {wrong}"


def test_no_template_links_to_the_assistant_page():
    wrong = sorted(name for name, text in _templates().items() if links_to_the_page(text))
    assert not wrong, f"a link to the assistant page, which no longer exists (rule 2): {wrong}"


def test_only_the_two_shells_carry_a_panel():
    callers = {
        name
        for name, text in _templates().items()
        if re.search(r"\bcall\s+\w+\.frame\(", text) and "_raakje_frame.html" in text
    }
    assert callers == SHELLS, f"the panel's frame is the shells' alone (rule 3): {sorted(callers)}"


def test_the_panel_holds_no_selector():
    templates = _templates()
    wrong = sorted(name for name in PANEL_BODIES if has_selector(templates[name]))
    assert not wrong, f"a selector in the panel — the screen owns its selection (rule 4): {wrong}"


def test_the_public_component_names_no_admin_address():
    widget = _templates()["_raakje_widget.html"]
    assert "panel.inner(" in widget and '"/raakje/vraag"' in widget
    assert "/admin" not in widget, "the public bell reaches for the back office (rule 5)"


CLEAN = """{{ ui.record_header(record_head.title, actions=record_head.actions) }}
{{ ui.btn_secondary(_("Exporteren"), href="/admin/x/export") }}"""


@pytest.mark.parametrize(
    "addition",
    [
        '{{ ui.btn_secondary(_("AI · Activiteit"), attrs="") }}',
        '{{ ui.btn_secondary(_("Vraag het"), lead_icon="sparkles") }}',
        '<button type="button">{{ ui.icon("sparkles") }}</button>',
        '{{ raakje.overlay("x", "/y", "", stt_mode) }}',
        '{% import "_raakje_overlay.html" as raakje %}',
    ],
)
def test_every_own_button_is_refused(addition):
    assert not own_ai_button(CLEAN)
    assert own_ai_button(CLEAN + "\n" + addition), addition


def test_a_link_to_the_page_and_a_selector_are_refused():
    assert not links_to_the_page(CLEAN) and not has_selector(CLEAN)
    assert links_to_the_page(CLEAN + '\n<a href="/admin/rapporten/raakje">Raakje</a>')
    # The endpoints under the old address are not the page.
    assert not links_to_the_page('<form hx-post="/admin/rapporten/raakje/scherm/betalingen">')
    assert has_selector(CLEAN + '\n{% call ui.select_control("bron") %}{% endcall %}')
    assert has_selector(CLEAN + '\n<input type="checkbox" name="keep">')
