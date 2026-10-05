"""The fiche's one write route, and the groups it shows (CR-11 block 7, #1559).

`POST /admin/activiteiten/{id}` with the whole form is the only way the screen
writes a date, a component, a product, an organiser or an attachment. This file
drives that route the way the screen does (`tests/_fiche.py` builds the form) and
reads the screen in its two states. What the save itself guarantees — one
transaction, every refusal, every history row — is proven on the service in
`test_fiche_save.py`; here the wiring: the form's names reach the save, a refusal
answers in the fiche's message line and leaves the form alone, and the rows read
and edit as the norm says (design-system-end-state §3.3).
"""

from __future__ import annotations

import io
import re
from datetime import date, time, timedelta

import pytest

from app.domains.activities.models import (
    Activity,
    ActivityDate,
    ActivityOrganiser,
    ActivityProduct,
    ActivitySubRegistration,
    Registration,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.media.api import MediaAsset
from tests._fiche import Fiche
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _seed(db):
    activity, component, product = seed_activity_with_product(db, price="10.00", is_free=False)
    db.commit()
    return activity, component, product


def _member(
    db, first: str, last: str = "Voorbeeld", *, member: bool = True
) -> tuple[Person, int | None]:
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first, last_name=last
    )
    db.add(person)
    db.flush()
    household_id = None
    if member:
        household = Member()
        db.add(household)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
        household_id = household.id
    db.commit()
    return person, household_id


def _group(html: str, group_id: str) -> str:
    """One repeating group of the page, from its opening tag to the next group
    or the closed last section."""
    start = html.index(f'id="{group_id}"')
    rest = html[start:]
    ends = [rest.find(marker, 10) for marker in ('id="aa-group-', "data-rare-settings")]
    ends = [e for e in ends if e != -1]
    return rest[: min(ends)] if ends else rest


def _page(client, activity_id: int, edit: bool = False) -> str:
    return client.get(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else "")).text


# ── The save, through the route ──────────────────────────────────────────────


def test_an_untouched_form_saves_and_changes_nothing(client, db_session):
    """The form the screen sends for an untouched fiche is read back to exactly
    what is stored: no row is added, removed or reordered."""
    activity, component, product = _seed(db_session)
    headers = _login(client)
    before = (
        db_session.query(ActivityDate).count(),
        db_session.query(ActivitySubRegistration).count(),
        db_session.query(ActivityProduct).count(),
    )
    response = Fiche(db_session, activity.id).post(client, headers)
    assert response.status_code == 200, response.text[:300]
    assert 'data-mode="read"' in response.text
    db_session.expire_all()
    assert before == (
        db_session.query(ActivityDate).count(),
        db_session.query(ActivitySubRegistration).count(),
        db_session.query(ActivityProduct).count(),
    )
    assert db_session.get(ActivityProduct, product.id).price == product.price


def test_a_date_is_added_and_an_existing_one_changed_with_their_hours(client, db_session):
    """#451/#454: a date with its begin and end hour, added and edited."""
    activity, _c, _p = _seed(db_session)
    headers = _login(client)
    existing = db_session.query(ActivityDate).filter_by(activity_id=activity.id).one()

    fiche = Fiche(db_session, activity.id)
    fiche.add("d", start_date="2031-09-01", start_time="19:30", end_time="22:00")
    fiche.set("d", existing.id, start_date="2032-01-15", start_time="10:00")
    response = fiche.post(client, headers)
    assert response.status_code == 200, response.text[:300]
    assert "19:30–22:00" in response.text and "10:00" in response.text

    db_session.expire_all()
    new = (
        db_session.query(ActivityDate)
        .filter_by(activity_id=activity.id, start_date=date(2031, 9, 1))
        .one()
    )
    assert (new.start_time, new.end_time) == (time(19, 30), time(22, 0))
    changed = db_session.get(ActivityDate, existing.id)
    assert (changed.start_date, changed.start_time) == (date(2032, 1, 15), time(10, 0))


def test_the_save_needs_the_csrf_token(client, db_session):
    activity, _c, _p = _seed(db_session)
    _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.add("d", start_date="2032-02-02")
    assert fiche.post(client, headers={}).status_code == 403
    assert db_session.query(ActivityDate).filter_by(activity_id=activity.id).count() == 1


