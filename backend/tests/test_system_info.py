"""#156 — admin Systeeminfo: gecureerde whitelist, nooit secrets.

Invarianten:
- het endpoint is admin-gated (geen toegang zonder geldige admin-token);
- de respons bevat GEEN secret-waarde (SECRET_KEY, DB-URL met wachtwoord,
  Mollie-key, Gmail-app-password) — bescherming tegen per-ongeluk lekken;
- Mollie wordt enkel als modus-label getoond, nooit de sleutel zelf.
"""

import json

from app.config import settings


def test_system_info_contains_no_secrets():
    """What the system screen reads (`app.ui.admin_api.get_system_info`)."""
    from app.ui.admin_api import get_system_info

    body = get_system_info()
    blob = json.dumps(body)

    # Geen enkele secret-waarde mag in de payload zitten.
    for secret in (settings.secret_key, settings.mollie_api_key, settings.gmail_app_password):
        if secret:
            assert secret not in blob
    # De DB-URL (kan een wachtwoord bevatten) mag nergens in de respons staan.
    assert settings.database_url not in blob

    # Mollie wordt als label getoond, niet als sleutel.
    assert body["mollie_mode"] in ("live", "test", "onbekend", "niet geconfigureerd")

    # Kernvelden aanwezig.
    assert body["version"]
    assert body["environment"]
