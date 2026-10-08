"""The one save of the activity fiche does what the seventeen row routes did (#1559).

`activities.fiche.save_fiche` writes the sections, the dates, the components with
their products and the organisers in one transaction. This file is the proof the
merge asks for, rule by rule: every refusal a row route (or the service behind
it) made is made here, every history row it wrote is written here, and a refusal
anywhere leaves nothing behind.

New with #1559, and marked NEW at their test:

- a component with registrations and a product on a registration cannot go
  (Koen, 4 October 2026) — in the service, so every entrance refuses;
- an empty name, a maximum of zero or less and a negative price are refused
  with a message (they were a 500 through the row routes);
- a row that did not change is not written and gets no history row;
- leaving the posters without a contact person needs the confirmation also when
  the last contact person is REMOVED, not only unticked.

Each rule was broken once to see its test red; what was broken stands in the
test's docstring.
"""

from __future__ import annotations

import asyncio
import io
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks
from starlette.datastructures import UploadFile

from app.domains.activities import service
from app.domains.activities.fiche import (
    ComponentRow,
    DateRow,
    FicheRefusal,
    FicheSave,
    FieldError,
    OrganiserRow,
    ProductRow,
    save_fiche,
)
from app.domains.activities.models import (
    ActiviteitFout,
    Activity,
    ActivityDate,
    ActivityDateHistory,
    ActivityHistory,
    ActivityOrganiser,
    ActivityProduct,
    ActivitySubRegistration,
    ComponentHistory,
    ProductHistory,
    Registration,
    RegistrationItem,
)
from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.media.api import MediaAsset
from tests.conftest import seed_activity_with_product, seed_question_form

SOON = date.today() + timedelta(days=30)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _as_is(db, activity_id: int) -> FicheSave:
    """The fiche as the form sends it when nothing was touched."""
    db.expire_all()
    activity = service._activity_met_boom(db, activity_id)
    return FicheSave(
        fields={},
        dates=[
            DateRow(str(d.id), d.start_date, d.end_date, d.start_time, d.end_time)
            for d in sorted(activity.dates, key=lambda d: d.id)
        ],
        components=[
            ComponentRow(
                str(c.id),
                c.name,
                team_name_required=c.team_name_required,
                max_participants=c.max_participants,
                registration_closes_on=c.registration_closes_on,
                form_id=c.form_id,
                links={
                    "external_register_url": c.external_register_url,
                    "external_registrations_url": c.external_registrations_url,
                    "info_url": c.info_url,
                },
                products=[
                    ProductRow(
                        str(p.id),
                        p.name,
                        price=p.price,
                        member_price=p.member_price,
                        is_free=p.is_free,
                        pay_on_site=p.pay_on_site,
                        is_active=p.is_active,
                        max_participants=p.max_participants,
                    )
                    for p in c.products
                ],
            )
            for c in activity.sub_registrations
        ],
        organisers=[
            OrganiserRow(
                str(o.id),
                o.person_id,
                is_contact=o.is_contact,
                show_email=o.show_email,
                show_mobile=o.show_mobile,
                email_override=o.email_override,
                mobile_override=o.mobile_override,
            )
            for o in service._organiser_rows(db, activity_id)
        ],
    )


def _save(db, activity_id: int, fiche: FicheSave, **files):
    return asyncio.run(
        save_fiche(
            db,
            activity_id,
            fiche,
            actor="board@example.com",
            background_tasks=BackgroundTasks(),
            **files,
        )
    )


def _refused(db, activity_id: int, fiche: FicheSave, **files) -> str:
    with pytest.raises(ActiviteitFout) as refusal:
        _save(db, activity_id, fiche, **files)
    return str(refusal.value)


def _history(db, model, **where) -> list[tuple[str, str]]:
    rows = db.query(model).filter_by(**where).order_by(model.id).all()
    return [(row.operation, row.action) for row in rows]


def _counts(db) -> dict[str, int]:
    """Everything a save can write, counted — to prove "nothing written"."""
    db.expire_all()
    models = (
        ActivityDate,
        ActivitySubRegistration,
        ActivityProduct,
        ActivityOrganiser,
        ActivityHistory,
        ActivityDateHistory,
        ComponentHistory,
        ProductHistory,
        MediaAsset,
    )
    return {m.__name__: db.query(m).execution_options(include_deleted=True).count() for m in models}


def _seed(db):
    activity, component, product = seed_activity_with_product(db, price="10.00", is_free=False)
    db.commit()
    return activity, component, product