def test_components_and_products_are_added_in_one_save_and_follow_the_forms_order(
    client, db_session
):
    """A new component with its first product, in the same save; then the order
    of the form is the order that is stored (#451/#454: reordering)."""
    activity, component, product = _seed(db_session)
    headers = _login(client)

    fiche = Fiche(db_session, activity.id)
    second = fiche.add(
        "c",
        name="Tweede",
        max_participants="40",
        registration_closes_on="2031-05-01",
        team_name_required=True,
    )
    fiche.add("p", parent=second, name="Soep", price="5,50", member_price="4", pay_on_site=True)
    assert fiche.post(client, headers).status_code == 200

    db_session.expire_all()
    new = (
        db_session.query(ActivitySubRegistration)
        .filter_by(activity_id=activity.id, name="Tweede")
        .one()
    )
    assert (new.max_participants, new.registration_closes_on, new.team_name_required) == (
        40,
        date(2031, 5, 1),
        True,
    )
    soup = db_session.query(ActivityProduct).filter_by(component_id=new.id).one()
    assert (
        str(soup.price),
        str(soup.member_price),
        soup.pay_on_site,
        soup.is_free,
        soup.is_active,
    ) == (
        "5.50",
        "4.00",
        True,
        False,
        True,
    ), "a comma is a decimal sign; the two payment switches arrive apart"

    def order() -> list[str]:
        db_session.expire_all()
        rows = db_session.query(ActivitySubRegistration).filter_by(activity_id=activity.id)
        return [c.name for c in rows.order_by(ActivitySubRegistration.sort_order)]

    assert order() == ["Onderdeel", "Tweede"]
    fiche = Fiche(db_session, activity.id)
    fiche.move("c", new.id, 0)
    assert fiche.post(client, headers).status_code == 200
    assert order() == ["Tweede", "Onderdeel"]


def test_the_deadline_is_set_and_cleared(client, db_session):
    """#1053: emptying "Inschrijven tot" is a valid choice and reaches the column."""
    activity, component, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, registration_closes_on="2031-04-30")
    fiche.post(client, headers)
    db_session.expire_all()
    assert db_session.get(ActivitySubRegistration, component.id).registration_closes_on == date(
        2031, 4, 30
    )

    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, registration_closes_on="")
    fiche.post(client, headers)
    db_session.expire_all()
    assert db_session.get(ActivitySubRegistration, component.id).registration_closes_on is None


def test_an_info_attachment_goes_with_the_save_also_on_a_new_component(client, db_session):
    """#654/#451: the fields and the file in one post; without a file the
    attachment stays; removing it is part of the save too (#1559 — it was a
    route of its own)."""
    activity, component, _p = _seed(db_session)
    headers = _login(client)

    fiche = Fiche(db_session, activity.id)
    new = fiche.add("c", name="Met bijlage")
    files = {
        f"c.{component.id}.file": ("info.png", io.BytesIO(PNG), "image/png"),
        f"c.{new}.file": ("reglement.png", io.BytesIO(PNG), "image/png"),
    }
    assert fiche.post(client, headers, files=files).status_code == 200
    db_session.expire_all()
    added = db_session.query(ActivitySubRegistration).filter_by(name="Met bijlage").one()

    def attachments(component_id: int) -> int:
        return db_session.query(MediaAsset).filter(MediaAsset.component_id == component_id).count()

    assert attachments(component.id) == 1 and attachments(added.id) == 1

    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, name="Hernoemd")
    assert fiche.post(client, headers).status_code == 200
    db_session.expire_all()
    assert attachments(component.id) == 1, "a save without a file leaves the attachment"

    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, info_delete="1")
    assert fiche.post(client, headers).status_code == 200
    db_session.expire_all()
    assert attachments(component.id) == 0 and attachments(added.id) == 1


def test_the_poster_is_stored_and_removed_with_the_save(client, db_session):
    activity, _c, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    assert (
        fiche.post(
            client, headers, files={"file": ("affiche.png", io.BytesIO(PNG), "image/png")}
        ).status_code
        == 200
    )
    assert db_session.query(MediaAsset).filter(MediaAsset.activity_id == activity.id).count() == 1

    fiche = Fiche(db_session, activity.id)
    fiche.data["file_delete"] = "1"
    assert fiche.post(client, headers).status_code == 200
    db_session.expire_all()
    assert db_session.query(MediaAsset).filter(MediaAsset.activity_id == activity.id).count() == 0


