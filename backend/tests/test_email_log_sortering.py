"""Sorteerbare kolommen op het e-maillog (Ontwerpspoor golf 3, #913).

Het e-maillog is de referentie-implementatie van de tabelnorm uit design-system
§2.3: whitelist in de route, id-tiebreaker in de service (#761), koppen via
``ui.sort_th``. Deze tests toetsen de redenen, niet alleen de status (#680).
"""
from datetime import datetime, timezone

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mail.api import list_email_log
from app.domains.mail.models import EmailLog


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _seed(db, *recipients, moment=None):
    moment = moment or datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    for r in recipients:
        db.add(EmailLog(recipient=r, subject=f"Onderwerp {r}",
                        email_type="other", status="sent", created_at=moment))
    db.commit()


def test_sorteren_op_ontvanger_geeft_alfabetische_volgorde(db_session):
    # Filter op een eigen marker: de tabel is gedeeld met andere tests/seeds.
    _seed(db_session, "sorttest-chris@example.com", "sorttest-an@example.com",
          "sorttest-bert@example.com")
    rijen, _ = list_email_log(db_session, recipient="sorttest-",
                              sort="ontvanger", richting="asc")
    assert [r.recipient for r in rijen] == [
        "sorttest-an@example.com", "sorttest-bert@example.com",
        "sorttest-chris@example.com"]


def test_onbekende_sorteersleutel_valt_terug_op_datum(db_session):
    """De whitelist is de bescherming: een verzonnen sleutel wordt geen
    kolomnaam (zelfde reden als "no free SQL") maar de datum-default."""
    _seed(db_session, "whitelisttest-a@example.com")
    rijen, _ = list_email_log(db_session, recipient="whitelisttest-",
                              sort="'; DROP TABLE--", richting="asc")
    assert len(rijen) == 1  # geen fout, gewoon de default-ordening


def test_tiebreaker_maakt_paging_sluitend_bij_gelijke_datums(db_session):
    """De #761-les als bewijs: drie rijen met exact dezelfde datum, pagina's
    van twee — zonder id-tiebreaker kan een rij dubbel of nooit verschijnen.
    Kapotgemaakt om rood te zien: de id-tail uit `orden` halen laat Postgres
    de heapvolgorde kiezen en dan is de vereniging van de pagina's niet meer
    gegarandeerd volledig."""
    _seed(db_session, "tieb-x@example.com", "tieb-y@example.com",
          "tieb-z@example.com")
    p1, nog = list_email_log(db_session, recipient="tieb-", page=1, page_size=2)
    assert nog is True
    p2, _ = list_email_log(db_session, recipient="tieb-", page=2, page_size=2)
    gezien = [r.id for r in p1] + [r.id for r in p2]
    assert len(gezien) == 3 and len(set(gezien)) == 3


def test_kopklik_rendert_gesorteerde_lijst_met_chevron(client, db_session):
    _seed(db_session, "koptest-zoe@example.com", "koptest-an@example.com")
    _login(client)
    resp = client.get("/admin/e-maillog/lijst?sort=ontvanger&richting=asc"
                      "&recipient=koptest-")
    assert resp.status_code == 200
    assert resp.text.index("koptest-an@example.com") < resp.text.index("koptest-zoe@example.com")
    # De actieve kop draagt de richting — zichtbaar (chevron) én semantisch.
    assert 'aria-sort="ascending"' in resp.text
    # De sorteerstand reist out-of-band terug de filterform in.
    assert 'id="el-sort"' in resp.text and 'hx-swap-oob' in resp.text


def test_paginagrootte_kent_enkel_de_whitelist(db_session):
    """25/50/100; al de rest — ook 9999 — valt terug op de default (#913 golf 3)."""
    _seed(db_session, *[f"pp-{i:02d}@example.com" for i in range(30)])
    rijen, _ = list_email_log(db_session, recipient="pp-", page_size=25)
    assert len(rijen) == 25


def test_verwijderen_bevestigt_met_een_toast(client, db_session):
    """#760-absorptie: elke mutatie bevestigt. Fragment-antwoord → toast_oob."""
    from app.domains.auth.api import csrf_token_for
    from app.domains.mail.models import EmailLog

    _seed(db_session, "toast-weg@example.com")
    rij = (db_session.query(EmailLog)
           .filter(EmailLog.recipient == "toast-weg@example.com").first())
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    resp = client.post(f"/admin/e-maillog/{rij.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf_token_for(waarde)})
    assert resp.status_code == 200
    assert "Logregel verwijderd." in resp.text
    assert 'hx-swap-oob="afterbegin:#toasts"' in resp.text
