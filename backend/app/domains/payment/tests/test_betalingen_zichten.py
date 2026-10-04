"""Golf 10 (#913): de statustabs (zichten) op de betalingenlijst.

Een zicht is een afgeleide doorsnede naast de statuskolom (#669 blijft gelden:
ze combineren met EN). De tab-aantallen tellen over de zicht-loze basis; de
export draagt het actieve zicht mee, anders exporteert "Openstaand" stil alles.

CR-11 pilot A, K1 (#1555): the tabs became the toolbar's status filter, a
segmented control with two segments — *Alle | Openstaand (n)* — and the status
select is gone. The tests below follow: a link of before K1 with `zicht=betaald`
or `status=failed` shows everything instead of filtering on something no control
on the screen shows; the count on "Openstaand" is what the click yields.
"""

import re
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _drie_boekingen(db):
    """Eén open vordering (Anna), één vereffende (Bram), één open refund (Cleo)."""
    db.add(
        PaymentRecord(
            payable_type="registration",
            payable_id=9001,
            amount=Decimal("20.00"),
            method="transfer",
            status="pending",
            type="charge",
        )
    )
    # 17,53 en niet 15,00: de totaalrij van de openstaande export is toevallig
    # net 20,00 − 5,00 = 15,00, en dan bewijst "15,00 afwezig" niets meer.
    db.add(
        PaymentRecord(
            payable_type="registration",
            payable_id=9002,
            amount=Decimal("17.53"),
            amount_paid=Decimal("17.53"),
            method="online",
            status="paid",
            type="charge",
        )
    )
    db.add(
        PaymentRecord(
            payable_type="registration",
            payable_id=9003,
            amount=Decimal("-5.00"),
            method="transfer",
            status="pending",
            type="refund",
        )
    )
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
        return {n for n in (9001, 9002, 9003) if f"/admin/inschrijvingen/{n}?" in html}

    assert _rijen("alle") == {9001, 9002, 9003}
    assert _rijen("openstaand") == {9001, 9003}  # open vordering + open refund
    # K1 (#1555): no segment for a done state; an old link falls back to "alle".
    assert _rijen("betaald") == {9001, 9002, 9003}
    assert _rijen("terugbetaald") == {9001, 9002, 9003}


def _segment(html: str, value: str) -> str:
    """The label of one segment of the status filter, radio and text."""
    at = html.index(f'name="zicht" value="{value}"')
    return html[at : html.index("</label>", at)]


def test_het_segment_openstaand_telt_wat_de_klik_oplevert(client, db_session):
    """K1 (#1555): "Openstaand (n)" counts over the selection BEFORE the status
    filter — on "Alle" as on "Openstaand" itself — and n is the number the
    toolbar's count shows after the click. "Alle" carries no count."""
    _drie_boekingen(db_session)
    _login(client)

    for zicht in ("alle", "openstaand"):
        pagina = client.get(f"/admin/betalingen?zicht={zicht}").text
        assert re.search(r"Openstaand\s*<span[^>]*>\(2\)</span>", _segment(pagina, "openstaand"))
        assert "(" not in re.sub(r"<[^>]+>", "", _segment(pagina, "alle"))
    na_de_klik = client.get("/admin/betalingen/lijst?zicht=openstaand").text
    assert re.search(r'id="bt-filter-count"[^>]*>\s*1–2 van 2\s*<', na_de_klik)
    # The fragment refreshes the segment's count out-of-band: the toolbar stands
    # outside it.
    assert re.search(r'id="bt-filter-n-openstaand" hx-swap-oob="true"[^>]*>\(2\)<', na_de_klik)
    assert 'role="tablist"' not in client.get("/admin/betalingen").text
    # 3 boekingen totaal, 2 open (vordering + refund), 1 vereffend, 1 refund.
    from app.domains.payment.api import count_zichten, enriched_records

    telling = count_zichten(enriched_records(db_session))
    assert (
        telling["alle"],
        telling["openstaand"],
        telling["betaald"],
        telling["terugbetaald"],
    ) == (3, 2, 1, 1)


def test_een_oude_statuslink_filtert_niet_meer(client, db_session):
    """K1 (#1555): the status select is gone (decision 03, point 4), so
    `status=failed` in an old link is ignored — the list would otherwise filter
    on something no control on the screen shows. (Until K1 this test held the
    opposite, #669: the tab and the status select combined with AND.)"""
    _drie_boekingen(db_session)
    db_session.add(
        PaymentRecord(
            payable_type="registration",
            payable_id=9004,
            amount=Decimal("40.00"),
            method="transfer",
            status="failed",
            type="charge",
        )
    )
    db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst?zicht=openstaand&status=failed").text
    assert "/admin/inschrijvingen/9004?" in html
    assert "/admin/inschrijvingen/9001?" in html
    assert (
        'name="status"'
        not in client.get("/admin/betalingen").text.split('id="betalingen-lijst"')[0]
    )


def test_oude_openstaand_link_landt_op_het_tab(client, db_session):
    """Bestaande links en export-URL's met openstaand=1 blijven hetzelfde
    tonen: ze vallen op het Openstaand-tab terug."""
    _drie_boekingen(db_session)
    _login(client)

    html = client.get("/admin/betalingen/lijst?openstaand=1").text
    assert "/admin/inschrijvingen/9002?" not in html
    pagina = client.get("/admin/betalingen?openstaand=1").text
    assert "checked" in _segment(pagina, "openstaand").split(">")[0]
    assert "checked" not in _segment(pagina, "alle").split(">")[0]


def test_zicht_overleeft_een_filterwissel(client, db_session):
    """The chosen segment is a field of the toolbar's own form (K1, #1555), so
    the next search term sends it along instead of falling back to "Alle"; and
    the list holder refreshes with that form's fields."""
    _drie_boekingen(db_session)
    _login(client)

    scherm = client.get("/admin/betalingen?zicht=openstaand").text
    toolbar = scherm[scherm.index('<form id="bt-filter"') : scherm.index("</form>")]
    assert "checked" in _segment(toolbar, "openstaand").split(">")[0]
    assert 'name="q"' in toolbar
    assert 'hx-include="#bt-filter"' in scherm


def test_de_rij_is_de_ingang_en_er_klapt_niets_meer_uit(client, db_session):
    """K2 (#1556): the unfold under a row is gone, and with it the Alpine
    expressions this test used to guard (a record id is a UUID string and had to
    be quoted in them). The row is the way in now: its link opens the booking's
    page, and no row says "Bewerken"."""
    from app.domains.auth.api import User, UserRole
    from tests.conftest import SEEDED_ADMIN_EMAIL as _admin

    _drie_boekingen(db_session)
    user = db_session.query(User).filter(User.email == _admin).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "open ===" not in html and "terug ===" not in html
    assert "Bewerken" not in html
    assert (
        len(
            re.findall(
                r'<a href="/admin/betalingen/[0-9a-f-]{36}\?terug=[^"]*" data-row-link', html
            )
        )
        == 3
    )


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
