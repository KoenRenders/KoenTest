"""#681 — geboortedatum én geslacht zijn verplicht voor élk lid, ook het hoofdlid.

De regel bestond al (#551) maar gold half: `register_family` sloeg het hoofdlid
over, en aan de beheerkant en in het gezinsportaal werd er niets getoetst. In het
programma waarmee Raak zijn ledenbestand voert zijn het twee verplichte velden;
half afdwingen betekent dat het ledenbestand alsnog gaten krijgt, langs precies
die wegen die niemand controleert.

**Waarom deze tests er zo uitzien.** Toetsen op "een 422" bewijst niets: een 422
om een andere reden — een ontbrekend verplicht veld, een ongeldig e-mailadres, een
onbekende postcode — zou net zo groen zijn. Elke test hieronder is daarom een
**paar**: hetzelfde verzoek, één keer zónder de twee velden en één keer mét, en
verder identiek. Het verschil ís het bewijs dat die twee velden de oorzaak zijn.

Bewust geen `match=` op de meldingstekst: die mag hertaald worden zonder deze
tests om te gooien (dezelfde afweging als in #680).

De vijf schrijfwegen staan hier naast elkaar met opzet — publieke registratie,
beheer aanmaken/toevoegen/bewerken, gezinsportaal. Zit de regel op de juiste plek
— in de servicelaag, gedeeld — dan is dit vijf keer dezelfde korte test. Zakt er
één door terwijl de andere slagen, dan is dát de nuttigste uitkomst: het bewijst
dat de regel aan de ingang hangt in plaats van bij de bewerking.

De ledenimport is de zesde weg en de enige uitzondering: die meldt in plaats van
te weigeren. Koens beslissing, en de reden staat bij die test.
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Person
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_family,
    household_fields,
    seed_postal_code,
)

pytestmark = pytest.mark.ui_agnostisch


def _admin(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _lid(client, email):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _gezin_payload(**hoofdlid):
    """De publieke registratie met één hoofdlid; `hoofdlid` overschrijft velden."""
    lid = {
        "last_name": "Peeters",
        "first_name": "Jan",
        "email": "hoofd681@example.com",
        "mobile": "0470000000",
        "relation_type": "HOOFDLID",
    }
    lid.update(hoofdlid)
    return {
        "street": "Milostraat",
        "house_number": "40",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [lid],
    }


# ── Weg 1: publieke registratie ──────────────────────────────────────────────


def test_publieke_registratie_eist_de_velden_ook_van_het_hoofdlid(client, db_session):
    """Dit is de uitbreiding van #681: het hoofdlid was uitgezonderd (#551).

    Twee registraties die alleen in deze twee velden verschillen. Zonder → 422,
    mét → 201. Zou de eerste om een andere reden afgekeurd worden, dan zou de
    tweede — identiek op die velden na — ook falen.
    """
    seed_postal_code(db_session)

    zonder = client.post("/api/v1/families", json=_gezin_payload())
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Jan").all(), (
        "een geweigerde registratie mag niemand aanmaken"
    )

    met = client.post(
        "/api/v1/families", json=_gezin_payload(date_of_birth="1980-01-01", gender_code="M")
    )
    assert met.status_code == 201, met.text


def test_publieke_registratie_eist_ze_ook_van_een_bijkomend_lid(client, db_session):
    """De oude #551-regel blijft gelden — de verruiming mag haar niet vervangen."""
    seed_postal_code(db_session)
    basis = _gezin_payload(date_of_birth="1980-01-01", gender_code="M")
    kind = {"last_name": "Peeters", "first_name": "Kind", "relation_type": "KIND"}

    zonder = client.post("/api/v1/families", json={**basis, "members": basis["members"] + [kind]})
    assert zonder.status_code == 422, zonder.text

    met = client.post(
        "/api/v1/families",
        json={
            **basis,
            "members": basis["members"]
            + [{**kind, "date_of_birth": "2012-03-04", "gender_code": "F"}],
        },
    )
    assert met.status_code == 201, met.text


# ── Weg 2: beheer — gezinslid toevoegen ──────────────────────────────────────


def test_beheer_toevoegen_eist_de_velden(client, db_session):
    member, _ = create_test_family(db_session, email="beheer-add@example.com")
    csrf = _admin(client)
    velden = {"first_name": "Partner", "last_name": "Persoon", "relation_type": "PARTNER"}

    zonder = client.post(
        f"/admin/leden/gezin/{member.id}/personen", data=velden, headers={"X-CSRF-Token": csrf}
    )
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Partner").all()

    met = client.post(
        f"/admin/leden/gezin/{member.id}/personen",
        data={**velden, "date_of_birth": "1985-05-05", "gender_code": "F"},
        headers={"X-CSRF-Token": csrf},
    )
    assert met.status_code == 200, met.text
    assert db_session.query(Person).filter(Person.first_name == "Partner").one()


# ── Weg 3: beheer — gezinslid bewerken ───────────────────────────────────────


