"""#662 — de drie CSRF-403's zijn uit elkaar te houden in het log.

Dit issue lost bewust niets op. De meting op HDEV sluit de verklaring uit die de
melding van #649 geeft: over drie uur vier 403's op vier verschillende endpoints
die alle vier óók 200 gaven, 101 geslaagde requests, nul aanmeldingen, op elke
adminpagina een geldig token van 64 tekens, en een vaste SECRET_KEY. "Herinlog in
een ander venster" verklaart dat niet.

`require_csrf` gaf drie wezenlijk verschillende situaties dezelfde 403: geen
cookie, geen header, of een mismatch. Elk vraagt een andere oplossing. Zolang je
niet weet wélke het is, is elke fix een gok — en een fix bovenop een onbekende
oorzaak maskeert het symptoom.

Wat hier NIET gebeurt: de statuscode, de gebruikersmelding en het gedrag blijven
gelijk. En de tokenwaarde wordt nooit gelogd, ook niet afgekort.
"""
import logging

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product


def _pad(activity, datum):
    return f"/admin/activiteiten/{activity.id}/datums/{datum.id}"


def _reden(caplog):
    """Het csrf_fail-veld uit de logregel, of None."""
    for record in caplog.records:
        if hasattr(record, "csrf_fail"):
            return record.csrf_fail
    return None


def test_zonder_sessiecookie_no_cookie(client, db_session, caplog):
    activity, _c, _p = seed_activity_with_product(db_session)
    datum = activity.dates[0]
    with caplog.at_level(logging.WARNING, logger="app.auth.csrf"):
        r = client.post(_pad(activity, datum), data={"start_date": "2032-01-01"},
                        headers={"X-CSRF-Token": "wat dan ook"})
    assert r.status_code == 403
    assert _reden(caplog) == "no_cookie"


def test_zonder_header_no_header(client, db_session, caplog):
    activity, _c, _p = seed_activity_with_product(db_session)
    datum = activity.dates[0]
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    with caplog.at_level(logging.WARNING, logger="app.auth.csrf"):
        r = client.post(_pad(activity, datum), data={"start_date": "2032-01-01"})
    assert r.status_code == 403
    assert _reden(caplog) == "no_header"


def test_lege_header_apart_van_een_mismatch(client, db_session, caplog):
    """Een lege header is iets anders dan een verkeerde: dan levert de pagina het
    token niet, in plaats van dat het bij een andere sessie hoort."""
    activity, _c, _p = seed_activity_with_product(db_session)
    datum = activity.dates[0]
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    with caplog.at_level(logging.WARNING, logger="app.auth.csrf"):
        r = client.post(_pad(activity, datum), data={"start_date": "2032-01-01"},
                        headers={"X-CSRF-Token": ""})
    assert r.status_code == 403
    assert _reden(caplog) == "empty_header"


def test_token_van_een_andere_sessie_mismatch(client, db_session, caplog):
    activity, _c, _p = seed_activity_with_product(db_session)
    datum = activity.dates[0]
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    with caplog.at_level(logging.WARNING, logger="app.auth.csrf"):
        r = client.post(_pad(activity, datum), data={"start_date": "2032-01-01"},
                        headers={"X-CSRF-Token": csrf_token_for("een andere sessie")})
    assert r.status_code == 403
    assert _reden(caplog) == "mismatch"


def test_het_token_staat_nooit_in_het_log(client, db_session, caplog):
    """De regel die niet mag verschuiven: deze logs worden opgehaald met
    `raak fetch`, dus een beveiligingstoken hoort er nooit in — ook niet afgekort."""
    activity, _c, _p = seed_activity_with_product(db_session)
    datum = activity.dates[0]
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    geldig = csrf_token_for(waarde)
    vreemd = csrf_token_for("een andere sessie")
    with caplog.at_level(logging.WARNING, logger="app.auth.csrf"):
        client.post(_pad(activity, datum), data={"start_date": "2032-01-01"},
                    headers={"X-CSRF-Token": vreemd})
    tekst = "\n".join(r.getMessage() + str(getattr(r, "csrf_fail", ""))
                      for r in caplog.records)
    for stuk in (geldig, vreemd, waarde):
        assert stuk not in tekst, "een tokenwaarde staat in het log (#662)"
        assert stuk[:12] not in tekst, "een afgekorte tokenwaarde staat in het log"


def test_een_geldig_token_logt_niets(client, db_session, caplog):
    """Geen ruis op de gelukte weg."""
    activity, _c, _p = seed_activity_with_product(db_session)
    datum = activity.dates[0]
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    with caplog.at_level(logging.WARNING, logger="app.auth.csrf"):
        r = client.post(_pad(activity, datum), data={"start_date": "2032-01-01"},
                        headers={"X-CSRF-Token": csrf_token_for(waarde)})
    assert r.status_code == 200
    assert _reden(caplog) is None


def test_csrf_fail_mag_in_een_json_logregel(caplog):
    """De allowlist van de JsonFormatter is bewust smal; dit veld hoort erin."""
    from app.logging_config import EXTRA_VELDEN, JsonFormatter

    assert "csrf_fail" in EXTRA_VELDEN
    record = logging.LogRecord("app.auth.csrf", logging.WARNING, "x", 1,
                               "CSRF-controle geweigerd", None, None)
    record.csrf_fail = "mismatch"
    regel = JsonFormatter().format(record)
    assert '"csrf_fail": "mismatch"' in regel
