"""#945: identificaties, rekeningen en links zijn lijsten, geen kolommen.

De vorm komt van UBL 2.1 / EN 16931. Wat hier getoetst wordt is niet dat de
tabellen bestaan — dat ziet de migratie zelf — maar de vier eigenschappen waarom
ze bestaan: een tweede geval is een rij, de eerste van meerdere wordt gekozen, een
vijfde netwerk raakt geen schema, en de persoonskant merkt er niets van.

Die laatste is de belangrijkste van dit issue. `contact_details` draagt sinds #945
zowel persoons- als organisatierijen, en de gevaarlijke fout is niet dat de nieuwe
rijen ontbreken maar dat ze in een bestaand antwoord opduiken.
"""
from __future__ import annotations

import pytest

from app.domains.mdm.api import (BankAccount, ContactDetail,
                                 OrganizationIdentification, Organization,
                                 Person, PostalCode)
from app.kernel.tenant_config import _actieve_tenant

pytestmark = pytest.mark.ui_agnostisch

TENANT = None  # gezet door de fixture; de UNIT, niet het ACCOUNT


@pytest.fixture
def organisatie(db_session):
    global TENANT
    TENANT = _actieve_tenant(None)
    return (db_session.query(Organization)
            .filter(Organization.id == TENANT)
            .execution_options(include_all_tenants=True).one())


def _contact(db_session, organisatie, code: str, waarde: str) -> ContactDetail:
    rij = ContactDetail(tenant_id=organisatie.id, organization_id=organisatie.id,
                        contact_type_code=code, value=waarde)
    db_session.add(rij)
    return rij


# ── 1. Het tweede geval is een rij ──────────────────────────────────────────

def test_two_vat_numbers_in_two_countries_are_two_rows(db_session, organisatie):
    """Koens eigen geval: *"op termijn kan één organisatie meerdere btw-nummers
    in verschillende landen hebben."*

    In de oude vorm was dat een kolom `vat_number_nl` en dus een migratie. UBL
    hangt aan `cac:PartyTaxScheme` een eigen registratieland, en dat is precies
    waarom dit een rij kan zijn.
    """
    db_session.add_all([
        OrganizationIdentification(organization_id=organisatie.id, scheme="VAT",
                                   value="BE0123456789", country="BE"),
        OrganizationIdentification(organization_id=organisatie.id, scheme="VAT",
                                   value="NL123456789B01", country="NL"),
    ])
    db_session.commit()

    rijen = (db_session.query(OrganizationIdentification)
             .filter(OrganizationIdentification.organization_id == organisatie.id,
                     OrganizationIdentification.scheme == "VAT")
             .execution_options(include_all_tenants=True).all())
    assert {(r.value, r.country) for r in rijen} == {
        ("BE0123456789", "BE"), ("NL123456789B01", "NL")}


