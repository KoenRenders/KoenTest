"""#475: publieke pagina's die vroeger de kale public_base gebruikten, moeten de
volledige SiteShell (site_base) met header/nav tonen — anders zit de bezoeker in
een navigatietrap (geen weg terug naar de homepage). We checken dat de nav-links
aanwezig zijn op elke betrokken publieke pagina."""
import pytest

# Een link die ALLEEN in de SiteShell-header staat (site_base.html), niet in de
# kale public_base — het bewijs dat de header meekomt.
NAV_MARKER = 'href="/fotos"'


@pytest.mark.parametrize("path", [
    "/activiteiten",
    "/activiteiten/archief",
    "/berichten",
    "/aanmelden",
])
def test_public_page_has_site_header(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    assert NAV_MARKER in resp.text, f"header/nav ontbreekt op {path}"
    # De homepagina-brand-link staat ook in de header.
    assert 'href="/"' in resp.text


def test_archief_redirect_lands_on_page_with_header(client):
    resp = client.get("/archief", follow_redirects=True)
    assert resp.status_code == 200
    assert NAV_MARKER in resp.text


# ── Footer + aanmelden (HDEV-testbevindingen 17 juli) ──────────────────────────

def test_footer_sociale_links_zijn_iconen(client, db_session):
    """#491/#519: mét een tenant-Facebook-URL is de sociale link in de footer een
    icoon (inline SVG), geen platte tekst. Zonder waarde geen (kapotte lege) link —
    er is geen hardgecodeerde Millegem-default meer."""
    from app.kernel.tenant_config import set_setting

    assert 'aria-label="Facebook"' not in client.get("/aanmelden").text
    set_setting(db_session, "facebook_url", "https://www.facebook.com/raakvoorbeeld")
    db_session.commit()
    html = client.get("/aanmelden").text
    assert 'aria-label="Facebook"' in html
    assert "<svg" in html  # het icoon is een inline SVG i.p.v. het woord 'Facebook'


def test_aanmelden_introtekst_en_knop(client):
    """#494: aangepaste introtekst én knoptekst op de aanmeldpagina."""
    html = client.get("/aanmelden").text
    assert "Je ontvangt een inloglink en een code." in html
    assert "Stuur inloginfo" in html


def test_footer_privacylink_is_config_driven(client, db_session):
    """#493: de privacyverklaring-link staat enkel in de footer als de tenant-
    setting `privacy_url` gezet is — niet hardcoded."""
    from app.kernel.tenant_config import set_setting

    assert "Privacyverklaring" not in client.get("/aanmelden").text
    set_setting(db_session, "privacy_url", "https://voorbeeld.be/privacy")
    db_session.commit()
    html = client.get("/aanmelden").text
    assert "Privacyverklaring" in html and "https://voorbeeld.be/privacy" in html
