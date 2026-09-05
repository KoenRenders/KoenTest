"""#649 — een mislukte mutatie mag niet geruisloos verdwijnen.

Op HDEV stonden over een half uur negentien mislukte POST's zonder één zichtbaar
signaal: elf op een datum, zes op een nieuw onderdeel, twee op het aanmaken van
een activiteit. Allemaal 403, geen enkele 5xx, geen traceback. Op het scherm
gebeurde er niets, dus leek willekeurig beheerwerk "kapot".

Twee lagen hier; de derde (ziet de gebruiker het echt?) kan alleen een browser
bewijzen en staat in tests_e2e/test_foutzichtbaarheid.py.
"""
import time

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

SCHILLEN = ("app/ui/templates/admin_base.html", "app/ui/templates/site_base.html")


def test_token_van_een_vorige_sessie_geeft_403(client, db_session, monkeypatch):
    """De oorzaak, uitgeschreven: het token hangt aan de exacte cookiewaarde.

    `csrf_token_for(raw)` tekent de volledige cookiewaarde, en die bevat een
    vervaltijd. Log je opnieuw in, dan krijgt de cookie een andere waarde en is
    het token dat in een reeds open tabblad staat niet meer geldig — zonder dat er
    iets aan dat tabblad te zien is. Precies de situatie van Koen.

    De bestaande test dekt een *ontbrekend* token; dit is het subtielere geval van
    een token dat er wel is, er goed uitziet, en toch niet meer past.
    """
    activity, _comp, _p = seed_activity_with_product(db_session)
    from app.domains.auth import session as sessiemodule

    # Een sessie van een uur geleden: dezelfde gebruiker, andere cookiewaarde.
    monkeypatch.setattr(sessiemodule.time, "time", lambda: time.time() - 3600)
    oude_waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    monkeypatch.undo()
    nieuwe_waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    assert oude_waarde != nieuwe_waarde, "de twee sessies moeten verschillen"

    # De browser draagt de nieuwe cookie (herinlog), het tabblad het oude token.
    client.cookies.set(SESSION_COOKIE, nieuwe_waarde)
    datum = activity.dates[0]
    r = client.post(f"/admin/activiteiten/{activity.id}/datums/{datum.id}",
                    data={"start_date": "2032-03-03"},
                    headers={"X-CSRF-Token": csrf_token_for(oude_waarde)})
    assert r.status_code == 403

    # Met het token van de huidige cookie lukt dezelfde POST wél — het bewijs dat
    # niet de invoer maar de sessie het probleem was.
    ok = client.post(f"/admin/activiteiten/{activity.id}/datums/{datum.id}",
                     data={"start_date": "2032-03-03"},
                     headers={"X-CSRF-Token": csrf_token_for(nieuwe_waarde)})
    assert ok.status_code == 200


@pytest.mark.parametrize("schil", SCHILLEN)
def test_de_schil_draagt_de_foutmelding(schil):
    """De melding hoort in de kit, niet per scherm — dus in beide schillen."""
    inhoud = open(schil, encoding="utf-8").read()
    assert "htmx_ux()" in inhoud, f"{schil} mist ui.htmx_ux()"
    assert "toast_host()" in inhoud, f"{schil} mist de landingsplek van de melding"


def test_de_foutafhandeling_geldt_ook_voor_gewone_hx_posts():
    """De regressie waar het om draait.

    De handler deed vóór #649 alleen iets `if (e.detail.boosted)`. Daardoor viel
    élke gewone hx-post — dus élk bewerkformulier op élk beheerscherm — buiten de
    foutafhandeling. Deze test leest de kit en houdt vast dat de niet-gebooste tak
    er is: een statuscontrole op 401/403 en een sjabloon om de melding uit te
    klonen.
    """
    kit = open("app/ui/templates/_macros.html", encoding="utf-8").read()
    handler = kit[kit.index("htmx:responseError', function"):]
    handler = handler[:handler.index("});")]
    assert "401" in handler and "403" in handler, (
        "de foutafhandeling onderscheidt 401/403 niet meer")
    assert "boosted" in handler and "return" in handler, (
        "de gebooste tak hoort te blijven bestaan naast de gewone")
    assert 'id="htmx-foutmelding"' in kit, "het meldingssjabloon is verdwenen"


def test_een_admin_scherm_levert_het_meldingssjabloon_mee(client, db_session):
    """Van bron naar scherm: staat het sjabloon ook echt in de HTML?"""
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    r = client.get("/admin/activiteiten")
    assert r.status_code == 200
    assert 'id="htmx-foutmelding"' in r.text and 'id="toasts"' in r.text
