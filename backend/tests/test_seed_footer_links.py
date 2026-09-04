"""Seed van de footer-links van Raak Millegem (#612).

De links zijn sinds v2.0.0 tenant-instellingen met "leeg = niet tonen" (#519/#493)
en stonden in v1.14 hardgecodeerd in de React-footer — er valt dus niets te
migreren. Zonder seed toont elke verse omgeving een footer zonder iconen en zonder
privacylink.

De invariant die telt is niet "de waarden staan er", maar dat het scherm daarna de
baas blijft: de seed draait één keer per omgeving en mag nooit iets terugzetten wat
iemand bewust heeft aangepast of leeggemaakt.
"""
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID
from app.kernel.tenant_config import get_setting, set_setting

from seed_tenant_settings import FOOTER_LINKS, MARKER, seed_footer_links


def _millegem(db, key):
    return get_setting(db, key, tenant_id=TENANT_MILLEGEM_ID)


def test_seed_vult_de_vier_links_en_zet_de_marker(db_session):
    gezet = seed_footer_links(db_session)

    assert sorted(gezet) == sorted(FOOTER_LINKS)
    for key, waarde in FOOTER_LINKS.items():
        assert _millegem(db_session, key) == waarde
    assert _millegem(db_session, MARKER) == "1"


def test_tweede_aanroep_doet_niets(db_session):
    seed_footer_links(db_session)
    assert seed_footer_links(db_session) is None


def test_een_handmatig_ingevulde_waarde_wordt_niet_overschreven(db_session):
    """Wat via /admin/tenants is ingesteld, blijft staan."""
    set_setting(db_session, "facebook_url", "https://facebook.com/eigen-pagina",
                tenant_id=TENANT_MILLEGEM_ID)
    db_session.commit()

    gezet = seed_footer_links(db_session)

    assert "facebook_url" not in gezet
    assert _millegem(db_session, "facebook_url") == "https://facebook.com/eigen-pagina"
    assert _millegem(db_session, "tiktok_url") == FOOTER_LINKS["tiktok_url"]


def test_leeggemaakt_na_de_seed_blijft_leeg(db_session):
    """De hele reden voor de marker: stopt Raak met TikTok, dan mag dat icoon niet
    bij elke deploy terugkomen."""
    seed_footer_links(db_session)
    set_setting(db_session, "tiktok_url", "", tenant_id=TENANT_MILLEGEM_ID)
    db_session.commit()

    seed_footer_links(db_session)

    assert _millegem(db_session, "tiktok_url") == ""


def test_andere_tenants_krijgen_niets(db_session):
    """Alleen Millegem — de voorbeeldafdeling heeft deze profielen niet."""
    seed_footer_links(db_session)

    for key in FOOTER_LINKS:
        assert not get_setting(db_session, key, tenant_id=TENANT_VOORBEELD_ID)
    assert not get_setting(db_session, MARKER, tenant_id=TENANT_VOORBEELD_ID)


def test_seed_draait_bij_elke_opstart(db_session):
    """startup.sh roept het script niet-fataal aan, net als de sponsors."""
    from pathlib import Path
    startup = (Path(__file__).resolve().parents[1] / "startup.sh").read_text()
    assert "python seed_tenant_settings.py" in startup
    assert "non-fatal" in startup.split("seed_tenant_settings.py")[1].split("\n")[0]
