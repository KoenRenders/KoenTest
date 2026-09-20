"""Zoekveld en filters op ÉÉN regel, op elk lijstscherm (#1079).

`ui.filter_bar` rendert `<form class="mb-4 space-y-3">`, dus **elk direct kind is
een eigen regel**. Het referentiescherm Betalingen heeft precies één kind — de
flex-rij met het zoekveld én de filters erin; de elf andere hadden er twee en
stonden daarom op twee regels. Er was niets stuk, ze waren anders opgebouwd.

Deze tests toetsen dus de STRUCTUUR en niet de statuscode: een 200 bewijst hier
niets, want de pagina antwoordde vóór dit issue ook al netjes. De meter hieronder
deelt elke zichtbare control in bij het directe kind van het formulier waar ze
onder hangt; de invariant is dat dat er precies één is.

**Rood gemaakt om te bewijzen dat hij meet** (tweemaal):

1. `test_de_meter_ziet_de_oude_vorm_als_twee_regels` doet het blijvend: dezelfde
   meter, losgelaten op de oude opbouw, moet twee kinderen zien. Zag hij daar ook
   één, dan telde hij iets anders dan nestdiepte en was de hoofdtest een lege huls.
2. Met de hand, tijdens het bouwen: in `admin_activiteiten.html` de chips weer
   buiten de flex-rij gezet. `test_zoek_en_filters_staan_in_een_rij[/admin/activiteiten]`
   viel om met "2 directe kinderen"; na het terugzetten weer groen.
"""
from html.parser import HTMLParser

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole,
                                  make_session_value)
from app.ui import templates
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


# ── De meter ─────────────────────────────────────────────────────────────────

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}

# Alleen een control die de gebruiker ZIET telt mee. De verborgen velden van de
# sorteerstand (e-maillog, ledenwijzigingen) en de recordscope staan bewust als
# eigen direct kind onder het formulier: ze renderen niets, dus ze maken geen
# regel. Een test die ze meetelde, zou die twee schermen afkeuren voor iets wat
# niemand kan zien.
_CONTROLS = {"input", "select", "textarea"}


