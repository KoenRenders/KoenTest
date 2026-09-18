"""Organisers of an activity, up to three (#1004, CR-10 §3.9).

The limit lives in three places and this file tests two of them: the service
refuses the fourth with a message, and the database refuses a row with
`sort_order = 3` even when the service is bypassed. The screen hiding the button
is the third and is a courtesy, not a limit.

The confirmation for unticking the LAST contact person is a server rule too: a
dialog in one screen cannot stop a script, and a poster without a contact person
silently falls back to Raak's own details.

Broken to see them red (measured):
- the `MAX_ORGANISERS` check out of `add_organiser` → the fourth is accepted;
- the CHECK out of the migration → the raw insert with sort_order 3 succeeds;
- the override ignored in `organisers_for` → the poster shows the member's own
  address;
- the `is_member` check out of `add_organiser` → a non-member becomes organiser;
- the `bevestigd` check out of the route → the last tick disappears silently.
"""
import pytest
from sqlalchemy import text as sql_text

from app.domains.activities.api import (MAX_ORGANISERS, add_organiser, get_activity,
                                        organisers_for, remove_organiser,
                                        update_organiser)
from app.domains.activities.models import ActiviteitFout, Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _persoon(db, voornaam, achternaam, *, lid=True, email=None, gsm=None):
    person = Person(first_name=voornaam, last_name=achternaam)
    db.add(person)
    db.flush()
    if lid:
        gezin = Member()
        db.add(gezin)
        db.flush()
        db.add(MemberPerson(member_id=gezin.id, person_id=person.id,
                            relation_type="HOOFDLID"))
    if email:
        db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
    if gsm:
        db.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=gsm))
    db.flush()
    return person


@pytest.fixture
def activiteit(db_session):
    a = Activity(name="Quiz met trekkers")
    db_session.add(a)
    db_session.flush()
    return a


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


# ── De grens van drie, in twee lagen ─────────────────────────────────────────

def test_the_service_refuses_a_fourth_organiser(db_session, activiteit):
    for i in range(MAX_ORGANISERS):
        add_organiser(db_session, activiteit.id, _persoon(db_session, f"Lid{i}", "Drager").id)

    with pytest.raises(ActiviteitFout) as fout:
        add_organiser(db_session, activiteit.id, _persoon(db_session, "Vier", "Teveel").id)

    assert "hoogstens" in str(fout.value)
    assert len(organisers_for(db_session, activiteit.id)) == MAX_ORGANISERS


def test_the_database_refuses_a_fourth_row_too(db_session, activiteit):
    """The net under the rule: a row that never passed the service.

    Written over the raw connection, exactly as a script or an import would.
    """
    from sqlalchemy.exc import IntegrityError

    person = _persoon(db_session, "Vier", "Rechtstreeks")
    with pytest.raises(IntegrityError):
        db_session.execute(sql_text(
            "INSERT INTO activities.activity_organisers "
            "(tenant_id, activity_id, person_id, sort_order, is_contact) "
            "VALUES (2, :a, :p, 3, false)"), {"a": activiteit.id, "p": person.id})
        db_session.flush()
    db_session.rollback()


def test_the_same_person_is_not_added_twice(db_session, activiteit):
    person = _persoon(db_session, "Twee", "Keer")
    add_organiser(db_session, activiteit.id, person.id)
    with pytest.raises(ActiviteitFout):
        add_organiser(db_session, activiteit.id, person.id)


def test_a_freed_place_is_used_again(db_session, activiteit):
    eerste = add_organiser(db_session, activiteit.id, _persoon(db_session, "A", "Een").id)
    add_organiser(db_session, activiteit.id, _persoon(db_session, "B", "Twee").id)
    remove_organiser(db_session, activiteit.id, eerste.id)

    add_organiser(db_session, activiteit.id, _persoon(db_session, "C", "Drie").id)
    add_organiser(db_session, activiteit.id, _persoon(db_session, "D", "Vier").id)
    assert [o.sort_order for o in organisers_for(db_session, activiteit.id)] == [0, 1, 2]


# ── Wat er op een affiche komt ───────────────────────────────────────────────

def test_an_override_wins_and_clearing_it_gives_the_member_value_back(
        db_session, activiteit):
    person = _persoon(db_session, "Els", "Contact",
                      email="els@example.org", gsm="0470 00 00 00")
    rij = add_organiser(db_session, activiteit.id, person.id)

    [uit_fiche] = organisers_for(db_session, activiteit.id)
    assert (uit_fiche.email, uit_fiche.mobile) == ("els@example.org", "0470 00 00 00")

    update_organiser(db_session, activiteit.id, rij.id, {
        "email_override": "quiz@example.org", "mobile_override": "0470 11 11 11"})
    [met_override] = organisers_for(db_session, activiteit.id)
    assert (met_override.email, met_override.mobile) == ("quiz@example.org",
                                                         "0470 11 11 11")

    update_organiser(db_session, activiteit.id, rij.id, {
        "email_override": "", "mobile_override": "  "})
    [terug] = organisers_for(db_session, activiteit.id)
    assert (terug.email, terug.mobile) == ("els@example.org", "0470 00 00 00")