# ── A refusal: the reason, and the form left alone ───────────────────────────


def _refusal(response) -> str:
    assert response.status_code == 422, response.text[:300]
    assert response.headers["HX-Retarget"] == "#aa-fiche-message"
    assert response.headers["HX-Reswap"].startswith("innerHTML")
    assert "data-form-flow" not in response.text, "the answer is the reason, not the form again"
    return response.text


def test_a_refusal_answers_in_the_message_line_and_writes_nothing(client, db_session):
    """An HTML 422 is swapped (#1515); retargeted to the fiche's message line it
    leaves every row typed in the page where it is. Proven red by answering with
    the re-rendered fragment: `data-form-flow` is then in the answer."""
    activity, component, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.data["location"] = "Niet bewaard"
    fiche.add("d", start_date="2031-06-14", end_date="2031-06-13")
    text = _refusal(fiche.post(client, headers))
    assert "De einddatum ligt vóór de begindatum." in text
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).location != "Niet bewaard"
    assert db_session.query(ActivityDate).filter_by(activity_id=activity.id).count() == 1

    page = _page(client, activity.id, edit=True)
    assert 'id="aa-fiche-message"' in page, "the line the answer is sent to exists on the page"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"start_date": "geen-datum"}, "Ongeldige datum bij een datum."),
        ({"start_date": ""}, "Een datum heeft een begindatum nodig."),
        ({"start_date": "2031-06-14", "start_time": "25:99"}, "Ongeldig uur bij een beginuur."),
    ],
)
def test_a_date_that_is_no_date_is_refused_with_a_message(client, db_session, change, message):
    """These were a 500 through the row route (a schema built outside its `try`)."""
    activity, _c, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.add("d", **change)
    assert message in _refusal(fiche.post(client, headers))


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"name": "Soep", "price": "veel"}, "Ongeldig bedrag bij de prijs van “Soep”."),
        ({"name": "Soep", "price": "-1"}, "De prijs van “Soep” mag niet negatief zijn."),
        (
            {"name": "Soep", "max_participants": "tien"},
            "Het maximum van “Soep” is geen geheel getal.",
        ),
        (
            {"name": "Soep", "max_participants": "0"},
            "Het maximum van “Soep” moet groter zijn dan nul.",
        ),
        (
            {"name": "Soep", "is_free": True, "pay_on_site": True},
            "niet tegelijk gratis én ter plaatse",
        ),
        ({"name": ""}, "Een product heeft een naam nodig."),
    ],
)
def test_a_product_that_cannot_be_is_refused_with_a_message(client, db_session, fields, message):
    activity, component, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.add("p", parent=component.id, **fields)
    assert message in _refusal(fiche.post(client, headers))
    assert db_session.query(ActivityProduct).filter_by(component_id=component.id).count() == 1


def test_a_refused_file_says_why_and_how(client, db_session):
    """#451: an upload that fails must not fail in silence — and a HEIC photo
    from an iPhone gets the way out with it."""
    activity, component, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, name="Niet hernoemd")
    text = _refusal(
        fiche.post(
            client,
            headers,
            files={f"c.{component.id}.file": ("foto.heic", io.BytesIO(b"x"), "image/heic")},
        )
    )
    assert "Niet-ondersteund bestandstype: foto.heic" in text and "iPhone-HEIC" in text
    db_session.expire_all()
    assert db_session.get(ActivitySubRegistration, component.id).name == "Onderdeel"


def test_a_component_with_registrations_is_refused_by_name(client, db_session):
    """The new rule of #1559, at the screen."""
    activity, component, _p = _seed(db_session)
    db_session.add(
        Registration(
            activity_id=activity.id,
            component_id=component.id,
            registration_type="INDIVIDUAL",
            contact_name="An Voorbeeld",
            contact_email="an@example.com",
        )
    )
    db_session.commit()
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.remove("c", component.id)
    assert "Het onderdeel “Onderdeel” heeft één inschrijving" in _refusal(
        fiche.post(client, headers)
    )
    assert db_session.query(ActivitySubRegistration).filter_by(id=component.id).count() == 1


