"""De footer leest de organisatie (#924).

Tweede van de drie omschakelingen. De sociale links verhuizen mee — een
Facebook-pagina van een vereniging bestaat ook als ze geen site heeft, en dat is de
beslisregel uit het issue.

Since #1588 (CR-11 pilot B) the organisation's details stand ONCE, in the
footer's legal line (`data-legal="address|email|phone|iban"`), and the free CMS
block `site-footer` is no longer rendered. The block is not cleaned up: a
migration cannot tell an address block from a sentence someone wrote, so it stays
as data.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.api import (
    CONTACT,
    Address,
    BankAccount,
    ContactDetail,
    Organization,
    PostalCode,
)
from app.kernel.tenant_config import _actieve_tenant

TENANT = _actieve_tenant(None)


@pytest.fixture
def organisatie(db_session):
    return (
        db_session.query(Organization)
        .filter(Organization.id == TENANT)
        .execution_options(include_all_tenants=True)
        .one()
    )


def _contact(db_session, organisatie, code: str, waarde: str) -> None:
    """Eén contactgegeven van de organisatie (#945).

    `tenant_id` krijgt de eigenaar mee omdat de kolom NOT NULL is; hij is hier
    niet de scope — zie de docstring van `ContactDetail`.
    """
    db_session.add(
        ContactDetail(
            tenant_id=TENANT, organization_id=organisatie.id, contact_type_code=code, value=waarde
        )
    )


@pytest.fixture
def met_adres(db_session, organisatie):
    pc = db_session.query(PostalCode).first()
    if pc is None:
        pc = PostalCode(postal_code="2400", municipality="Mol")
        db_session.add(pc)
        db_session.flush()
    # Sinds #945 zijn contact en rekening rijen en geen kolommen.
    _contact(db_session, organisatie, "EMAIL", "bestuur@example.com")
    _contact(db_session, organisatie, "PHONE", "014 00 00 00")
    db_session.add(BankAccount(organization_id=organisatie.id, iban="BE68 5390 0754 7034"))
    db_session.add(
        Address(
            tenant_id=TENANT,
            organization_id=organisatie.id,
            street="Kerkstraat",
            house_number="12",
            bus_number="3",
            postal_code_id=pc.id,
        )
    )
    db_session.commit()
    return organisatie


def test_the_footer_shows_the_organisation_block(client, db_session, met_adres):
    html = client.get("/aanmelden").text
    assert "Kerkstraat 12 bus 3" in html
    assert "2400 Mol" in html
    assert "bestuur@example.com" in html
    assert "014 00 00 00" in html
    assert "BE68 5390 0754 7034" in html
    # #1588: each detail stands once, in the legal line — the separate centred
    # organisation block is gone.
    assert html.count("Kerkstraat 12 bus 3") == 1
    assert html.count("BE68 5390 0754 7034") == 1
    line = html[html.index("data-footer-line") : html.index("</footer>")]
    for kind in ("address", "email", "phone", "iban"):
        assert line.count(f'data-legal="{kind}"') == 1, kind
    assert html.count("data-legal=") == 4


def test_the_free_footer_block_is_no_longer_rendered(client, db_session, met_adres):
    """#1588 (CR-11 pilot B) stopped rendering the free CMS block `site-footer`:
    the organisation's details stand in the legal line, from one source. The
    block stays as data — nothing is deleted, so what the tenant wrote can
    still be read and moved in the back office.
    """
    from app.domains.cms.api import CmsPage

    pagina = db_session.query(CmsPage).filter(CmsPage.slug == "site-footer").one_or_none()
    if pagina is None:
        pagina = CmsPage(
            tenant_id=TENANT,
            slug="site-footer",
            title="Footer",
            is_published=True,
            show_in_nav=False,
        )
        db_session.add(pagina)
    pagina.content = "Elke woensdag open vanaf 19u."
    pagina.is_published = True
    db_session.commit()

    html = client.get("/aanmelden").text
    assert "Elke woensdag open vanaf 19u." not in html, (
        "the free footer block is rendered again; since #1588 the footer shows "
        "the organisation's details from the entity only"
    )
    footer = html[html.index("<footer") : html.index("</footer>")]
    assert '<span data-legal="address">Kerkstraat 12 bus 3, 2400 Mol</span>' in footer
    db_session.expire_all()
    kept = db_session.query(CmsPage).filter(CmsPage.slug == "site-footer").one()
    assert kept.content == "Elke woensdag open vanaf 19u.", "the block stays as data"


def test_an_empty_organisation_renders_no_block(client, db_session, organisatie):
    """Een blok met alleen een naam erin ziet eruit als een renderfout.

    De footer draagt onderaan al de naam van de site, dus een tweede kale naam
    voegt niets toe en roept de vraag op wat er mis is.
    """
    db_session.query(ContactDetail).filter(ContactDetail.organization_id == organisatie.id).delete()
    db_session.query(BankAccount).filter(BankAccount.organization_id == organisatie.id).delete()
    db_session.query(Address).filter(Address.organization_id == organisatie.id).delete()
    db_session.commit()

    html = client.get("/aanmelden").text
    assert "Kerkstraat" not in html


def test_the_social_links_come_from_the_organisation(client, db_session, organisatie):
    _contact(db_session, organisatie, "INSTAGRAM", "https://instagram.com/raakvoorbeeld")
    db_session.commit()
    assert 'aria-label="Instagram"' in client.get("/aanmelden").text


def test_the_social_settings_are_gone_from_the_screen():
    """Blijven ze op het scherm staan, dan is er een tweede bewerkbare bron."""
    from app.ui.tenants_ui import BEKENDE_SLEUTELS

    sleutels = {sleutel for sleutel, _label, _hulp in BEKENDE_SLEUTELS}
    assert not ({"facebook_url", "instagram_url", "tiktok_url"} & sleutels)
    # En de instellingen die er wél horen staan er nog — anders toetst de regel
    # hierboven alleen dat de lijst leeg is.
    assert {"base_url", "language"} <= sleutels


def test_a_tenant_setting_no_longer_wins(client, db_session, organisatie):
    """Verhuisd en gekopieerd zien er in de uitvoer identiek uit.

    Dus wordt hier een instelling gezet die van de organisatie verschilt. Wint die,
    dan is het veld op twee plaatsen bewerkbaar gebleven.
    """
    from app.kernel.tenant_config import set_setting

    db_session.query(ContactDetail).filter(
        ContactDetail.organization_id == organisatie.id,
        ContactDetail.contact_type_code == CONTACT.FACEBOOK,
    ).delete()
    db_session.commit()
    set_setting(db_session, "facebook_url", "https://facebook.com/oud", tenant_id=TENANT)
    db_session.commit()

    assert 'aria-label="Facebook"' not in client.get("/aanmelden").text, (
        "de tenant-instelling hoort niet meer mee te spelen"
    )