def test_beheer_bewerken_kan_de_velden_niet_leegmaken(client, db_session):
    """Bewerken telt mee: een lid dat de velden hád, mag ze niet kwijtraken.

    Dit was tot #681 geen 422 maar stille schade: het beheerformulier stuurt alle
    velden mee, dus een lege geboortedatum overschreef de bestaande waarde met
    NULL zonder dat iemand het merkte.
    """
    member, person = create_test_family(db_session, email="beheer-edit@example.com")
    origineel = person.date_of_birth
    csrf = _admin(client)
    velden = {"first_name": "Gewijzigd", "last_name": person.last_name, "relation_type": "HOOFDLID"}

    zonder = client.post(
        f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
        data=velden,
        headers={"X-CSRF-Token": csrf},
    )
    assert zonder.status_code == 422, zonder.text
    db_session.expire_all()
    bewaard = db_session.get(Person, person.id)
    assert bewaard.date_of_birth == origineel, "de weigering mag niets wegschrijven"
    assert bewaard.first_name != "Gewijzigd"

    met = client.post(
        f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
        data={**velden, "date_of_birth": origineel.isoformat(), "gender_code": "M"},
        headers={"X-CSRF-Token": csrf},
    )
    assert met.status_code == 200, met.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name == "Gewijzigd"


# ── Weg 4: gezinsportaal — eigen gegevens en een gezinslid ───────────────────
#
# Since #1590 the portal has one door: the whole household is one form and one
# save (`POST /leden/gezin`). The pair stays what it was — the same form, once
# without the two fields and once with them — and the refusal is asked at its
# place, which is stricter than "a 422".


def _save(client, csrf, fields):
    return client.post("/leden/gezin", data=fields, headers={"X-CSRF-Token": csrf})


def test_portaal_bewerken_kan_de_velden_niet_leegmaken(client, db_session):
    _member, person = create_test_family(
        db_session, email="portaal681@example.com", mobile="0470 00 00 01"
    )
    db_session.commit()
    origineel = person.date_of_birth
    csrf = _lid(client, "portaal681@example.com")
    velden = household_fields(client)
    velden[f"h.{person.id}.first_name"] = "Aangepast"

    zonder = _save(
        client,
        csrf,
        {k: v for k, v in velden.items() if k != f"h.{person.id}.gender_code"}
        | {f"h.{person.id}.date_of_birth": ""},
    )
    assert zonder.status_code == 422, zonder.text
    assert f'data-error-for="h.{person.id}.date_of_birth"' in zonder.text
    db_session.expire_all()
    bewaard = db_session.get(Person, person.id)
    assert bewaard.first_name != "Aangepast"
    assert bewaard.date_of_birth == origineel, "de weigering mag niets wegschrijven"

    met = _save(client, csrf, velden)
    assert met.status_code == 200, met.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name == "Aangepast"


def test_portaal_toevoegen_eist_de_velden(client, db_session):
    _member, _person = create_test_family(
        db_session, email="portaal-add@example.com", mobile="0470 00 00 01"
    )
    db_session.commit()
    csrf = _lid(client, "portaal-add@example.com")
    velden = household_fields(client)
    velden["h_order"] = [*velden["h_order"], "n1"]
    velden.update({"h.n1.first_name": "Kindje", "h.n1.last_name": "Persoon"})

    zonder = _save(client, csrf, velden)
    assert zonder.status_code == 422, zonder.text
    assert 'data-error-for="h.n1.date_of_birth"' in zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Kindje").all()

    met = _save(
        client, csrf, {**velden, "h.n1.date_of_birth": "2015-06-07", "h.n1.gender_code": "F"}
    )
    assert met.status_code == 200, met.text
    assert db_session.query(Person).filter(Person.first_name == "Kindje").one()


# ── The main member's mobile: the member's doors ask it, the board's does not ──


def _mobiles(db, person) -> list[str]:
    db.expire_all()
    return [
        c.value
        for c in db.get(Person, person.id).contact_details
        if c.contact_type_code == "MOBILE"
    ]


