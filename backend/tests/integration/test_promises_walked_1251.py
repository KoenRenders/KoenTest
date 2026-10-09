"""The promises a test walks, because the gate's static walk cannot (#1251, cut C8).

A `required`, `min` or `pattern` in a template promises the visitor that the
server asks the same. The gate *promise kept* walks template → form → route →
column; where it cannot — the field is no column, the form's target is a
variable, the route reads the form as a whole — the input names the test that
walks it instead (`{# promise walked by: … #}`), and those tests stand here.

Each test posts to the real route what the browser would refuse and says, in
its docstring, which form and route it walks, what it posts, and **what the
visitor gets**: the words in the form, or a bare refusal that only someone past
the browser's own check can meet.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.designstudio.api import Design
from app.domains.forms.api import FormField, FormSubmission
from app.domains.media.api import MediaAsset
from app.domains.meetings.api import Meeting
from app.kernel.tenant_config import tenant_newsletter_daily_cap
from tests import forms_door
from tests.conftest import SEEDED_ADMIN_EMAIL, form_guard_fields
from tests.integration.test_design_slots_on_the_picker import _activity, _design


def _board(client) -> dict[str, str]:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


@pytest.mark.parametrize("empty", ["naam", "bericht"])
def test_the_contact_form_refuses_an_empty_name_and_an_empty_message(client, db_session, empty):
    """Form: the public contact form (`forms/_berichten_form.html`), route
    `POST /berichten`. Posts everything filled in but one field, empty — with a
    valid proof for the form guard, so the answer is the form's and not the guard's.
    The visitor gets the form back with the sentence in it (the form swaps into
    itself, 200); no submission is stored."""
    data = {**form_guard_fields(), "naam": "An", "email": "an@example.org", "bericht": "Hallo"}
    data[empty] = ""
    answer = client.post("/berichten", data=data)
    assert answer.status_code == 200
    assert "Vul je naam, een geldig e-mailadres en je bericht in." in answer.text
    assert db_session.query(FormSubmission).count() == 0


def test_the_newsletter_sign_up_refuses_an_empty_address(client, db_session):
    """Form: the public newsletter sign-up (`newsletter/_nb_publiek.html`), route
    `POST /nieuwsbrief`. Posts `"email"` empty, with a valid proof for the form
    guard (without it the guard answers, friendly, and this test would pass for
    the wrong reason). The visitor gets the sign-up block back with the sentence
    in it and no confirmation (200); nobody is subscribed."""
    from app.domains.newsletter.api import Subscriber

    answer = client.post("/nieuwsbrief", data={**form_guard_fields(), "email": ""})
    assert answer.status_code == 200
    assert "Dat is geen geldig e-mailadres." in answer.text
    assert "We stuurden een mail" not in answer.text
    assert db_session.query(Subscriber).count() == 0


def test_the_media_upload_refuses_a_post_without_a_file(client, db_session):
    """Form: the upload form of the media library (`media/admin_media_nieuw.html`),
    route `POST /admin/media`. Posts the kind and no `"files"`. The server answers
    a bare 422 — the route's required file — and stores nothing. In a browser the
    `required` on the file input stops this before it is sent; a visitor past
    that check gets the screen's general refusal, not words in the form."""
    headers = _board(client)
    before = db_session.query(MediaAsset).count()
    answer = client.post("/admin/media", data={"kind": "sponsor"}, headers=headers)
    assert answer.status_code == 422
    db_session.expire_all()
    assert db_session.query(MediaAsset).count() == before


