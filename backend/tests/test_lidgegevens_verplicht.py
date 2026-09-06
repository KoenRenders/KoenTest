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
from app.domains.mdm.api import Person
from tests.conftest import (SEEDED_ADMIN_EMAIL, create_test_family,
                            seed_postal_code)

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
    lid = {"last_name": "Peeters", "first_name": "Jan",
           "email": "hoofd681@example.com", "mobile": "0470000000",
           "relation_type": "HOOFDLID"}
    lid.update(hoofdlid)
    return {"street": "Milostraat", "house_number": "40", "postal_code": "2400",
            "payment_method": "transfer", "members": [lid]}


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
        "een geweigerde registratie mag niemand aanmaken")

    met = client.post("/api/v1/families", json=_gezin_payload(
        date_of_birth="1980-01-01", gender_code="M"))
    assert met.status_code == 201, met.text


def test_publieke_registratie_eist_ze_ook_van_een_bijkomend_lid(client, db_session):
    """De oude #551-regel blijft gelden — de verruiming mag haar niet vervangen."""
    seed_postal_code(db_session)
    basis = _gezin_payload(date_of_birth="1980-01-01", gender_code="M")
    kind = {"last_name": "Peeters", "first_name": "Kind", "relation_type": "KIND"}

    zonder = client.post("/api/v1/families",
                         json={**basis, "members": basis["members"] + [kind]})
    assert zonder.status_code == 422, zonder.text

    met = client.post("/api/v1/families", json={**basis, "members": basis["members"] + [
        {**kind, "date_of_birth": "2012-03-04", "gender_code": "F"}]})
    assert met.status_code == 201, met.text


# ── Weg 2: beheer — gezinslid toevoegen ──────────────────────────────────────

def test_beheer_toevoegen_eist_de_velden(client, db_session):
    member, _ = create_test_family(db_session, email="beheer-add@example.com")
    csrf = _admin(client)
    velden = {"first_name": "Partner", "last_name": "Persoon",
              "relation_type": "PARTNER"}

    zonder = client.post(f"/admin/leden/gezin/{member.id}/personen",
                         data=velden, headers={"X-CSRF-Token": csrf})
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Partner").all()

    met = client.post(f"/admin/leden/gezin/{member.id}/personen",
                      data={**velden, "date_of_birth": "1985-05-05",
                            "gender_code": "F"},
                      headers={"X-CSRF-Token": csrf})
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
    velden = {"first_name": "Gewijzigd", "last_name": person.last_name,
              "relation_type": "HOOFDLID"}

    zonder = client.post(f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
                         data=velden, headers={"X-CSRF-Token": csrf})
    assert zonder.status_code == 422, zonder.text
    db_session.expire_all()
    bewaard = db_session.get(Person, person.id)
    assert bewaard.date_of_birth == origineel, "de weigering mag niets wegschrijven"
    assert bewaard.first_name != "Gewijzigd"

    met = client.post(f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
                      data={**velden, "date_of_birth": origineel.isoformat(),
                            "gender_code": "M"},
                      headers={"X-CSRF-Token": csrf})
    assert met.status_code == 200, met.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name == "Gewijzigd"


# ── Weg 4: gezinsportaal — eigen gegevens en een gezinslid ───────────────────

def test_portaal_bewerken_kan_de_velden_niet_leegmaken(client, db_session):
    _member, person = create_test_family(db_session, email="portaal681@example.com")
    origineel = person.date_of_birth
    csrf = _lid(client, "portaal681@example.com")
    velden = {"first_name": "Aangepast", "last_name": person.last_name}

    zonder = client.post(f"/leden/gezin/personen/{person.id}",
                         data=velden, headers={"X-CSRF-Token": csrf})
    assert zonder.status_code == 422, zonder.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name != "Aangepast"

    met = client.post(f"/leden/gezin/personen/{person.id}",
                      data={**velden, "date_of_birth": origineel.isoformat(),
                            "gender_code": "M"},
                      headers={"X-CSRF-Token": csrf})
    assert met.status_code == 200, met.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name == "Aangepast"