# ── Organisers, through the route ────────────────────────────────────────────


def test_organisers_are_picked_ordered_changed_and_removed(client, db_session):
    activity, _c, _p = _seed(db_session)
    an, _ = _member(db_session, "An")
    bert, _ = _member(db_session, "Bert")
    headers = _login(client)

    fiche = Fiche(db_session, activity.id)
    fiche.add("o", person_id=an.id, is_contact=True)
    fiche.add("o", person_id=bert.id, email_override="bert@example.com", show_mobile=False)
    assert fiche.post(client, headers).status_code == 200

    def rows() -> list[ActivityOrganiser]:
        db_session.expire_all()
        return (
            db_session.query(ActivityOrganiser)
            .filter_by(activity_id=activity.id)
            .order_by(ActivityOrganiser.sort_order)
            .all()
        )

    first, second = rows()
    assert (first.person_id, first.is_contact, second.person_id) == (an.id, True, bert.id)
    assert (second.email_override, second.show_mobile, second.show_email) == (
        "bert@example.com",
        False,
        True,
    )

    fiche = Fiche(db_session, activity.id)
    fiche.move("o", second.id, 0)
    assert fiche.post(client, headers).status_code == 200
    assert [r.person_id for r in rows()] == [bert.id, an.id]

    fiche = Fiche(db_session, activity.id)
    fiche.remove("o", second.id)
    assert fiche.post(client, headers).status_code == 200
    assert [(r.person_id, r.sort_order) for r in rows()] == [(an.id, 0)]


def test_only_a_member_becomes_organiser(client, db_session):
    """The rule, not the screen: the search only SHOWS members, and a form post
    does not go through the search (#1004)."""
    activity, _c, _p = _seed(db_session)
    guest, _ = _member(db_session, "Gast", member=False)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.add("o", person_id=guest.id)
    assert "Alleen leden kunnen organisator zijn." in _refusal(fiche.post(client, headers))
    assert db_session.query(ActivityOrganiser).filter_by(activity_id=activity.id).count() == 0


def test_the_last_contact_person_goes_only_after_the_confirmation(client, db_session):
    """#1004: a poster without a contact person silently falls back to the
    association's own details, so losing the last one is a question. The answer
    carries the button that confirms; the same form with `bevestigd` saves."""
    activity, _c, _p = _seed(db_session)
    an, _ = _member(db_session, "An")
    bert, _ = _member(db_session, "Bert")
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.add("o", person_id=an.id, is_contact=True)
    fiche.add("o", person_id=bert.id, is_contact=True)
    fiche.post(client, headers)
    db_session.expire_all()
    first, second = (
        db_session.query(ActivityOrganiser)
        .filter_by(activity_id=activity.id)
        .order_by(ActivityOrganiser.sort_order)
        .all()
    )

    # Unticking one of two needs no confirmation.
    fiche = Fiche(db_session, activity.id)
    fiche.set("o", second.id, is_contact=False)
    assert fiche.post(client, headers).status_code == 200

    fiche = Fiche(db_session, activity.id)
    fiche.set("o", first.id, is_contact=False)
    text = _refusal(fiche.post(client, headers))
    assert "Zonder contactpersoon" in text and "data-confirm-save" in text
    db_session.expire_all()
    assert db_session.get(ActivityOrganiser, first.id).is_contact is True

    fiche.data["bevestigd"] = "1"
    assert fiche.post(client, headers).status_code == 200
    db_session.expire_all()
    assert db_session.get(ActivityOrganiser, first.id).is_contact is False


