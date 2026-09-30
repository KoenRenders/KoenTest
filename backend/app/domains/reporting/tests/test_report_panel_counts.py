"""The report panel counts its rows and pages with the kit pager (#1391, CR-11 W8).

The panel used to fetch one row extra and say "Pagina n"; it now runs a count
next to the page and says "x–y van n", like every other list. What would stay
green if the count were wrong: a count that reads the page instead of the whole
selection. So the selection here is run with a page of ONE row, and the count
must still equal the rows of the unpaged run — for a grouped table and for a
detail listing, whose count statements are built apart.
"""

from __future__ import annotations

import re

import pytest

from app.domains.reporting import admin_ui
from app.domains.reporting.api import Selection, run_validated
from app.domains.reporting.tests.test_reporting_panel_ui import login
from tests._reporting_seed import EXPECTED, TENANT_A, seed

GROUPED = ("payment_method", "payment_amount")
# A listing refuses a measure, so it gets its own objects.
LISTED = ("payment_payable_label", "payment_due")


@pytest.fixture
def situation(db_session):
    return seed(db_session)


@pytest.mark.parametrize("layout, objects", [("table", GROUPED), ("detail", LISTED)])
def test_the_count_is_the_whole_selection_not_the_page(db_session, situation, layout, objects):
    everything = run_validated(
        db_session, Selection(object_keys=objects, layout=layout, limit=5000), tenant_id=TENANT_A
    )
    assert len(everything.rows) > 1, "the seed must give more than one row to tell them apart"
    one_page = run_validated(
        db_session,
        Selection(object_keys=objects, layout=layout, limit=1),
        tenant_id=TENANT_A,
        with_count=True,
    )
    assert len(one_page.rows) == 1
    assert one_page.total_rows == len(everything.rows)


def test_no_count_unless_asked(db_session, situation):
    """The assistant and the exports run the same entry point; only the paged
    panel pays for the count."""
    result = run_validated(db_session, Selection(object_keys=GROUPED), tenant_id=TENANT_A)
    assert result.total_rows is None


def test_the_panel_pages_with_x_y_of_n(client, db_session, situation, monkeypatch):
    monkeypatch.setattr(admin_ui, "PER_PAGE", 1)
    login(client, db_session)
    methods = len(EXPECTED["payments"]["per_method"])
    assert methods > 1

    html = client.get("/admin/rapporten/paneel?object=payment_method&object=payment_amount").text

    assert f"1–1 van {methods}" in html
    assert "Pagina" not in re.sub(r"Paginering|Pagina's", "", html)
    nav = html[html.index('aria-label="Paginering"') :]
    nav = nav[: nav.index("</nav>")]
    assert 'hx-get="/admin/rapporten/paneel?goto=2"' in nav
    # Target, swap and the form state come from the panel's outer div.
    assert "hx-target" not in nav and "hx-swap" not in nav

    page_two = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount&goto=2"
    ).text
    assert f"2–2 van {methods}" in page_two
