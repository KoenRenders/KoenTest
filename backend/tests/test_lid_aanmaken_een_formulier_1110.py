"""Een lid aanmaken in de backoffice: één formulier, één opslaan-actie (#1110).

Gemeld door Koen op 20 september 2026: aanmaken werkte anders dan hij verwacht en
anders dan het publieke formulier waarmee hij het vergelijkt. Van "niets" tot
"gezin met hoofdlid, adres, contactgegevens en lidmaatschap" waren er vier aparte
opslag-acties, elk met een eigen commit — en e-mail en gsm van het hoofdlid, die
publiek verplicht zijn, vroeg het beheerscherm zelfs niet. Je kon via de
beheerkant dus een lid aanmaken dat publiek geweigerd zou worden.

Sinds dit issue is er één schrijfweg
(`household_service.create_family_with_members`) met twee ingangen: de publieke
registratie hangt er haar dedup, betaling en bevestigingsmail omheen, de
beheerkant haar eigen actor en een meteen actief lidmaatschap. Deze tests staan
op de beheeringang; dat de publieke ingang dezelfde weg gebruikt, bewijzen de
bestaande publieke tests die mee moesten blijven werken.

De vier uit het issue, in volgorde:

1. één POST levert gezin, hoofdlid, adres én contactgegevens (en het lidmaatschap);
2. een hoofdlid zonder e-mail of zonder gsm wordt geweigerd, met dezelfde reden
   als publiek — de regel komt uit hetzelfde schema, dus hij kán niet uiteenlopen;
3. hoofdlid plus twee gezinsleden komen in één keer binnen;
4. faalt er iets halverwege, dan staat er niets in de databank. Twee keer: met een
   ongeldig tweede gezinslid (wat een beheerder echt kan intypen) én met een fout
   ná de eerste rijen, want alleen dat tweede bewijst de transactie in plaats van
   de volgorde van de controles.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
de contactregel uit `FamilyCreate` gehaald → test 2 valt om; de `begin_nested`
in `create_family_by_admin` vervangen door een kale aanroep → test 4b valt om met
een half gezin in de databank.
"""
from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import (Address, ContactDetail, Member, MemberPerson,
                                 Person)
from app.domains.membership.api import Membership
from tests.conftest import SEEDED_ADMIN_EMAIL, nieuw_lid_velden

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> str:
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _gezin_uit(antwoord) -> int:
    assert antwoord.status_code == 204, antwoord.text[:400]
    return int(antwoord.headers["HX-Redirect"].rsplit("/", 1)[1])


def _persoon(db, voornaam: str) -> Person:
    return db.query(Person).filter(Person.first_name == voornaam).one()


def _telling(db) -> tuple[int, int]:
    return (db.query(Member).count(), db.query(Person).count())


# ── 1. Eén POST, alles erin ──────────────────────────────────────────────────

def test_een_post_maakt_gezin_hoofdlid_adres_en_contactgegevens(client, db_session):
    csrf = _login(client)

    gezin = _gezin_uit(client.post("/admin/leden",
                                   data=nieuw_lid_velden(db_session),
                                   headers={"X-CSRF-Token": csrf}))

    db_session.expire_all()
    persoon = _persoon(db_session, "Nieuw")
    koppeling = db_session.query(MemberPerson).filter(
        MemberPerson.person_id == persoon.id).one()
    assert koppeling.member_id == gezin and koppeling.relation_type == "HOOFDLID"

    adres = db_session.query(Address).filter(Address.person_id == persoon.id).one()
    assert (adres.street, adres.house_number) == ("Nieuwstraat", "7")
    assert adres.postal_code.postal_code == "2400"

    contacten = {c.contact_type_code: c.value for c in
                 db_session.query(ContactDetail).filter(
                     ContactDetail.person_id == persoon.id).all()}
    assert contacten["EMAIL"] == "nieuw@example.com"
    assert contacten["MOBILE"] == "0470000000"

    # Het lidmaatschap hoorde bij dezelfde handeling en is meteen actief: er hangt
    # in de beheerkant geen betaling aan die het nog moet activeren.
    lidmaatschap = db_session.query(Membership).filter(
        Membership.member_id == gezin).one()
    assert lidmaatschap.is_active is True
    assert lidmaatschap.valid_from is not None and lidmaatschap.valid_to is not None


def test_het_scherm_is_een_formulier_met_een_opslaan_actie(client, db_session):
    """De vorm van het scherm, niet alleen de route: één `<form>` dat post naar
    /admin/leden, met de gedeelde veldenset en het adres erin."""
    _login(client)
    html = client.get("/admin/leden/nieuw").text

    assert html.count('hx-post="/admin/leden"') == 1, "meer dan één opslaan-actie"
    for veld in ('name="m0_first_name"', 'name="m0_email"', 'name="m0_mobile"',
                 'name="street"', 'name="house_number"', 'name="postal_code"'):
        assert veld in html, f"{veld} ontbreekt op het aanmaakscherm"
    # Een gezinslid erbij haalt een lege rij op; dat is geen opslag.
    assert 'hx-get="/admin/leden/nieuw/persoon-rij"' in html


