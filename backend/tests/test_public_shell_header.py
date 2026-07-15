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
