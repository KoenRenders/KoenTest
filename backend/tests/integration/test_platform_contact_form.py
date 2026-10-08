"""#1567 — the platform has its contact form, a message lands in its Werkbank, and
a page shows a button to a form through a placeholder.

Measured before the build: every tenant had its `berichten` form (#1509) except
the platform. The cause was the kind, not the timing: the startup seed
(`seed_contact_forms.py`) walked `list_units`, the UNIT organisations, and the
platform is a PLATFORM organisation. It is a tenant with the modules Forms and
Workflow since #1523, so it takes a message like any other — through the same
`seed_contact_form` and `seed_message_workflow`, not a second definition.

- After the seed the platform has exactly one contact form and one definition;
  a second start adds nothing.
- A message posted on the platform's contact page makes one task in the
  platform's Werkbank, and none in another tenant's.

**The button is a placeholder, for any form** (Koen, 4 October 2026): a page
carries `{{form:<slug>}}` or `{{form:<slug>|<button label>}}`, in the family of
`{{tenants}}`. It renders one button where the form can take a submission and
nothing where it cannot — never a button that leads nowhere, never the raw
code. There is no automatic button under a home page; the association's fixed
home (`home.html`) keeps its own.

Proven red against master `7bc656e5`: the seed leaves the platform without a
form (the first two tests fail), and the code stays on the page as typed (the
placeholder tests fail). On this branch, each on its own: the open check taken
out of `form_button_target` → the closed-form case fails; the tenant filter
bypassed there → the other tenant's slug renders a button; the label passed to
the page unescaped → the markup test fails; the contact form looked up without
`contact_form` → the "cannot take a message" case fails.
"""

from __future__ import annotations

import re
import secrets

import pytest

from app.domains.cms.api import CmsPage
from app.domains.forms.api import CONTACT_FORM_SLUG, Form, FormSubmission
from app.domains.mdm.api import platform_org
from app.domains.workflow.api import MESSAGE_WORKFLOW, WorkflowTask
from app.domains.workflow.models import WorkflowDefinition
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from seed_contact_forms import seed_contact_forms
from tests.conftest import form_guard_fields

pytestmark = pytest.mark.ui_serverrendered


def _all(db, model):
    return db.query(model).execution_options(include_all_tenants=True)


def _forms(db, tenant_id: int) -> list:
    return _all(db, Form).filter(Form.tenant_id == tenant_id, Form.slug == CONTACT_FORM_SLUG).all()


def _definitions(db, tenant_id: int) -> list:
    return (
        _all(db, WorkflowDefinition)
        .filter(
            WorkflowDefinition.tenant_id == tenant_id,
            WorkflowDefinition.code == MESSAGE_WORKFLOW,
        )
        .all()
    )


def _bare_platform(db):
    """The platform as every environment had it: no contact form, no definition."""
    platform = platform_org(db)
    assert platform is not None, "the test database has no platform organisation"
    for row in (*_forms(db, platform.id), *_definitions(db, platform.id)):
        db.delete(row)
    db.commit()
    return platform


def test_the_seed_gives_the_platform_one_contact_form_and_a_second_start_adds_nothing(db_session):
    platform = _bare_platform(db_session)

    first = seed_contact_forms(db_session)

    assert f"{platform.code}: contactformulier + werkbankdefinitie" in first
    assert len(_forms(db_session, platform.id)) == 1
    assert len(_definitions(db_session, platform.id)) == 1
    form = _forms(db_session, platform.id)[0]
    assert form.title == "Contacteer ons" and len(form.fields) == 1 and form.fields[0].required
    counts = (_all(db_session, Form).count(), _all(db_session, WorkflowDefinition).count())

    assert seed_contact_forms(db_session) == [], "a second start adds nothing"
    assert (_all(db_session, Form).count(), _all(db_session, WorkflowDefinition).count()) == counts
    assert len(_forms(db_session, platform.id)) == 1


def test_a_message_on_the_platform_makes_a_task_in_the_platforms_werkbank(
    client, platform_workspace, db_session
):
    platform = _bare_platform(db_session)
    seed_contact_forms(db_session)
    tasks_elsewhere = (
        _all(db_session, WorkflowTask).filter(WorkflowTask.tenant_id != platform.id).count()
    )

    name = f"Afzender {secrets.token_hex(3)}"
    answer = client.post(
        "/berichten",
        data={**form_guard_fields(), "naam": name, "email": "a@example.com", "bericht": "Vraag?"},
    )

    assert answer.status_code == 200, answer.text[:300]
    assert "tijdelijk niet beschikbaar" not in answer.text
    db_session.expire_all()
    submission = (
        _all(db_session, FormSubmission).filter(FormSubmission.submitter_name == name).one()
    )
    assert submission.tenant_id == platform.id
    task = (
        _all(db_session, WorkflowTask).filter(WorkflowTask.subject_id == str(submission.id)).one()
    )
    assert task.tenant_id == platform.id, "the task is not in the platform's Werkbank"
    assert task.tenant_id != TENANT_MILLEGEM_ID
    assert (
        _all(db_session, WorkflowTask).filter(WorkflowTask.tenant_id != platform.id).count()
        == tasks_elsewhere
    ), "the message made a task in another tenant's Werkbank"


# ── the placeholder ──────────────────────────────────────────────────────────


def _button(html: str) -> list[tuple[str, str]]:
    """The form buttons on a page: (address, label)."""
    return [
        (href, re.sub(r"\s+", " ", label).strip())
        for href, label in re.findall(
            r'<span data-form-button="[^"]*"[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', html, re.S
        )
    ]