def _member(db, first: str, last: str = "Voorbeeld", *, member: bool = True) -> Person:
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first, last_name=last
    )
    db.add(person)
    db.flush()
    if member:
        household = Member()
        db.add(household)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
    db.commit()
    return person


def _registration(db, component, product=None) -> Registration:
    registration = Registration(
        activity_id=component.activity_id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        contact_name="An Voorbeeld",
        contact_email="an@example.com",
    )
    db.add(registration)
    db.flush()
    if product is not None:
        db.add(RegistrationItem(registration_id=registration.id, product_id=product.id, quantity=1))
    db.commit()
    return registration


def _upload(
    name: str = "info.png", content_type: str = "image/png", data: bytes = PNG
) -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=name, headers={"content-type": content_type})


def _places(db, activity_id: int, fiche: FicheSave, **files) -> dict[str, str]:
    """Where the save was refused, and why: {place: message} (#1561)."""
    with pytest.raises(FicheRefusal) as refusal:
        _save(db, activity_id, fiche, **files)
    places = [error.field for error in refusal.value.errors]
    assert len(places) == len(set(places)), f"a place named twice: {places}"
    return {error.field: error.message for error in refusal.value.errors}


# ── A save that changes nothing writes nothing ───────────────────────────────


def test_an_untouched_fiche_writes_no_row_and_no_history(db_session):
    """NEW: only what changed is written. Proven red by dropping the `if changed`
    before `apply_date_update`: every save then logs `date_updated`."""
    activity, _component, _product = _seed(db_session)
    before = _counts(db_session)
    assert _save(db_session, activity.id, _as_is(db_session, activity.id)) is not None
    assert _counts(db_session) == before


def test_a_fiche_of_an_activity_that_does_not_exist_is_none(db_session):
    assert _save(db_session, 999_999, FicheSave(fields={})) is None


# ── The activity's own fields ────────────────────────────────────────────────


def test_the_sections_are_written_with_one_history_row(db_session):
    activity, _c, _p = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"location": "Parochiezaal", "members_only": True, "name": activity.name}
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    saved = db_session.get(Activity, activity.id)
    assert (saved.location, saved.members_only) == ("Parochiezaal", True)
    assert _history(db_session, ActivityHistory, activity_id=activity.id)[-1] == (
        "update",
        "activity_updated",
    )


def test_a_slug_that_is_taken_refuses_the_whole_save(db_session):
    """The rule of `update_activity` (#884), and the proof of one transaction: the
    date added in the same save is not written either."""
    activity, _c, _p = _seed(db_session)
    db_session.add(Activity(name="Bezet", slug="bezet-1559"))
    db_session.commit()
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"slug": "bezet-1559"}
    fiche.dates.append(DateRow("n1", SOON + timedelta(days=1)))
    assert _refused(db_session, activity.id, fiche) == (
        "De URL 'bezet-1559' is al in gebruik door een andere activiteit."
    )
    assert _counts(db_session) == before
    assert db_session.get(Activity, activity.id).slug != "bezet-1559"


def test_an_unknown_audience_is_refused(db_session):
    activity, _c, _p = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"target_audience": "aliens"}
    assert _refused(db_session, activity.id, fiche) == "Onbekend doelpubliek."


# ── Dates ────────────────────────────────────────────────────────────────────


def test_dates_are_added_changed_and_removed_with_their_history(db_session):
    activity, _c, _p = _seed(db_session)
    first = db_session.query(ActivityDate).filter_by(activity_id=activity.id).one()
    fiche = _as_is(db_session, activity.id)
    fiche.dates.append(
        DateRow("n1", SOON + timedelta(days=7), start_time=time(14, 0), end_time=time(17, 0))
    )
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    dates = (
        db_session.query(ActivityDate)
        .filter_by(activity_id=activity.id)
        .order_by(ActivityDate.id)
        .all()
    )
    assert len(dates) == 2 and dates[1].start_time == time(14, 0)
    assert _history(db_session, ActivityDateHistory, activity_date_id=dates[1].id) == [
        ("insert", "date_created")
    ]
    assert _history(db_session, ActivityDateHistory, activity_date_id=first.id) == [], (
        "the untouched row"
    )

    fiche = _as_is(db_session, activity.id)
    fiche.dates[0].end_date = fiche.dates[0].start_date + timedelta(days=1)
    del fiche.dates[1]
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    assert db_session.get(ActivityDate, first.id).end_date == first.start_date + timedelta(days=1)
    assert _history(db_session, ActivityDateHistory, activity_date_id=first.id) == [
        ("update", "date_updated")
    ]
    gone = db_session.query(ActivityDate).execution_options(include_deleted=True).get(dates[1].id)
    assert gone.deleted_at is not None, "a soft delete, as the row route did"
    assert _history(db_session, ActivityDateHistory, activity_date_id=dates[1].id)[-1] == (
        "delete",
        "date_deleted",
    )


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            DateRow("n1", SOON, end_date=SOON - timedelta(days=1)),
            "De einddatum ligt vóór de begindatum.",
        ),
        (
            DateRow("n1", SOON, start_time=time(17, 0), end_time=time(14, 0)),
            "Het einduur ligt niet na het beginuur.",
        ),
    ],
)
def test_an_incoherent_date_refuses_the_whole_save(db_session, row, message):
    """The model's rule (#792) fires in the flush of the one transaction."""
    activity, _c, _p = _seed(db_session)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"location": "Niet bewaard"}
    fiche.dates.append(row)
    assert _refused(db_session, activity.id, fiche) == message
    assert _counts(db_session) == before
    assert db_session.get(Activity, activity.id).location != "Niet bewaard"


