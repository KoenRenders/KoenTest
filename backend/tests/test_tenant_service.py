"""Tenants aanmaken en instellen (#635 G).

Deze regels stonden volledig inline in `app/ui/tenants_ui.py`: de slug-vorm, de
uniciteit van de code, de basis-settings, en — de gevoeligste — de "leeg laten =
ongewijzigd"-semantiek voor geheime sleutels. Een Mollie-key en een
Gmail-wachtwoord worden nooit teruggetoond, dus een leeg veld betekent "ik heb
niets ingetypt" en niet "wis dit". Zonder die regel wist elke opslag van een ander
veld stilzwijgend de sleutel waarmee de vereniging betaald wordt.

Nu los testbaar, zonder scherm.
"""
import pytest

from app.kernel.tenant_service import (TenantFout, create_tenant, list_units,
                                       secrets_gezet, update_tenant_settings)

pytestmark = pytest.mark.ui_agnostisch


def test_een_tenant_krijgt_zijn_basisinstellingen(db_session):
    org = create_tenant(db_session, name="Raak Voorbeeld", code="voorbeeld",
                        base_url="https://voorbeeld.example")

    from app.kernel.tenant_config import get_setting

    assert org.org_type == "UNIT" and org.is_active is True
    assert get_setting(db_session, "display_name", tenant_id=org.id) == "Raak Voorbeeld"
    assert get_setting(db_session, "base_url", tenant_id=org.id) == "https://voorbeeld.example"
    assert org.id in {u.id for u in list_units(db_session)}


@pytest.mark.parametrize("code", ["", "Met Hoofdletters", "met_underscore",
                                  "met spatie", "ümlaut"])
def test_een_ongeldige_code_wordt_geweigerd(db_session, code):
    """De code is de sleutel waarmee een verzoek naar zijn tenant resolvet."""
    with pytest.raises(TenantFout):
        create_tenant(db_session, name="Naam", code=code)


def test_een_lege_naam_wordt_geweigerd(db_session):
    with pytest.raises(TenantFout):
        create_tenant(db_session, name="   ", code="geldig")


def test_dezelfde_code_kan_niet_twee_keer(db_session):
    create_tenant(db_session, name="Eerste", code="dubbel")
    with pytest.raises(TenantFout):
        create_tenant(db_session, name="Tweede", code="dubbel")


# ── Instellingen ─────────────────────────────────────────────────────────────

GEHEIM = ["mollie_api_key"]
GEWOON = ["tagline"]


def _tenant(db):
    return create_tenant(db, name="Instelbaar", code="instelbaar").id


def test_een_geheime_sleutel_blijft_staan_als_het_veld_leeg_is(db_session):
    """De regel die geld kost als ze wegvalt."""
    tenant = _tenant(db_session)
    update_tenant_settings(db_session, tenant, {"mollie_api_key": "live_geheim"},
                           known=GEWOON, secret=GEHEIM)
    assert secrets_gezet(db_session, tenant, GEHEIM) == {"mollie_api_key": True}

    # Iemand slaat het scherm opnieuw op zonder de sleutel opnieuw in te typen.
    update_tenant_settings(db_session, tenant, {"mollie_api_key": "", "tagline": "Nieuw"},
                           known=GEWOON, secret=GEHEIM)

    assert secrets_gezet(db_session, tenant, GEHEIM) == {"mollie_api_key": True}


def test_wissen_gebeurt_expliciet(db_session):
    tenant = _tenant(db_session)
    update_tenant_settings(db_session, tenant, {"mollie_api_key": "live_geheim"},
                           known=GEWOON, secret=GEHEIM)

    update_tenant_settings(db_session, tenant, {"mollie_api_key_wissen": "1"},
                           known=GEWOON, secret=GEHEIM)

    assert secrets_gezet(db_session, tenant, GEHEIM) == {"mollie_api_key": False}


def test_een_gewone_sleutel_mag_wel_leeggemaakt_worden(db_session):
    """Daar betekent leeg wél leeg: de waarde staat op het scherm, dus wie hem
    weghaalt, bedoelt dat."""
    from app.kernel.tenant_config import get_setting

    tenant = _tenant(db_session)
    update_tenant_settings(db_session, tenant, {"tagline": "Iets"},
                           known=GEWOON, secret=GEHEIM)
    assert get_setting(db_session, "tagline", tenant_id=tenant) == "Iets"

    update_tenant_settings(db_session, tenant, {"tagline": ""},
                           known=GEWOON, secret=GEHEIM)
    assert not get_setting(db_session, "tagline", tenant_id=tenant)


def test_het_scherm_raakt_de_sessie_niet_meer_aan():
    """#635 regel 2 voor dit scherm: geen enkele db.<iets> in tenants_ui."""
    import ast
    from pathlib import Path

    bron = (Path(__file__).resolve().parents[1] / "app" / "ui" / "tenants_ui.py")
    boom = ast.parse(bron.read_text())
    gebruik = [f"db.{n.attr}" for n in ast.walk(boom)
               if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
               and n.value.id == "db"]
    assert not gebruik, gebruik
