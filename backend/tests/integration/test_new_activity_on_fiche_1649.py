""" "+ Nieuwe activiteit" opens the fiche itself, empty, in edit mode (#1649; CR-11 Q84).

Koen, 6 October 2026: "Kunnen we dat startscherm om een activiteit aan te
maken niet skippen?" The start screen (#623) asked a few fields and then sent
you to the editor for the rest; the record page now does both, and Raakje's
proposer (#1604) can fill the empty form.

Because this moves the creation of a core object, what the start screen did
that the fiche did not was measured first, rule by rule; each has its test here:

| The start screen                                   | The new way                         |
|----------------------------------------------------|-------------------------------------|
| a name is required                                 | refused at the field                |
| a first date is required (as the JSON API asks)    | refused at the row / without a row  |
| the friendly URL is proposed from the name (#884)  | still proposed; a typed one wins    |
| a hand-made activity was published at once         | **a draft** (Koen, 6 October 2026)  |
| no poster upload ("zodra de activiteit bestaat")   | the poster goes with the one save   |
| ADMIN / OPERATOR, with CSRF                        | the same dependencies               |
| nothing in the database before the form is sent    | the GET writes nothing              |

And two things the issue asks of a creation: it is ONE transaction — a refusal
of any part leaves no activity, no date, no history — and it writes one row
"created" in the activity's history.

Broken on purpose (6 October 2026), each red for its own reason: the date rule
taken out of `create_fiche`; `status=NEW_ACTIVITY_STATUS` not passed; the
activity added OUTSIDE the savepoint (before `_write`) → a refused component
leaves an activity behind; the extra fields written by an update after the
insert → two history rows; the edit context returned for the new address; the
old create route put back.
"""

from __future__ import annotations

import io
import re
from datetime import date, time

import pytest

from app.domains.activities.api import Activity, ActivityStatus
from app.domains.activities.models import ActivityDate, ActivityHistory, ActivitySubRegistration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.reporting.assistant_context import context_for
from tests._fiche import post_new_activity
from tests.conftest import SEEDED_ADMIN_EMAIL, form_fields

pytestmark = pytest.mark.ui_serverrendered

NEW = "/admin/activiteiten/nieuw"


def _login(client, email: str = SEEDED_ADMIN_EMAIL) -> dict:
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _counts(db) -> tuple[int, int, int, int]:
    db.expire_all()
    return (
        db.query(Activity).execution_options(include_deleted=True).count(),
        db.query(ActivityDate).execution_options(include_deleted=True).count(),
        db.query(ActivitySubRegistration).execution_options(include_deleted=True).count(),
        db.query(ActivityHistory).count(),
    )


def _named(db, name: str) -> Activity:
    db.expire_all()
    return db.query(Activity).filter(Activity.name == name).one()


# ── The page ─────────────────────────────────────────────────────────────────


def test_the_route_renders_the_record_page_in_edit_mode_without_a_record(client, db_session):
    """Red on master: a card with five fields and a line "extra datums, onderdelen
    en producten vul je daarna aan"."""
    _login(client)
    before = _counts(db_session)

    page = client.get(NEW)

    assert page.status_code == 200
    html = page.text[page.text.index("<main") :]
    assert 'data-form-flow data-mode="edit"' in html
    for part in (
        'id="aa-section-activity"',
        'id="aa-section-audience"',
        'id="aa-section-internal"',
        'id="aa-group-dates"',
        'id="aa-group-components"',
        'id="aa-group-organisers"',
        "data-rare-settings",
    ):
        assert part in html, f"{part} is not on the new fiche"
    form = re.search(r'<form id="aa-act-form"[^>]*>', html, re.S).group(0)
    assert f'hx-post="{NEW}"' in form and 'hx-target="#aa-record"' in form
    # the head: a title, what it will be, the way back — and nothing to act on
    head = html[html.index('id="aa-recordkop"') : html.index("data-record-frame")]
    assert ">Nieuwe activiteit<" in head and ">Concept<" in head and ">Bewerken<" in head
    assert 'data-way-back href="/admin/activiteiten"' in head
    assert "data-actions-trigger" not in head and "data-related-tabs" not in head
    assert 'id="aa-rail"' not in html, "a record that does not exist has no summary"
    # one bar: Annuleren to the list, Opslaan, no Verwijderen
    assert html.count("data-action-bar") == 1
    assert 'href="/admin/activiteiten" data-form-cancel' in html
    assert "data-form-save" in html and "data-form-delete" not in html
    # one empty date row to start from, and no row anywhere else
    sent = form_fields(page.text, "aa-act-form")
    assert sent["d_order"] == ["n1"] and sent["d.n1.start_date"] == ""
    assert "c_order" not in sent and "o_order" not in sent
    assert sent["name"] == ""
    assert _counts(db_session) == before, "opening the page wrote something"