def test_the_last_date_may_go_as_before(db_session):
    """No rule kept a last date through the row route; none does here."""
    activity, _c, _p = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.dates = []
    _save(db_session, activity.id, fiche)
    assert db_session.query(ActivityDate).filter_by(activity_id=activity.id).count() == 0


def test_a_date_of_another_activity_is_not_touched(db_session):
    """The row route looked a date up by its id AND its activity. A key that is
    not a date of this activity is a row that no longer exists here."""
    activity, _c, _p = _seed(db_session)
    other = Activity(name="Ander")
    db_session.add(other)
    db_session.flush()
    foreign = ActivityDate(activity_id=other.id, start_date=SOON)
    db_session.add(foreign)
    db_session.commit()
    fiche = _as_is(db_session, activity.id)
    fiche.dates.append(DateRow(str(foreign.id), SOON + timedelta(days=3)))
    assert "bestaat niet meer" in _refused(db_session, activity.id, fiche)
    db_session.expire_all()
    assert db_session.get(ActivityDate, foreign.id).start_date == SOON


# ── Components ───────────────────────────────────────────────────────────────


def test_a_new_component_is_what_the_row_route_made_of_it(db_session):
    """INDIVIDUAL, price 0, free, with `component_created` — and its place in the
    form as its order (the row route always wrote 0)."""
    activity, component, _p = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components.append(
        ComponentRow(
            "n1",
            "  Avondwandeling ",
            max_participants=40,
            registration_closes_on=SOON,
            team_name_required=True,
        )
    )
    _save(db_session, activity.id, fiche)
    new = (
        db_session.query(ActivitySubRegistration)
        .filter_by(activity_id=activity.id, name="Avondwandeling")
        .one()
    )
    assert (new.registration_type_code, new.price, new.is_free) == (
        "INDIVIDUAL",
        Decimal("0"),
        True,
    )
    assert (new.max_participants, new.registration_closes_on, new.team_name_required) == (
        40,
        SOON,
        True,
    )
    assert new.sort_order == 1
    assert _history(db_session, ComponentHistory, component_id=new.id) == [
        ("insert", "component_created")
    ]
    assert _history(db_session, ComponentHistory, component_id=component.id) == []


def test_a_component_is_changed_reordered_and_removed(db_session):
    activity, component, product = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components.append(ComponentRow("n1", "Tweede"))
    _save(db_session, activity.id, fiche)
    second = db_session.query(ActivitySubRegistration).filter_by(name="Tweede").one()

    # Swap the two and rename the first: one update row, none for the move alone.
    fiche = _as_is(db_session, activity.id)
    fiche.components.reverse()
    fiche.components[1].name = "Hernoemd"
    fiche.components[1].links = {
        "external_register_url": "https://example.com/in",
        "external_registrations_url": None,
        "info_url": None,
    }
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    assert [
        c.name for c in service._activity_met_boom(db_session, activity.id).sub_registrations
    ] == ["Tweede", "Hernoemd"]
    assert (
        db_session.get(ActivitySubRegistration, component.id).external_register_url
        == "https://example.com/in"
    )
    assert _history(db_session, ComponentHistory, component_id=component.id) == [
        ("update", "component_updated")
    ]
    assert _history(db_session, ComponentHistory, component_id=second.id) == [
        ("insert", "component_created")
    ], "a reorder writes no history, as before"

    # Remove the first one: the component and its products go, each with its row.
    fiche = _as_is(db_session, activity.id)
    fiche.components = [c for c in fiche.components if c.key != str(component.id)]
    _save(db_session, activity.id, fiche)
    gone = (
        db_session.query(ActivitySubRegistration)
        .execution_options(include_deleted=True)
        .get(component.id)
    )
    assert gone.deleted_at is not None
    assert _history(db_session, ComponentHistory, component_id=component.id)[-1] == (
        "delete",
        "component_deleted",
    )
    assert _history(db_session, ProductHistory, product_id=product.id)[-1] == (
        "delete",
        "component_deleted",
    )
    assert db_session.query(ActivityProduct).filter_by(id=product.id).count() == 0