def test_the_main_members_mobile_can_be_emptied_at_both_doors_and_word_lid_asks_it(
    client, db_session
):
    """#1603 (Koen, 5 October 2026): the main member's mobile number is asked by
    Word lid only. One household, the same emptied field at the member's door and
    at the board's: both store a main member without a number. And the sign-up
    still refuses one, at its field — the rule did not go, it has one door."""
    from tests.conftest import signup_fields

    member, person = create_test_family(
        db_session, email="gsm-hoofd@example.com", mobile="0470 00 00 01"
    )
    db_session.commit()

    csrf = _lid(client, "gsm-hoofd@example.com")
    fields = household_fields(client)
    assert fields[f"h.{person.id}.mobile"] == "0470 00 00 01"
    saved = _save(client, csrf, {**fields, f"h.{person.id}.mobile": ""})
    assert saved.status_code == 200, saved.text[:300]
    assert _mobiles(db_session, person) == []

    db_session.add(
        ContactDetail(
            person_id=person.id, contact_type_code="MOBILE", value="0470 00 00 02", is_primary=True
        )
    )
    db_session.commit()
    csrf = _admin(client)
    answer = client.post(
        f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
        data={
            "first_name": person.first_name,
            "last_name": person.last_name,
            "date_of_birth": person.date_of_birth.isoformat(),
            "gender_code": person.gender_code,
            "relation_type": "HOOFDLID",
            "mobile": "",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert answer.status_code == 200, answer.text
    assert _mobiles(db_session, person) == []

    client.cookies.clear()
    refused = client.post(
        "/lid-worden",
        data=signup_fields(db_session, emails=("nieuw-gsm@example.com",), **{"h.n0.mobile": ""}),
    )
    assert refused.status_code == 422
    assert 'data-error-for="h.n0.mobile"' in refused.text


# ── De regel zelf ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "dob, geslacht",
    [
        (None, "M"),
        ("1980-01-01", None),
        ("1980-01-01", ""),
        ("1980-01-01", "   "),
        (None, None),
    ],
)
def test_de_regel_weigert_elke_onvolledige_combinatie(dob, geslacht):
    """Since CR-13 phase 3 the rule lives on the household link, `mdm`'s
    `MemberPerson` (#1250); `require_details` is what a door asks before it changes
    anything, and `check()` holds the same rule on every flush."""
    from app.domains.mdm.api import MemberPerson, PersonDetailsMissing

    with pytest.raises(PersonDetailsMissing):
        MemberPerson.require_details(dob, geslacht)


def test_de_regel_laat_een_volledig_lid_door():
    """De keerzijde: zonder deze test bewijst niets dat de regel niet álles weigert."""
    from app.domains.mdm.api import MemberPerson

    MemberPerson.require_details("1980-01-01", "M")


def test_de_regel_staat_in_de_service_en_niet_in_de_schermen():
    """Eén plek, zes aanroepen. Zodra een scherm de regel zelf gaat formuleren,
    bestaat ze twee keer en drijven de twee uit elkaar (#635, #679)."""
    for pad in ("app/domains/membership/ui.py", "app/domains/mdm/ui.py"):
        bron = open(pad, encoding="utf-8").read()
        assert "date_of_birth or not" not in bron and "Geboortedatum en geslacht" not in bron, (
            f"{pad} formuleert de regel zelf; ze hoort op MemberPerson in mdm/models.py"
        )


# ── Weg 5: beheer — "Nieuw lid" (Koens beslissing, #681) ─────────────────────


def test_nieuw_lid_scherm_vraagt_de_velden_en_dwingt_ze_af(client, db_session):
    """Het aanmaakscherm vroeg sinds #627 enkel een naam.

    Dat was precies de ene weg waarlangs een lid zónder deze twee in het bestand
    kon komen terwijl élke andere ingang ze afdwingt. Koen koos ervoor de twee
    velden toe te voegen in plaats van de uitzondering te laten bestaan.
    """
    from tests.conftest import nieuw_lid_velden

    csrf = _admin(client)

    scherm = client.get("/admin/leden/nieuw")
    assert scherm.status_code == 200
    # #1110: één formulier met de gedeelde veldenset, dus m0_-namen.
    assert 'name="m0_date_of_birth"' in scherm.text and 'name="m0_gender_code"' in scherm.text

    zonder = client.post(
        "/admin/leden",
        data=nieuw_lid_velden(db_session, m0_date_of_birth=None, m0_gender_code=None),
        headers={"X-CSRF-Token": csrf},
    )
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Nieuw").all()

    met = client.post(
        "/admin/leden", data=nieuw_lid_velden(db_session), headers={"X-CSRF-Token": csrf}
    )
    assert met.status_code == 204, met.text
    assert db_session.query(Person).filter(Person.first_name == "Nieuw").one()


# ── De ledenimport meldt, maar weigert niet ──────────────────────────────────


def test_de_import_meldt_een_onvolledige_rij_zonder_ze_te_weigeren(db_session):
    """Koens beslissing: een ledenrapport is geen formulier.

    Het komt uit een ander systeem, gaat over honderden rijen tegelijk, en op
    productie missen er vandaag twee een geboortedatum. Een import die daarop
    afbreekt kost meer dan hij oplevert — maar zwijgen mag ze evenmin, want dan is
    de import de ene weg waarlangs onvolledige leden ongemerkt binnenkomen.
    """
    from app.domains.mdm.import_service import ImportReport, _meld_onvolledig

    report = ImportReport()
    _meld_onvolledig(
        {"voornaam": "Jan", "naam": "Peeters", "geboortedatum": None, "geslacht": "M"}, report
    )
    assert len(report.warnings) == 1
    assert "geboortedatum" in report.warnings[0] and "Peeters" in report.warnings[0]

    _meld_onvolledig(
        {"voornaam": "An", "naam": "Janssens", "geboortedatum": None, "geslacht": None}, report
    )
    assert "geboortedatum en geslacht" in report.warnings[1]

    # Volledig → geen ruis. Een rapport dat alles meldt, meldt niets.
    _meld_onvolledig(
        {"voornaam": "Vol", "naam": "Ledig", "geboortedatum": "1980-01-01", "geslacht": "F"}, report
    )
    assert len(report.warnings) == 2