def test_the_list_links_to_it_and_the_old_form_target_is_gone(client, db_session):
    headers = _login(client)
    assert f'href="{NEW}"' in client.get("/admin/activiteiten").text
    # the start screen posted its five fields here
    old = client.post("/admin/activiteiten", headers=headers, data={"name": "x"})
    assert old.status_code == 405


def test_who_may_not_manage_activities_may_not_open_or_send_it(client, db_session):
    from app.domains.auth.api import User, UserRole

    user = User(email="finance-1649@example.org")
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db_session.commit()
    headers = _login(client, "finance-1649@example.org")
    assert client.get(NEW, headers={"HX-Request": "true"}).status_code == 403
    assert (
        post_new_activity(client, headers, {"name": "x", "start_date": "2031-01-01"}).status_code
        == 403
    )
    _login(client)
    no_csrf = post_new_activity(client, {}, {"name": "x", "start_date": "2031-01-01"})
    assert no_csrf.status_code == 403
    assert db_session.query(Activity).filter(Activity.name == "x").count() == 0


# ── Opslaan creates ──────────────────────────────────────────────────────────


def test_one_save_creates_the_activity_with_its_groups_and_one_history_row(client, db_session):
    headers = _login(client)
    before = _counts(db_session)

    answer = post_new_activity(
        client,
        headers,
        {
            "name": "Schaatsen met Draak",
            "location": "Schaatsbaan",
            "description": "Samen het ijs op.",
            "board_notes": "Sleutel bij de conciërge.",
            "members_only": "1",
            "start_date": "2031-11-08",
            "start_time": "10:00",
            "end_time": "12:00",
            "c_order": ["n1"],
            "c.n1.name": "Deelname",
            "p_order.n1": ["n2"],
            "p.n2.name": "Ticket",
            "p.n2.price": "5,00",
            "p.n2.settlement": "paid",
            "p.n2.is_active": "1",
        },
    )

    assert answer.status_code == 200, answer.text[:400]
    activity = _named(db_session, "Schaatsen met Draak")
    assert answer.headers["HX-Push-Url"] == f"/admin/activiteiten/{activity.id}"
    assert (activity.location, activity.description) == ("Schaatsbaan", "Samen het ijs op.")
    assert activity.board_notes == "Sleutel bij de conciërge." and activity.members_only is True
    assert activity.status is ActivityStatus.DRAFT, "a new activity starts as a draft"
    assert activity.slug == "schaatsen-met-draak", "the friendly URL is proposed from the name"
    assert [(d.start_date, d.start_time, d.end_time) for d in activity.dates] == [
        (date(2031, 11, 8), time(10, 0), time(12, 0))
    ]
    (component,) = activity.sub_registrations
    assert component.name == "Deelname" and [p.name for p in component.products] == ["Ticket"]
    after = _counts(db_session)
    assert (after[0], after[1], after[2]) == (before[0] + 1, before[1] + 1, before[2] + 1)
    rows = db_session.query(ActivityHistory).filter_by(activity_id=activity.id).all()
    assert [r.action for r in rows] == ["activity_created"], "one row says: created"
    assert rows[0].name == "Schaatsen met Draak"
    # the answer is the record page of what now exists, reading, with the toast
    html = answer.text
    assert 'id="aa-recordkop"' in html and 'data-mode="read"' in html
    assert "Schaatsen met Draak" in html and "data-related-tabs" in html
    assert "Opgeslagen" in html and 'id="aa-act-form"' not in html
    assert "<html" not in html.lower(), "a fragment for #aa-record, not a page"


