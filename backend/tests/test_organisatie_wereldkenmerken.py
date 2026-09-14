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

from app.domains.mdm.api import Address, Organization, Person, PostalCode
from app.kernel.tenant_config import (set_setting, tenant_display_name,
                                      tenant_payment_beneficiary,
                                      tenant_payment_iban)

TENANT = 1


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
    organisatie.payment_iban = "BE68 5390 0754 7034"
    organisatie.payment_beneficiary = "Raak Millegem"
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
    organisatie.payment_iban = "BE11 1111 1111 1111"
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

    organisatie.payment_iban = None
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


def test_an_explicit_display_name_still_wins(db_session):
    """De merknaam mag de juridische naam overrulen — Koens eigen voorbehoud."""
    tweede = Organization(org_type="UNIT", code="derde-afdeling",
                          name="Raak Derdegem", legal_form="FEITELIJKE_VERENIGING")
    db_session.add(tweede)
    db_session.commit()
    set_setting(db_session, "display_name", "Derdegem Beweegt", tenant_id=tweede.id)

    assert tenant_display_name(db_session, tweede.id) == "Derdegem Beweegt"


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