def test_the_search_offers_members_with_their_address_and_skips_who_is_there(client, db_session):
    """#1004/#1353: members only, each with the address the mails would go to,
    and nobody who already organises. Picking one adds a row in the page: the
    button carries the name, the household link and the person."""
    from app.domains.mdm.api import ContactDetail

    activity, _c, _p = _seed(db_session)
    an, an_household = _member(db_session, "Zoekan")
    bert, _ = _member(db_session, "Zoekbert")
    _member(db_session, "Zoekgast", member=False)
    db_session.add(
        ContactDetail(person_id=an.id, contact_type_code="EMAIL", value="zoekan@example.com")
    )
    db_session.add(ActivityOrganiser(activity_id=activity.id, person_id=bert.id, sort_order=0))
    db_session.commit()
    _login(client)

    found = client.get(f"/admin/activiteiten/{activity.id}/organisatoren?organiser_q=Zoek").text
    assert "Zoekan Voorbeeld" in found and "zoekan@example.com" in found
    assert "Zoekbert" not in found, "already an organiser"
    assert "Zoekgast" not in found, "no member"
    assert "data-form-flow" not in found, "the candidates alone, not the fiche"
    pick = re.search(r'data-group-pick="o_order" data-pick="([^"]+)"', found).group(1)
    assert f"/admin/leden/gezin/{an_household}" in pick and f"&#34;{an.id}&#34;" in pick
    assert (
        client.get(f"/admin/activiteiten/{activity.id}/organisatoren?organiser_q=").text.strip()
        == ""
    )


# ── The groups on the screen ─────────────────────────────────────────────────


def _full(db):
    """Three dates, two components (one with two products), two organisers."""
    activity, component, product = _seed(db)
    first = db.query(ActivityDate).filter_by(activity_id=activity.id).one()
    first.start_time, first.end_time = time(14, 0), time(17, 0)
    db.add(ActivityDate(activity_id=activity.id, start_date=first.start_date + timedelta(days=7)))
    db.add(
        ActivityDate(
            activity_id=activity.id,
            start_date=first.start_date + timedelta(days=14),
            end_date=first.start_date + timedelta(days=15),
        )
    )
    db.add(
        ActivityProduct(
            component_id=component.id,
            name="Brood",
            price=2,
            member_price=1.5,
            is_free=False,
            sort_order=1,
            is_active=False,
        )
    )
    db.add(
        ActivitySubRegistration(
            activity_id=activity.id,
            name="Molen",
            registration_type_code="INDIVIDUAL",
            price=0,
            is_free=True,
            sort_order=1,
            info_url="https://example.com/molen",
        )
    )
    an, household = _member(db, "An")
    bert, _ = _member(db, "Bert")
    db.add(
        ActivityOrganiser(activity_id=activity.id, person_id=an.id, sort_order=0, is_contact=True)
    )
    db.add(ActivityOrganiser(activity_id=activity.id, person_id=bert.id, sort_order=1))
    db.commit()
    return activity, component, product, household


def test_read_mode_shows_the_rows_and_nothing_that_edits(client, db_session):
    """§2.2: read mode shows data and navigation — no add button, no handle, no
    row menu, no input. A date is one line in words; a product two short lines;
    an organiser's name links to the household."""
    activity, component, product, household = _full(db_session)
    _login(client)
    html = _page(client, activity.id)
    flow = html[html.index("data-form-flow") : html.index("data-rare-settings")]
    for edits in (
        "data-group-add",
        "data-row-handle",
        "data-row-menu",
        "<input",
        "<select",
        "<template",
    ):
        assert edits not in flow, f"{edits} in read mode"

    dates = _group(html, "aa-group-dates")
    lines = re.findall(r"data-date-line[^>]*>([^<]+)<", dates)
    assert len(lines) == 3
    assert lines[0].endswith("· 14:00–17:00") and " – " in lines[2], lines
    assert "data-group-head" not in dates, "a head of labels is for the editor"

    components = _group(html, "aa-group-components")
    assert re.findall(r"<h3 data-row-title[^>]*>([^<]+)</h3>", components) == ["Onderdeel", "Molen"]
    product_lines = re.findall(r"data-product-line[^>]*>(.*?)</p>", components, re.S)
    assert len(product_lines) == 2
    assert "Testproduct · €&nbsp;10,00" in product_lines[0]
    assert (
        "Brood · €&nbsp;2,00 · leden €&nbsp;1,50" in product_lines[1]
        and "Niet publiek" in product_lines[1]
    )
    # #1608: how a product is settled is one word.
    assert re.findall(r"data-product-settlement[^>]*>([^<]+)<", components) == ["Betalend"] * 2
    assert "Nog geen producten." in components, "the second component's empty child group"

    organisers = _group(html, "aa-group-organisers")
    assert f'href="/admin/leden/gezin/{household}" data-reference' in organisers
    assert "An Voorbeeld" in organisers and "op de affiche" in organisers


