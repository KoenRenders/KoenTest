"""The shell of the document editor's dialogs, as the page renders it (CR-17).

Every dialog of the editor is the kit's dialog with the focus hand-back turned
off, wrapped in an element that tells the editor's script when the dialog has
closed. The browser tests hold the behaviour; this holds what is rendered —
and it is the test that caught the shell's first form, in which the dialogs'
content was asked for inside the kit dialog's own call block: Jinja answered
"No caller defined" and every page with the editor was a server error, which
the browser tests showed only as fifty-four timeouts.

Broken on purpose (13 October 2026), put back by the reverse edit:
`{{ _content }}` in the shell made `{{ caller() }}` again → red, with that
"No caller defined".
"""

from __future__ import annotations

import re

from app.domains.cms import schema
from app.ui import templates


def _opening_tag(html: str, state: str) -> str:
    """The dialog's own opening tag, whole. Not `[^>]*>`: its `x-effect` holds
    an arrow function, and `=>` would end the tag there."""
    start = html.index(f'<div x-show="{state}" x-cloak role="dialog"')
    effect = html.index('x-effect="', start)
    return html[start : html.index('">', effect) + 2]


def _editor() -> str:
    source = (
        '{% import "_macros.html" as ui %}'
        '{{ ui.document_editor("document", config, "{}", id="ed", button_pages=[(1, "Over ons")],'
        ' button_forms=[("contact", "Contact")], codes=[{"code": "VOORBEELD", "label": "Een voorbeeld"}]) }}'
    )
    return templates.env.from_string(source).render(config=schema.schema_for("page"))


def test_each_dialog_of_the_editor_is_rendered_through_the_shell():
    html = _editor()
    dialogs = re.findall(r'<div x-show="([a-z]+)" x-cloak role="dialog"', html)
    assert sorted(dialogs) == ["button", "card", "codes", "figure", "link"], dialogs
    for state in dialogs:
        # The shell: an element that watches this dialog's state and names this editor…
        watcher = (
            "$watch('" + state + "', open => { if (!open) "
            "$dispatch('raak-editor-dialog-closed', { editor: 'ed' }) })"
        )
        assert watcher in html, f"the {state} dialog does not tell the editor of its closing"
        # …around the kit's dialog, which no longer hands the focus back itself.
        tag = _opening_tag(html, state)
        assert ": ($el._vorige = null)" in tag and "_vorige.focus()" not in tag, tag[-160:]
        assert html.index(watcher) < html.index(tag), (
            f"the watcher does not stand around the {state} dialog"
        )


def test_the_dialogs_keep_their_content():
    """The content of each dialog stands inside it: a field or a button that
    only that dialog has."""
    html = _editor()
    for state, mark in (
        ("figure", 'id="ed-fig-alt"'),
        ("link", 'id="ed-link-url"'),
        ("button", 'id="ed-btn-label"'),
        ("card", 'id="ed-card-title"'),
        ("codes", "data-code-choices"),
    ):
        start = html.index(f'<div x-show="{state}" x-cloak role="dialog"')
        following = [
            html.find(f'<div x-show="{other}" x-cloak role="dialog"', start + 1)
            for other in ("figure", "link", "button", "card", "codes")
        ]
        end = min([p for p in following if p != -1] or [len(html)])
        assert mark in html[start:end], (
            f"the {state} dialog is rendered without its content ({mark})"
        )
