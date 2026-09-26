"""#1174 — het scherm om e-mailadressen te beheren.

De nieuwsbriefverantwoordelijke heeft een tiental adressen die het portaal niet
kent. De opslag kon ze al dragen en het aanmelden herkende ze al; wat ontbrak was
de bediening. Dit bestand toetst die drie handelingen — toevoegen, aanwijzen als
hoofdadres, verwijderen — en vooral de invariant eromheen:

**er is altijd precies één hoofdadres.** De databank bewaakt daar maar de helft
van: `uq_contact_details_one_primary_per_type` (migratie 053) laat *hoogstens*
één primair adres per persoon toe. Dat er ook *minstens* één is, is gedrag, en
gedrag zonder test verdwijnt bij de eerstvolgende herschrijving.
"""
from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Person
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family

pytestmark = pytest.mark.ui_serverrendered

HOOFD = "hoofd@example.com"
TWEEDE = "tweede@example.com"
DERDE = "derde@example.com"


@pytest.fixture
def gezin(db_session):
    member, person = create_test_family(db_session, email=HOOFD)
    db_session.commit()
    return member, person


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _adressen(db, person) -> dict[str, bool]:
    db.expire_all()
    person = db.query(Person).filter(Person.id == person.id).one()
    return {c.value: bool(c.is_primary) for c in person.contact_details
            if c.contact_type_code == "EMAIL"}


def _rij_id(db, person, waarde: int | str) -> int:
    person = db.query(Person).filter(Person.id == person.id).one()
    return next(c.id for c in person.contact_details
                if c.contact_type_code == "EMAIL" and c.value == waarde)


def _post(client, csrf, pad: str, **data):
    return client.post(pad, data=data, headers={"X-CSRF-Token": csrf})


# ── Toevoegen ───────────────────────────────────────────────────────────────

def test_een_tweede_adres_erbij_zetten(client, db_session, gezin):
    """De handeling waar dit issue om begon.

    Het blijft een EXTRA adres: het hoofdadres verandert niet, want dat is wat
    Raak Nationaal in zijn programma heeft.
    """
    member, person = gezin
    csrf = _login(client)

    respons = _post(client, csrf,
                    f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email",
                    extra_email=TWEEDE)
    assert respons.status_code == 200
    assert _adressen(db_session, person) == {HOOFD: True, TWEEDE: False}


def test_hetzelfde_adres_twee_keer_levert_een_rij_op(client, db_session, gezin):
    """Een vergissing, geen tweede geval — en hoofdletterongevoelig.

    Zonder deze grens staat hetzelfde adres twee keer bij één persoon, krijgt die
    mailbox de nieuwsbrief dubbel, en mag iemand het later met de hand opruimen.
    """
    member, person = gezin
    csrf = _login(client)
    pad = f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email"

    _post(client, csrf, pad, extra_email=TWEEDE)
    _post(client, csrf, pad, extra_email=TWEEDE.upper())

    assert _adressen(db_session, person) == {HOOFD: True, TWEEDE: False}


def test_het_eerste_adres_van_een_persoon_wordt_meteen_hoofdadres(client, db_session):
    """Zonder adressen is het nieuwe per definitie het hoofdadres.

    Anders had die persoon adressen en géén hoofdadres — de toestand die de
    invariant net uitsluit.
    """
    member, person = create_test_family(db_session, email=HOOFD)
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    db_session.commit()
    csrf = _login(client)

    _post(client, csrf,
          f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email",
          extra_email=TWEEDE)

    assert _adressen(db_session, person) == {TWEEDE: True}


# ── Hoofdadres aanwijzen ────────────────────────────────────────────────────