def test_links_the_form_did_not_send_are_left_alone(db_session):
    """A component's external links live in the closed last section; a row
    without them (`links=None`) keeps what it has."""
    activity, component, _p = _seed(db_session)
    component.info_url = "https://example.com/info"
    db_session.commit()
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].links = None
    fiche.components[0].name = "Anders"
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    assert (
        db_session.get(ActivitySubRegistration, component.id).info_url == "https://example.com/info"
    )


def test_new_a_component_with_registrations_cannot_go(db_session):
    """NEW (Koen, 4 October 2026). Until #1559 this was an unconditional soft
    delete behind a dialog. Proven red by dropping the count from
    `service.remove_component`: the component goes and the registration stays
    behind without it."""
    activity, component, _p = _seed(db_session)
    _registration(db_session, component)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"location": "Niet bewaard"}
    fiche.components = []
    message = _refused(db_session, activity.id, fiche)
    assert (
        message == "Het onderdeel “Onderdeel” heeft één inschrijving en kan niet verwijderd worden."
    )
    assert _counts(db_session) == before
    assert db_session.get(Activity, activity.id).location != "Niet bewaard"

    _registration(db_session, component)
    assert "heeft 2 inschrijvingen" in _refused(db_session, activity.id, fiche)


def test_a_component_whose_registrations_are_deleted_may_go(db_session):
    """The rule counts living registrations: a deleted one holds nothing back."""
    from app.soft_delete import soft_delete

    activity, component, _p = _seed(db_session)
    registration = _registration(db_session, component)
    soft_delete(registration)
    db_session.commit()
    fiche = _as_is(db_session, activity.id)
    fiche.components = []
    _save(db_session, activity.id, fiche)
    assert db_session.query(ActivitySubRegistration).filter_by(id=component.id).count() == 0


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (ComponentRow("n1", "   "), "Een onderdeel heeft een naam nodig."),
        (
            ComponentRow("n1", "Nul", max_participants=0),
            "Het maximum van “Nul” moet groter zijn dan nul.",
        ),
        (
            ComponentRow("n1", "Min", max_participants=-3),
            "Het maximum van “Min” moet groter zijn dan nul.",
        ),
    ],
)
def test_new_a_nameless_component_and_a_maximum_of_nothing_are_refused(db_session, row, message):
    """NEW: an empty name passed, and a maximum of zero came back as a 500 from
    the CHECK of the database."""
    activity, _c, _p = _seed(db_session)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components.append(row)
    assert _refused(db_session, activity.id, fiche) == message
    assert _counts(db_session) == before


def test_the_question_form_rules_hold_for_an_existing_and_for_a_new_component(db_session):
    """`_check_questions` (CR-14 §B4.5): a form that does not exist, a form a
    registration page cannot ask, and no swap once a registration answered. A new
    row of the fiche can attach a form (the row route could only on an update)."""
    from app.domains.forms.models import FormSubmission

    activity, component, _p = _seed(db_session)
    good = seed_question_form(db_session, title="Vragen 1559")
    closed = seed_question_form(db_session, title="Dicht 1559", status="closed")
    db_session.commit()

    fiche = _as_is(db_session, activity.id)
    fiche.components[0].form_id = 999_999
    assert _refused(db_session, activity.id, fiche) == "Dat formulier bestaat niet."
    fiche.components[0].form_id = closed.id
    assert "staat niet open" in _refused(db_session, activity.id, fiche)

    fiche.components[0].form_id = good.id
    fiche.components.append(ComponentRow("n1", "Nieuw met vragen", form_id=good.id))
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    assert db_session.get(ActivitySubRegistration, component.id).form_id == good.id
    assert (
        db_session.query(ActivitySubRegistration).filter_by(name="Nieuw met vragen").one().form_id
        == good.id
    )

    new_closed = _as_is(db_session, activity.id)
    new_closed.components.append(ComponentRow("n2", "Nieuw met dicht formulier", form_id=closed.id))
    assert "staat niet open" in _refused(db_session, activity.id, new_closed)

    # Once a registration answered, another form is refused; detaching is not.
    submission = FormSubmission(form_id=good.id, submitter_name="Ward", attached=True)
    db_session.add(submission)
    db_session.flush()
    registration = _registration(db_session, component)
    registration.form_submission_id = submission.id
    other = seed_question_form(db_session, title="Ander 1559")
    db_session.commit()
    swap = _as_is(db_session, activity.id)
    swap.components[0].form_id = other.id
    assert "heeft al antwoorden op zijn vragen" in _refused(db_session, activity.id, swap)
    swap.components[0].form_id = None
    _save(db_session, activity.id, swap)
    assert db_session.get(ActivitySubRegistration, component.id).form_id is None