def test_a_typed_friendly_url_wins_and_a_taken_one_is_refused_at_its_field(client, db_session):
    headers = _login(client)
    first = post_new_activity(
        client, headers, {"name": "Eerste", "slug": "kerstmarkt", "start_date": "2031-12-20"}
    )
    assert first.status_code == 200
    assert _named(db_session, "Eerste").slug == "kerstmarkt"

    before = _counts(db_session)
    second = post_new_activity(
        client, headers, {"name": "Tweede", "slug": "kerstmarkt", "start_date": "2031-12-21"}
    )
    assert second.status_code == 422
    assert 'data-error-for="slug"' in second.text
    assert _counts(db_session) == before


# ── The refusals, and nothing half written ───────────────────────────────────


def test_an_empty_name_is_refused_at_the_field_and_nothing_exists(client, db_session):
    headers = _login(client)
    before = _counts(db_session)

    answer = post_new_activity(client, headers, {"name": "  ", "start_date": "2031-01-01"})

    assert answer.status_code == 422
    assert answer.headers["HX-Retarget"] == "#aa-fiche-message"
    assert 'data-error-for="name"' in answer.text
    assert "De activiteit heeft een naam nodig." in answer.text
    assert "<html" not in answer.text.lower() and "data-form-flow" not in answer.text
    assert _counts(db_session) == before


def test_a_new_activity_needs_a_first_date_on_the_row_or_without_one(client, db_session):
    """The rule of the start screen and of the JSON API. The empty fiche opens
    with one row: left empty, the refusal stands on its date; taken out, on the
    form as a whole."""
    headers = _login(client)
    before = _counts(db_session)

    empty_row = post_new_activity(client, headers, {"name": "Zonder dag"})
    assert empty_row.status_code == 422
    assert 'data-error-for="d.n1.start_date"' in empty_row.text

    no_row = post_new_activity(client, headers, {"name": "Zonder rij", "d_order": []})
    assert no_row.status_code == 422
    assert "Een nieuwe activiteit heeft een eerste datum nodig." in no_row.text
    assert _counts(db_session) == before


def test_a_refused_part_leaves_no_activity_behind(client, db_session):
    """One transaction. The name and the date are good; the product is not (a
    negative price) — the activity that was added for it is taken back with it,
    history and all."""
    headers = _login(client)
    before = _counts(db_session)

    answer = post_new_activity(
        client,
        headers,
        {
            "name": "Half ontstaan",
            "start_date": "2031-05-01",
            "c_order": ["n1"],
            "c.n1.name": "Deelname",
            "p_order.n1": ["n2"],
            "p.n2.name": "Ticket",
            "p.n2.price": "-5,00",
            "p.n2.settlement": "paid",
        },
    )

    assert answer.status_code == 422, answer.text[:300]
    assert "mag niet negatief zijn" in answer.text
    assert _counts(db_session) == before, "a refused creation left something behind"
    assert db_session.query(Activity).filter(Activity.name == "Half ontstaan").count() == 0


def test_a_refused_date_leaves_nothing_either(client, db_session):
    headers = _login(client)
    before = _counts(db_session)
    answer = post_new_activity(
        client,
        headers,
        {"name": "Achterstevoren", "start_date": "2031-09-20", "end_date": "2031-09-18"},
    )
    assert answer.status_code == 422 and "einddatum ligt vóór de begindatum" in answer.text
    assert _counts(db_session) == before


def test_the_poster_goes_with_the_one_save(client, db_session):
    """The start screen said "een affiche opladen kan zodra de activiteit
    bestaat"; on the fiche the upload is part of the creation."""
    headers = _login(client)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92"
        b"\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    answer = post_new_activity(
        client,
        headers,
        {"name": "Met affiche", "start_date": "2031-03-01"},
        files={"file": ("affiche.png", io.BytesIO(png), "image/png")},
    )
    assert answer.status_code == 200, answer.text[:300]
    from app.domains.activities.api import get_activity_detail

    detail = get_activity_detail(db_session, _named(db_session, "Met affiche").id)
    assert detail.poster_asset_url, "the poster was not stored with the creation"


# ── What stays ───────────────────────────────────────────────────────────────


