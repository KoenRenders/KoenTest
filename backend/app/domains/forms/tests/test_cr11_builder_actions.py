"""CR-11 phase 1 (#1391): the form builder's actions sit by what they work on.

W14: the builder's actions work on the definition and say so: "Definitie
exporteren (JSON)" and "Definitie importeren (JSON)…". The export of the
submissions ("Export (.ods)") sits on the Inzendingen tab. So the builder has no
action with the word "Export", and the tab has one.
W18: the import block takes a file only: one input, of type `file`.

Proven red against master `112ed593` (this file on an export of it): the builder
had "Export" and "JSON"/"JSON-import", the tab had no export, and the import
block had a paste box next to the file.
"""

from __future__ import annotations

import re
import secrets

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.forms.models import Form, FormField
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _form(db) -> Form:
    tag = secrets.token_hex(3)
    form = Form(title="Opruimdag", slug=f"opruimdag-{tag}", status="open", share_token=f"t-{tag}")
    db.add(form)
    db.flush()
    db.add(FormField(form_id=form.id, label="Je naam", field_type="text", position=0))
    db.commit()
    return form


def _actions(html: str) -> list[str]:
    """The text of every link and button, whitespace collapsed."""
    found = re.findall(r"<(?:a|button)\b[^>]*>(.*?)</(?:a|button)>", html, re.S)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip() for t in found]


def test_w14_the_builder_acts_on_the_definition_and_the_tab_exports(client, db_session):
    form = _form(db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    builder = _actions(client.get(f"/admin/formulieren/{form.id}").text)
    tab = client.get(f"/admin/formulieren/{form.id}/inzendingen").text

    assert "Definitie exporteren (JSON)" in builder
    assert "Definitie importeren (JSON)…" in builder
    assert not [a for a in builder if a.startswith("Export")], builder
    exports = [a for a in _actions(tab) if a.startswith("Export")]
    assert exports == ["Export (.ods)"], exports
    assert f'href="/admin/formulieren/{form.id}/export"' in tab


def test_w18_the_import_takes_a_file_only(client, db_session):
    form = _form(db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/formulieren/{form.id}").text

    block = re.search(r'<div x-show="jsonimport".*?</form>', html, re.S)
    assert block, "the import block is on the builder of a form without submissions"
    inputs = re.findall(r"<(?:input|textarea|select)\b[^>]*>", block.group(0))
    visible = [i for i in inputs if 'type="hidden"' not in i]
    assert len(visible) == 1 and 'type="file"' in visible[0], visible