# ── 2. Dezelfde regel als publiek ────────────────────────────────────────────

@pytest.mark.parametrize("weg", ["m0_email", "m0_mobile"])
def test_een_hoofdlid_zonder_email_of_gsm_wordt_geweigerd(client, db_session, weg):
    csrf = _login(client)
    voor = _telling(db_session)

    antwoord = client.post("/admin/leden",
                           data=nieuw_lid_velden(db_session, **{weg: None}),
                           headers={"X-CSRF-Token": csrf})

    assert antwoord.status_code == 422
    reden = "E-mailadres" if weg == "m0_email" else "Mobiel nummer"
    assert reden in antwoord.text, antwoord.text[:400]
    db_session.expire_all()
    assert _telling(db_session) == voor, "er is toch iets bewaard"


def test_de_reden_komt_uit_hetzelfde_schema_als_publiek(client, db_session):
    """Niet "een foutmelding", maar dezelfde: publiek en beheer bouwen allebei een
    `FamilyCreate`, en die draagt de regel. Twee formuleringen zouden betekenen
    dat de regel op twee plaatsen staat."""
    from pydantic import ValidationError

    from app.domains.membership.api import FamilyCreate, FamilyMemberCreate

    with pytest.raises(ValidationError) as fout:
        FamilyCreate(street="S", house_number="1", postal_code="2400",
                     members=[FamilyMemberCreate(first_name="A", last_name="B",
                                                 relation_type="HOOFDLID")])
    schema_reden = str(fout.value.errors()[0]["msg"])

    csrf = _login(client)
    antwoord = client.post("/admin/leden",
                           data=nieuw_lid_velden(db_session, m0_email=None),
                           headers={"X-CSRF-Token": csrf})
    assert schema_reden.split(":")[-1].strip() in antwoord.text


# ── 3. Hoofdlid plus twee gezinsleden, in één keer ───────────────────────────

def test_een_gezin_met_twee_extra_leden_komt_in_een_keer_binnen(client, db_session):
    csrf = _login(client)
    velden = nieuw_lid_velden(
        db_session,
        m1_first_name="Partner", m1_last_name="Lid", m1_date_of_birth="1981-02-02",
        m1_gender_code="F", m1_relation_type="PARTNER",
        m2_first_name="Kind", m2_last_name="Lid", m2_date_of_birth="2012-03-03",
        m2_gender_code="M", m2_relation_type="KIND",
    )

    gezin = _gezin_uit(client.post("/admin/leden", data=velden,
                                   headers={"X-CSRF-Token": csrf}))

    db_session.expire_all()
    rollen = {mp.person.first_name: mp.relation_type for mp in
              db_session.query(MemberPerson).filter(
                  MemberPerson.member_id == gezin).all()}
    assert rollen == {"Nieuw": "HOOFDLID", "Partner": "PARTNER", "Kind": "KIND"}

    # Het adres hangt aan het hoofdlid en aan niemand anders (#125).
    adressen = {a.person.first_name for a in db_session.query(Address).join(Person).all()}
    assert adressen == {"Nieuw"}


# ── 4. Halverwege mislukken laat niets achter ────────────────────────────────

def test_een_ongeldig_tweede_gezinslid_laat_geen_half_gezin_achter(client, db_session):
    """Wat een beheerder echt kan intypen: een gezinslid zonder geboortedatum."""
    csrf = _login(client)
    voor = _telling(db_session)

    antwoord = client.post("/admin/leden",
                           data=nieuw_lid_velden(
                               db_session,
                               m1_first_name="Half", m1_last_name="Lid",
                               m1_gender_code="F", m1_relation_type="PARTNER"),
                           headers={"X-CSRF-Token": csrf})

    assert antwoord.status_code == 422
    assert "Geboortedatum" in antwoord.text
    db_session.expire_all()
    assert _telling(db_session) == voor
    assert not db_session.query(Person).filter(Person.first_name.in_(("Nieuw", "Half"))).all()


def test_een_fout_na_de_eerste_rijen_laat_niets_achter(client, db_session, monkeypatch):
    """De echte transactietest.

    De controle op de lidgegevens staat vóór het schrijven, dus de test hierboven
    bewijst de volgorde en niet de transactie. Hier faalt het pas bij het
    lidmaatschap — ná gezin, persoon, adres en contactgegevens. Blijft daar iets
    van staan, dan was "één opslaan-actie" alleen een schermkwestie.
    """
    from app.domains.audit import api as audit_api

    def _knal(*args, **kwargs):
        raise RuntimeError("bewust kapot, na de eerste rijen")

    monkeypatch.setattr(audit_api, "snapshot_membership", _knal)

    csrf = _login(client)
    voor = _telling(db_session)

    with pytest.raises(RuntimeError):
        client.post("/admin/leden", data=nieuw_lid_velden(db_session),
                    headers={"X-CSRF-Token": csrf})

    db_session.expire_all()
    assert _telling(db_session) == voor, "er staat een half gezin in de databank"
    assert not db_session.query(Address).join(Person).filter(
        Person.first_name == "Nieuw").all()
