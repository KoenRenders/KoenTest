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

def test_footer_sociale_links_zijn_iconen(client):
    """#491: de sociale links in de footer zijn iconen (inline SVG), geen platte
    tekst meer."""
    html = client.get("/aanmelden").text
    assert 'aria-label="Facebook"' in html
    assert "<svg" in html  # het icoon is een inline SVG i.p.v. het woord 'Facebook'


def test_aanmelden_introtekst(client):
    """#494: aangepaste introtekst op de aanmeldpagina."""
    assert "Je ontvangt een inloglink en een code." in client.get("/aanmelden").text


def test_footer_privacylink_is_config_driven(client, db_session):
    """#493: de privacyverklaring-link staat enkel in de footer als de tenant-
    setting `privacy_url` gezet is — niet hardcoded."""
    from app.kernel.tenant_config import set_setting

    assert "Privacyverklaring" not in client.get("/aanmelden").text
    set_setting(db_session, "privacy_url", "https://voorbeeld.be/privacy")
    db_session.commit()
    html = client.get("/aanmelden").text
    assert "Privacyverklaring" in html and "https://voorbeeld.be/privacy" in html
