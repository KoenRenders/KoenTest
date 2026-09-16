"""Een organisatie is ook iets in de wereld, niet alleen een rol (#924).

Koen: *"als ik platform negeer, zijn zowel de account als de units eigenlijk
organisaties."* Raak vzw is een vzw die andere organisaties bezit; Raak Millegem is
een feitelijke vereniging die een site heeft. Eén ding met twee assen — **wat het
is** en **welke rol het speelt** — en alleen die tweede bestond.

**De belangrijkste test van dit issue is niet de nieuwe functionaliteit** maar dat
de bestaande ledenschermen onveranderd werken: `mdm.addresses` gaf zijn NOT NULL op
`person_id` af, en dat is de tabel die elk ledenscherm leest.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.mdm.api import (Address, BankAccount, Organization, Person,
                                 PostalCode)
from app.kernel.tenant_config import (_actieve_tenant, set_setting,
                                      tenant_display_name,
                                      tenant_payment_beneficiary,
                                      tenant_payment_iban)

# De tenant die de applicatie werkelijk gebruikt, en niet 1. De seed zet vier
# organisaties neer: 1 is het ACCOUNT ("Raak"), 2 is de UNIT "Raak Millegem" — en
# dát is de tenant. Mijn eerste versie van dit bestand toetste op 1 en slaagde,
# omdat elke aanroep dezelfde verkeerde rij meekreeg: het mechanisme klopte, de rij
# niet. Zichtbaar geworden toen de footer (die zelf resolveert) een waarde op 1
# niet zag.
TENANT = _actieve_tenant(None)


@pytest.fixture
def organisatie(db_session):
    return (db_session.query(Organization)
            .filter(Organization.id == TENANT)
            .execution_options(include_all_tenants=True).one())


@pytest.fixture
def postcode(db_session):
    """De testdatabank draagt geen postcodes; een adres heeft er één nodig."""
    bestaande = db_session.query(PostalCode).first()
    if bestaande:
        return bestaande
    rij = PostalCode(postal_code="2400", municipality="Mol")
    db_session.add(rij)
    db_session.flush()
    return rij


# ── 1. De betaalinstructies komen uit de organisatie ────────────────────────

def test_the_payment_details_come_from_the_organisation(db_session, organisatie):
    # #945: de rekening is een eigen rij geworden (UBL `cac:PayeeFinancialAccount`).
    db_session.add(BankAccount(organization_id=organisatie.id,
                               iban="BE68 5390 0754 7034",
                               beneficiary="Raak Millegem"))
    db_session.commit()

    assert tenant_payment_iban(db_session, TENANT) == "BE68 5390 0754 7034"
    assert tenant_payment_beneficiary(db_session, TENANT) == "Raak Millegem"


def test_the_tenant_setting_no_longer_exists_as_a_source(db_session, organisatie):
    """De andere helft, en zonder haar bewijst de eerste niets.

    "Verhuisd" en "gekopieerd" zien er in de uitvoer identiek uit: allebei geven ze
    het juiste nummer terug. Het verschil is of de oude bron nog meespeelt — dus
    wordt er hier eentje gezet die van de organisatie verschilt. Wint die, dan is
    het veld verplaatst in plaats van weggenomen.
    """
    db_session.add(BankAccount(organization_id=organisatie.id,
                               iban="BE11 1111 1111 1111"))
    db_session.commit()
    set_setting(db_session, "payment_iban", "BE99 9999 9999 9999", tenant_id=TENANT)

    assert tenant_payment_iban(db_session, TENANT) == "BE11 1111 1111 1111", (
        "de tenant-instelling hoort niet meer mee te spelen; doet ze dat wel, dan "
        "is het veld op twee plaatsen bewerkbaar")


def test_the_setting_is_gone_from_the_settings_screen():
    """Blijft het veld op het scherm staan, dan is er een tweede bron gebouwd."""
    from app.ui.tenants_ui import BEKENDE_SLEUTELS

    sleutels = {sleutel for sleutel, _label, _hulp in BEKENDE_SLEUTELS}
    assert "payment_iban" not in sleutels
    assert "payment_beneficiary" not in sleutels
    # En de instellingen die er wél horen, staan er nog — anders toetst de regel
    # hierboven alleen dat de lijst leeg is.
    assert {"mail_mode", "language", "privacy_url"} <= sleutels


def test_the_env_stays_the_safety_net(db_session, organisatie):
    """Een organisatie zonder rekeningnummer valt terug op `.env`."""
    from app.config import settings

    db_session.query(BankAccount).filter(
        BankAccount.organization_id == organisatie.id).delete()
    db_session.commit()
    assert tenant_payment_iban(db_session, TENANT) == settings.payment_iban


# ── 2. Een adres hangt aan een persoon OF aan een organisatie ───────────────

def test_an_address_can_belong_to_an_organisation(db_session, organisatie,
                                                  postcode):
    """Het goede geval: een adres zonder persoon eronder."""
    adres = Address(tenant_id=TENANT, organization_id=organisatie.id,
                    street="Kerkstraat", house_number="1",
                    postal_code_id=postcode.id)
    db_session.add(adres)
    db_session.commit()
    assert adres.id and adres.person_id is None


def test_an_address_with_both_owners_is_refused(db_session, organisatie,
                                                postcode):
    """De XOR-regel, bewaakt door de DATABANK en niet door de code.

    Eigen test per richting, want een regel die maar één kant afdekt laat precies
    de andere door — en beide richtingen in één test betekent dat de eerste
    terugrol de tweede onmogelijk maakt.
    """
    persoon = Person(tenant_id=TENANT, first_name="Test", last_name="Persoon")
    db_session.add(persoon)
    db_session.flush()
    db_session.add(Address(tenant_id=TENANT, person_id=persoon.id,
                           organization_id=organisatie.id, street="Fout",
                           house_number="1", postal_code_id=postcode.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_an_address_without_an_owner_is_refused(db_session, postcode):
    """De andere kant: een adres dat nergens aan hangt."""
    db_session.add(Address(tenant_id=TENANT, person_id=None,
                           organization_id=None, street="Fout",
                           house_number="1", postal_code_id=postcode.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_live_address_per_organisation(db_session, organisatie, postcode):
    """Dezelfde partiële uniciteit als voor een persoon (migratie 053)."""
    pc = postcode
    db_session.add(Address(tenant_id=TENANT, organization_id=organisatie.id,
                           street="Kerkstraat", house_number="1",
                           postal_code_id=pc.id))
    db_session.commit()
    db_session.add(Address(tenant_id=TENANT, organization_id=organisatie.id,
                           street="Tweede straat", house_number="2",
                           postal_code_id=pc.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── 3. De bestaande ledenschermen zijn onveranderd ──────────────────────────

def test_a_person_address_still_works_exactly_as_before(db_session, postcode):
    """De belangrijkste test van dit issue.

    `person_id` gaf zijn NOT NULL af, en dat is de kolom waar élk ledenscherm op
    zoekt. Een adres aan een persoon hoort te werken alsof er niets veranderd is —
    en een query op `person_id` hoort de organisatierijen níét te zien.
    """
    pc = postcode
    persoon = Person(tenant_id=TENANT, first_name="Anna", last_name="Test")
    db_session.add(persoon)
    db_session.flush()
    db_session.add(Address(tenant_id=TENANT, person_id=persoon.id,
                           street="Dorpsstraat", house_number="5",
                           postal_code_id=pc.id))
    organisatie = (db_session.query(Organization)
                   .filter(Organization.id == TENANT)
                   .execution_options(include_all_tenants=True).one())
    db_session.add(Address(tenant_id=TENANT, organization_id=organisatie.id,
                           street="Kerkstraat", house_number="1",
                           postal_code_id=pc.id))
    db_session.commit()

    van_de_persoon = (db_session.query(Address)
                      .filter(Address.person_id == persoon.id).all())
    assert len(van_de_persoon) == 1
    assert van_de_persoon[0].street == "Dorpsstraat"

    # En de organisatierij komt in geen enkele persoonsquery voor.
    alle_persoonsadressen = (db_session.query(Address)
                             .filter(Address.person_id.isnot(None)).all())
    assert all(a.organization_id is None for a in alle_persoonsadressen)


def test_the_members_screen_still_renders(client, db_session):
    """Niet alleen het model: het scherm dat erop staat."""
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from tests.test_reporting_panel_ui import login

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    antwoord = client.get("/admin/leden")
    assert antwoord.status_code == 200


# ── 4. De naam komt uit de organisatie ──────────────────────────────────────

def test_a_tenant_without_its_own_name_is_not_called_raak_millegem(db_session):
    """De losstaande bug die meekwam (#924).

    De terugval was de letterlijke string "Raak Millegem", dus élke tenant zonder
    eigen `display_name` heette zo — in zijn paginatitel, zijn mails, zijn
    afzender. Zelfde soort lek als het hardgecodeerde "— Raak Millegem" in #881.
    """
    tweede = Organization(org_type="UNIT", code="tweede-afdeling",
                          name="Raak Testgem", legal_form="FEITELIJKE_VERENIGING")
    db_session.add(tweede)
    db_session.commit()

    assert tenant_display_name(db_session, tweede.id) == "Raak Testgem", (
        "een tenant zonder eigen naam hoort zijn organisatienaam te dragen, niet "
        "die van een andere afdeling")


def test_no_setting_overrules_the_organisation_name(db_session):
    """Omgedraaid door #945, en dat is de hele wijziging.

    Tot #945 won een `display_name`-instelling van de organisatienaam. Die
    overrule bestond dus al terwijl niemand erom gevraagd had — twee plaatsen voor
    één feit, met de bekende afloop. Koen op 14 september: *"laten we gaan voor de
    naam die we in organisatie hebben."*

    De instelling wordt hier alsnog gezet, want anders toetst deze test alleen dat
    er niets staat. Wint ze, dan is de tweede bron er nog.
    """
    tweede = Organization(org_type="UNIT", code="derde-afdeling",
                          name="Raak Derdegem", legal_form="FEITELIJKE_VERENIGING")
    db_session.add(tweede)
    db_session.commit()
    set_setting(db_session, "display_name", "Derdegem Beweegt", tenant_id=tweede.id)

    assert tenant_display_name(db_session, tweede.id) == "Raak Derdegem", (
        "de instelling hoort niet meer mee te spelen; doet ze dat wel, dan is de "
        "naam op twee plaatsen bewerkbaar")


# ── 5. De rechtsvorm ────────────────────────────────────────────────────────

def test_the_legal_form_is_set_by_role_and_not_guessed_by_name(db_session):
    """ACCOUNT is de vzw die de afdelingen bezit, UNIT is een afdeling.

    Op naam raden zou bij de tweede afdeling meteen fout zitten. En PLATFORM
    krijgt niets: het platform is geen vereniging, en een verzonnen rechtsvorm is
    erger dan een lege kolom.
    """
    rijen = db_session.execute(text(
        "SELECT org_type, legal_form FROM mdm.organizations "
        "WHERE deleted_at IS NULL")).all()
    per_rol = {rol: vorm for rol, vorm in rijen}
    assert per_rol.get("UNIT") == "FEITELIJKE_VERENIGING"
    if "ACCOUNT" in per_rol:
        assert per_rol["ACCOUNT"] == "VZW"
    if "PLATFORM" in per_rol:
        assert per_rol["PLATFORM"] is None


def test_the_legal_form_code_list_follows_the_779_pattern(db_session):
    """Code in de databank, label per taal op één plek."""
    codes = {rij[0] for rij in db_session.execute(text(
        "SELECT DISTINCT code FROM mdm.legal_form_codes"))}
    assert codes == {"VZW", "FEITELIJKE_VERENIGING", "BEDRIJF"}
    talen = {rij[0] for rij in db_session.execute(text(
        "SELECT DISTINCT language FROM mdm.legal_form_codes"))}
    assert {"nl", "en"} <= talen


def test_org_type_is_untouched(db_session):
    """Uitdrukkelijk buiten scope: de rol-as blijft zoals ze was.

    Rechtsvorm en adres toevoegen is neutraal; een nieuwe toets op `org_type` is
    dat niet, en zou de latere samenvoeging van account-én-tenant moeilijker maken.
    """
    soorten = {rij[0] for rij in db_session.execute(text(
        "SELECT DISTINCT org_type FROM mdm.organizations"))}
    assert soorten <= {"ACCOUNT", "UNIT", "PLATFORM"}


# ── 6. De velden zijn ergens te bewerken ────────────────────────────────────

def test_the_organisation_fields_have_a_screen(client, db_session):
    """De fout die ik zelf maakte, en die erger was dan wat ze verving.

    Bij de eerste twee omschakelingen verdwenen IBAN, begunstigde en de sociale
    links uit `/admin/tenants` — en er kwam niets voor in de plaats. Een
    penningmeester kon het rekeningnummer daarna langs geen enkele weg wijzigen.
    Dubbel is verwarrend; onbereikbaar is stuk.

    **Sinds #971 staan ze op `/admin/organisaties` en NIET meer op
    `/admin/tenants`.** Die tweede helft hoort in dezelfde test: verhuisd en
    gekopieerd zien er in de uitvoer identiek uit zolang je alleen kijkt of het veld
    érgens staat. Zonder de tegenproef zou dit groen blijven bij twee schermen voor
    één feit — precies de duplicatie die #924 en #945 uit de kolommen haalden.

    De reden dat ze ooit op het tenantscherm stonden was juist: er was geen ander.
    De reden dat ze daar weg zijn is even eenvoudig: dat scherm bestaat alleen voor
    organisaties die een site draaien, en de rechtspersoon draait er geen.
    """
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from tests.test_reporting_panel_ui import login

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))
    velden = ("payment_iban", "payment_beneficiary", "legal_form",
              "facebook_url", "email")

    organisatie = client.get(f"/admin/organisaties/{TENANT}").text
    for veld in velden:
        assert f'name="{veld}"' in organisatie, f"{veld} is nergens te bewerken"

    tenant = client.get(f"/admin/tenants/{TENANT}").text
    for veld in velden:
        assert f'name="{veld}"' not in tenant, (
            f"{veld} staat nog op het tenantscherm — dan is het gekopieerd en niet "
            "verhuisd, en zijn er twee plaatsen voor één feit")


def test_saving_the_screen_writes_to_the_organisation(client, db_session,
                                                      organisatie):
    """En het slaat op in de organisatie, niet in de instellingen."""
    from app.domains.mdm.api import update_organization_details

    update_organization_details(db_session, TENANT, {
        "payment_iban": " BE68 5390 0754 7034 ", "payment_beneficiary": "",
        "legal_form": "VZW"})
    db_session.refresh(organisatie)

    rekening = (db_session.query(BankAccount)
                .filter(BankAccount.organization_id == TENANT)
                .execution_options(include_all_tenants=True).one())
    assert rekening.iban == "BE68 5390 0754 7034", "en getrimd"
    assert rekening.beneficiary is None, (
        "leeg wordt None en niet de lege string, anders betekent 'leeg' twee "
        "dingen en valt de lezer niet terug op .env")
    assert organisatie.legal_form == "VZW"


def test_an_unknown_legal_form_is_not_stored(db_session, organisatie):
    """Een code zonder label levert straks een lege cel op."""
    from app.domains.mdm.api import update_organization_details

    organisatie.legal_form = "VZW"
    db_session.commit()
    update_organization_details(db_session, TENANT, {"legal_form": "VERZONNEN"})
    db_session.refresh(organisatie)
    assert organisatie.legal_form == "VZW"
