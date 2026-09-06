"""Render-gate: controleert de GERENDERDE HTML van elke adminpagina (#622, laag 1).

De suite testte endpoints, niet schermen. Dat is precies de naad waar de bugs van de
v2.0.0-validatie zaten: knoppen die niets doen omdat hun attributen ge-escaped raakten
(#514, #613, #616 — drie keer dezelfde klasse), terwijl 830 endpoint-tests groen
stonden. Geen enkele daarvan kan zien wat de browser krijgt.

Deze gate staat naast de lint-gate en vervangt hem niet: die kijkt naar **templates**,
deze naar **gerenderde output**. Een template kan er correct uitzien en toch fout
renderen — dat is nu net wat er gebeurde.

De pagina's komen uit `_ADMIN_NAV`, zodat een nieuw menu-item automatisch meegetest
wordt zonder dat iemand deze lijst moet bijwerken.
"""
import re
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.ui import _ADMIN_NAV
from tests.conftest import (SEEDED_ADMIN_EMAIL, create_test_family,
                            seed_activity_with_product, seed_postal_code)

pytestmark = pytest.mark.ui_serverrendered

# hx-post=&#34;…&#34; — htmx ziet dan geen bruikbare waarde en de knop is inert.
GEESCAPED = re.compile(r'\b(hx-(?:post|get|put|delete|target|swap|trigger)|data-confirm)=&#(?:34|39);')
# Elementen met een htmx-verzoek, om hun doel te kunnen nakijken.
HX_ELEMENT = re.compile(r"<[^>]*\shx-(?:post|get|put|delete)=[\"'][^\"']*[\"'][^>]*>")
HX_TARGET = re.compile(r"hx-target=[\"']([^\"']*)[\"']")
# Wat htmx als doel accepteert naast een CSS-selector.
HX_SPECIAAL = ("this", "closest ", "find ", "next", "previous", "body", "window")