def test_read_mode_shows_the_occupancy_and_the_deadline_on_the_component(client, db_session):
    """The Publicatie card leaves with #1560, so the component says it itself:
    "2 / 20" where the maximum stands, the count alone without a maximum, and
    "t/m <date>". The editor keeps the bare maximum."""
    activity, component, _p, _h = _full(db_session)
    component.max_participants = 20
    component.registration_closes_on = date(2031, 5, 4)
    for name in ("An", "Bert"):
        db_session.add(
            Registration(
                activity_id=activity.id,
                component_id=component.id,
                registration_type="INDIVIDUAL",
                contact_name=f"{name} Voorbeeld",
                contact_email=f"{name.lower()}@example.com",
            )
        )
    db_session.commit()
    _login(client)

    def values(html: str, label: str) -> list[str]:
        components = _group(html, "aa-group-components")
        found = re.findall(rf">{label}</p>\s*<p data-value[^>]*>([^<]*)<", components)
        return [v.strip() for v in found]

    read = _page(client, activity.id)
    assert values(read, "Bezetting") == ["2 / 20", "0"], "with a maximum, and without"
    assert values(read, "Inschrijven tot")[0] == "t/m zondag 4 mei 2031"
    assert values(read, "Maximum") == [], "read mode shows the occupancy, not the bare maximum"

    edit = _group(_page(client, activity.id, edit=True), "aa-group-components")
    assert "Bezetting" not in edit and "2 / 20" not in edit
    field = re.search(rf'<input[^>]*name="c\.{component.id}\.max_participants"[^>]*>', edit)
    assert field and 'value="20"' in field.group(0), field


def test_edit_mode_gives_every_row_its_fields_under_its_key(client, db_session):
    activity, component, product, _household = _full(db_session)
    _login(client)
    html = _page(client, activity.id, edit=True)
    form = html[html.index('<form id="aa-act-form"') : html.index("</form>")]

    dates = _group(html, "aa-group-dates")
    assert dates.count("data-group-head") == 1, "the labels stand once, above the first row"
    head = dates[dates.index("data-group-head") :].split("data-group-rows", 1)[0]
    assert [label for label in ("Datum", "Van", "Einddatum", "Tot") if f">{label}" in head] == [
        "Datum",
        "Van",
        "Einddatum",
        "Tot",
    ]
    rows = dates.split("<template", 1)[0]
    assert rows.count('name="d_order"') == 3 and "data-row-handle" not in dates, (
        "dates have no order to drag"
    )
    assert 'data-row-action="up"' not in dates and 'data-row-action="duplicate"' in dates

    components = _group(html, "aa-group-components")
    assert len(re.findall(r'name="c_order" value="\d+"', components)) == 2, (
        "two stored components (the template is a third row)"
    )
    assert (
        f'name="c.{component.id}.name"' in components
        and f'name="p_order.{component.id}"' in components
    )
    assert f'name="p.{product.id}.price"' in components and 'value="10.00"' in components
    for action in ("up", "down", "duplicate", "remove"):
        assert f'data-row-action="{action}"' in components
    assert components.count("data-row-handle") >= 4, (
        "two components and two products, and the templates"
    )
    assert "<template data-group-template>" in components

    organisers = _group(html, "aa-group-organisers")
    assert 'data-row-action="duplicate"' not in organisers, "a member is not duplicated"
    assert 'data-row-action="up"' in organisers and "data-row-handle" in organisers
    assert "data-organiser-search" in organisers and 'name="organiser_q"' in organisers

    # Every row field is inside the one form; the closed last section too.
    for name in ("d_order", "c_order", "o_order", "fiche_groups", "bevestigd"):
        assert f'name="{name}"' in form
    rare = form[form.index("data-rare-settings") :]
    assert f'name="c.{component.id}.external_register_url"' in rare
    assert "https://example.com/molen" in rare and ">Molen</p>" in rare, (
        "the links of every component, named by it"
    )