# ── Products ─────────────────────────────────────────────────────────────────


def test_products_are_added_changed_reordered_and_removed(db_session):
    activity, component, product = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products.insert(
        0,
        ProductRow(
            "n1", " Soep ", price=Decimal("5.00"), member_price=Decimal("4.00"), max_participants=60
        ),
    )
    _save(db_session, activity.id, fiche)
    soup = db_session.query(ActivityProduct).filter_by(component_id=component.id, name="Soep").one()
    db_session.expire_all()
    assert (soup.price, soup.member_price, soup.max_participants) == (
        Decimal("5.00"),
        Decimal("4.00"),
        60,
    )
    assert (soup.sort_order, db_session.get(ActivityProduct, product.id).sort_order) == (0, 1)
    assert _history(db_session, ProductHistory, product_id=soup.id) == [
        ("insert", "product_created")
    ]
    assert _history(db_session, ProductHistory, product_id=product.id) == [], "moved, not changed"

    fiche = _as_is(db_session, activity.id)
    rows = fiche.components[0].products
    rows[0].price = Decimal("6.00")
    rows[0].is_active = False
    del rows[1]
    _save(db_session, activity.id, fiche)
    db_session.expire_all()
    assert (soup.price, soup.is_active) == (Decimal("6.00"), False)
    assert _history(db_session, ProductHistory, product_id=soup.id)[-1] == (
        "update",
        "product_updated",
    )
    assert _history(db_session, ProductHistory, product_id=product.id) == [
        ("delete", "product_deleted")
    ]
    assert db_session.query(ActivityProduct).filter_by(id=product.id).count() == 0


def test_free_and_pay_on_site_together_are_refused(db_session):
    """`_controleer_afrekening`, for a new product and for a changed one. With two
    switches in the fiche (they were one select) the screen can now send both."""
    activity, _c, product = _seed(db_session)
    before = _counts(db_session)
    message = "Een product kan niet tegelijk gratis én ter plaatse te betalen zijn."
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products.append(ProductRow("n1", "Beide", is_free=True, pay_on_site=True))
    assert _refused(db_session, activity.id, fiche) == message
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products[0].is_free = True
    fiche.components[0].products[0].pay_on_site = True
    assert _refused(db_session, activity.id, fiche) == message
    assert _counts(db_session) == before
    db_session.expire_all()
    assert db_session.get(ActivityProduct, product.id).pay_on_site is False


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (ProductRow("n1", ""), "Een product heeft een naam nodig."),
        (
            ProductRow("n1", "Duur", price=Decimal("-1")),
            "De prijs van “Duur” mag niet negatief zijn.",
        ),
        (
            ProductRow("n1", "Leden", member_price=Decimal("-0.50")),
            "De prijs van “Leden” mag niet negatief zijn.",
        ),
        (
            ProductRow("n1", "Vol", max_participants=0),
            "Het maximum van “Vol” moet groter zijn dan nul.",
        ),
    ],
)
def test_new_a_product_without_a_name_or_with_impossible_numbers_is_refused(
    db_session, row, message
):
    """NEW as a message: a negative price failed a schema built outside the
    route's `try`, a maximum of zero the CHECK — both a 500."""
    activity, _c, _p = _seed(db_session)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products.append(row)
    assert _refused(db_session, activity.id, fiche) == message
    assert _counts(db_session) == before


def test_new_a_product_on_a_registration_cannot_go(db_session):
    """NEW (Koen, 4 October 2026). Proven red by dropping the count from
    `service.remove_product`."""
    activity, component, product = _seed(db_session)
    _registration(db_session, component, product)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products = []
    message = _refused(db_session, activity.id, fiche)
    assert message.startswith(
        "Het product “Testproduct” staat op een inschrijving en kan niet verwijderd worden."
    )
    assert "Publiek zichtbaar" in message, "the way out: take it off the public form instead"
    assert _counts(db_session) == before


