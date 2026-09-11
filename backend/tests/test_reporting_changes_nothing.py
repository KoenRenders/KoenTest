"""v2.3.0 adds; it replaces and removes nothing (#833 test 9, CR-06 principle 8).

Koen's rule for this release, and the reason it needs a test rather than care:
"we vervangen of verwijderen niets dat nu draait". Reporting is a new domain, a
new schema and a new screen — but it does touch two things that already existed,
and those two are exactly where an additive change quietly stops being additive:

- the **ODS kernel** gained an optional `intro_rows`, used by the report export to
  put the active filters in the header of sheet 1;
- the **admin menu** gained one item.

Both are checked here from the outside: the four existing export routes still
answer with the sheets and the numbers they always did, and the menu is the old
list with exactly one entry inserted.

**The counter-proof.** Changing `for intro in (intro_rows or [])` to
`(intro_rows or [[""]])` in the kernel made two of these fail at once — the header
row of the kernel test and the header row of the payments export both moved down
by one — with the expected columns in the message. Restored afterwards.

Note what did *not* work as a break: giving the `_add_sheet` parameter a different
default changes nothing, because `build_ods_multi` always passes the value
explicitly. That is worth writing down: the first break was tried, came back
green, and the reason was that it never reached the code the test guards.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest

from tests._reporting_seed import seed
from tests.test_reporting_panel_ui import login


def _first_sheet(content: bytes) -> list[list[str]]:
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    document = load(BytesIO(content))
    tabel = document.getElementsByType(Table)[0]
    return [["".join(str(p) for p in cel.getElementsByType(P))
             for cel in rij.getElementsByType(TableCell)]
            for rij in tabel.getElementsByType(TableRow)]


def test_the_ods_kernel_is_untouched_when_no_intro_rows_are_given():
    """The addition is inert by default — the header is still the first row."""
    from app.kernel.ods import build_ods, build_ods_multi

    headers = ["Naam", "Bedrag"]
    rows = [["Aap", 1.0], ["Noot", 2.0]]

    for content in (build_ods("Blad", headers, rows),
                    build_ods_multi([{"name": "Blad", "headers": headers,
                                      "rows": rows}])):
        blad = _first_sheet(content)
        assert blad[0] == headers, "de kopregel staat nog altijd bovenaan"
        assert len(blad) == len(rows) + 1, "er is geen rij bijgekomen"

    # And with intro rows it does what the report export needs, without moving
    # anything else: the intro sits above the header, the rest is unchanged.
    met_intro = _first_sheet(build_ods_multi([{
        "name": "Blad", "headers": headers, "rows": rows,
        "intro_rows": [["Rapport", "Test"], []]}]))
    assert met_intro[0] == ["Rapport", "Test"]
    assert met_intro[2] == headers
    assert met_intro[3:] == [["Aap", "1.0"], ["Noot", "2.0"]]


def test_the_payments_export_still_answers_as_it_did(client, db_session):
    """One of the four existing exports, end to end (#307)."""
    from app.domains.auth.api import User, UserRole
    from tests.conftest import SEEDED_ADMIN_EMAIL

    situatie = seed(db_session)
    assert situatie
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db_session.flush()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN", "FINANCE"))

    antwoord = client.get("/admin/betalingen/export")
    assert antwoord.status_code == 200
    blad = _first_sheet(antwoord.content)
    assert blad[0] == ["Waarvoor", "Soort", "Type", "Betaalwijze", "Status",
                       "Mededeling (OGM)", "Te betalen", "Betaald", "Saldo",
                       "Betaald op", "Notitie"], "de kopregel is onveranderd"
    assert blad[-1][0] == "Totaal"
    # The same net total as the reporting fact gives for this tenant — two
    # implementations, one number.
    assert Decimal(blad[-1][6]) == Decimal("120.00")


def test_the_member_changes_export_keeps_its_columns(client, db_session):
    """#512 is an external contract: Raak Nationaal reads this file."""
    from tests.conftest import SEEDED_ADMIN_EMAIL

    seed(db_session)
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    antwoord = client.get("/admin/ledenwijzigingen/export?vanaf=2000-01-01")
    assert antwoord.status_code == 200
    blad = _first_sheet(antwoord.content)
    assert blad[0], "de export heeft een kopregel"
    assert blad[0][0] != "Rapport", (
        "geen introregel in een bestaande export — dat is precies wat "
        "`intro_rows` niet mag doen")


def test_the_form_submissions_export_still_works(client, db_session):
    from app.domains.forms.api import Form as FormModel
    from tests.conftest import SEEDED_ADMIN_EMAIL

    formulier = db_session.query(FormModel).first()
    if formulier is None:
        pytest.skip("geen formulier in de seed")
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    antwoord = client.get(f"/admin/formulieren/{formulier.id}/export")
    assert antwoord.status_code == 200
    assert _first_sheet(antwoord.content)[0], "de export heeft een kopregel"


def test_the_component_export_still_works(client, db_session):
    from tests.conftest import SEEDED_ADMIN_EMAIL

    situatie = seed(db_session)
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    antwoord = client.get(
        f"/admin/activiteiten/{situatie['activity_id']}"
        f"/onderdelen/{situatie['component_id']}/export")
    assert antwoord.status_code == 200
    assert _first_sheet(antwoord.content)[0], "de export heeft een kopregel"


def test_the_menu_gained_exactly_one_item_and_nothing_else_moved():
    """One entry inserted after Betalingen; every other entry in its old place.

    `/admin/design-system` left this list with #878 — Koen took it out of the bar because
    it is reference material and not a screen where a board member does work. That is a
    decision, not a loosening of this gate: the list below is still exact and still holds
    the position of Rapporten. The route itself is very much alive, and
    `test_design_system_out_of_the_admin_bar.py` is what keeps it that way.
    """
    from app.ui import _ADMIN_NAV

    hrefs = [href for href, _label in _ADMIN_NAV]
    assert hrefs == [
        "/admin/werkbank", "/admin/activiteiten", "/admin/leden",
        "/admin/betalingen", "/admin/rapporten", "/admin/formulieren",
        "/admin/paginas", "/admin/media", "/admin/gebruikers",
        "/admin/ledenwijzigingen", "/admin/ai-context", "/admin/e-maillog",
        "/admin/tenants", "/admin/info",
    ]
    assert hrefs.index("/admin/rapporten") == hrefs.index("/admin/betalingen") + 1


def test_the_dashboard_keeps_its_six_tiles_and_its_place(client, db_session):
    """What still has to hold after #848 — and what no longer does.

    This test used to assert that the dashboard knew nothing of reporting: no
    link, not even the word. **Koen revised principle 8 for this one screen** on
    10 September 2026: *"Gelieve in v2.3 de zaken te voorzien zodat alle bestaande
    tegels vervangen kunnen worden door Reporting."* So the clause about the word
    is gone, on purpose and with a decision behind it — not because it became
    inconvenient.

    Three things did NOT change and are what this now guards:

    - the screen stays on `/admin`, the landing page of the back office;
    - six tiles in, six tiles out, with the same titles;
    - each keeps its operational link — at "Open taken" you want the workbench,
      not a table — and the link to its report comes beside it, not instead.

    That the six NUMBERS did not change is a different test and a sharper one:
    `test_reporting_dashboard.py` computes each of them the old way and through
    its report and compares. It only works while both roads exist, which is why
    `get_stats` stays.
    """
    from tests.conftest import SEEDED_ADMIN_EMAIL

    seed(db_session)
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    assert pagina.status_code == 200

    for titel, doel in [("Leden", "/admin/leden"),
                        ("Actieve leden", "/admin/leden"),
                        ("Leden (personen)", "/admin/leden"),
                        ("Komende activiteiten", "/admin/activiteiten"),
                        ("Open taken (werkbank)", "/admin/werkbank"),
                        ("Openstaand saldo", "/admin/betalingen")]:
        assert titel in pagina.text, titel
        assert doel in pagina.text, doel

    from app.ui.system_ui import DASHBOARD_TEGELS

    assert len(DASHBOARD_TEGELS) == 6, "zes tegels erin, zes eruit"


def test_the_outstanding_tile_still_writes_its_amount_the_way_it_did(client,
                                                                     db_session):
    """A finding, kept as a test rather than quietly fixed.

    The tile writes `€45.00` with a POINT, while #735 made the comma the house
    rule and `ui.geld` exists for exactly this. #848 moves where the number comes
    from and changes nothing about what is displayed, so the format stayed as it
    was — and this pins it, so that when somebody does fix it, it is a decision
    with a diff and not a side effect of moving a query.
    """
    import re

    from tests.conftest import SEEDED_ADMIN_EMAIL

    seed(db_session)
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    bedragen = re.findall(r"€\d+\.\d{2}", pagina.text)
    assert bedragen, "de tegel toont een bedrag met een punt, zoals voordien"