def _login(client, db):
    """Sessie mét FINANCE, anders blijven de betaalacties onzichtbaar en test de
    gate precies de knoppen niet die stuk waren."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    for rol in ("FINANCE", "OPERATOR"):
        if not any(r.role_code == rol for r in user.roles):
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


@pytest.fixture
def gevulde_admin(client, db_session):
    """Een adminomgeving mét data — een lege lijst heeft geen knoppen om te toetsen.

    Levert de id's van de detailschermen die alleen met een id bestaan.
    """
    from app.domains.cms.api import CmsPage
    from app.domains.forms.api import Form
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    seed_postal_code(db_session)
    member, person = create_test_family(db_session, email="rendergate@example.com")
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)

    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 2}]})
    assert resp.status_code in (200, 201), resp.text
    reg_id = resp.json()["id"]

    # Eén openstaande en één betaalde charge, zodat zowel "Bevestig betaald" als
    # "Terugbetalen…" en de editors in de HTML staan.
    db_session.add(PaymentRecord(
        payable_type="registration", payable_id=reg_id, type="charge",
        amount=Decimal("20.00"), amount_paid=Decimal("20.00"), method="transfer",
        status="paid"))
    # Een lidmaatschap, zodat het gezinsdetail zijn lidmaatschapsrijen rendert — daar
    # zitten de verwijderknoppen met confirm_attrs, het toneel van #514.
    from datetime import date

    jaar = date.today().year
    db_session.add(Membership(member_id=member.id, year=jaar, is_active=True,
                              valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31)))

    # Ook een formulier en een CMS-pagina: hun editors dragen de knoppen met
    # aria-labels en bevestigingen, en die vielen buiten de eerste versie van deze
    # gate — precies waar nog ge-escapete attributen bleken te staan.
    formulier = Form(title="Rendergate-formulier", share_token="tok-rendergate",
                     status="draft")
    pagina = CmsPage(title="Rendergate-pagina", slug="rendergate", content="<p>x</p>")
    db_session.add_all([formulier, pagina])
    db_session.commit()

    _login(client, db_session)
    return {"member": member.id, "activity": activity.id, "registration": reg_id,
            "formulier": formulier.id, "pagina": pagina.id}


def _admin_gets_zonder_parameter() -> list[str]:
    """Élke admin-GET zonder padparameter, uit de ROUTETABEL (#695).

    De lijst was het menu plus vijf met de hand opgesomde detailschermen. Daardoor
    zag deze gate zeventien admin-GET-routes niet, waaronder alle zes de
    aanmaakschermen — en #627 maakte in één klap precies zo'n soort pagina, buiten
    het menu om. Zelfs mét de juiste controle had de gate de kapotte doelen op
    /admin/media/nieuw en /admin/gebruikers/nieuw gemist, simpelweg omdat hij die
    pagina's nooit opende.

    Er stond al een `assert len(_ADMIN_NAV) >= 13` die bewaakt dat het menu niet
    krimpt; niets bewaakte dat de gate álle schermen ziet. Uit de routetabel lezen
    doet dat wel: een nieuw scherm is meteen meegetest, zonder dat iemand eraan hoeft
    te denken.
    """
    from fastapi.responses import HTMLResponse

    from app.main import app

    paden = set()
    for route in app.routes:
        pad = getattr(route, "path", "")
        methoden = getattr(route, "methods", set()) or set()
        if not pad.startswith("/admin") or "{" in pad or "GET" not in methoden:
            continue
        # Alleen schermen. Exports leveren een bestand en de JSON-API onder /admin
        # levert geen HTML; die hebben geen hx-target om te controleren en zouden
        # de gate enkel ruis geven.
        # FastAPI bewaart `response_class` als een `DefaultPlaceholder` rond de
        # klasse, niet als de klasse zelf — een identiteitsvergelijking geeft dan
        # voor élke route False en de gate scant niets meer. Precies dát gebeurde
        # bij de eerste versie hiervan, en `test_de_gate_ziet_ook_de_aanmaakschermen`
        # ving het: een gate die nergens kijkt staat groen (#678).
        soort = getattr(route, "response_class", None)
        if getattr(soort, "value", soort) is not HTMLResponse:
            continue
        paden.add(pad)
    return sorted(paden)


def _open(client, pad: str):
    """De HTML van een adminpagina, of None als ze voor deze sessie niet open gaat.

    Een 301 (`/admin/instellingen` ging op in /admin/tenants) of een 403 (tenants is
    OPERATOR-only) is geen renderfout — dat scherm bestaat gewoon niet voor deze
    gebruiker. Álles daarbuiten wél: een 404 of een 500 hoort deze gate rood te
    maken, want dan is er iets stuk.
    """
    resp = client.get(pad)
    if resp.status_code in (301, 302, 307, 308, 401, 403):
        return None
    assert resp.status_code == 200, f"{pad} → {resp.status_code}"
    return resp.text


def _paginas(ids) -> list[str]:
    detail = [f"/admin/leden/gezin/{ids['member']}",
              f"/admin/activiteiten/{ids['activity']}",
              f"/admin/inschrijvingen/{ids['registration']}",
              f"/admin/formulieren/{ids['formulier']}",
              f"/admin/paginas/{ids['pagina']}"]
    return _admin_gets_zonder_parameter() + detail


def test_geen_geescapete_attributen_op_enige_adminpagina(client, gevulde_admin):
    """De klasse die drie keer opdook (#514/#613/#616), nu op de output getoetst."""
    fouten = []
    for pad in _paginas(gevulde_admin):
        html = _open(client, pad)
        if html is None:
            continue
        for treffer in GEESCAPED.finditer(html):
            regel = html[:treffer.start()].count("\n") + 1
            fouten.append(f"{pad} (regel {regel}): {treffer.group(0)}")
    assert not fouten, (
        "Ge-escapete attributen in de gerenderde HTML — htmx ziet ze niet en de knop "
        "is inert:\n  " + "\n  ".join(fouten)
    )


def test_elk_htmx_element_heeft_een_bruikbaar_doel(client, gevulde_admin):
    """Een hx-target die niet als selector te lezen is, mislukt stil in de browser."""
    fouten = []
    for pad in _paginas(gevulde_admin):
        html = _open(client, pad)
        if html is None:
            continue
        for element in HX_ELEMENT.finditer(html):
            doel = HX_TARGET.search(element.group(0))
            if doel is None:
                continue  # geen target = het element zelf; dat is geldig htmx
            waarde = doel.group(1).strip()
            if not waarde or ("&#" in waarde):
                fouten.append(f"{pad}: onleesbaar doel {waarde!r}")
                continue
            if waarde.startswith(HX_SPECIAAL) or waarde in HX_SPECIAAL:
                continue
            if not re.match(r"^[#.\[]?[\w\-\[\]='\"#. >:()]+$", waarde):
                fouten.append(f"{pad}: doel parseert niet als selector: {waarde!r}")
                continue
            # #695: leesbaar is niet hetzelfde als bestaand. `#me-lijst` leest
            # perfect, maar het element stond alleen op de lijstpagina — en htmx
            # zoekt het doel vóórdat hij verstuurt, dus het verzoek vertrok nooit.
            # Uploaden en Annuleren deden allebei niets, en de gate zag het niet:
            # hij vroeg alleen óf de waarde als selector te lezen was.
            #
            # Alleen `#id`-doelen: die zijn eenduidig te controleren zonder een DOM
            # te bouwen, en het is de vorm die in dit project overal gebruikt wordt.
            if re.fullmatch(r"#[\w\-]+", waarde):
                if f'id="{waarde[1:]}"' not in html:
                    fouten.append(
                        f"{pad}: doel {waarde} bestaat niet op deze pagina")
    assert not fouten, (
        "Onbruikbare hx-target — htmx zoekt het doel vóór het verzoek vertrekt, dus "
        "een onvindbaar doel maakt de knop volledig inert (#695):\n  "
        + "\n  ".join(fouten))


def test_geen_hx_confirm_in_de_output(client, gevulde_admin):
    """Bevestiging gaat sinds #595 via de in-app modal; hx-confirm toont het native
    browser-confirm. De lint-gate dekt de templates, dit de gerenderde output."""
    fouten = [pad for pad in _paginas(gevulde_admin)
              if "hx-confirm" in (_open(client, pad) or "")]
    assert not fouten, f"hx-confirm in de output van: {fouten}"


def test_de_gate_dekt_alle_menu_items(client, gevulde_admin):
    """Bewaakt de bron: een nieuw menu-item wordt automatisch meegetest, en een
    scherm dat 500't valt hier op in plaats van in productie."""
    assert len(_ADMIN_NAV) >= 13
    for pad, _label in _ADMIN_NAV:
        assert client.get(pad).status_code == 200, f"{pad} rendert niet"


def test_de_gate_ziet_ook_de_aanmaakschermen(client, gevulde_admin):
    """Bewaakt de bron van de paginalijst (#695).

    De lijst kwam uit het menu plus vijf handgeschreven detailpaden, en miste
    daardoor álle zes de aanmaakschermen — precies de soort pagina die #627
    introduceerde. De controle op onvindbare doelen zou de twee kapotte schermen
    ook mét de juiste regel gemist hebben, simpelweg omdat hij ze nooit opende.

    Deze test bewaakt niet dát ze werken (dat doen de gates hierboven), maar dat ze
    in beeld zijn. Zonder haar kan de routetabel-afleiding stilletjes terug naar een
    handlijst zonder dat iets rood wordt.
    """
    gezien = set(_paginas(gevulde_admin))
    for pad in ("/admin/media/nieuw", "/admin/gebruikers/nieuw",
                "/admin/activiteiten/nieuw", "/admin/formulieren/nieuw",
                "/admin/paginas/nieuw", "/admin/leden/nieuw"):
        assert pad in gezien, f"{pad} valt buiten de rendergate"
    assert len(gezien) >= 20, (
        f"de gate ziet er nog maar {len(gezien)}; kwam de paginalijst terug uit een "
        "handgeschreven opsomming?")
