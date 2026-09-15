"""De contactgegevens komen uit de organisatie (#924, derde omschakeling).

Koen na het bekijken van HDEV: de footer toonde alles dubbel — bovenaan het blok
uit de entiteit, eronder de oude CMS-tekst met dezelfde naam, hetzelfde adres,
hetzelfde rekeningnummer. En op de privacypagina staat het e-mailadres zelfs
meermaals.

**Dit is de enige stap in de reeks die bestaande tekst weghaalt.** Bij de eerste
twee stond de oude bron in een instellingenscherm; hier staat ze in een pagina die
Koen zelf geschreven heeft. Daarom toetst dit bestand vooral de kant die zegt dat
er níéts sneuvelt: een achtergebleven zin is een schoonheidsfoutje, een weggegooide
alinea niet.

De opruiming kijkt naar wat een alinea **is** en niet naar hoe vaak er iets in
staat. Een e-mailadres komt in een link twee keer voor — in `mailto:` en als
linktekst — dus tellen en vervangen breekt de link.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MIGRATIE = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
            / "121_organization_contact_block.py")


def _opruimer():
    spec = importlib.util.spec_from_file_location("m121", MIGRATIE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WAARDEN = ["Raak Voorbeeld", "bestuur@raakvoorbeeld.example", "014 00 00 00",
           "BE68 5390 0754 7034", "GKCCBEBB", "Kerkstraat 12",
           "2400 Mol", "Mol", "Kerkstraat"]


def test_a_pure_contact_paragraph_goes():
    m = _opruimer()
    inhoud = ('<p>Raak Voorbeeld</p>'
              '<p>Kerkstraat 12, 2400 Mol</p>'
              '<p>E-mail: <a href="mailto:bestuur@raakvoorbeeld.example">'
              'bestuur@raakvoorbeeld.example</a></p>')
    assert m._opgeruimd(inhoud, WAARDEN).strip() == ""


def test_a_paragraph_with_anything_else_stays():
    """De regel waar deze stap op valt of staat.

    Blijft er na het wegdenken van de contactgegevens nog tekst over, dan blijft
    de alinea staan — ook als er een adres of een e-mailadres in zit.
    """
    m = _opruimer()
    inhoud = ('<p>Je kan ons bereiken via bestuur@raakvoorbeeld.example, '
              'elke woensdag vanaf 19u.</p>')
    assert m._opgeruimd(inhoud, WAARDEN) == inhoud


def test_headings_are_never_touched():
    """Een kop met de naam erin is een titel, geen contactregel."""
    m = _opruimer()
    inhoud = "<h2>Raak Voorbeeld</h2><p>Wie zijn wij?</p>"
    assert m._opgeruimd(inhoud, WAARDEN) == inhoud


def test_the_rest_of_the_page_survives():
    """Wat een afdeling zelf schreef blijft gewoon staan en werken."""
    m = _opruimer()
    inhoud = ('<h2>Privacyverklaring</h2>'
              '<p>Wij verwerken je gegevens zorgvuldig.</p>'
              '<p>Raak Voorbeeld</p>'
              '<p>Kerkstraat 12</p>'
              '<p>Je rechten oefen je uit via een schriftelijk verzoek.</p>')
    uit = m._opgeruimd(inhoud, WAARDEN)
    assert "Wij verwerken je gegevens zorgvuldig." in uit
    assert "Je rechten oefen je uit" in uit
    assert "<h2>Privacyverklaring</h2>" in uit
    assert "Kerkstraat 12" not in uit


def test_a_mailto_link_is_not_broken_halfway():
    """Het geval waar een naïeve vervanging op stukloopt.

    Het adres staat twee keer in dezelfde link. Wie per voorkomen vervangt, houdt
    een halve link over; wie per alinea werkt, haalt de hele link weg of laat hem
    staan.
    """
    m = _opruimer()
    inhoud = ('<p>Vragen? Schrijf naar '
              '<a href="mailto:bestuur@raakvoorbeeld.example">bestuur@raakvoorbeeld.example</a> '
              'en we antwoorden binnen de week.</p>')
    uit = m._opgeruimd(inhoud, WAARDEN)
    assert uit == inhoud, "deze alinea zegt méér dan het adres, dus ze blijft"
    assert 'href="mailto:bestuur@raakvoorbeeld.example"' in uit


def test_running_it_twice_changes_nothing():
    """Idempotent: na de eerste run staan de waarden er niet meer."""
    m = _opruimer()
    inhoud = ('<p>Raak Voorbeeld</p><p>Iets wat blijft staan.</p>')
    een = m._opgeruimd(inhoud, WAARDEN)
    assert m._opgeruimd(een, WAARDEN) == een


def test_an_iban_with_and_without_spaces_both_count():
    """Een rekeningnummer wordt op twee manieren geschreven."""
    m = _opruimer()
    assert m._opgeruimd("<p>BE68539007547034</p>", WAARDEN).strip() == ""
    assert m._opgeruimd("<p>BE68 5390 0754 7034</p>", WAARDEN).strip() == ""


def test_nothing_is_removed_without_values():
    """Een organisatie zonder gegevens ruimt niets op.

    Anders zou een lege organisatie een pagina kunnen leegvegen — precies de fout
    die bij deze stap het duurst is.
    """
    m = _opruimer()
    inhoud = "<p>Raak Voorbeeld</p><p>Kerkstraat 12</p>"
    assert m._opgeruimd(inhoud, []) == inhoud


def test_the_privacy_page_shows_the_block(client, db_session):
    """En de andere helft: het blok komt uit de entiteit.

    Alleen toetsen dat de oude tekst weg is, zou groen staan bij een pagina waar
    de gegevens gewoon verdwenen zijn.
    """
    from app.domains.cms.api import CmsPage
    from app.domains.mdm.api import (Address, ContactDetail, Organization,
                                     PostalCode)
    from app.kernel.tenant_config import _actieve_tenant

    tenant = _actieve_tenant(None)
    organisatie = (db_session.query(Organization)
                   .filter(Organization.id == tenant)
                   .execution_options(include_all_tenants=True).one())
    # Sinds #945 is het e-mailadres een rij en geen kolom. `organisatie.email = …`
    # zou hier geruisloos een Python-attribuut zetten dat nooit in de databank
    # belandt — precies het soort stille nuloperatie waar deze week vol mee zat.
    db_session.add(ContactDetail(tenant_id=tenant, organization_id=organisatie.id,
                                 contact_type_code="EMAIL",
                                 value="bestuur@example.com"))
    pc = db_session.query(PostalCode).first()
    if pc is None:
        pc = PostalCode(postal_code="2400", municipality="Mol")
        db_session.add(pc)
        db_session.flush()
    db_session.add(Address(tenant_id=tenant, organization_id=organisatie.id,
                           street="Kerkstraat", house_number="12",
                           postal_code_id=pc.id))
    pagina = (db_session.query(CmsPage)
              .filter(CmsPage.slug == "privacy").one_or_none())
    if pagina is None:
        pagina = CmsPage(tenant_id=tenant, slug="privacy", title="Privacy")
        db_session.add(pagina)
    pagina.content = "<p>Wij verwerken je gegevens zorgvuldig.</p>"
    pagina.is_published = True
    db_session.commit()

    html = client.get("/privacy").text
    assert "Wij verwerken je gegevens zorgvuldig." in html
    assert "Contactgegevens" in html
    assert "bestuur@example.com" in html
    assert "Kerkstraat 12" in html


def test_another_page_does_not_get_the_block(client, db_session):
    """Eén vaste slug, en niet elke pagina."""
    from app.domains.cms.api import CmsPage
    from app.kernel.tenant_config import _actieve_tenant

    pagina = CmsPage(tenant_id=_actieve_tenant(None), slug="werking",
                     title="Werking", content="<p>Hoe we werken.</p>",
                     is_published=True)
    db_session.add(pagina)
    db_session.commit()

    html = client.get("/werking").text
    assert "Hoe we werken." in html
    assert "Contactgegevens" not in html


def test_a_short_value_inside_a_long_one_does_not_break_the_match():
    """De bug die deze tests vonden, vastgelegd.

    "Raak Voorbeeld" zonder spaties zit ín "bestuur@raakvoorbeeld.example".
    Wie de korte waarde eerst wegneemt, houdt "bestuur@.example" over en herkent
    het e-mailadres daarna niet meer — en dan blijft een pure contactalinea staan. De veilige kant
    op, maar wel fout, en precies het soort fout dat je niet ziet omdat er niets
    misgaat.
    """
    m = _opruimer()
    blok = ('<p>E-mail: <a href="mailto:bestuur@raakvoorbeeld.example">'
            'bestuur@raakvoorbeeld.example</a></p>')
    assert m._opgeruimd(blok, WAARDEN).strip() == ""
    # En omgekeerd gesorteerd zou het blijven staan: dat is wat er misging.
    assert m._rest_na_de_waarden(m._kale_tekst(blok), WAARDEN) == ""
