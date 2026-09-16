"""Het scherm voor organisaties (#971), en wat het niet mag breken.

Twee dingen staan hier naast elkaar, en de tweede weegt zwaarder dan de eerste.

**Het gat.** `/admin/tenants` toont het platform en de afdelingen. De
ACCOUNT-organisatie — de vzw zelf — is géén tenant en stond daardoor in geen enkel
scherm, terwijl zij nu net degene is met een ondernemingsnummer en een rekening.
Haar rechtsvorm kunnen wijzigen is de eerste test: lukt dat, dan werkt het
fundament.

**Het risico.** `addresses` en `contact_details` worden gedeeld met personen — twee
mogelijke eigenaars, XOR-regel. Werk in die buurt kan de LEDENSCHERMEN breken zonder
dat iemand het merkt, en dat is de organisatie die live staat: haar gegevens
verschijnen op het publieke portaal en in de mails. De tests die ertoe doen zijn dus
niet die op de nieuwe functionaliteit — die zie je meteen als ze stuk is — maar die
op wat onveranderd hoort te blijven.

Twee daarvan kijken bewust **door de uitvoer heen** in plaats van een functie aan te
roepen: de `From`-regel van een werkelijk verstuurde mail, en de betaalinstructies
zoals een lid ze op zijn scherm leest. Een test die `tenant_display_name()`
rechtstreeks aanroept blijft groen op de dag dat niemand die functie nog aanroept —
dat is de vorm die deze week zes keer misging.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import (SEEDED_ADMIN_EMAIL, create_test_family,
                            seed_postal_code)
from tests.test_reporting_panel_ui import login

ACCOUNT_ID = 1          # Raak vzw — de rechtspersoon, géén tenant
MILLEGEM_ID = 2         # de afdeling die live staat


@pytest.fixture(autouse=True)
def postcode(db_session):
    """De postcodetabel is in de testdatabank leeg.

    Het adresformulier eist een postcode uit de lijst — zoals overal in v2.0 — dus
    zonder deze rij weigert élke opslag met "Kies een postcode uit de lijst". Dat is
    de bedoelde weigering en geen testprobleem; ze hoort alleen niet in de weg te
    staan bij tests die over iets anders gaan.
    """
    return seed_postal_code(db_session)


def _operator(client, db):
    login(client, db, SEEDED_ADMIN_EMAIL, ("OPERATOR",))
    return csrf_token_for(make_session_value(SEEDED_ADMIN_EMAIL))


def _post(client, db, organization_id: int, **velden):
    csrf = _operator(client, db)
    return client.post(f"/admin/organisaties/{organization_id}", data=velden,
                       headers={"X-CSRF-Token": csrf})


# ── Het gat: de organisatie die geen tenant is ───────────────────────────────

def test_the_organisation_that_is_not_a_tenant_is_in_the_list(client, db_session):
    _operator(client, db_session)
    html = client.get("/admin/organisaties").text
    assert "Raak" in html
    assert f'/admin/organisaties/{ACCOUNT_ID}' in html


def test_the_legal_form_of_the_account_can_be_changed(client, db_session):
    """De eerste test van dit issue: lukt dit, dan werkt het fundament.

    Raak vzw staat niet op `/admin/tenants` — ze draait geen site — en haar
    rechtsvorm was daardoor nergens te wijzigen.

    Kapotgemaakt om het rood te zien: `organization_options` teruggezet op
    `list_manageable_tenants` — de ACCOUNT valt dan uit de lijst en dit geeft 404.
    """
    resp = _post(client, db_session, ACCOUNT_ID, name="Raak", legal_form="VZW")

    assert resp.status_code == 200
    rij = db_session.execute(text(
        "SELECT legal_form FROM mdm.organizations WHERE id = :i"),
        {"i": ACCOUNT_ID}).scalar()
    assert rij == "VZW"


def test_the_tenant_screen_does_not_know_this_organisation(client, db_session):
    """En de tegenproef: dit is waarom het scherm bestaat.

    Zou `/admin/tenants/1` óók werken, dan was er geen gat en geen issue.
    """
    _operator(client, db_session)
    assert client.get(f"/admin/tenants/{ACCOUNT_ID}").status_code == 404


# ── Het risico: de ledenschermen blijven werken ──────────────────────────────

def test_the_member_screens_keep_working(client, db_session):
    """De test die ertoe doet (#971): aan de ledenkant verandert er niets.

    `addresses` en `contact_details` dragen sinds #924/#945 twee mogelijke
    eigenaars. Een organisatieadres wegschrijven met een verkeerde filter, of een
    query die de XOR-regel vergeet, breekt hier — en op een scherm dat niemand
    meteen opent.

    Kapotgemaakt om het rood te zien: in `update_organization_address` het filter op
    `organization_id` weggehaald, zodat hij het adres van een PERSOON pakt. Het
    gezinsscherm toont dan het adres van de vereniging.
    """
    member, persoon = create_test_family(db_session, email="lid971@example.com")
    _operator(client, db_session)

    # Een organisatieadres wegschrijven — precies het werk dat dit kan breken.
    _post(client, db_session, MILLEGEM_ID, name="Raak Millegem",
          street="Verenigingsstraat", house_number="1", postal_code="2400")

    html = client.get(f"/admin/leden/gezin/{member.id}").text
    assert html.count("Verenigingsstraat") == 0, (
        "het adres van de vereniging staat op het gezinsscherm")
    assert persoon.last_name in html


def test_a_member_address_still_saves(client, db_session, postcode):
    """Het schrijfpad van de leden, ná dat van de organisatie, in dezelfde tabel.

    Een organisatierij die per ongeluk als persoonsrij wegschrijft — of een filter
    dat de XOR-regel vergeet — valt hier om. Beide adressen worden daarom nagekeken:
    het lid moet gewijzigd zijn én de vereniging onaangeroerd.

    Het lid krijgt eerst een adres, want het beheerscherm WIJZIGT er een en maakt er
    geen aan; zonder die rij antwoordt de route "Address not found". Dat is bestaand
    gedrag en geen onderdeel van dit issue.
    """
    from app.domains.mdm.api import Address

    member, persoon = create_test_family(db_session, email="lid971b@example.com")
    db_session.add(Address(person_id=persoon.id, street="Oudestraat",
                           house_number="3", postal_code_id=postcode.id))
    db_session.flush()
    csrf = _operator(client, db_session)

    _post(client, db_session, MILLEGEM_ID, name="Raak Millegem",
          street="Verenigingsstraat", house_number="1", postal_code="2400")
    resp = client.post(f"/admin/leden/gezin/{member.id}/adres",
                       data={"street": "Ledenlaan", "house_number": "9",
                             "bus_number": "", "postal_code": "2400"},
                       headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 200
    van_lid = db_session.execute(text(
        "SELECT street FROM mdm.addresses WHERE person_id = :p "
        "AND deleted_at IS NULL"), {"p": persoon.id}).scalar()
    van_vereniging = db_session.execute(text(
        "SELECT street FROM mdm.addresses WHERE organization_id = :o "
        "AND deleted_at IS NULL"), {"o": MILLEGEM_ID}).scalar()
    assert van_lid == "Ledenlaan"
    assert van_vereniging == "Verenigingsstraat", (
        "het adres van de vereniging is meegeschreven met dat van het lid")


# ── Door de uitvoer heen: de twee kanalen naar buiten ────────────────────────

def test_the_organisation_name_reaches_the_from_line_of_a_sent_mail(db_session,
                                                                    monkeypatch):
    """De afzender van een echte mail, niet de functie die hem samenstelt.

    `tenant_display_name()` rechtstreeks toetsen blijft groen op de dag dat niemand
    die functie nog aanroept. Deze test leest de `From`-regel van het bericht dat
    aan SMTP is aangeboden.

    En hij gebruikt een AFWIJKENDE naam met opzet: de terugval in `_display_name()`
    geeft letterlijk "Raak Millegem" terug, dus met de gezaaide naam zou dit slagen
    terwijl de organisatie helemaal niet geraadpleegd werd.

    Kapotgemaakt om het rood te zien: `tenant_display_name(db)` vervangen door de
    terugval — dan staat de gezaaide naam in de `From` en niet de gewijzigde.
    """
    from app.domains.mail import service as mail_mod
    from app.domains.mdm.api import update_organization_details

    update_organization_details(db_session, MILLEGEM_ID,
                               {"name": "Vereniging Zevenbergen"})
    db_session.flush()

    # `_display_name()` opent zijn eigen sessie; de testsessie commit niet, dus die
    # tweede zou de gezaaide naam lezen. De sessie wordt omgeleid, de code niet.
    class _Sessie:
        def __init__(self, echte):
            self._echte = echte

        def __getattr__(self, naam):
            return getattr(self._echte, naam)

        def close(self):
            pass   # de testsessie sluiten zou de rest van de test slopen

    import app.database as database_mod
    monkeypatch.setattr(database_mod, "SessionLocal", lambda: _Sessie(db_session))
    monkeypatch.setattr(mail_mod.settings, "gmail_user", "x@example.org")
    monkeypatch.setattr(mail_mod.settings, "gmail_app_password", "pw")

    verstuurd = {}

    class _FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def sendmail(self, afzender, ontvangers, bericht):
            verstuurd["bericht"] = bericht

    monkeypatch.setattr(mail_mod.smtplib, "SMTP_SSL", lambda *a, **k: _FakeSMTP())

    mail_mod.send_form_confirmation(to_email="lezer@example.org",
                                    form_title="Contact", name="Lezer")

    assert "bericht" in verstuurd, "er is geen mail aan SMTP aangeboden"
    from_regel = next(r for r in verstuurd["bericht"].splitlines()
                      if r.startswith("From:"))
    assert "Vereniging Zevenbergen" in from_regel, from_regel


def test_the_payment_instructions_a_member_reads_come_from_the_organisation(
        client, db_session):
    """De betaalinstructies op het scherm van een lid, niet de functie eronder.

    Kapotgemaakt om het rood te zien: `tenant_payment_iban(db)` uit
    `membership/ui.py` gehaald — dan staat het rekeningnummer niet meer op het
    gezinsportaal en valt de laatste assertie om.
    """
    from app.domains.membership.api import Membership
    from app.domains.mdm.api import update_organization_details
    from app.domains.payment.api import PaymentRecord

    update_organization_details(db_session, MILLEGEM_ID,
                               {"payment_iban": "BE68 5390 0754 7034",
                                "payment_beneficiary": "Vereniging Zevenbergen"})
    member, _persoon = create_test_family(db_session, email="betaler@example.org")
    jaar = date.today().year + 1
    ms = Membership(member_id=member.id, year=jaar, is_active=False,
                    valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31))
    db_session.add(ms)
    db_session.flush()
    db_session.add(PaymentRecord(
        payable_type="membership", payable_id=ms.id, amount=Decimal("35.00"),
        method="transfer", status="pending",
        structured_communication="+++123/4567/89012+++"))
    db_session.commit()

    client.cookies.set(SESSION_COOKIE, make_session_value("betaler@example.org"))
    html = client.get("/leden/gezin").text

    # In het betaalblok, niet ergens op de pagina. De eerste versie zocht het
    # rekeningnummer in de hele HTML en bleef groen toen ik de aanroep uit het
    # scherm haalde: de FOOTER toont datzelfde nummer, om een andere reden. Een
    # assertie die door twee oorzaken waar kan zijn, toetst geen van beide.
    assert "+++123/4567/89012+++" in html, "dit is niet het betaalscherm"
    start = html.index("Vernieuwing geregistreerd")
    blok = html[start:html.index("</div>", start)]

    assert "BE68 5390 0754 7034" in blok, blok
    assert "Vereniging Zevenbergen" in blok


# ── De codelijst, en wat er NIET overschreven wordt ──────────────────────────

def test_the_legal_form_dropdown_grows_with_the_code_list(client, db_session):
    """Uit `mdm.legal_form_codes` en niet uit een lijst in de template.

    Een rij toevoegen en de dropdown groeit mee, zonder codewijziging. Dat is de
    hele reden om een codelijst te hebben; een tweede opsomming in een sjabloon zou
    een tweede plek voor hetzelfde feit zijn.
    """
    db_session.execute(text(
        "INSERT INTO mdm.legal_form_codes (code, language, value) "
        "VALUES ('STICHTING', 'nl', 'Stichting')"))
    db_session.flush()

    _operator(client, db_session)
    html = client.get(f"/admin/organisaties/{ACCOUNT_ID}").text

    assert 'value="STICHTING"' in html
    assert "Stichting" in html


def test_a_second_bank_account_survives_a_save(client, db_session):
    """Het model laat er meer toe, het scherm biedt er één (#971).

    Staat er ooit een tweede rekening, dan bewerkt het scherm de eerste en laat het
    de tweede met rust. Niet stilzwijgend overschrijven of verwijderen — dat is hoe
    gegevens verdwijnen op de dag dat iemand het model gebruikt zoals het bedoeld is.

    Kapotgemaakt om het rood te zien: de `order_by(sort_order, id).first()` in
    `_bewaar_rekening` vervangen door een `delete()` van alle rijen.
    """
    db_session.execute(text(
        "INSERT INTO mdm.bank_accounts "
        "(organization_id, iban, sort_order, created_at, updated_at) "
        "VALUES (:o, 'BE11 1111 1111 1111', 0, now(), now()), "
        "       (:o, 'BE22 2222 2222 2222', 1, now(), now())"),
        {"o": ACCOUNT_ID})
    db_session.flush()

    _post(client, db_session, ACCOUNT_ID, name="Raak",
          payment_iban="BE33 3333 3333 3333")

    rijen = [r[0] for r in db_session.execute(text(
        "SELECT iban FROM mdm.bank_accounts WHERE organization_id = :o "
        "AND deleted_at IS NULL ORDER BY sort_order, id"), {"o": ACCOUNT_ID})]
    assert rijen == ["BE33 3333 3333 3333", "BE22 2222 2222 2222"], rijen


# ── Het adres, in de vorm van de leden ───────────────────────────────────────

def test_the_address_round_trips(client, db_session):
    _post(client, db_session, ACCOUNT_ID, name="Raak", street="Kerkstraat",
          house_number="7", bus_number="B", postal_code="2400")

    _operator(client, db_session)
    html = client.get(f"/admin/organisaties/{ACCOUNT_ID}").text
    assert 'value="Kerkstraat"' in html
    assert 'value="7"' in html
    assert 'value="B"' in html


def test_clearing_street_and_number_removes_the_address(client, db_session):
    _post(client, db_session, ACCOUNT_ID, name="Raak", street="Kerkstraat",
          house_number="7", postal_code="2400")
    _post(client, db_session, ACCOUNT_ID, name="Raak", street="", house_number="",
          postal_code="")

    aantal = db_session.execute(text(
        "SELECT count(*) FROM mdm.addresses WHERE organization_id = :o "
        "AND deleted_at IS NULL"), {"o": ACCOUNT_ID}).scalar()
    assert aantal == 0


def test_the_address_form_has_the_shape_of_the_member_screen(client, db_session):
    """Vier kolommen, straat over twee, postcode als dropdown over de volle breedte.

    Een vastgelegde UI-beslissing (CLAUDE.md), overgenomen en niet opnieuw bedacht.
    """
    _operator(client, db_session)
    html = client.get(f"/admin/organisaties/{ACCOUNT_ID}").text

    assert "grid-cols-4" in html
    assert 'name="postal_code"' in html and "<select" in html
    assert 'name="street"' in html and "col-span-2" in html