def test_a_product_of_another_component_is_not_touched(db_session):
    """`_product` looked a product up by its id AND its component."""
    activity, component, product = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components.append(
        ComponentRow("n1", "Tweede", products=[ProductRow(str(product.id), "Gekaapt")])
    )
    assert "bestaat niet meer" in _refused(db_session, activity.id, fiche)
    db_session.expire_all()
    assert db_session.get(ActivityProduct, product.id).name == "Testproduct"


# ── Organisers ───────────────────────────────────────────────────────────────


def _organisers(db, activity_id: int) -> list[tuple[int, int, bool]]:
    db.expire_all()
    return [
        (r.person_id, r.sort_order, r.is_contact) for r in service._organiser_rows(db, activity_id)
    ]


def test_organisers_are_added_in_the_order_of_the_form(db_session):
    activity, _c, _p = _seed(db_session)
    an, bert, cas = (_member(db_session, name) for name in ("An", "Bert", "Cas"))
    fiche = _as_is(db_session, activity.id)
    fiche.organisers = [OrganiserRow("n1", an.id, is_contact=True), OrganiserRow("n2", bert.id)]
    _save(db_session, activity.id, fiche)
    assert _organisers(db_session, activity.id) == [(an.id, 0, True), (bert.id, 1, False)]

    # Reorder, add one in the middle, change the flags and an override.
    fiche = _as_is(db_session, activity.id)
    first, second = fiche.organisers
    second.email_override = "  bert@example.com "
    second.show_mobile = False
    fiche.organisers = [second, OrganiserRow("n3", cas.id), first]
    _save(db_session, activity.id, fiche)
    assert _organisers(db_session, activity.id) == [
        (bert.id, 0, False),
        (cas.id, 1, False),
        (an.id, 2, True),
    ]
    row = service._organiser_rows(db_session, activity.id)[0]
    assert (row.email_override, row.show_mobile, row.show_email) == (
        "bert@example.com",
        False,
        True,
    )

    # Remove the middle one: the places close up, the UNIQUE on the order holds.
    fiche = _as_is(db_session, activity.id)
    del fiche.organisers[1]
    fiche.organisers[0].email_override = "   "
    _save(db_session, activity.id, fiche)
    assert _organisers(db_session, activity.id) == [(bert.id, 0, False), (an.id, 1, True)]
    assert service._organiser_rows(db_session, activity.id)[0].email_override is None, (
        "empty = the member's own"
    )


def test_an_organiser_twice_a_non_member_and_a_stranger_are_refused(db_session):
    """The rules of `service.add_organiser`, in its words."""
    activity, _c, _p = _seed(db_session)
    an = _member(db_session, "An")
    guest = _member(db_session, "Gast", member=False)
    before = _counts(db_session)

    fiche = _as_is(db_session, activity.id)
    fiche.organisers = [OrganiserRow("n1", an.id), OrganiserRow("n2", an.id)]
    assert _refused(db_session, activity.id, fiche) == "Die persoon staat er al bij."
    fiche.organisers = [OrganiserRow("n1", guest.id)]
    assert _refused(db_session, activity.id, fiche) == "Alleen leden kunnen organisator zijn."
    fiche.organisers = [OrganiserRow("n1", 999_999)]
    assert "bestaat niet meer" in _refused(db_session, activity.id, fiche)
    assert _counts(db_session) == before


def test_leaving_the_posters_without_a_contact_person_needs_the_confirmation(db_session):
    """The rule of the row route (#1004): unticking the last contact person is
    refused until confirmed. NEW: REMOVING the last one asks the same — the row
    route for removing asked nothing.

    Proven red by dropping the check from `_save_organisers`."""
    activity, _c, _p = _seed(db_session)
    an, bert = _member(db_session, "An"), _member(db_session, "Bert")
    fiche = _as_is(db_session, activity.id)
    fiche.organisers = [OrganiserRow("n1", an.id, is_contact=True), OrganiserRow("n2", bert.id)]
    _save(db_session, activity.id, fiche)

    unticked = _as_is(db_session, activity.id)
    unticked.organisers[0].is_contact = False
    assert _refused(db_session, activity.id, unticked).endswith("Bevestig om door te gaan.")
    removed = _as_is(db_session, activity.id)
    del removed.organisers[0]
    assert _refused(db_session, activity.id, removed).endswith("Bevestig om door te gaan.")
    assert _organisers(db_session, activity.id) == [(an.id, 0, True), (bert.id, 1, False)]

    # Moving the tick to someone else is no loss of a contact person.
    moved = _as_is(db_session, activity.id)
    moved.organisers[0].is_contact, moved.organisers[1].is_contact = False, True
    _save(db_session, activity.id, moved)

    unticked = _as_is(db_session, activity.id)
    unticked.organisers[1].is_contact = False
    unticked.confirmed_no_contact = True
    _save(db_session, activity.id, unticked)
    assert not any(contact for _person, _place, contact in _organisers(db_session, activity.id))
    # With no contact person to lose, nothing is asked.
    _save(db_session, activity.id, _as_is(db_session, activity.id))