def test_the_scheme_must_exist_in_the_code_list(db_session, organisatie):
    """De tegenproef bij de vorige: het schema is geen vrij tekstveld.

    Zonder deze foreign key zou een tikfout een identificatie opleveren die
    nergens een label heeft, en dan staat er straks een lege cel op het scherm.
    """
    from sqlalchemy.exc import IntegrityError

    db_session.add(OrganizationIdentification(
        organization_id=organisatie.id, scheme="VERZONNEN", value="X"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── 2. Twee rekeningen, en de footer kiest ──────────────────────────────────

def test_a_second_bank_account_is_a_row_and_the_first_one_is_shown(
        db_session, organisatie, client):
    """Een vzw met een aparte rekening per werking is niets bijzonders.

    `sort_order` beslist welke er getoond wordt; zonder die keuze zou de footer
    de rekening tonen die toevallig als eerste is aangemaakt.
    """
    db_session.add_all([
        BankAccount(organization_id=organisatie.id, iban="BE22 2222 2222 2222",
                    sort_order=1),
        BankAccount(organization_id=organisatie.id, iban="BE11 1111 1111 1111",
                    sort_order=0),
    ])
    db_session.commit()

    html = client.get("/aanmelden").text
    assert "BE11 1111 1111 1111" in html
    assert "BE22 2222 2222 2222" not in html, (
        "de footer hoort één rekening te tonen, en de eerste volgens sort_order")


def test_the_payment_instructions_follow_the_same_first_account(
        db_session, organisatie):
    """Dezelfde keuze, langs de andere lezer.

    Zouden footer en overschrijvingsinstructie elk hun eigen "eerste" kiezen, dan
    krijgt iemand een ander nummer te zien dan waarop hij moet betalen.
    """
    from app.kernel.tenant_config import tenant_payment_iban

    db_session.add_all([
        BankAccount(organization_id=organisatie.id, iban="BE22 2222 2222 2222",
                    sort_order=1),
        BankAccount(organization_id=organisatie.id, iban="BE11 1111 1111 1111",
                    sort_order=0),
    ])
    db_session.commit()

    assert tenant_payment_iban(db_session, organisatie.id) == "BE11 1111 1111 1111"


# ── 3. Een vijfde netwerk raakt geen schema ─────────────────────────────────

def test_a_fifth_network_is_only_a_row_in_the_code_list(db_session, organisatie,
                                                        client):
    """De belofte van dit issue, letterlijk getoetst.

    Er wordt hier géén kolom toegevoegd, géén migratie gedraaid en géén
    sjabloonregel geschreven: één rij in `contact_type_codes` en één in
    `contact_details`. Verschijnt de link dan in de footer, dan is de vorm goed.

    #1160 verlegde de weg zonder de belofte te breken: de rij zegt er nu bij
    dát ze een netwerk is (`is_social_network`), in plaats van dat de footer
    alles toont wat ze niet herkent. Die restcategorie zette het gsm-nummer van
    de vereniging tussen de iconen.
    """
    from app.domains.mdm.api import ContactTypeCode

    db_session.add(ContactTypeCode(code="MASTODON", language="nl",
                                   value="Mastodon", is_social_network=True))
    db_session.flush()
    _contact(db_session, organisatie, "MASTODON", "https://mastodon.example/@raak")
    db_session.commit()

    html = client.get("/aanmelden").text
    assert "https://mastodon.example/@raak" in html


def test_email_and_phone_do_not_end_up_between_the_icons(db_session, organisatie,
                                                         client):
    """De tegenproef: niet élk contactgegeven is een sociale link.

    Zonder deze grens zou het e-mailadres als icoonlink in de rij verschijnen —
    de lijst wordt immers uit dezelfde tabel opgebouwd.
    """
    from app.ui import _sociale_links

    _contact(db_session, organisatie, "EMAIL", "bestuur@example.com")
    _contact(db_session, organisatie, "PHONE", "014 00 00 00")
    _contact(db_session, organisatie, "WEBSITE", "https://example.com")
    db_session.commit()

    codes = {link["code"] for link in _sociale_links(db_session, organisatie)}
    assert codes == set(), (
        "e-mail, telefoon en website horen in het contactblok, niet tussen de iconen")


# ── 4. De persoonskant merkt er niets van (de belangrijkste) ────────────────

def test_a_person_only_sees_their_own_contact_details(db_session, organisatie):
    """De belangrijkste test van #945.

    De tabel draagt nu twee soorten eigenaars. Het gevaar is niet dat de
    organisatierij ontbreekt maar dat ze opduikt in een antwoord over een persoon
    — en dan klopt het scherm nog steeds, met het verkeerde nummer erin.
    """
    persoon = Person(first_name="Test", last_name="Persoon")
    db_session.add(persoon)
    db_session.flush()
    db_session.add(ContactDetail(tenant_id=organisatie.id, person_id=persoon.id,
                                 contact_type_code="EMAIL",
                                 value="persoon@example.com"))
    _contact(db_session, organisatie, "EMAIL", "bestuur@example.com")
    db_session.commit()
    db_session.refresh(persoon)

    waarden = {c.value for c in persoon.contact_details}
    assert waarden == {"persoon@example.com"}, (
        "de organisatierij hoort niet in de contactgegevens van een persoon te zitten")


def test_a_row_cannot_belong_to_both_at_once(db_session, organisatie):
    """De XOR die de containment draagt, en ze moet rood kunnen.

    Alle bestaande lezers zoeken op `person_id`. Dat ze de organisatierijen niet
    zien, geldt alleen zolang géén rij allebei draagt — anders duikt de
    organisatie op in het antwoord over een persoon.

    **Kapotgemaakt om te toetsen:** een rij met beide kolommen gevuld. De CHECK
    weigert hem; zonder die CHECK zou hij er gewoon in gaan.
    """
    from sqlalchemy.exc import IntegrityError

    persoon = Person(first_name="Test", last_name="Persoon")
    db_session.add(persoon)
    db_session.flush()
    db_session.add(ContactDetail(tenant_id=organisatie.id, person_id=persoon.id,
                                 organization_id=organisatie.id,
                                 contact_type_code="EMAIL", value="beide@example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # En de andere kant: een rij zonder eigenaar is evengoed geweigerd.
    db_session.add(ContactDetail(tenant_id=organisatie.id,
                                 contact_type_code="EMAIL", value="wees@example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_audit_lookup_ignores_the_organisation_row(db_session, organisatie):
    """Het gevaar dat dit issue zelf maakte, vastgelegd.

    `_person_by_email` zocht op waarde + type EMAIL zonder `person_id`-voorwaarde,
    met een `.first()` zonder ordening. Deelt de organisatie haar adres met een
    persoon — een bestuurslid dat de gedeelde mailbox gebruikt — dan kon die
    `.first()` de organisatierij pakken en `None` teruggeven: de auditregel
    verliest stil haar onderwerp.

    **Kapotgemaakt om te toetsen:** de voorwaarde `person_id IS NOT NULL` uit
    `changes.py` weggehaald. Deze test faalt dan met `None`, want de
    organisatierij wordt als eerste aangemaakt en komt dus eerst.
    """
    from app.domains.audit.changes import _SubjectResolver

    _contact(db_session, organisatie, "EMAIL", "gedeeld@example.com")
    db_session.flush()
    persoon = Person(first_name="Bestuurs", last_name="Lid")
    db_session.add(persoon)
    db_session.flush()
    db_session.add(ContactDetail(tenant_id=organisatie.id, person_id=persoon.id,
                                 contact_type_code="EMAIL",
                                 value="gedeeld@example.com"))
    db_session.commit()

    gevonden = _SubjectResolver(db_session)._person_by_email("gedeeld@example.com")
    assert gevonden == persoon.id, (
        "de auditregel hoort de persoon te vinden, niet de organisatierij")


# ── 5. De tenant-naad, expliciet ────────────────────────────────────────────

def test_an_organisation_row_is_invisible_under_the_tenant_filter(db_session,
                                                                  organisatie):
    """`tenant_id` is op een organisatierij niet de scope — vastgelegd (#945).

    De kolom is NOT NULL en krijgt de eigenaar mee omdat er geen betere waarde
    bestaat. Wie ooit RLS aanzet schrijft een policy op `tenant_id` en mis-scoopt
    deze rijen stil; deze test maakt het gedrag opzettelijk in plaats van
    toevallig.

    Getoetst met de ACCOUNT-organisatie: die is géén tenant, dus haar rijen mogen
    onder de gewone filter nooit opduiken.
    """
    from app.kernel.tenancy import current_tenant_id

    account = (db_session.query(Organization)
               .filter(Organization.org_type == "ACCOUNT")
               .execution_options(include_all_tenants=True).first())
    assert account is not None and account.id != organisatie.id
    db_session.add(ContactDetail(tenant_id=account.id, organization_id=account.id,
                                 contact_type_code="EMAIL",
                                 value="account@example.com"))
    db_session.commit()

    token = current_tenant_id.set(organisatie.id)
    try:
        zonder = (db_session.query(ContactDetail)
                  .filter(ContactDetail.value == "account@example.com").all())
        met = (db_session.query(ContactDetail)
               .filter(ContactDetail.value == "account@example.com")
               .execution_options(include_all_tenants=True).all())
    finally:
        current_tenant_id.reset(token)

    assert zonder == [], (
        "zonder include_all_tenants hoort een organisatierij van een ándere "
        "organisatie onzichtbaar te zijn")
    assert len(met) == 1, (
        "en mét die optie hoort ze er wél te zijn — anders toetst de regel "
        "hierboven alleen dat de rij nergens bestaat")


# ── 6. De telling in de migratie kan rood worden ────────────────────────────

def test_the_migration_count_refuses_a_silent_zero():
    """De vangnetvorm van #945, en ze moet rood kunnen.

    De migratie kopieert en dropt in één transactie, met een telling ertussen. Die
    telling is het enige wat een stille nuloperatie tegenhoudt — migratie 121
    meldde "0 pagina's ontdubbeld" en niemand keek. Postgres rolt bij een fout de
    hele migratie terug, dus de kolommen blijven staan.

    **Kapotgemaakt om te toetsen:** een bind die voor elke "oude" telling 1
    teruggeeft en voor elke "nieuwe" telling 0 — precies het geval waarin de
    kopie niets deed en de drops toch zouden volgen.
    """
    import importlib.util
    from pathlib import Path

    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "124_organization_lists.py")
    spec = importlib.util.spec_from_file_location("migratie_124", pad)
    migratie = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migratie)

    class _Resultaat:
        def __init__(self, waarde):
            self._waarde = waarde

        def scalar(self):
            return self._waarde

    class _StilleBind:
        """Oude waarden: 1. Nieuwe rijen: 0. De kopie deed dus niets."""

        def execute(self, statement, params=None):
            sql = str(statement)
            oud = "FROM mdm.organizations" in sql
            return _Resultaat(1 if oud else 0)

    with pytest.raises(RuntimeError) as fout:
        migratie._controleer(_StilleBind())
    assert "er wordt niets gedropt" in str(fout.value)

    class _GoedeBind:
        def execute(self, statement, params=None):
            return _Resultaat(1)

    # De tegenproef: klopt de telling, dan laat ze door. Zonder deze helft zou de
    # test ook slagen bij een controle die altijd weigert.
    migratie._controleer(_GoedeBind())


# ── 7. Het scherm bewerkt nog steeds één van elk ────────────────────────────

def test_the_screen_round_trips_through_three_tables(db_session, organisatie):
    """Elf invoervelden, drie tabellen, één plat woordenboek.

    Het scherm hoeft niet te weten welke tabel welk veld draagt — maar wat erin
    gaat moet er ook weer uitkomen, anders staat een penningmeester te kijken naar
    een leeg veld dat hij net ingevuld heeft.
    """
    from app.domains.mdm.api import (organization_details,
                                     update_organization_details)

    update_organization_details(db_session, organisatie.id, {
        "legal_form": "VZW",
        "enterprise_number": " 0123.456.789 ",
        "vat_number": "BE0123456789",
        "email": "bestuur@example.com",
        "phone": "014 00 00 00",
        "website": "https://example.com",
        "facebook_url": "https://facebook.com/raak",
        "instagram_url": "",
        "tiktok_url": "",
        "payment_iban": " BE68 5390 0754 7034 ",
        "payment_beneficiary": "Raak Voorbeeld",
        "payment_bic": "GKCCBEBB",
    })

    uit = organization_details(db_session, organisatie.id)
    assert uit["legal_form"] == "VZW"
    assert uit["enterprise_number"] == "0123.456.789", "en getrimd"
    assert uit["vat_number"] == "BE0123456789"
    assert uit["email"] == "bestuur@example.com"
    assert uit["payment_iban"] == "BE68 5390 0754 7034", "en getrimd"
    assert uit["payment_bic"] == "GKCCBEBB"
    assert uit["instagram_url"] == ""


def test_clearing_a_field_removes_the_row(db_session, organisatie):
    """Leeg betekent "er is er geen", en dan hoort de rij weg te zijn.

    Een rij met een lege waarde is een derde toestand die nergens iets betekent en
    die een volgende lezer als "ingevuld" telt.
    """
    from app.domains.mdm.api import (organization_details,
                                     update_organization_details)

    update_organization_details(db_session, organisatie.id,
                                {"email": "bestuur@example.com"})
    update_organization_details(db_session, organisatie.id, {"email": ""})

    assert organization_details(db_session, organisatie.id)["email"] == ""
    rijen = (db_session.query(ContactDetail)
             .filter(ContactDetail.organization_id == organisatie.id,
                     ContactDetail.contact_type_code == "EMAIL")
             .execution_options(include_all_tenants=True).all())
    assert rijen == [], "een leeg veld hoort geen lege rij achter te laten"