def test_removing_a_row_asks_no_confirmation(client, db_session):
    """Decision 07: inside an unsaved form "Annuleren" undoes a removal; the
    kit's dialog is for deleting a record. Proven red with `data-confirm` on the
    remove item of `_row_menu`."""
    activity, _c, _p, _h = _full(db_session)
    _login(client)
    html = _page(client, activity.id, edit=True)
    flow = html[html.index("data-form-flow") : html.index("data-action-bar")]
    removes = re.findall(r'<button[^>]*data-row-action="remove"[^>]*>', flow)
    assert len(removes) >= 7, len(removes)
    assert not [button for button in removes if "confirm" in button], "a row removal asks nothing"
    assert "hx-post" not in "".join(removes), "and writes nothing until the save"


def test_the_fiche_has_one_form_and_one_save(client, db_session):
    """No form per row, no save per row: one `<form>`, one "Opslaan"."""
    activity, _c, _p, _h = _full(db_session)
    _login(client)
    html = _page(client, activity.id, edit=True)
    flow = html[html.index("data-form-flow") : html.index("data-action-bar")]
    assert flow.count("<form") == 1
    bar = html[html.index("data-action-bar") : html.index("<template data-save-failed>")]
    assert bar.count("data-save-idle>Opslaan<") == 1 and bar.count('type="submit"') == 1
    assert 'type="submit"' not in flow and "Opslaan" not in flow


# ── #1561: the refusal names its fields; delete and the state commands ask ───


def test_a_refused_save_names_every_field_at_once_with_its_place(client, db_session):
    """The acceptance of #1561: the name empty and a maximum of 0 are two fields,
    told together, each as a link to its field; nothing is written."""
    activity, component, _p = _seed(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.data["name"] = ""
    fiche.data["location"] = "Niet bewaard"
    fiche.set("c", component.id, max_participants="0")
    response = fiche.post(client, headers)
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#aa-fiche-message"
    assert "data-form-flow" not in response.text, "the banner alone: the form keeps what was typed"
    assert "Opslaan kan nog niet: controleer 2 velden." in response.text
    assert "Je andere wijzigingen zijn behouden." in response.text
    assert re.findall(r'data-error-for="([^"]+)"', response.text) == [
        "name",
        f"c.{component.id}.max_participants",
    ]
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).location != "Niet bewaard"
    assert db_session.get(Activity, activity.id).name


def test_a_removed_component_with_registrations_is_named_as_its_row(client, db_session):
    activity, component, _p = _seed(db_session)
    db_session.add(
        Registration(
            activity_id=activity.id,
            component_id=component.id,
            registration_type="INDIVIDUAL",
            contact_name="An Voorbeeld",
            contact_email="an@example.com",
        )
    )
    db_session.commit()
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.remove("c", component.id)
    response = fiche.post(client, headers)
    assert response.status_code == 422
    assert f'data-error-for="c.{component.id}"' in response.text, "the row, not a status alone"
    assert "heeft één inschrijving en kan niet verwijderd worden" in response.text


def test_an_activity_without_registrations_is_deleted_after_the_dialog(client, db_session):
    """§3.18: the dialog names the record and says what goes with it — in Acties
    while reading, in the bar while editing — and the delete does exactly that."""
    activity, _c, _p = _seed(db_session)
    headers = _login(client)
    sentence = "De activiteit verdwijnt met haar datums, onderdelen en producten."
    read = _page(client, activity.id)
    item = re.search(r'<button role="menuitem"[^>]*/verwijderen"[^>]*>', read).group(0)
    assert f'data-confirm="{sentence}"' in item and 'data-confirm-tone="delete"' in item
    assert "data-action-bar" not in read, "no bar while reading"

    edit = _page(client, activity.id, edit=True)
    button = re.search(r"<button[^>]*data-form-delete[^>]*>", edit, re.S).group(0)
    assert f'data-confirm="{sentence}"' in button and "data-notice" not in button
    assert f'hx-post="/admin/activiteiten/{activity.id}/verwijderen"' in button
    assert "verwijderen?" in button and activity.name in button, "the dialog names the record"
    head = edit[edit.index("data-record-head") : edit.index("data-related-tabs")]
    assert "/verwijderen" not in head, "in edit mode not also in Acties"

    answer = client.post(f"/admin/activiteiten/{activity.id}/verwijderen", headers=headers)
    assert answer.status_code == 204 and answer.headers["HX-Redirect"] == "/admin/activiteiten"
    db_session.expire_all()
    assert db_session.query(Activity).filter_by(id=activity.id).count() == 0
    assert db_session.query(ActivityDate).filter_by(activity_id=activity.id).count() == 0
    assert db_session.query(ActivitySubRegistration).filter_by(activity_id=activity.id).count() == 0