def test_the_json_api_creates_as_before_published(client, db_session, admin_headers):
    answer = client.post(
        "/api/v1/activities",
        headers=admin_headers,
        json={"name": "Via de API", "dates": [{"start_date": "2031-04-04"}]},
    )
    assert answer.status_code in (200, 201), answer.text
    assert _named(db_session, "Via de API").status is ActivityStatus.PUBLISHED
    without = client.post(
        "/api/v1/activities", headers=admin_headers, json={"name": "x", "dates": []}
    )
    assert without.status_code == 422, "the API still asks a first date"


def test_copying_keeps_its_own_way(client, db_session):
    """The copy never passed the start screen: its own step, `copy_activity`,
    and the fiche of the copy."""
    headers = _login(client)
    post_new_activity(client, headers, {"name": "Origineel", "start_date": "2031-06-14"})
    original = _named(db_session, "Origineel")

    step = client.get(f"/admin/activiteiten/{original.id}/kopieren")
    assert step.status_code == 200 and "Origineel" in step.text
    made = client.post(
        f"/admin/activiteiten/{original.id}/kopieren",
        headers=headers,
        data={"start_date": "2032-06-12"},
    )
    assert made.status_code == 204, made.text[:300]
    copy_id = int(made.headers["HX-Redirect"].rsplit("/", 1)[1])
    assert copy_id != original.id
    db_session.expire_all()
    copy = db_session.get(Activity, copy_id)
    assert copy.status is ActivityStatus.DRAFT and copy.dates[0].start_date == date(2032, 6, 12)


# ── Raakje ───────────────────────────────────────────────────────────────────


def test_the_assistents_context_there_is_a_new_activity(db_session):
    context = context_for(db_session, f"http://testserver{NEW}", tenant_id=1)
    assert context.key == "activity-new" and context.can_ask
    assert context.label == "voorstel voor een nieuwe activiteit"
    assert context.post_url == f"{NEW}/raakje/voorstel"


def test_the_proposer_fills_the_empty_fiche_from_the_request_alone(client, db_session, monkeypatch):
    """The proposer of #1604 on an activity that holds nothing: name, location,
    description and the first date row — every base empty, nothing written."""
    import json

    from app.domains.chatbot.providers.base import AssistantMessage
    from app.kernel.tenant_config import set_setting

    class Scripted:
        name, model = "mock", "scripted"

        def __init__(self, *answers):
            self.answers = list(answers)

        def complete(self, messages, tools=None, tool_choice=None):
            return AssistantMessage(
                content=self.answers.pop(0) if self.answers else json.dumps({"unsupported": []})
            )

    provider = Scripted(
        json.dumps(
            {
                "reply": "Voorstel klaar.",
                "name": "Schaatsen met Draak",
                "location": "schaatsbaan Herentals",
                "description": "Kom mee schaatsen.",
                "date": {"start_date": "2026-11-08", "start_time": "10:00"},
                "date_source": "zondag 8 november",
            }
        )
    )
    monkeypatch.setattr("app.domains.chatbot.api.get_provider", lambda model="": provider)
    monkeypatch.setattr("app.config.settings.admin_chat_enabled", True)
    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()
    headers = _login(client)
    before = _counts(db_session)

    answer = client.post(
        f"{NEW}/raakje/voorstel",
        headers={**headers, "HX-Request": "true"},
        data={
            "vraag": "Schaatsen met Draak in de schaatsbaan Herentals op zondag 8 november om 10 uur"
        },
    )

    assert answer.status_code == 200 and "X-Raakje-Failed" not in answer.headers
    fields = json.loads(
        re.search(
            r"<script type=\"application/json\" data-proposal-fields>(.*?)</script>",
            answer.text,
            re.S,
        ).group(1)
    )
    assert [f["name"] for f in fields] == [
        "name",
        "location",
        "description",
        "start_date",
        "start_time",
    ]
    assert all(f["base"] == "" for f in fields), "the fiche is empty: every base is"
    assert "data-proposal-apply-url" not in answer.text
    assert _counts(db_session) == before, "a proposal wrote something"

    monkeypatch.setattr("app.config.settings.admin_chat_enabled", False)
    off = client.post(f"{NEW}/raakje/voorstel", headers=headers, data={"vraag": "x"})
    assert off.status_code == 404
