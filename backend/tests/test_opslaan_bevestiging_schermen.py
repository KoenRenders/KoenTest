"""#742 — vier beheerschermen bevestigen een geslaagde opslag met een toast.

`ui.toast()` werd in de hele app precies één keer aangeroepen: #717, op het
inschrijvingspaneel. Vier schermen die op dezelfde manier bewaren hadden hem niet —
je klikte Opslaan, het scherm werd opnieuw opgebouwd, en verder zei niets je of het
gelukt was.

`docs/ui-conventies.md` §2.9: na een geslaagde opslag blijf je waar je bent, met een
toast. Eén formulering voor de hele app, via `ui.toast_oob()`; twee bevestigings-
teksten naast elkaar is precies de inconsistentie die de conventie wegneemt.

**De tweede test per scherm is de belangrijkste.** Bij een fout hoort de foutbanner
te blijven en de toast weg te blijven — anders bevestigt het scherm iets wat niet
gebeurd is. Zonder die helft staat de eerste test ook groen wanneer je de toast
onvoorwaardelijk meestuurt.

Servertests volstaan hier: dát htmx het oob-element oppikt en in `#toasts` laat
landen is bij #717 met een e2e bewezen, en dat hoeft geen vier keer.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal): per
scherm `toast=True` teruggezet op de standaard → de eerste test van dat scherm valt
om; `toast_opgeslagen` onvoorwaardelijk op True in het sjabloon → de tweede valt om.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, seed_postal_code

pytestmark = pytest.mark.ui_serverrendered

# Het contract uit ui.toast_oob(): de aanroeper hangt dit attribuut aan de wikkel.
OOB = 'hx-swap-oob="afterbegin:#toasts"'


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": waarde and csrf_token_for(waarde), "HX-Request": "true"}


def _operator(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "OPERATOR" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.flush()


# ── CMS-pagina ───────────────────────────────────────────────────────────────

def _pagina(db):
    from app.domains.cms.models import CmsPage

    pagina = CmsPage(slug="toast-test", title="Toasttest", share_token=None,
                     content="<p>hoi</p>") if False else CmsPage(
        slug="toast-test", title="Toasttest", content="<p>hoi</p>")
    db.add(pagina)
    db.flush()
    return pagina


def test_een_pagina_opslaan_bevestigt(client, db_session):
    pagina = _pagina(db_session)
    hdr = _login(client)

    resp = client.post(f"/admin/paginas/{pagina.id}", headers=hdr, data={
        "title": "Toasttest", "slug": "toast-test", "content": "<p>hoi</p>",
        "sort_order": "0"})

    assert resp.status_code == 200, resp.text
    assert OOB in resp.text, "een geslaagde opslag zegt niets"


def test_een_pagina_openen_bevestigt_niets(client, db_session):
    """De tegenhanger: zonder haar bevestigt het scherm bij élke render."""
    pagina = _pagina(db_session)
    hdr = _login(client)

    resp = client.get(f"/admin/paginas/{pagina.id}", headers=hdr)

    assert OOB not in resp.text


# ── Activiteit ───────────────────────────────────────────────────────────────

def _activiteit(client, db, admin_headers):
    from datetime import date, timedelta

    resp = client.post("/api/v1/activities", headers=admin_headers, json={
        "name": "Toastactiviteit",
        "dates": [{"start_date": (date.today() + timedelta(days=30)).isoformat()}]})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_een_activiteit_opslaan_bevestigt(client, db_session, admin_headers):
    activity_id = _activiteit(client, db_session, admin_headers)
    hdr = _login(client)

    resp = client.post(f"/admin/activiteiten/{activity_id}", headers=hdr,
                       data={"name": "Toastactiviteit", "location": "Zaal"})

    assert resp.status_code == 200, resp.text
    assert OOB in resp.text


def test_een_deelactie_op_de_activiteit_bevestigt_niet(client, db_session,
                                                       admin_headers):
    """De grens uit #717: een datum toevoegen is geen afsluitende opslag."""
    activity_id = _activiteit(client, db_session, admin_headers)
    hdr = _login(client)

    resp = client.post(f"/admin/activiteiten/{activity_id}/datums", headers=hdr,
                       data={"start_date": "2030-05-05"})

    assert resp.status_code == 200, resp.text
    assert OOB not in resp.text, "een deelactie hoort niet te bevestigen"


# ── Gezin ────────────────────────────────────────────────────────────────────

def test_een_persoon_opslaan_bevestigt(client, db_session):
    """De afsluitende "Opslaan" van een gezinslid."""
    member, person = create_test_family(db_session, email="toast@example.com")
    hdr = _login(client)

    resp = client.post(f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
                       headers=hdr, data={
                           "first_name": person.first_name,
                           "last_name": person.last_name,
                           "date_of_birth": person.date_of_birth.isoformat(),
                           "gender_code": "M", "relation_type": "HOOFDLID"})

    assert resp.status_code == 200, resp.text
    assert OOB in resp.text


def test_een_gezin_openen_bevestigt_niets(client, db_session):
    member, _person = create_test_family(db_session, email="toast2@example.com")
    hdr = _login(client)

    resp = client.get(f"/admin/leden/gezin/{member.id}", headers=hdr)

    assert OOB not in resp.text


# ── Tenant ───────────────────────────────────────────────────────────────────

def test_tenantinstellingen_opslaan_bevestigt(client, db_session):
    """#748: hier staat de toast ÍN de host, niet als out-of-band broer ernaast.

    Dit scherm stuurt een volledige pagina terug (`hx-target="body"`), en dan wordt
    de host zelf mee vervangen — een oob-toast wordt geplaatst en meteen weggegooid.
    Gemeten in een browser: nul kinderen in `#toasts`.

    Deze servertest kan dat verschil niet zien; hij kijkt of de bevestiging op de
    JUISTE plek staat. Dat ze ook echt zichtbaar wordt, toetst
    `tests_e2e/test_tenant_toast.py`.
    """
    from app.domains.mdm.api import list_units

    _operator(db_session)
    hdr = _login(client)
    tenant = list_units(db_session, alleen_actief=False)[0]

    resp = client.post(f"/admin/tenants/{tenant.id}", headers=hdr,
                       data={"site_name": "Raak"})

    assert resp.status_code == 200, resp.text
    assert OOB not in resp.text, (
        "een out-of-band toast overleeft een body-swap niet (#748)")
    host = resp.text[resp.text.index('id="toasts"'):]
    assert "Opgeslagen" in host[:600], "de bevestiging staat niet in de host"


def test_de_tenant_editor_openen_bevestigt_niets(client, db_session):
    from app.domains.mdm.api import list_units

    _operator(db_session)
    hdr = _login(client)
    tenant = list_units(db_session, alleen_actief=False)[0]

    resp = client.get(f"/admin/tenants/{tenant.id}", headers=hdr)

    assert OOB not in resp.text