class _Regelmeter(HTMLParser):
    """Deelt elke zichtbare control van een `ui.filter_bar` in bij haar DIRECTE kind.

    Ankert op de vingerafdruk van de macro — `hx-headers` met `X-Raak-Filter` —
    en niet op de klasse: die zegt hoe de balk eruitziet, de header zegt wát ze
    is. Zo wijst de meter nog altijd naar de filterbalk als de opmaak verandert.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_balk = False
        self._diepte = 0        # diepte binnen het <form>; 0 = direct kind
        self._svg = 0           # binnen een icoon niets tellen
        self._kind = 0          # volgnummer van het lopende directe kind
        self._teller = 0
        self.controls: list[tuple[int, str, str]] = []   # (kind, naam, type)
        self.gevonden = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if not self._in_balk:
            if tag == "form" and "X-Raak-Filter" in (d.get("hx-headers") or ""):
                self._in_balk, self._diepte, self.gevonden = True, 0, True
            return
        if self._svg:
            if tag == "svg":
                self._svg += 1
            return
        if tag == "svg":
            self._svg = 1
            return
        if self._diepte == 0:
            self._teller += 1
            self._kind = self._teller
        if tag in _CONTROLS:
            self.controls.append((self._kind, d.get("name", ""), d.get("type", "")))
        if tag not in _VOID:
            self._diepte += 1

    def handle_endtag(self, tag):
        if not self._in_balk or tag in _VOID:
            return
        if self._svg:
            if tag == "svg":
                self._svg -= 1
            return
        self._diepte -= 1
        if self._diepte < 0:        # de </form> zelf
            self._in_balk = False


def meet(html: str) -> list[tuple[int, str, str]]:
    """De zichtbare controls van de filterbalk, elk met het nummer van hun regel."""
    meter = _Regelmeter()
    meter.feed(html)
    assert meter.gevonden, "geen ui.filter_bar in deze pagina gevonden"
    return [(kind, naam, soort) for kind, naam, soort in meter.controls
            if soort != "hidden"]


# ── De schermen ──────────────────────────────────────────────────────────────

def _login(client, db):
    """OPERATOR erbij: Organisaties en Tenants zijn OPERATOR-only (#581)."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    for rol in ("ADMIN", "OPERATOR"):
        if not any(r.role_code == rol for r in user.roles):
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _seed(db):
    """Genoeg data om élke filter-control te laten renderen.

    Twee ervan zijn voorwaardelijk en zouden zonder deze seed stilletjes
    ontbreken — dan toetst de rij ze niet en blijft de test groen terwijl de
    control naar een tweede regel verhuisd kan zijn.
    """
    from datetime import date, timedelta

    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.media.api import MediaAsset
    from app.domains.membership.api import Membership
    from tests.conftest import create_test_family

    # Leden: `jaar` verschijnt alleen als er lidmaatschapsjaren in de data zitten.
    member, _persoon = create_test_family(db)
    db.add(Membership(member_id=member.id, year=date.today().year))

    # Media: `activity_id` verschijnt alleen bij activiteitenfoto's van een
    # activiteit die al media heeft.
    activiteit = Activity(name="Fotoactiviteit")
    db.add(activiteit)
    db.flush()
    db.add(ActivityDate(activity_id=activiteit.id,
                        start_date=date.today() + timedelta(days=30)))
    db.add(MediaAsset(kind="activity_photo", activity_id=activiteit.id,
                      is_active=True, data=b"\x89PNG", content_type="image/png",
                      title="foto"))
    db.flush()
    return activiteit


# Per scherm: het pad, en élke filter-control die erop hoort te staan. De namen
# staan er expliciet bij en niet als "wat we toevallig vinden" — verdwijnt er een
# filter, dan hoort deze test dat te melden en niet mee te schuiven.
SCHERMEN = [
    ("/admin/activiteiten", {"q", "scope"}),
    ("/admin/paginas", {"q", "status"}),
    ("/admin/formulieren", {"q", "status"}),
    ("/admin/rapporten", {"q", "owner", "shared"}),
    ("/admin/e-maillog", {"recipient", "email_type", "status"}),
    ("/admin/organisaties", {"q", "org_type"}),
    ("/admin/tenants", {"q", "status"}),
    ("/admin/leden", {"q", "status", "jaar"}),
    ("/admin/media", {"q", "kind", "activity_id"}),
    ("/admin/ledenwijzigingen", {"actor", "since", "group"}),
    ("/admin/gebruikers", {"q", "rol", "actief"}),
]


@pytest.mark.parametrize("pad,verwacht", SCHERMEN, ids=[p for p, _ in SCHERMEN])
def test_zoek_en_filters_staan_in_een_rij(client, db_session, pad, verwacht):
    """Zoekveld en filters horen onder hetzelfde directe kind van de filterbalk."""
    _login(client, db_session)
    _seed(db_session)

    resp = client.get(pad)
    assert resp.status_code == 200, resp.text
    controls = meet(resp.text)

    namen = {naam for _kind, naam, _soort in controls}
    assert namen == verwacht, f"{pad}: filter-controls {namen}, verwacht {verwacht}"

    regels = {kind for kind, _naam, _soort in controls}
    assert len(regels) == 1, (
        f"{pad}: de controls hangen onder {len(regels)} directe kinderen van de "
        f"filterbalk ({sorted(regels)}) — elk kind is een eigen regel. "
        f"Verdeling: {sorted(controls)}")


def test_het_zoekveld_wint_de_restbreedte(client, db_session):
    """De wrapper van de referentie moet mee, anders staat het zoekveld op zijn
    vaste `sm:w-64` naast een leeg gat — de F8-bevinding van #996.

    Op de bron getoetst en niet op de gerenderde pagina: de klasse zit op de
    wrapper rond de macro-aanroep, en dat is precies de regel die per scherm
    vergeten kan worden.
    """
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    balken = [app / p for p in (
        "domains/activities/templates/admin_activiteiten.html",
        "domains/cms/templates/admin_paginas.html",
        "domains/forms/templates/admin_formulieren.html",
        "domains/reporting/templates/admin_rapporten.html",
        "domains/mail/templates/email_log.html",
        "ui/templates/admin_organisaties.html",
        "ui/templates/admin_tenants.html",
        "domains/mdm/templates/leden.html",
        "domains/media/templates/admin_media.html",
        "ui/templates/admin_ledenwijzigingen.html",
        "domains/auth/templates/admin_gebruikers.html",
    )]
    for pad in balken:
        assert pad.exists(), pad          # een verplaatst bestand mag niet stil overslaan
        assert 'class="flex-1 min-w-[14rem]"' in pad.read_text(), \
            f"{pad.name}: het zoekveld mist de flex-1-wrapper van de referentie"


# ── Media: de rij verspringt niet bij het wisselen van soort ─────────────────

def test_media_blijft_een_rij_met_en_zonder_de_activiteitenlijst(client, db_session):
    """`activity_id` verschijnt alleen bij activiteitenfoto's (#891), dus de rij
    verandert van inhoud als je van soort wisselt. Beide toestanden horen één
    regel te blijven — anders springt de balk onder je vingers."""
    _login(client, db_session)
    _seed(db_session)

    met = meet(client.get("/admin/media", params={"kind": "activity_photo"}).text)
    assert {n for _k, n, _s in met} == {"q", "kind", "activity_id"}
    assert len({k for k, _n, _s in met}) == 1

    zonder = meet(client.get("/admin/media", params={"kind": "sponsor"}).text)
    assert {n for _k, n, _s in zonder} == {"q", "kind"}, \
        "bij een sponsorlogo hoort er geen activiteitenfilter te staan"
    assert len({k for k, _n, _s in zonder} ) == 1


# ── Gebruikers: de rollen zijn één keuzelijst geworden ───────────────────────

def test_rollen_zijn_een_keuzelijst_met_leesbare_labels(client, db_session):
    """Het aantal rollen is data-gedreven — het groeit mee met `role_codes` — dus
    een rij knoppen groeit mee met de breedte van het scherm. En zodra het een
    keuzelijst is, leest een ruwe `FINANCE` als een bug: het label komt uit de
    codetabel, de code blijft de waarde."""
    _login(client, db_session)
    html = client.get("/admin/gebruikers").text

    controls = meet(html)
    rol = [(k, n, s) for k, n, s in controls if n == "rol"]
    assert len(rol) == 1 and rol[0][2] == "", \
        f"'rol' hoort één <select> te zijn, gemeten: {rol}"

    # De labels: de omschrijving uit role_codes, niet de code zelf.
    from app.domains.auth.api import list_assignable_roles, role_options

    rollen = [r for r in list_assignable_roles(db_session) if r.code != "OPERATOR"]
    opties = role_options(rollen)
    assert opties, "geen toekenbare rollen — dan toetst deze test niets"
    for code, label in opties:
        assert label != code, f"{code} draagt nog zijn code als label"
        assert f'value="{code}"' in html and f">{label}</option>" in html


def test_filteren_op_rol_levert_dezelfde_rijen_als_met_de_knoppen(client, db_session):
    """De keuzelijst is opmaak: parameternaam en waarden zijn niet veranderd.

    Getoetst via het SCHERM en niet via de filterfunctie: een dropdown die de
    verkeerde waarde verstuurt, zou een directe aanroep niet opmerken.
    """
    from app.domains.auth.api import User, UserRole
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    _login(client, db_session)
    werkruimte = current_tenant_id.get() or DEFAULT_TENANT_ID

    def maak(adres, rol):
        gebruiker = User(email=adres, is_active=True)
        db_session.add(gebruiker)
        db_session.flush()
        # Mét werkruimte: het scherm toont sinds #963 de rollen van de ACTIEVE
        # werkruimte, en een rij zonder tenant is platformbreed (alleen OPERATOR).
        db_session.add(UserRole(user_id=gebruiker.id, role_code=rol,
                                tenant_id=werkruimte))
        db_session.flush()

    maak("penning@example.com", "FINANCE")
    maak("enkel-admin@example.com", "ADMIN")

    # Het KAARTENfragment, niet de hele pagina: het accountmenu in de schil draagt
    # het adres van de ingelogde beheerder, dus op de volle pagina meet je de schil
    # in plaats van het filter. (De geseede beheerder is hier bewust geen ijkpunt:
    # migratie 056 geeft hém ook FINANCE.)
    fragment = {"HX-Request": "true"}
    alles = client.get("/admin/gebruikers", headers=fragment).text
    assert "penning@example.com" in alles and "enkel-admin@example.com" in alles

    finance = client.get("/admin/gebruikers", params={"rol": "FINANCE"},
                         headers=fragment).text
    assert "penning@example.com" in finance
    assert "enkel-admin@example.com" not in finance, \
        "wie geen FINANCE heeft, hoort weg te vallen bij filteren op FINANCE"


# ── Tegenproef op de meter ───────────────────────────────────────────────────

def _render(body: str) -> str:
    return templates.env.from_string(
        "{% import '_macros.html' as ui %}" + body).render()


_OUDE_VORM = """
{% call ui.filter_bar("/x", "#y") %}
  <div>{{ ui.search(standalone=False) }}</div>
  {{ ui.chips("scope", [("a", "A"), ("b", "B")], "a") }}
{% endcall %}
"""

_NIEUWE_VORM = """
{% call ui.filter_bar("/x", "#y") %}
  <div class="flex flex-wrap gap-3 items-center">
    <div class="flex-1 min-w-[14rem]">{{ ui.search(standalone=False) }}</div>
    {{ ui.chips("scope", [("a", "A"), ("b", "B")], "a") }}
  </div>
{% endcall %}
"""


def test_de_meter_ziet_de_oude_vorm_als_twee_regels():
    """De tegenproef: dezelfde meter op de opbouw van vóór #1079.

    Zonder deze test bewijst de hoofdtest niets — een meter die altijd één kind
    terugmeldt, staat groen bij elke vorm. Hier telt hij op de ECHTE macro's, dus
    ze toetst meteen dat `filter_bar` nog altijd per direct kind een regel maakt.
    """
    oud = meet(_render(_OUDE_VORM))
    assert {k for k, _n, _s in oud} == {1, 2}, \
        f"de oude vorm hoort twee directe kinderen te hebben, gemeten: {oud}"

    nieuw = meet(_render(_NIEUWE_VORM))
    assert {k for k, _n, _s in nieuw} == {1}, \
        f"de nieuwe vorm hoort één direct kind te hebben, gemeten: {nieuw}"
    assert {n for _k, n, _s in nieuw} == {"q", "scope"}
