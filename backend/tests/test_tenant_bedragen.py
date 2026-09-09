"""#797 — een komma in een tenant-bedrag mag de site niet platleggen.

Op UAT werd bij `membership_price_half` de waarde `17,5` ingevuld: de Belgische
notatie, en precies wat de applicatie zélf toont (`€ 17,50`). Daarna gaf **elke**
publieke pagina een 500 — ook de homepage, want `tenant_membership_config` hangt
onder `site_context` en `Decimal("17,5")` gooit `InvalidOperation`.

Twee lagen, en ze vervangen elkaar niet:

- **bij het opslaan** hoort een bedragveld alleen een bedrag te aanvaarden, mét de
  komma. De gebruiker corrigeren voor de notatie van zijn eigen taal is de
  verkeerde kant op, dus we normaliseren naar het punt dat `Decimal` verwacht;
- **bij het lezen** mag één onleesbare instelling de site niet omleggen. Dat pad
  hoort na de eerste laag onbereikbaar te zijn via het scherm, maar instellingen
  zijn door mensen te bewerken data — een import, een handmatige insert of een
  oudere rij komt er niet langs het formulier in.

De leestest zet de waarde daarom **rechtstreeks in de databank**. Ging ze via het
formulier, dan toetste ze de validatie van de eerste laag nog een keer en zou het
vangnet ongetest blijven.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de
`BEDRAG_SLEUTELS`-controle uit `update_tenant_settings` gehaald → de opslagtests
vallen om; `_bedrag()` in `tenant_config.py` terug op `Decimal(str(...))` → de
homepage-test valt om met een 500.
"""
import logging

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value)

pytestmark = pytest.mark.ui_serverrendered


def _operator(client, db_session, email="op-bedrag@example.com"):
    u = User(email=email, is_active=True)
    db_session.add(u)
    db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_code="OPERATOR"))
    db_session.flush()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _tenant_id(db_session) -> int:
    from app.domains.mdm.api import list_units

    return list_units(db_session)[0].id


def _opslaan(client, csrf, tenant_id, **velden):
    return client.post(f"/admin/tenants/{tenant_id}", data=velden,
                       headers={"X-CSRF-Token": csrf})


def test_een_komma_wordt_aanvaard_en_genormaliseerd(client, db_session):
    """`17,50` hoort gewoon te werken — dat is de notatie die het scherm toont."""
    from app.kernel.tenant_config import get_setting, tenant_membership_config

    csrf = _operator(client, db_session)
    tid = _tenant_id(db_session)

    resp = _opslaan(client, csrf, tid, membership_price_half="17,50")

    assert resp.status_code == 200, resp.text[:500]
    db_session.expire_all()
    assert get_setting(db_session, "membership_price_half", tenant_id=tid) == "17.50", (
        "de komma is niet genormaliseerd; dan struikelt Decimal er later alsnog over")
    from decimal import Decimal
    assert tenant_membership_config(db_session, tid)["price_half"] == Decimal("17.50")


def test_onzin_wordt_geweigerd_en_bereikt_de_databank_niet(client, db_session):
    """De melding noemt het veld, want een scherm met twintig velden en 'er ging iets
    mis' is precies wat de storing zo duur maakte."""
    from app.kernel.tenant_config import get_setting

    csrf = _operator(client, db_session)
    tid = _tenant_id(db_session)

    resp = _opslaan(client, csrf, tid, membership_price_half="zeventien euro")

    assert resp.status_code == 422
    assert "Lidgeld half" in resp.text, "de melding wijst het veld niet aan"
    db_session.expire_all()
    assert get_setting(db_session, "membership_price_half", tenant_id=tid) is None, (
        "de onleesbare waarde staat tóch in de databank")


def test_de_ingetypte_waarden_blijven_staan_na_een_fout(client, db_session):
    """Anders veegt één tikfout het hele scherm leeg en is de melding erger dan de fout."""
    csrf = _operator(client, db_session)
    tid = _tenant_id(db_session)

    resp = _opslaan(client, csrf, tid, display_name="Raak Voorbeeld",
                    membership_price_half="fout")

    assert resp.status_code == 422
    assert "Raak Voorbeeld" in resp.text


def test_een_geheel_getalveld_weigert_een_bedrag(client, db_session):
    """`payment_term_days` is een aantal dagen; `7,5` hoort daar niet in."""
    csrf = _operator(client, db_session)
    tid = _tenant_id(db_session)

    resp = _opslaan(client, csrf, tid, payment_term_days="7,5")

    assert resp.status_code == 422
    assert "Betaaltermijn" in resp.text


def test_niets_wordt_geschreven_als_een_ander_veld_faalt(client, db_session):
    """Alles-of-niets. Half opgeslagen is verwarrender dan niet opgeslagen: dan klopt
    het scherm niet meer met de databank en weet je niet welke helft je opnieuw moet
    intypen."""
    from app.kernel.tenant_config import get_setting

    csrf = _operator(client, db_session)
    tid = _tenant_id(db_session)

    _opslaan(client, csrf, tid, display_name="Wel geldig", membership_price_half="fout")

    db_session.expire_all()
    assert get_setting(db_session, "display_name", tenant_id=tid) is None, (
        "het geldige veld is geschreven terwijl een ander veld faalde")


def test_een_onleesbare_waarde_in_de_databank_legt_de_homepage_niet_plat(
        client, db_session, caplog):
    """Het vangnet. De waarde gaat RECHTSTREEKS in de databank — via het formulier
    zou hij nu geweigerd worden en toetsen we de eerste laag opnieuw."""
    from app.config import settings
    from app.kernel.tenant_config import set_setting, tenant_membership_config

    tid = _tenant_id(db_session)
    set_setting(db_session, "membership_price_half", "17,5", tenant_id=tid)
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        config = tenant_membership_config(db_session, tid)
        resp = client.get("/")

    assert resp.status_code == 200, "de homepage valt om op één tenant-instelling"
    from decimal import Decimal
    assert config["price_half"] == Decimal(str(settings.membership_price_half)), (
        "er wordt niet teruggevallen op de omgevingswaarde")
    assert any("membership_price_half" in r.getMessage() for r in caplog.records), (
        "de waarschuwing noemt de sleutel niet; dan blijft zoeken in twintig velden")
