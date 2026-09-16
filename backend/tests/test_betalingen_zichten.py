"""Golf 10 (#913): de statustabs (zichten) op de betalingenlijst.

Een zicht is een afgeleide doorsnede naast de statuskolom (#669 blijft gelden:
ze combineren met EN). De tab-aantallen tellen over de zicht-loze basis; de
export draagt het actieve zicht mee, anders exporteert "Openstaand" stil alles.
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
from decimal import Decimal

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.payment.api import PaymentRecord


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _drie_boekingen(db):
    """Eén open vordering (Anna), één vereffende (Bram), één open refund (Cleo)."""
    db.add(PaymentRecord(payable_type="registration", payable_id=9001,
                         amount=Decimal("20.00"), method="transfer",
                         status="pending", type="charge"))
    # 17,53 en niet 15,00: de totaalrij van de openstaande export is toevallig
    # net 20,00 − 5,00 = 15,00, en dan bewijst "15,00 afwezig" niets meer.
    db.add(PaymentRecord(payable_type="registration", payable_id=9002,
                         amount=Decimal("17.53"), amount_paid=Decimal("17.53"),
                         method="online", status="paid", type="charge"))
    db.add(PaymentRecord(payable_type="registration", payable_id=9003,
                         amount=Decimal("-5.00"), method="transfer",
                         status="pending", type="refund"))
    db.commit()


def test_zicht_openstaand_snijdt_de_tabel(client, db_session):
    """Rood bewezen bij de bouw: zonder de apply_zicht-stap toonde elk tab
    dezelfde drie boekingen."""
    _drie_boekingen(db_session)
    _login(client)

    # Op de RIJ-links getoetst en niet op bedragen: de kengetallenband telt
    # bewust over de zicht-loze basis, dus elk bedrag staat ook op elk tab.
    def _rijen(zicht):
        html = client.get(f"/admin/betalingen/lijst?zicht={zicht}").text
        return {n for n in (9001, 9002, 9003)
                if f"/admin/inschrijvingen/{n}?" in html}

    assert _rijen("alle") == {9001, 9002, 9003}
    assert _rijen("openstaand") == {9001, 9003}   # open vordering + open refund
    assert _rijen("betaald") == {9002}
    assert _rijen("terugbetaald") == {9003}


def test_tabaantallen_tellen_over_de_zichtloze_basis(client, db_session):
    """Op het Betaald-tab blijven de andere tabs hun eigen aantal dragen —
    zouden ze over de gesneden set tellen, dan stond overal hetzelfde getal."""
    _drie_boekingen(db_session)
    _login(client)

    html = client.get("/admin/betalingen/lijst?zicht=betaald").text
    for stuk in (">Alle <", ">Openstaand <", ">Betaald <", ">Terugbetaald <"):
        assert stuk in html
    # 3 boekingen totaal, 2 open (vordering + refund), 1 vereffend, 1 refund.
    from app.domains.payment.api import count_zichten, enriched_records
    telling = count_zichten(enriched_records(db_session))
    assert (telling["alle"], telling["openstaand"],
            telling["betaald"], telling["terugbetaald"]) == (3, 2, 1, 1)


def test_zicht_combineert_met_de_statuskolom(client, db_session):
    """#669 blijft overeind: het Openstaand-tab en de statuskeuzelijst zijn
    twee dimensies en combineren met EN — open posten onder de mislukte
    betalingen blijft een stelbare vraag."""
    _drie_boekingen(db_session)
    db_session.add(PaymentRecord(payable_type="registration", payable_id=9004,
                                 amount=Decimal("40.00"), method="transfer",
                                 status="failed", type="charge"))
    db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst?zicht=openstaand&status=failed").text
    assert "/admin/inschrijvingen/9004?" in html
    assert "/admin/inschrijvingen/9001?" not in html


def test_oude_openstaand_link_landt_op_het_tab(client, db_session):
    """Bestaande links en export-URL's met openstaand=1 blijven hetzelfde
    tonen: ze vallen op het Openstaand-tab terug."""
    _drie_boekingen(db_session)
    _login(client)

    html = client.get("/admin/betalingen/lijst?openstaand=1").text
    assert 'name="zicht" value="openstaand"' in html
    assert "/admin/inschrijvingen/9002?" not in html


def test_zicht_overleeft_een_filterwissel(client, db_session):
    """Het verborgen veld hoort via het form-attribuut bij de filterbalk: bij
    de eerstvolgende zoekterm reist het actieve tab mee in plaats van stil op
    "Alle" terug te vallen."""
    _drie_boekingen(db_session)
    _login(client)

    html = client.get("/admin/betalingen/lijst?zicht=betaald").text
    assert '<input type="hidden" name="zicht" value="betaald" form="bt-filter">' in html


def test_export_draagt_het_zicht(client, db_session):
    """Rood zonder de zicht-parameter in de exportbouwer: dan exporteert het
    Openstaand-tab stil ook de vereffende boekingen."""
    from app.domains.payment.exports import build_payments_export_ods

    _drie_boekingen(db_session)
    _login(client)

    resp = client.get("/admin/betalingen/export?zicht=openstaand")
    assert resp.status_code == 200
    # De .ods is gezipt; de inhoud toetsen we via de bouwer zelf.
    import zipfile
    from io import BytesIO

    def _cellen(zicht):
        ods = build_payments_export_ods(db_session, zicht=zicht)
        with zipfile.ZipFile(BytesIO(ods)) as zf:
            return zf.read("content.xml").decode()

    # De bouwer schrijft floats: office:value="20.0" resp. "17.53".
    open_ = _cellen("openstaand")
    assert "20.0" in open_
    assert "17.53" not in open_
    alles = _cellen("alle")
    assert "17.53" in alles