def test_portaal_toevoegen_eist_de_velden(client, db_session):
    _member, _person = create_test_family(db_session, email="portaal-add@example.com")
    csrf = _lid(client, "portaal-add@example.com")
    velden = {"first_name": "Kindje", "last_name": "Persoon"}

    zonder = client.post("/leden/gezin/personen", data=velden,
                         headers={"X-CSRF-Token": csrf})
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Kindje").all()

    met = client.post("/leden/gezin/personen",
                      data={**velden, "date_of_birth": "2015-06-07",
                            "gender_code": "F"},
                      headers={"X-CSRF-Token": csrf})
    assert met.status_code == 200, met.text
    assert db_session.query(Person).filter(Person.first_name == "Kindje").one()


# ── De regel zelf ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dob, geslacht", [
    (None, "M"),
    ("1980-01-01", None),
    ("1980-01-01", ""),
    ("1980-01-01", "   "),
    (None, None),
])
def test_de_regel_weigert_elke_onvolledige_combinatie(dob, geslacht):
    from app.domains.membership.api import (LidgegevensFout,
                                            controleer_geboortedatum_en_geslacht)

    with pytest.raises(LidgegevensFout):
        controleer_geboortedatum_en_geslacht(dob, geslacht)


def test_de_regel_laat_een_volledig_lid_door():
    """De keerzijde: zonder deze test bewijst niets dat de regel niet álles weigert."""
    from app.domains.membership.api import controleer_geboortedatum_en_geslacht

    controleer_geboortedatum_en_geslacht("1980-01-01", "M")


def test_de_regel_staat_in_de_service_en_niet_in_de_schermen():
    """Eén plek, zes aanroepen. Zodra een scherm de regel zelf gaat formuleren,
    bestaat ze twee keer en drijven de twee uit elkaar (#635, #679)."""
    for pad in ("app/domains/membership/ui.py", "app/domains/mdm/ui.py"):
        bron = open(pad, encoding="utf-8").read()
        assert "date_of_birth or not" not in bron and "Geboortedatum en geslacht" not in bron, (
            f"{pad} formuleert de regel zelf; ze hoort in membership/service.py")


# ── Weg 5: beheer — "Nieuw lid" (Koens beslissing, #681) ─────────────────────

def test_nieuw_lid_scherm_vraagt_de_velden_en_dwingt_ze_af(client, db_session):
    """Het aanmaakscherm vroeg sinds #627 enkel een naam.

    Dat was precies de ene weg waarlangs een lid zónder deze twee in het bestand
    kon komen terwijl élke andere ingang ze afdwingt. Koen koos ervoor de twee
    velden toe te voegen in plaats van de uitzondering te laten bestaan.
    """
    csrf = _admin(client)

    scherm = client.get("/admin/leden/nieuw")
    assert scherm.status_code == 200
    assert 'name="date_of_birth"' in scherm.text and 'name="gender_code"' in scherm.text

    velden = {"first_name": "Nieuw", "last_name": "Lid"}
    zonder = client.post("/admin/leden", data=velden, headers={"X-CSRF-Token": csrf})
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Person).filter(Person.first_name == "Nieuw").all()

    met = client.post("/admin/leden",
                      data={**velden, "date_of_birth": "1980-01-01",
                            "gender_code": "M"},
                      headers={"X-CSRF-Token": csrf})
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
    _meld_onvolledig({"voornaam": "Jan", "naam": "Peeters",
                      "geboortedatum": None, "geslacht": "M"}, report)
    assert len(report.warnings) == 1
    assert "geboortedatum" in report.warnings[0] and "Peeters" in report.warnings[0]

    _meld_onvolledig({"voornaam": "An", "naam": "Janssens",
                      "geboortedatum": None, "geslacht": None}, report)
    assert "geboortedatum en geslacht" in report.warnings[1]

    # Volledig → geen ruis. Een rapport dat alles meldt, meldt niets.
    _meld_onvolledig({"voornaam": "Vol", "naam": "Ledig",
                      "geboortedatum": "1980-01-01", "geslacht": "F"}, report)
    assert len(report.warnings) == 2