def test_een_ander_adres_aanwijzen_verplaatst_het_hoofdadres(client, db_session, gezin):
    """Precies één blijft primair — het oude wordt een gewoon adres.

    De volgorde in de service is bewust: eerst het oude terugzetten, dan het
    nieuwe aanwijzen. Andersom zouden er even twee primair zijn en weigert de
    partiële unieke index de flush. Zou iemand die volgorde omdraaien, dan valt
    deze test om met een IntegrityError in plaats van met een assertie — ook
    goed, maar dit is de reden dat ze bestaat.
    """
    member, person = gezin
    csrf = _login(client)
    _post(client, csrf, f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email",
          extra_email=TWEEDE)
    tweede_id = _rij_id(db_session, person, TWEEDE)

    _post(client, csrf,
          f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email/{tweede_id}/hoofd")

    assert _adressen(db_session, person) == {HOOFD: False, TWEEDE: True}


# ── Verwijderen ─────────────────────────────────────────────────────────────

def test_een_extra_adres_verwijderen_laat_het_hoofdadres_staan(client, db_session, gezin):
    member, person = gezin
    csrf = _login(client)
    _post(client, csrf, f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email",
          extra_email=TWEEDE)
    tweede_id = _rij_id(db_session, person, TWEEDE)

    _post(client, csrf,
          f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email/{tweede_id}/verwijderen")

    assert _adressen(db_session, person) == {HOOFD: True}


def test_het_hoofdadres_verwijderen_wijst_er_geen_ander_aan(client, db_session, gezin):
    """Nul hoofdadressen is een geldige toestand (Koen, 27 september 2026).

    Ik had hier eerst het oudste overgebleven adres laten promoveren, met het
    argument dat een lid anders adressen op het scherm houdt en toch geen post
    krijgt. Koen heeft dat teruggedraaid, en zijn reden gaat dieper: het
    hoofdadres is geen voorkeur maar een HERKOMST — het adres dat Raak Nationaal
    in zijn programma heeft. Zelf een ander aanwijzen omdat er toevallig een rij
    overblijft, verzint die herkomst. *"Dan heb ik nog liever dat een lid geen
    hoofdadres heeft."*

    Mijn argument vervalt bovendien: geen enkele verzending hangt nog aan het
    hoofdadres.

    Tegenproef: de promotie terugzetten → deze test faalt met `TWEEDE: True`.
    """
    member, person = gezin
    csrf = _login(client)
    pad = f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email"
    _post(client, csrf, pad, extra_email=TWEEDE)
    _post(client, csrf, pad, extra_email=DERDE)
    hoofd_id = _rij_id(db_session, person, HOOFD)

    _post(client, csrf, f"{pad}/{hoofd_id}/verwijderen")

    assert _adressen(db_session, person) == {TWEEDE: False, DERDE: False}, (
        "er hoort geen nieuw hoofdadres aangewezen te worden")


def test_ook_het_laatste_adres_mag_weg(client, db_session, gezin):
    """*Niets aanwijzen, niets weigeren* (Koen, 27 september 2026).

    Ik had hier een grendel gezet — zonder adres kan een lid zich niet meer
    aanmelden — maar dat was een eis die niemand gevraagd had. Een verkeerd adres
    moet je kunnen weghalen zonder eerst een ander te verzinnen; wat er stond
    blijft in de audit-snapshot bewaard.
    """
    member, person = gezin
    csrf = _login(client)
    hoofd_id = _rij_id(db_session, person, HOOFD)

    respons = _post(
        client, csrf,
        f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email/{hoofd_id}/verwijderen")

    assert respons.status_code == 200
    assert _adressen(db_session, person) == {}


# ── Het scherm zelf ─────────────────────────────────────────────────────────

def test_de_kaart_toont_alle_adressen_met_hun_rol(client, db_session, gezin):
    """Wat de beheerder ziet: elk adres, en welk het hoofdadres is.

    Op het TOTALE antwoord en niet op een fragment: deze kaart is wat een route
    teruggeeft na elke deelactie, dus wat hier staat is wat de beheerder na een
    klik op het scherm krijgt.
    """
    member, person = gezin
    csrf = _login(client)
    _post(client, csrf, f"/admin/leden/gezin/{member.id}/persoon/{person.id}/email",
          extra_email=TWEEDE)

    html = client.get(f"/admin/leden/gezin/{member.id}").text
    assert HOOFD in html and TWEEDE in html
    assert "hoofdadres" in html, "de kaart zegt niet welk adres het hoofdadres is"
    assert "Maak hoofdadres" in html, "er is geen knop om een ander adres aan te wijzen"
