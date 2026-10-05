"""A help text keeps its line breaks, from the builder to the public form (#1379).

Koen, 30 September 2026: the help text of a question was a single input line in
the builder, so a help text of several sentences showed only in part and could
not hold a line break. It is now the kit's growing textarea, and the public form
shows a line break as a line break (`whitespace-pre-line`).

Proven red against master `4cc36c76`, this file copied onto an export of it: both
failed — the builder offered an input line, and the public form showed the help
text without `whitespace-pre-line`. (A POST could already store a line break; the
builder's input line could not type one.)
"""

from __future__ import annotations

import re
import secrets

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import Form, FormField
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

HELP = "Kom op tijd.\nBreng je eigen beker mee.\nParkeren kan achter de zaal."


def _form(db) -> tuple[Form, FormField]:
    tag = secrets.token_hex(3)
    form = Form(title="Opruimdag", slug=f"opruimdag-{tag}", status="open", share_token=f"t-{tag}")
    db.add(form)
    db.flush()
    field = FormField(form_id=form.id, label="Je naam", field_type="text", position=0)
    db.add(field)
    db.commit()
    return form, field


def test_the_builder_offers_a_growing_textarea_for_the_help_text(client, db_session):
    form, field = _form(db_session)
    field.help_text = HELP
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/formulieren/{form.id}").text

    textarea = re.search(
        rf'<textarea name="help_text" id="fh-{field.id}"[^>]*>([^<]*)</textarea>', html
    )
    assert textarea, "the help text is a textarea in the builder"
    assert textarea.group(1) == HELP, "with every line of it"
    assert 'x-on:input="groei()"' in textarea.group(0), "and it grows with the kit's autogrow"


def test_a_line_break_is_kept_and_shown_on_the_public_form(client, db_session):
    form, field = _form(db_session)
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)

    answer = client.post(
        f"/admin/formulieren/{form.id}/velden/{field.id}",
        data={"label": "Je naam", "field_type": "text", "help_text": HELP},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )
    assert answer.status_code == 200, answer.text[:200]
    db_session.expire_all()
    assert db_session.get(FormField, field.id).help_text == HELP, "the line breaks are stored"

    client.cookies.clear()
    public = client.get(f"/f/{form.slug}").text
    shown = re.search(r'<p [^>]*class="([^"]*)">' + re.escape(HELP) + "</p>", public)
    assert shown, "the help text is on the public form as it was typed"
    assert "whitespace-pre-line" in shown.group(1), "and a line break shows as one"
