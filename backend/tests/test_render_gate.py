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
    from app.domains.payment.api import PaymentRecord
    from app.domains.activities.api import Registration, RegistrationItem

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
    db_session.commit()

    _login(client, db_session)
    return {"member": member.id, "activity": activity.id, "registration": reg_id}


def _paginas(ids) -> list[str]:
    detail = [f"/admin/leden/gezin/{ids['member']}",
              f"/admin/activiteiten/{ids['activity']}",
              f"/admin/inschrijvingen/{ids['registration']}"]
    return [href for href, _label in _ADMIN_NAV] + detail


def test_geen_geescapete_attributen_op_enige_adminpagina(client, gevulde_admin):
    """De klasse die drie keer opdook (#514/#613/#616), nu op de output getoetst."""
    fouten = []
    for pad in _paginas(gevulde_admin):
        resp = client.get(pad)
        assert resp.status_code == 200, f"{pad} → {resp.status_code}"
        for treffer in GEESCAPED.finditer(resp.text):
            regel = resp.text[:treffer.start()].count("\n") + 1
            fouten.append(f"{pad} (regel {regel}): {treffer.group(0)}")
    assert not fouten, (
        "Ge-escapete attributen in de gerenderde HTML — htmx ziet ze niet en de knop "
        "is inert:\n  " + "\n  ".join(fouten)
    )


def test_elk_htmx_element_heeft_een_bruikbaar_doel(client, gevulde_admin):
    """Een hx-target die niet als selector te lezen is, mislukt stil in de browser."""
    fouten = []
    for pad in _paginas(gevulde_admin):
        html = client.get(pad).text
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
    assert not fouten, "Onbruikbare hx-target:\n  " + "\n  ".join(fouten)


def test_geen_hx_confirm_in_de_output(client, gevulde_admin):
    """Bevestiging gaat sinds #595 via de in-app modal; hx-confirm toont het native
    browser-confirm. De lint-gate dekt de templates, dit de gerenderde output."""
    fouten = [pad for pad in _paginas(gevulde_admin)
              if "hx-confirm" in client.get(pad).text]
    assert not fouten, f"hx-confirm in de output van: {fouten}"


def test_de_gate_dekt_alle_menu_items(client, gevulde_admin):
    """Bewaakt de bron: een nieuw menu-item wordt automatisch meegetest, en een
    scherm dat 500't valt hier op in plaats van in productie."""
    assert len(_ADMIN_NAV) >= 13
    for pad, _label in _ADMIN_NAV:
        assert client.get(pad).status_code == 200, f"{pad} rendert niet"
