"""#690 — een leesbare naam voor de deellink, naast de tokenlink.

Optioneel per formulier, en **met** een unieke index (Koens beslissing). De kolom
en `get_form_by_slug` bestonden al, maar er was geen constraint: twee formulieren
met dezelfde slug konden gewoon naast elkaar bestaan en `.first()` koos er stil
één. Welk formulier je te zien kreeg, hing af van de rijvolgorde.

De **tokenlink blijft altijd werken**, ook naast een slug. Een rondgestuurde link
mag niet breken omdat iemand er later een naam bij zet — precies wat een deellink
onbruikbaar maakt. Dat is de belangrijkste test hier.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _formulier(client, admin_headers, titel="Zomerfeest"):
    r = client.post("/api/v1/forms",
                    json={"title": titel, "status": "open",
                          "is_anonymous": True, "fields": []},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _zet_slug(client, csrf, form, slug, *, titel=None):
    return client.post(f"/admin/formulieren/{form['id']}/instellingen",
                       data={"title": titel or form["title"], "status": "open",
                             "is_anonymous": "1", "slug": slug},
                       headers={"X-CSRF-Token": csrf})


# ── 1. De leesbare link werkt ────────────────────────────────────────────────

def test_een_formulier_is_bereikbaar_via_zijn_slug(client, admin_headers):
    form = _formulier(client, admin_headers)
    csrf = _login(client)
    assert _zet_slug(client, csrf, form, "zomerfeest").status_code == 200

    pagina = client.get("/f/zomerfeest")
    assert pagina.status_code == 200, pagina.text
    assert "Zomerfeest" in pagina.text


def test_een_onbekende_slug_geeft_404(client, admin_headers):
    assert client.get("/f/bestaat-niet").status_code == 404


# ── 2. De tokenlink blijft werken — test 3 uit het issue ────────────────────

def test_de_tokenlink_blijft_werken_naast_een_slug(client, admin_headers):
    """De belangrijkste van de reeks: rondgestuurde links mogen niet breken."""
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    via_token = client.get(f"/formulier/{form['share_token']}")
    assert via_token.status_code == 200

    assert _zet_slug(client, csrf, form, "zomerfeest").status_code == 200

    nog_altijd = client.get(f"/formulier/{form['share_token']}")
    assert nog_altijd.status_code == 200, (
        "de tokenlink brak toen er een leesbare link bij kwam")
    assert client.get("/f/zomerfeest").status_code == 200, "en de nieuwe werkt ook"


# ── 3. Uniek, en `berichten` is verboden ────────────────────────────────────

def test_twee_formulieren_kunnen_niet_dezelfde_slug_hebben(client, admin_headers):
    eerste = _formulier(client, admin_headers, "Eerste")
    tweede = _formulier(client, admin_headers, "Tweede")
    csrf = _login(client)

    assert _zet_slug(client, csrf, eerste, "feest").status_code == 200
    botsing = _zet_slug(client, csrf, tweede, "feest")
    assert botsing.status_code == 200, botsing.text
    assert "bestaat al een formulier" in botsing.text

    # En het eerste formulier is nog altijd wat je op die link krijgt.
    assert "Eerste" in client.get("/f/feest").text


def test_een_formulier_mag_zijn_eigen_slug_houden(client, admin_headers):
    """De keerzijde: zonder deze test zou "weiger elke bestaande slug" ook slagen,
    en dan kun je een formulier met een slug nooit meer opslaan."""
    form = _formulier(client, admin_headers)
    csrf = _login(client)
    assert _zet_slug(client, csrf, form, "feest").status_code == 200

    opnieuw = _zet_slug(client, csrf, form, "feest", titel="Andere titel")
    assert opnieuw.status_code == 200, opnieuw.text


def test_berichten_is_voorbehouden_aan_de_site(client, admin_headers):
    """`/berichten` zoekt het contactformulier op slug op; een tweede formulier met
    die naam zou dat scherm kapen."""
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    geweigerd = _zet_slug(client, csrf, form, "berichten")
    assert geweigerd.status_code == 200, geweigerd.text
    assert "voorbehouden" in geweigerd.text


# ── 4. Vorm van de slug ─────────────────────────────────────────────────────

@pytest.mark.parametrize("slug", ["Zomer Feest", "zomer_feest", "zomer/feest",
                                  "-feest", "feest-", "zomer feest"])
def test_een_ongeldige_vorm_wordt_geweigerd(client, admin_headers, slug):
    """Spaties, liggende streepjes en schuine strepen worden geweigerd.

    Ze zijn niet ondubbelzinnig te herstellen: wordt "zomer feest" nu
    "zomer-feest" of "zomerfeest"? Stil iets kiezen levert een link op die de
    beheerder niet intypte, en die hij dus verkeerd doorstuurt.
    """
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    resp = _zet_slug(client, csrf, form, slug)
    # Sinds #694 een foutbanner (200) i.p.v. een kale 422: dit scherm swapt zijn
    # antwoord, en een 422 zou de generieke toast geven i.p.v. de uitleg.
    assert resp.status_code == 200, resp.text[:200]
    assert "koppeltekens" in resp.text, f"{slug!r} werd aanvaard: {resp.text[:200]}"


@pytest.mark.parametrize("ingetypt", ["Zomerfeest", "ZOMERFEEST", "  zomerfeest  "])
def test_hoofdletters_en_spatie_eromheen_worden_rechtgezet(client, admin_headers,
                                                           db_session, ingetypt):
    """Hier wél normaliseren, en dat is geen inconsistentie met de test hierboven.

    Een hoofdletter of een spatie aan de rand heeft precies één redelijke lezing;
    daarvoor een 422 geven is pesterig. Een spatie in het mídden heeft er meerdere,
    en dan is weigeren eerlijker dan gokken.
    """
    from app.domains.forms.models import Form

    form = _formulier(client, admin_headers)
    csrf = _login(client)

    assert _zet_slug(client, csrf, form, ingetypt).status_code == 200
    db_session.expire_all()
    assert db_session.get(Form, form["id"]).slug == "zomerfeest"


def test_leeg_laten_betekent_geen_leesbare_link(client, admin_headers, db_session):
    """Optioneel is optioneel: leeg mag, en levert NULL op — niet een lege string,
    want die zou met de unieke index botsen zodra een tweede formulier ook leeg is.
    """
    from app.domains.forms.models import Form

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    assert _zet_slug(client, csrf, form, "").status_code == 200

    db_session.expire_all()
    assert db_session.get(Form, form["id"]).slug is None

    tweede = _formulier(client, admin_headers, "Tweede")
    assert _zet_slug(client, csrf, tweede, "").status_code == 200


# ── 5. Het scherm ───────────────────────────────────────────────────────────

def test_de_bouwer_toont_beide_links(client, admin_headers):
    form = _formulier(client, admin_headers)
    csrf = _login(client)
    _zet_slug(client, csrf, form, "zomerfeest")

    html = client.get(f"/admin/formulieren/{form['id']}").text
    assert f"/formulier/{form['share_token']}" in html, "de tokenlink is verdwenen"
    assert "/f/zomerfeest" in html, "de leesbare link staat er niet"
    assert 'data-copy="/f/zomerfeest"' in html, "en is niet te kopiëren"


def test_zonder_slug_staat_er_geen_lege_regel(client, admin_headers):
    form = _formulier(client, admin_headers)
    _login(client)

    html = client.get(f"/admin/formulieren/{form['id']}").text
    assert "/f/" not in html


# ── 6. Een geweigerde instelling zegt wát er mis is (#694) ──────────────────

def test_een_geweigerde_link_toont_de_reden_in_het_scherm(client, admin_headers):
    """Koen zette een liggend streepje in de link en kreeg de generieke toast.

    De 422 ontsnapte aan `instellingen_opslaan`, dus htmx kreeg een kale foutcode en
    de uitleg viel weg. Dezelfde fout als in de importroute van ditzelfde bestand
    (#692), één route verder.

    Toetsen op de **reden**, niet op de statuscode: een 422 krijg je ook bij een
    ongeldige status, en dan bewijst de test niets over déze melding.
    """
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    resp = _zet_slug(client, csrf, form, "zomer feest")
    assert resp.status_code == 200, "een kale 422 geeft de generieke toast"
    assert "koppeltekens" in resp.text, resp.text[:400]


def test_een_bezette_link_toont_de_reden_in_het_scherm(client, admin_headers):
    """Zelfde weg, andere regel — anders dekt de test alleen de vormcontrole."""
    eerste = _formulier(client, admin_headers, "Eerste")
    tweede = _formulier(client, admin_headers, "Tweede")
    csrf = _login(client)
    _zet_slug(client, csrf, eerste, "feest")

    resp = _zet_slug(client, csrf, tweede, "feest")
    assert resp.status_code == 200
    assert "bestaat al een formulier" in resp.text, resp.text[:400]


def test_een_ongeldige_status_toont_ook_de_reden(client, admin_headers):
    """De statuscontrole in dezelfde route wierp op dezelfde manier."""
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    resp = client.post(f"/admin/formulieren/{form['id']}/instellingen",
                       data={"title": form["title"], "status": "bestaat-niet"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert "Ongeldige status" in resp.text, resp.text[:400]


# ── 7. Het liggend streepje mag (#694) ─────────────────────────────────────

@pytest.mark.parametrize("slug", ["enquete_ledenfeest_2026", "zomer_feest",
                                  "zomer-feest", "zomer_feest-2026"])
def test_een_liggend_streepje_is_toegestaan(client, admin_headers, db_session, slug):
    """Koen vroeg in #690 letterlijk om `enquete_ledenfeest_2026`. Die notatie
    weigeren terwijl ze in een URL niets breekt, is een regel omwille van de regel."""
    from app.domains.forms.models import Form

    form = _formulier(client, admin_headers)
    csrf = _login(client)

    assert _zet_slug(client, csrf, form, slug).status_code == 200
    db_session.expire_all()
    assert db_session.get(Form, form["id"]).slug == slug
    assert client.get(f"/f/{slug}").status_code == 200


@pytest.mark.parametrize("slug", ["_feest", "feest_", "zomer__feest"])
def test_een_liggend_streepje_aan_de_rand_of_dubbel_blijft_geweigerd(client,
                                                                     admin_headers,
                                                                     slug):
    """Dezelfde grens als voor het koppelteken. Zonder deze test zou "laat `_` toe"
    ook een slug als `__` doorlaten, en dat leest niemand meer als een naam."""
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    resp = _zet_slug(client, csrf, form, slug)
    assert resp.status_code == 200, resp.text[:200]
    assert "koppeltekens" in resp.text, f"{slug!r} werd aanvaard"