# ── One transaction ──────────────────────────────────────────────────────────


def test_a_refusal_in_the_last_group_leaves_the_first_groups_unwritten(db_session):
    """Dates and components are written before the organisers are judged; a
    non-member among the organisers takes all of it back."""
    activity, _c, _p = _seed(db_session)
    guest = _member(db_session, "Gast", member=False)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"location": "Niet bewaard"}
    fiche.dates.append(DateRow("n1", SOON + timedelta(days=2)))
    fiche.components.append(
        ComponentRow("n1", "Niet bewaard", products=[ProductRow("n1", "Ook niet")])
    )
    fiche.organisers = [OrganiserRow("n1", guest.id)]
    assert _refused(db_session, activity.id, fiche) == "Alleen leden kunnen organisator zijn."
    assert _counts(db_session) == before
    assert db_session.get(Activity, activity.id).location != "Niet bewaard"


def test_a_group_the_form_did_not_send_is_left_alone(db_session):
    """A caller that saves the sections only removes no rows."""
    activity, component, product = _seed(db_session)
    before = _counts(db_session)
    fiche = FicheSave(fields={"location": "Alleen de secties"}, groups=frozenset())
    _save(db_session, activity.id, fiche)
    after = _counts(db_session)
    assert after["ActivityHistory"] == before["ActivityHistory"] + 1
    assert {k: v for k, v in after.items() if k != "ActivityHistory"} == {
        k: v for k, v in before.items() if k != "ActivityHistory"
    }
    assert db_session.query(ActivityProduct).filter_by(id=product.id).count() == 1


# ── Uploads in the same transaction ──────────────────────────────────────────


def test_the_poster_and_an_info_attachment_of_a_new_component_are_stored(db_session):
    activity, component, _p = _seed(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.components.append(ComponentRow("n1", "Met bijlage"))
    _save(
        db_session,
        activity.id,
        fiche,
        poster=_upload("affiche.png"),
        component_files={"n1": _upload()},
    )
    new = db_session.query(ActivitySubRegistration).filter_by(name="Met bijlage").one()
    kinds = {
        (str(a.kind).split(".")[-1].lower(), a.activity_id, a.component_id)
        for a in db_session.query(MediaAsset).all()
    }
    assert ("activity_poster", activity.id, None) in kinds
    assert ("component_info", None, new.id) in kinds

    drop = _as_is(db_session, activity.id)
    next(c for c in drop.components if c.key == str(new.id)).drop_info = True
    _save(db_session, activity.id, drop)
    assert db_session.query(MediaAsset).filter(MediaAsset.component_id == new.id).count() == 0


def test_a_refused_file_refuses_the_whole_save(db_session):
    """The row route committed the fields first and the file second: a refused
    file left the fields written. One transaction now."""
    activity, component, _p = _seed(db_session)
    before = _counts(db_session)
    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"location": "Niet bewaard"}
    fiche.components[0].name = "Niet hernoemd"
    message = _refused(
        db_session,
        activity.id,
        fiche,
        component_files={str(component.id): _upload("foto.heic", "image/heic", b"x")},
    )
    assert "Niet-ondersteund bestandstype: foto.heic" in message and "HEIC" in message
    assert _counts(db_session) == before
    db_session.expire_all()
    assert db_session.get(ActivitySubRegistration, component.id).name == "Onderdeel"


# ── The same refusals through the doors that stay ────────────────────────────


# ── #1561: a refusal names its place, and the save names all of them ─────────