def _home_with(db, platform, content: str):
    """The platform's own home page (#1543), with this content.

    CR-17 (#1671): the site shows the page's PUBLISHED DOCUMENT, not her
    stored HTML — so the test writes her the way an author does, through the
    app's own doors: the migration's parse into a document (a placeholder
    code stays TEXT), Opslaan and Publiceren. Writing `page.content` would
    test nothing: the reader no longer looks at her.
    """
    from app.domains.cms.api import publish, save_document
    from app.domains.cms.parse import parse_html

    page = (
        _all(db, CmsPage).filter(CmsPage.tenant_id == platform.id, CmsPage.is_home.is_(True)).one()
    )
    document = parse_html(content, on_page=True)
    assert document is not None, f"the test's content does not convert: {content!r}"
    save_document(db, page.id, document)
    publish(db, page.id)
    return page


def test_both_forms_of_the_code_render_one_button(client, platform_workspace, db_session):
    platform = _bare_platform(db_session)
    seed_contact_forms(db_session)

    _home_with(db_session, platform, "<p>Welkom.</p><p>{{form:berichten|Contacteer ons}}</p>")
    home = client.get("/").text
    assert _button(home) == [("/berichten", "Contacteer ons")]
    assert "{{form" not in home

    # Without a label the button carries the form's title.
    form = _forms(db_session, platform.id)[0]
    form.title = "Stel je vraag"
    _home_with(db_session, platform, "<p>{{form:berichten}}</p>")
    assert _button(client.get("/").text) == [("/berichten", "Stel je vraag")]
    # The button leads to a form that can be sent.
    page = client.get("/berichten")
    assert page.status_code == 200 and "Je bericht" in page.text


def test_any_form_of_the_tenant_can_have_a_button(client, platform_workspace, db_session):
    platform = _bare_platform(db_session)
    other = Form(
        title="Inschrijven voor de infoavond",
        slug="infoavond",
        status="open",
        share_token=secrets.token_hex(16),
    )
    other.tenant_id = platform.id
    db_session.add(other)
    _home_with(
        db_session, platform, "<p>{{form:infoavond}}</p><p>{{form:infoavond|Schrijf je in}}</p>"
    )

    assert _button(client.get("/").text) == [
        ("/f/infoavond", "Inschrijven voor de infoavond"),
        ("/f/infoavond", "Schrijf je in"),
    ]


def test_a_form_that_cannot_take_a_submission_renders_nothing(
    client, platform_workspace, db_session
):
    platform = _bare_platform(db_session)
    closed = Form(
        title="Gesloten", slug="gesloten", status="closed", share_token=secrets.token_hex(16)
    )
    closed.tenant_id = platform.id
    elsewhere = Form(
        title="Van een ander", slug="vanelders", status="open", share_token=secrets.token_hex(16)
    )
    elsewhere.tenant_id = TENANT_MILLEGEM_ID
    db_session.add_all([closed, elsewhere])
    _home_with(
        db_session,
        platform,
        "<p>A {{form:onbekend}} B {{form:gesloten|Dicht}} C {{form:vanelders|Elders}} "
        "D {{form:berichten|Contact}} E</p>",
    )

    home = client.get("/").text

    # An unknown slug, a closed form, another tenant's form, and the contact form
    # that cannot take a message (the platform has none here): no button, and
    # never the raw code.
    assert _button(home) == []
    assert "{{form" not in home and "data-form-button=" not in home
    assert re.search(r"A\s+B\s+C\s+D\s+E", home), "the text around the codes is gone"

    # The contact form with its definition taken away is no contact form (#1509).
    seed_contact_forms(db_session)
    for row in _definitions(db_session, platform.id):
        db_session.delete(row)
    db_session.commit()
    assert _button(client.get("/").text) == []


def test_a_label_with_markup_is_escaped(client, platform_workspace, db_session):
    platform = _bare_platform(db_session)
    seed_contact_forms(db_session)
    # As the editor stores what an author types: through the document editor
    # the tags are LITERAL TEXT in the code (the toolbar makes marks, it
    # cannot type a tag), so the code stays one text node and the renderer
    # hands the builder the label as typed. What she renders is escaped.
    from app.domains.cms.api import publish, save_document

    home = (
        _all(db_session, CmsPage)
        .filter(CmsPage.tenant_id == platform.id, CmsPage.is_home.is_(True))
        .one()
    )
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "{{form:berichten|<b>vet</b>}}"},
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "{{form:berichten|<script>alert(1)</script> & meer}}",
                    },
                ],
            },
        ],
    }
    save_document(db_session, home.id, document)
    publish(db_session, home.id)

    home_html = client.get("/").text

    labels = [label for _href, label in _button(home_html)]
    assert labels == [
        "&lt;b&gt;vet&lt;/b&gt;",
        "&lt;script&gt;alert(1)&lt;/script&gt; &amp; meer",
    ], f"the labels lost their escaping: {labels}"
    main = home_html[home_html.index("cms-content") :]
    assert "<b>vet</b>" not in main and "<script>alert(1)" not in main


def test_the_editor_lists_the_code_with_its_two_forms():
    from app.domains.cms.render import PLACEHOLDER_LABELS

    assert "form:berichten" in PLACEHOLDER_LABELS
    assert "form:berichten|Contacteer ons" in PLACEHOLDER_LABELS


def test_the_associations_fixed_home_keeps_its_button(client, db_session):
    """No automatic button under a page that is a home — but `home.html`, the
    association's fixed home, keeps the one it had (#1509)."""
    home = client.get("/").text
    assert "Contacteer ons" in home and "data-form-button=" not in home
