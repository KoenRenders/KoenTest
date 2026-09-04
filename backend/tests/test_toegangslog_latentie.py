"""Gestructureerd toegangslog en de traag-drempel (#645 A).

De duur stond in de tekst van de logregel (`"GET /x -> 200 (412.3 ms)"`). Met de
JSON-formatter is dat niet filterbaar: je kan geen "toon alles boven 300 ms"
draaien zonder de tekst te parsen. En er was geen drempel, dus een trage route
viel alleen op als iemand er toevallig naar keek.

Twee dingen worden hier vastgelegd: dat de duur als **veld** in de JSON-regel
staat, en dat de allowlist die dat regelt geen vrije dump is — een logregel mag
nooit per ongeluk een e-mailadres of querystring meedragen.
"""
import json
import logging

import pytest

from app.logging_config import EXTRA_VELDEN, JsonFormatter

pytestmark = pytest.mark.ui_agnostisch


def _regel(**extra) -> dict:
    record = logging.LogRecord("app.main", logging.INFO, __file__, 1,
                               "GET /admin/leden -> 200 (412.3 ms)", (), None)
    for k, v in extra.items():
        setattr(record, k, v)
    return json.loads(JsonFormatter().format(record))


def test_de_duur_staat_als_veld_in_de_json_regel():
    uit = _regel(duration_ms=412.3, method="GET", path="/admin/leden",
                 route="/admin/leden", status=200)

    assert uit["duration_ms"] == 412.3
    assert uit["route"] == "/admin/leden"
    assert uit["status"] == 200


def test_een_veld_zonder_waarde_komt_niet_in_de_regel():
    """`slow` is None bij een snelle request; dat hoort geen `"slow": null` te
    worden — anders staat het in élke regel."""
    uit = _regel(duration_ms=12.0, slow=None)

    assert "slow" not in uit
    assert uit["duration_ms"] == 12.0


def test_alleen_velden_uit_de_allowlist_komen_erin():
    """Geen vrije dump van record.__dict__: een logregel mag nooit per ongeluk
    persoonsgegevens meedragen."""
    uit = _regel(duration_ms=5.0, email="iemand@example.com", query="?q=jan")

    assert "email" not in uit and "query" not in uit
    assert "email" not in EXTRA_VELDEN and "query" not in EXTRA_VELDEN


def test_de_allowlist_bevat_geen_persoonsgegevens():
    """Wie een veld toevoegt, doet dat zichtbaar — en niet een dat een naam of
    adres kan bevatten."""
    verdacht = {"email", "user", "gebruiker", "naam", "name", "query", "body",
                "cookie", "session", "token"}
    assert not (verdacht & set(EXTRA_VELDEN))


def test_de_drempel_is_instelbaar_en_staat_standaard_op_300ms():
    from app.config import settings

    assert settings.slow_request_ms == 300


def test_elk_antwoord_draagt_zijn_serverduur(client):
    """X-Process-Time maakt server- en netwerkduur scheidbaar voor het meetscript."""
    antwoord = client.get("/api/health")

    assert "X-Process-Time" in antwoord.headers
    assert float(antwoord.headers["X-Process-Time"]) >= 0