def test_new_an_activity_with_registrations_cannot_be_deleted(client, db_session, admin_headers):
    """NEW (Koen, 4 October 2026): until #1561 the delete took the registrations
    along. The screen says why BEFORE any click — the item in Acties is no button,
    the bar's button opens a notice — and the service refuses the request that
    comes anyway, also through the JSON API. A deleted registration does not
    count; another activity's neither. Proven red by dropping the refusal from
    `delete_activity` (the activity and its registration go), and by counting
    the registrations of every activity (the empty one is refused too)."""
    activity, component, _p = _seed(db_session)
    empty, _c2, _p2 = seed_activity_with_product(db_session)
    registrations = [
        Registration(
            activity_id=activity.id,
            component_id=component.id,
            registration_type="INDIVIDUAL",
            contact_name=f"{name} Voorbeeld",
            contact_email=f"{name.lower()}@example.com",
        )
        for name in ("An", "Bert")
    ]
    db_session.add_all(registrations)
    db_session.commit()
    headers = _login(client)
    two = (
        "De activiteit heeft 2 inschrijvingen en kan niet verwijderd worden. "
        "Gaat ze niet door, gebruik dan “Activiteit annuleren”."
    )

    assert "data-menu-refused" not in _page(client, empty.id), "another activity's do not count"
    read = _page(client, activity.id)
    menu = read[read.index("data-actions-menu") : read.index("data-related-tabs")]
    assert "/verwijderen" not in menu, "no request to press"
    refused = re.search(r"<div[^>]*data-menu-refused[^>]*>(.*?)</div>", menu, re.S)
    assert 'aria-disabled="true"' in refused.group(0)
    assert ">Verwijderen<" in refused.group(1) and two in refused.group(1)

    edit = _page(client, activity.id, edit=True)
    button = re.search(r"<button[^>]*data-form-delete[^>]*>", edit, re.S).group(0)
    assert f'data-notice="{two}"' in button
    assert "kan niet verwijderd worden" in re.search(r'data-notice-title="([^"]+)"', button).group(
        1
    )
    assert "hx-post" not in button and "data-confirm" not in button

    for answer in (
        client.post(f"/admin/activiteiten/{activity.id}/verwijderen", headers=headers),
        client.delete(f"/api/v1/activities/{activity.id}", headers=admin_headers),
    ):
        assert answer.status_code == 422 and answer.json()["detail"] == two
    db_session.expire_all()
    assert db_session.query(Activity).filter_by(id=activity.id).count() == 1
    assert db_session.query(Registration).filter_by(activity_id=activity.id).count() == 2

    # one left: the sentence counts; none left: the activity may go
    from app.soft_delete import soft_delete

    soft_delete(db_session.get(Registration, registrations[0].id))
    db_session.commit()
    assert "heeft 1 inschrijving en kan niet" in _page(client, activity.id)
    soft_delete(db_session.get(Registration, registrations[1].id))
    db_session.commit()
    assert "data-menu-refused" not in _page(client, activity.id)
    assert (
        client.delete(f"/api/v1/activities/{activity.id}", headers=admin_headers).status_code == 200
    )


def test_every_state_command_names_its_consequence_and_its_toast(client, db_session):
    """§3.18: a state command asks with its consequence (the lighter dialog) and
    says afterwards that it happened."""
    activity, _c, _p = _seed(db_session)
    _login(client)
    html = _page(client, activity.id)
    menu = html[html.index("data-actions-menu") :]
    for path in ("/status", "/annulering"):
        item = re.search(rf'<button role="menuitem"[^>]*{path}"[^>]*>', menu).group(0)
        assert re.search(r'data-confirm="[^"]{30,}"', item), f"{path}: no consequence"
        assert "data-confirm-ok=" in item and "data-toast-after=" in item, item
        assert "data-confirm-tone" not in item, "the lighter dialog, not the delete one"