def test_every_refusal_of_one_save_comes_back_at_once_each_at_its_field(db_session):
    """The acceptance of #1561: an empty name and a maximum of nothing are two
    fields to correct, told together — with every other refusal of that save.
    Proven red by raising at the first refusal again (`errors.add` raising):
    one place comes back instead of seven."""
    activity, component, product = _seed(db_session)
    other, _c, _p = seed_activity_with_product(db_session)
    other.slug = "bezet"
    db_session.commit()
    before = _counts(db_session)
    first = db_session.query(ActivityDate).filter_by(activity_id=activity.id).one()

    fiche = _as_is(db_session, activity.id)
    fiche.fields = {"slug": "bezet", "location": "Niet bewaard"}
    fiche.errors = [FieldError("name", "De activiteit heeft een naam nodig.")]
    fiche.dates[0].end_date = first.start_date - timedelta(days=1)
    fiche.dates.append(DateRow("new1", SOON, start_time=time(14, 0), end_time=time(13, 0)))
    fiche.components[0].max_participants = 0
    fiche.components[0].products[0].price = Decimal("-1")
    fiche.components[0].products.append(ProductRow("new2", "", is_free=True, pay_on_site=True))
    fiche.components.append(ComponentRow("new3", " "))

    places = _places(db_session, activity.id, fiche)
    assert places == {
        "name": "De activiteit heeft een naam nodig.",
        "slug": places["slug"],
        f"d.{first.id}.end_date": "De einddatum ligt vóór de begindatum.",
        "d.new1.end_time": "Het einduur ligt niet na het beginuur.",
        f"c.{component.id}.max_participants": "Het maximum van “Onderdeel” moet groter zijn dan nul.",
        f"p.{product.id}.price": "De prijs van “Testproduct” mag niet negatief zijn.",
        "p.new2.name": "Een product heeft een naam nodig.",
        "c.new3.name": "Een onderdeel heeft een naam nodig.",
    }
    assert "bezet" in places["slug"] or "gebruik" in places["slug"], places["slug"]
    assert _counts(db_session) == before, "eight refusals, nothing written"
    assert db_session.get(Activity, activity.id).location != "Niet bewaard"


def test_a_removed_row_that_cannot_go_is_named_as_that_row(db_session):
    """The form no longer has the row; the refusal names it by its key, so the
    screen can put it back with the reason on it."""
    activity, component, product = _seed(db_session)
    _registration(db_session, component, product)
    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products = []
    assert _places(db_session, activity.id, fiche) == {
        f"p.{product.id}": "Het product “Testproduct” staat op een inschrijving en kan niet "
        "verwijderd worden. Zet “Publiek zichtbaar” uit als het niet meer gekozen mag worden."
    }
    fiche = _as_is(db_session, activity.id)
    fiche.components = []
    assert list(_places(db_session, activity.id, fiche)) == [f"c.{component.id}"]


def test_the_rules_with_one_field_name_that_field(db_session):
    """Free and pay-on-site together, the question form, an unknown audience, an
    organiser who is no member, a refused file."""
    activity, component, product = _seed(db_session)
    outsider = _member(db_session, "Cas", member=False)

    fiche = _as_is(db_session, activity.id)
    fiche.components[0].products[0].is_free = True
    fiche.components[0].products[0].pay_on_site = True
    fiche.components[0].form_id = 999_999
    fiche.fields = {"target_audience": "ONBEKEND"}
    fiche.organisers.append(OrganiserRow("new1", outsider.id))
    places = _places(db_session, activity.id, fiche)
    assert set(places) == {
        f"p.{product.id}.pay_on_site",
        f"c.{component.id}.form_id",
        "target_audience",
        "o.new1",
    }
    assert places["o.new1"] == "Alleen leden kunnen organisator zijn."
    assert places[f"c.{component.id}.form_id"] == "Dat formulier bestaat niet."

    fiche = _as_is(db_session, activity.id)
    text = _upload("nota.txt", "text/plain", b"geen afbeelding")
    places = _places(
        db_session, activity.id, fiche, poster=text, component_files={str(component.id): text}
    )
    assert set(places) == {"file", f"c.{component.id}.file"}


def test_the_question_about_the_contact_person_waits_for_a_save_that_would_go_through(
    db_session,
):
    """A refused save does not also ask to confirm: first the fields, then the question."""
    activity, component, _p = _seed(db_session)
    an = _member(db_session, "An")
    db_session.add(
        ActivityOrganiser(activity_id=activity.id, person_id=an.id, sort_order=0, is_contact=True)
    )
    db_session.commit()
    fiche = _as_is(db_session, activity.id)
    fiche.organisers[0].is_contact = False
    fiche.components[0].max_participants = -3
    assert list(_places(db_session, activity.id, fiche)) == [f"c.{component.id}.max_participants"]