def test_a_meeting_is_not_made_without_its_date(client, db_session):
    """Form: the new-meeting form (`meetings/admin_vergadering_nieuw.html`), route
    `POST /admin/vergaderingen` (the same template posts an edit to
    `/admin/vergaderingen/{id}/bewerken`; its target is a variable, which is why
    the gate cannot walk it). Posts `"meeting_date"` empty. The server answers a
    bare 422 and makes no meeting. It is a plain form post: in a browser the
    `required` on the date stops it; past that check the visitor gets the bare
    refusal as a page, not words in the form."""
    headers = _board(client)
    before = db_session.query(Meeting).count()
    answer = client.post(
        "/admin/vergaderingen",
        data={"meeting_date": "", "location": "Zaal"},
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    db_session.expire_all()
    assert db_session.query(Meeting).count() == before


def test_the_form_builder_refuses_a_question_without_a_label(client, db_session):
    """Form: the question form of the form builder (`forms/_fb_builder.html`),
    route `POST /admin/formulieren/{form_id}/velden` (a new question; the same
    form posts an existing one to `…/velden/{field_id}`, chosen by a Jinja `if`,
    which is why the gate cannot walk it). Posts `"label"` empty. The server
    answers a bare 422 and adds no question; in a browser the `required` on the
    label stops it, and past that check the builder shows its general refusal."""
    headers = _board(client)
    form_id = forms_door.create_form(client, {"title": "Wandeling", "sections": []}).json()["id"]
    answer = client.post(
        f"/admin/formulieren/{form_id}/velden",
        data={"label": "", "field_type": "text"},
        headers=headers,
    )
    assert answer.status_code == 422
    db_session.expire_all()
    assert db_session.query(FormField).filter(FormField.form_id == form_id).count() == 0


def test_the_form_builder_refuses_an_option_without_a_label(client, db_session):
    """Form: the option form of the form builder (the second form of
    `forms/_fb_builder.html`), route
    `POST /admin/formulieren/{form_id}/velden/{field_id}/opties` (a new option;
    an existing one posts to `…/opties/{option_id}`, chosen by a Jinja `if`).
    Posts `"label"` empty. The server answers a bare 422 and adds no option; in a
    browser the `required` on the label stops it, and past that check the builder
    shows its general refusal."""
    headers = _board(client)
    form_id = forms_door.create_form(client, {"title": "Wandeling", "sections": []}).json()["id"]
    made = client.post(
        f"/admin/formulieren/{form_id}/velden",
        data={"label": "Welke afstand?", "field_type": "radio"},
        headers=headers,
    )
    assert made.status_code == 200, made.text[:200]
    db_session.expire_all()
    field = db_session.query(FormField).filter(FormField.form_id == form_id).one()
    answer = client.post(
        f"/admin/formulieren/{form_id}/velden/{field.id}/opties",
        data={"label": ""},
        headers=headers,
    )
    assert answer.status_code == 422
    db_session.expire_all()
    assert db_session.get(FormField, field.id).options == []


@pytest.mark.parametrize("below_one", ["0", "-5"])
def test_the_daily_cap_of_the_newsletter_is_not_set_below_one(client, db_session, below_one):
    """Form: the newsletter's settings (`newsletter/_nb_instellingen.html`), route
    `POST /admin/nieuwsbrieven/instellingen`. Posts `"daily_cap"` below the
    `min="1"` of the input. The board gets the settings back with the sentence in
    them (the block swaps into itself, 200) and the cap stays what it was."""
    headers = _board(client)
    before = tenant_newsletter_daily_cap(db_session)
    answer = client.post(
        "/admin/nieuwsbrieven/instellingen",
        data={"house_style": "Warm.", "daily_cap": below_one},
        headers=headers,
    )
    assert answer.status_code == 200
    assert "Het dagplafond is een getal groter dan nul." in answer.text
    db_session.expire_all()
    assert tenant_newsletter_daily_cap(db_session) == before


@pytest.mark.parametrize(("posted", "stored"), [("-1", 0), ("7", 1)])
def test_a_focus_point_outside_the_picture_is_stored_at_its_edge(
    client, db_session, posted, stored
):
    """Form: the editor of the Design Studio (`designstudio/admin_ontwerp.html`),
    route `POST /admin/ontwerpen/{design_id}`. Posts `"main_focus_x"` and
    `"main_focus_y"` outside the `min="0"`/`max="1"` of the two inputs.

    **The server does not refuse here: it clamps.** The save succeeds (a redirect
    with "bewaard") and the value is stored at the edge of the range — so nothing
    outside 0..1 is ever stored, which is what the promise is for. A slider cannot
    be pushed out of range by hand, so nobody meets this in a browser."""
    headers = _board(client)
    activity = _activity(db_session, "Kerstmarkt")
    design = _design(db_session, activity)
    db_session.commit()
    answer = client.post(
        f"/admin/ontwerpen/{design.id}",
        data={
            "duo_code": design.duo_code,
            "preset": "beeld",
            "main_focus_x": posted,
            "main_focus_y": posted,
            "layout": "print_a",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303 and "notice=bewaard" in answer.headers["location"]
    db_session.expire_all()
    saved = db_session.get(Design, design.id)
    assert (float(saved.main_focus_x), float(saved.main_focus_y)) == (stored, stored)


def test_the_specimen_form_of_the_design_system_posts_nowhere(client, db_session):
    """Form: the specimen of a form on the design-system page
    (`ui/templates/design_system.html`), which shows the kit's `"naam"` field with
    its `required` mark. It is a specimen: it has no route to post to, so its
    `required` promises nothing to a server — there is nothing to refuse. Held
    here: the page renders the field, and no form around it has a target."""
    import re

    _board(client)
    page = client.get("/admin/design-system")
    assert page.status_code == 200
    field = page.text.index('id="ds-naam"')
    opened = page.text.rfind("<form", 0, field)
    closed = page.text.rfind("</form>", 0, field)
    if opened > closed:  # the field stands inside a form: that form must post nowhere
        tag = page.text[opened : page.text.index(">", opened)]
        assert not re.search(r"\b(hx-post|action)=", tag), tag
