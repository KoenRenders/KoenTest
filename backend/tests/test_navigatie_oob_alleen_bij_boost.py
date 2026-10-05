"""#718 — de out-of-band navigatie hoort alleen bij een gebooste navigatie.

Het gemelde symptoom: vernieuw je op `/leden/gezin` je lidmaatschap, dan staan de
betaalinstructies er wel maar is de menubalk weg. Logo en baseline blijven staan.

De server deed niets fout — de navigatie zit gewoon in de HTML — en dat is precies
waarom geen enkele bestaande test dit ving. Het ging mis bij het samenvoegen in de
browser: sinds #714 dragen de vier navigatiecontainers `hx-swap-oob="true"`, htmx
licht zo'n element uit het antwoord vóór de gewone swap, en negen formulieren doen
`hx-target="body" hx-swap="innerHTML"`. Het lichaam werd dus vervangen door wat er
ná die uitname overbleef: alles behalve de navigatie.

**Wat deze tests wél kunnen bewijzen.** Niet de samenvoeging — dat doet de e2e
(`tests_e2e/test_navigatie_overleeft_body_swap.py`) — maar wél de voorwaarde
waarop alles steunt: het attribuut staat er enkel bij een gebooste navigatie. Elke
test is daarom een **paar**: hetzelfde verzoek, één keer met en één keer zonder de
`HX-Boosted`-header, en verder identiek. Het verschil ís het bewijs.

Er wordt bewust op de hele geopende tag getoetst (`<nav id="site-nav-breed" class=`)
en niet op de losse string `hx-swap-oob`: dat laatste komt sinds #717 ook elders in
antwoorden voor (de toast), en een assert die daarop struikelt zou over iets anders
gaan dan waarover hij beweert te gaan.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `nav_oob` hard op
True gezet → de vier "zonder boost"-asserts vallen om; hard op False → de vier
"met boost"-asserts. Beide richtingen apart, want een vlag die maar één kant op
getoetst wordt kan altijd blijven staan of altijd wegblijven.
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, household_fields

pytestmark = pytest.mark.ui_serverrendered

LID_EMAIL = "portaal718@example.com"

# De geopende tag zoals de schil hem rendert, met en zonder het attribuut.
# #1588: the wide list is a <nav> now, and the drawer (`site-nav-mobiel`) is the
# second container that travels out of band — both are checked, as a pair.
PUBLIEK_ZONDER = '<nav id="site-nav-breed" class='
PUBLIEK_MET = '<nav id="site-nav-breed" hx-swap-oob="true" class='
MOBIEL_ZONDER = '<div id="site-nav-mobiel" x-show='
MOBIEL_MET = '<div id="site-nav-mobiel" hx-swap-oob="true" x-show='
BEHEER_ZONDER = '<nav id="admin-nav-zijbalk" class='
BEHEER_MET = '<nav id="admin-nav-zijbalk" hx-swap-oob="true" class='

GEBOOST = {"HX-Request": "true", "HX-Boosted": "true"}


def _als_lid(client, db):
    create_test_family(db, email=LID_EMAIL)
    waarde = make_session_value(LID_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _als_admin(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


# ── De publieke schil ────────────────────────────────────────────────────────


def test_de_publieke_schil_stuurt_de_navigatie_alleen_out_of_band_bij_een_boost(client, db_session):
    """Het paar: dezelfde pagina, alleen de HX-Boosted-header verschilt."""
    _als_lid(client, db_session)

    gewoon = client.get("/leden/gezin")
    assert gewoon.status_code == 200, gewoon.text
    assert PUBLIEK_ZONDER in gewoon.text, "de navigatie hoort gewoon in de pagina"
    assert PUBLIEK_MET not in gewoon.text
    assert MOBIEL_ZONDER in gewoon.text and MOBIEL_MET not in gewoon.text

    geboost = client.get("/leden/gezin", headers=GEBOOST)
    assert geboost.status_code == 200, geboost.text
    assert PUBLIEK_MET in geboost.text, (
        "zonder dit attribuut volgt de actieve markering een gebooste navigatie niet "
        "meer — dat is wat #714 oploste"
    )
    assert MOBIEL_MET in geboost.text and MOBIEL_ZONDER not in geboost.text
    assert PUBLIEK_ZONDER not in geboost.text


def test_een_body_swap_krijgt_de_navigatie_mee_in_het_antwoord(client, db_session):
    """Het gemelde geval, op de weg die er altijd is.

    Since #1590 the portal's one save (`POST /leden/gezin`) is that way: it is
    an htmx request that is not boosted, and it answers a whole page, of which
    the form takes `#gezin-pagina`. The navigation in that answer must not carry
    the out-of-band attribute: htmx lifts an out-of-band element out of any
    answer, whatever the form selects from it, and swaps it by itself — a
    navigation travelling on every save is what #718 was. (Until #1590 the form
    targeted the body, and the lifted navigation was simply gone.)
    """
    csrf = _als_lid(client, db_session)
    db_session.commit()
    fields = household_fields(client)
    # The main member's mobile, typed on the page: the save asks it (#1590).
    (main,) = fields["h_order"]
    fields[f"h.{main}.mobile"] = "0470 00 00 01"
    fields["h_order"] = [*fields["h_order"], "n1"]
    fields.update(
        {
            "h.n1.first_name": "Nieuw",
            "h.n1.last_name": "Gezinslid",
            "h.n1.date_of_birth": "2010-04-05",
            "h.n1.gender_code": "M",
        }
    )

    resp = client.post(
        "/leden/gezin", headers={"X-CSRF-Token": csrf, "HX-Request": "true"}, data=fields
    )

    assert resp.status_code == 200, resp.text
    assert "Gezinslid" in resp.text, "the save did not answer the household"
    assert PUBLIEK_ZONDER in resp.text, "de navigatie ontbreekt in het antwoord"
    assert PUBLIEK_MET not in resp.text, (
        "out-of-band bij een antwoord dat geen gebooste navigatie is: htmx haalt de "
        "navigatie er dan uit"
    )
    assert MOBIEL_ZONDER in resp.text and MOBIEL_MET not in resp.text


# ── De beheerschil ───────────────────────────────────────────────────────────


def test_de_beheerschil_stuurt_de_zijbalk_alleen_out_of_band_bij_een_boost(client):
    """Dezelfde behandeling kreeg de beheerschil in #714, dus dezelfde regel."""
    _als_admin(client)

    gewoon = client.get("/admin/leden")
    assert gewoon.status_code == 200, gewoon.text
    assert BEHEER_ZONDER in gewoon.text
    assert BEHEER_MET not in gewoon.text

    geboost = client.get("/admin/leden", headers=GEBOOST)
    assert geboost.status_code == 200, geboost.text
    assert BEHEER_MET in geboost.text
