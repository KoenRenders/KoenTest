"""The slug of the contact form is written in one place (#1377).

`"berichten"` stood in `forms/ui.py` and again in `workflow/handlers.py`, and
three more times inside `forms`. Change the form's slug, or one of the copies,
and the werkbank stopped making a task for a new message, without an error. It
now lives in `forms/service.py` as `CONTACT_FORM_SLUG`; the rest of `forms`
uses that name, and `workflow` reads it through `forms.api`.

The gate reads every module under `app/` and counts the string constants that
are exactly the slug: one, the definition. Docstrings and comments are full
sentences and never equal to it. Frozen migrations live outside `app/`.

Proven red with an additive violation: `SLUG_COPY = "berichten"` added to
`workflow/handlers.py` fails the first test and names the file; on master
`5d92eb2b` the first test fails with five places.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
SLUG = "berichten"


def _places() -> list[str]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        if "tests" in path.relative_to(APP).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Constant) and node.value == SLUG:
                found.append(f"{path.relative_to(APP)}:{node.lineno}")
    return found


def test_the_slug_is_written_once():
    places = _places()
    assert places, "the gate found no place at all: the slug moved or the walk broke"
    assert len(places) == 1, f"the contact form's slug is written in more than one place: {places}"
    assert places[0].startswith("domains/forms/service.py:"), f"it moved out of forms: {places}"


def test_workflow_reads_the_slug_from_forms():
    from app.domains.forms import api as forms_api
    from app.domains.workflow import handlers

    assert handlers.CONTACT_FORM_SLUG is forms_api.CONTACT_FORM_SLUG == SLUG