def test_nobody_is_a_contact_person_until_ticked(db_session, activiteit):
    rij = add_organiser(db_session, activiteit.id,
                        _persoon(db_session, "Jan", "Drager").id)
    assert organisers_for(db_session, activiteit.id)[0].is_contact is False

    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    assert organisers_for(db_session, activiteit.id)[0].is_contact is True


# ── Alleen leden, via de route ───────────────────────────────────────────────

def test_only_members_can_become_organiser(client, db_session, activiteit):
    """Through the route: the picker only SHOWS members, and a post skips it."""
    geen_lid = _persoon(db_session, "Nina", "Ondersteuner", lid=False)
    csrf = _login(client)

    resp = client.post(f"/admin/activiteiten/{activiteit.id}/organisatoren",
                       data={"person_id": geen_lid.id}, headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 200
    assert "Alleen leden" in resp.text
    assert organisers_for(db_session, activiteit.id) == []


def test_the_picker_offers_members_and_skips_who_is_already_there(
        client, db_session, activiteit):
    lid = _persoon(db_session, "Mia", "Zoekbaar")
    geen_lid = _persoon(db_session, "Nina", "Zoekbaar", lid=False)
    _login(client)

    html = client.get(f"/admin/activiteiten/{activiteit.id}/organisatoren",
                      params={"organiser_q": "zoekbaar"},
                      headers={"HX-Request": "true"}).text
    assert "Mia" in html and "Nina" not in html

    add_organiser(db_session, activiteit.id, lid.id)
    html = client.get(f"/admin/activiteiten/{activiteit.id}/organisatoren",
                      params={"organiser_q": "zoekbaar"},
                      headers={"HX-Request": "true"}).text
    assert "Geen lid gevonden" in html


# ── De bevestiging bij het laatste vinkje, via de route ──────────────────────

def _post_vinkje(client, csrf, activiteit, organiser_id, **extra):
    data = {"email_override": "", "mobile_override": ""}
    data.update(extra)
    return client.post(
        f"/admin/activiteiten/{activiteit.id}/organisatoren/{organiser_id}",
        data=data, headers={"X-CSRF-Token": csrf})


def test_the_last_tick_needs_a_confirmation(client, db_session, activiteit):
    rij = add_organiser(db_session, activiteit.id,
                        _persoon(db_session, "Els", "Contact").id)
    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    csrf = _login(client)

    zonder = _post_vinkje(client, csrf, activiteit, rij.id)
    assert zonder.status_code == 200
    assert "Zonder contactpersoon" in zonder.text
    db_session.expire_all()
    assert organisers_for(db_session, activiteit.id)[0].is_contact is True, (
        "het vinkje verdween zonder bevestiging")

    met = _post_vinkje(client, csrf, activiteit, rij.id, bevestigd="1")
    assert met.status_code == 200
    db_session.expire_all()
    assert organisers_for(db_session, activiteit.id)[0].is_contact is False


def test_unticking_one_of_two_needs_no_confirmation(client, db_session, activiteit):
    eerste = add_organiser(db_session, activiteit.id, _persoon(db_session, "A", "Een").id)
    tweede = add_organiser(db_session, activiteit.id, _persoon(db_session, "B", "Twee").id)
    for rij in (eerste, tweede):
        update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    csrf = _login(client)

    _post_vinkje(client, csrf, activiteit, eerste.id)

    db_session.expire_all()
    aangevinkt = [o.is_contact for o in organisers_for(db_session, activiteit.id)]
    assert aangevinkt == [False, True]


# ── De publieke kant verandert niet ──────────────────────────────────────────

def test_the_public_activity_page_shows_nothing_of_this(client, db_session, activiteit):
    from datetime import date, timedelta

    from app.domains.activities.api import ActivityDate

    db_session.add(ActivityDate(activity_id=activiteit.id,
                                start_date=date.today() + timedelta(days=30)))
    # Namen die nergens anders in een pagina voorkomen: "Els" zit toevallig in
    # "snelder" in een scriptregel, en dan meet je de paginatekst, niet het lek.
    person = _persoon(db_session, "Zwaluwke", "Kontaktnaam",
                      email="kontakt-1004@example.org", gsm="0470 12 34 56")
    rij = add_organiser(db_session, activiteit.id, person.id)
    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})

    html = client.get(f"/activiteiten/{activiteit.id}").text
    assert get_activity(db_session, activiteit.id) is not None
    for geheim in ("Zwaluwke", "Kontaktnaam", "kontakt-1004@example.org",
                   "0470 12 34 56", "organisator"):
        assert geheim.lower() not in html.lower(), geheim
