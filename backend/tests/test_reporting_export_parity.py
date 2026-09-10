"""The payments export, twice: the old button and the new saved report (#841 p4).

CR-06 §7.3 changed on 10 September 2026 — person data is allowed in the universe —
and this is the first report that uses that room. It reproduces
`/admin/betalingen/export` out of the universe and stands **beside** it: the
existing button, route and output are untouched, and this report does not call
them.

That means two independent roads to comparable output, which can drift apart.
That price was accepted knowingly, and this test is what is bought with it: the
two are compared cell by cell, as **two living outputs** on the same seed rather
than one output and a stored expectation. If either side changes, this fails.

**"Byte for byte" cannot be taken literally**, and saying so is part of the test:
odfpy stamps a creation date into every document, so two runs of the *same* code
differ in bytes. What is compared is every cell of the sheet — headers, each row
in order, the totals row — with the report's intro rows (its name and its active
filters) as the one allowed difference, which is what #841 permits.

Would this be green if the subject were broken? Change one column's order in the
universe selection, or the sign of a refund in either implementation, and the
comparison fails on the first differing cell with both values in the message.
"""
from __future__ import annotations

from io import BytesIO

import pytest

from app.domains.auth.api import User, UserRole
from app.domains.reporting.api import (
    Selection, build_report_ods, list_saved_reports, run_validated, selection_of,
)
from tests._reporting_seed import TENANT_A, seed
from tests.conftest import SEEDED_ADMIN_EMAIL
from tests.test_reporting_panel_ui import ADMIN_EMAIL, login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _sheet(content: bytes, name: str | None = None) -> list[list[str]]:
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    document = load(BytesIO(content))
    tabellen = document.getElementsByType(Table)
    tabel = tabellen[0] if name is None else next(
        t for t in tabellen if t.getAttribute("name") == name)
    return [["".join(str(p) for p in cel.getElementsByType(P))
             for cel in rij.getElementsByType(TableCell)]
            for rij in tabel.getElementsByType(TableRow)]


def _old_export(client, db) -> list[list[str]]:
    """The existing button, through its real route."""
    gebruiker = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in gebruiker.roles):
        db.add(UserRole(user_id=gebruiker.id, role_code="FINANCE"))
        db.flush()
    login(client, db, SEEDED_ADMIN_EMAIL, ("ADMIN", "FINANCE"))
    antwoord = client.get("/admin/betalingen/export")
    assert antwoord.status_code == 200
    return _sheet(antwoord.content)


def _new_report(db) -> list[list[str]]:
    """The saved report, through the engine."""
    rapport = next(r for r in list_saved_reports(db, tenant_id=TENANT_A,
                                                 viewer=ADMIN_EMAIL)
                   if r.builtin_key == "payments_list")
    selectie = selection_of(rapport, limit=5000)
    resultaat = run_validated(db, selectie, tenant_id=TENANT_A)
    content = build_report_ods(db, resultaat, selectie, title=rapport.name,
                               tenant_id=TENANT_A)
    return _sheet(content, name=rapport.name[:31])


def _strip_intro(blad: list[list[str]], kop: list[str]) -> list[list[str]]:
    """Drop the report's intro rows — the one difference #841 allows."""
    return blad[blad.index(kop):]


def test_the_saved_report_and_the_button_produce_the_same_sheet(client, db_session,
                                                                situation):
    oud = _old_export(client, db_session)
    nieuw = _strip_intro(_new_report(db_session), oud[0])

    assert nieuw[0] == oud[0], "de kopregel is dezelfde, in dezelfde volgorde"
    assert len(nieuw) == len(oud), (
        f"de nieuwe lijst heeft {len(nieuw)} regels, de bestaande {len(oud)}")

    for index, (rij_nieuw, rij_oud) in enumerate(zip(nieuw, oud)):
        assert rij_nieuw == rij_oud, (
            f"regel {index} verschilt:\n  rapport: {rij_nieuw}\n  knop:    {rij_oud}")


def test_the_intro_is_the_only_thing_the_report_adds(db_session, situation):
    blad = _new_report(db_session)
    kop = ["Waarvoor", "Soort", "Type", "Betaalwijze", "Status",
           "Mededeling (OGM)", "Te betalen", "Betaald", "Saldo", "Betaald op",
           "Notitie"]
    assert kop in blad, "de kop staat er, met exact deze kolommen"
    intro = blad[:blad.index(kop)]
    assert intro[0][:2] == ["Rapport", "Betalingen en vorderingen"]
    assert any(rij[:1] == ["Filter"] for rij in intro)


def test_the_totals_row_is_the_same_total(client, db_session, situation):
    oud = _old_export(client, db_session)
    nieuw = _strip_intro(_new_report(db_session), oud[0])
    assert oud[-1][0] == "Totaal" and nieuw[-1][0] == "Totaal"
    assert nieuw[-1] == oud[-1], "hetzelfde totaal, in dezelfde kolommen"


def test_the_report_reads_the_universe_and_not_the_old_export(db_session):
    """#841: the report stands on its own legs; domains stay separate.

    A saved report that called the existing export would make the comparison
    above meaningless — it would be comparing something with itself.
    """
    from pathlib import Path

    domein = Path(__file__).resolve().parents[1] / "app" / "domains" / "reporting"
    verboden = ("payment.exports", "build_payments_export_ods",
                "activities.export", "forms.export", "audit.changes")
    for pad in domein.rglob("*.py"):
        tekst = pad.read_text(encoding="utf-8")
        for naam in verboden:
            assert naam not in tekst, (
                f"{pad.name} roept {naam} aan — een rapport haalt zijn rijen uit "
                "de universe")


def test_a_row_list_refuses_a_measure(db_session, situation):
    """A listing answers "which ones", not "how much"."""
    from app.domains.reporting.api import SelectionError

    with pytest.raises(SelectionError) as exc:
        run_validated(db_session,
                      Selection(object_keys=("payment_payable_label",
                                             "payment_amount"),
                                layout="detail"),
                      tenant_id=TENANT_A)
    assert "'Te betalen'" in str(exc.value)
    assert "geen totalen" in str(exc.value)


def test_a_row_list_is_ordered_and_pages_without_repeating(db_session, situation):
    """#761 on a listing: without a unique tail, page 2 shows page 1 again."""
    objecten = ("payment_payable_label", "payment_due")
    heel = run_validated(db_session, Selection(object_keys=objecten,
                                               layout="detail", limit=5000),
                         tenant_id=TENANT_A).rows
    stukjes = []
    for offset in range(0, len(heel), 2):
        deel = run_validated(
            db_session,
            Selection(object_keys=objecten, layout="detail", limit=2, offset=offset),
            tenant_id=TENANT_A)
        stukjes.extend(deel.rows)
    assert stukjes == heel


def test_a_row_list_stays_inside_its_tenant(db_session, situation):
    from tests._reporting_seed import EXPECTED, TENANT_B

    objecten = ("payment_payable_label", "payment_due")
    a = run_validated(db_session, Selection(object_keys=objecten, layout="detail",
                                            limit=5000), tenant_id=TENANT_A)
    b = run_validated(db_session, Selection(object_keys=objecten, layout="detail",
                                            limit=5000), tenant_id=TENANT_B)
    assert len(a.rows) == EXPECTED["payments"]["count"]
    assert len(b.rows) == 1
