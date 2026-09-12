"""A refusal is not an empty result, and must not look like one (#877).

Koen selected *Te betalen* in the table shape, got €1059, clicked **Draaitabel**
and reported: *"er staat niets"*. Two faults met there.

The pivot refused a selection without a row dimension, which contradicts what
`engine.py` says about itself — both shapes read the same objects, and the pivot
only moves one of them to the column axis. A selection that totals in the table
may then not come back empty. One cell with the grand total is the right answer:
the degenerate case, and what a spreadsheet does too.

**And the refusal was drawn as an absence.** The panel caught the `SelectionError`
and put the reason in `message`, which the template rendered with `empty_state` —
the same grey line as zero rows. Those two mean the opposite: with zero rows the
question is fine and there is no data; with a refusal the user has to change
something. Drawn identically, an instruction reads as "there is nothing here",
which is exactly how Koen read it.

**This is the third time this shape has come round.** In #847 the panel showed no
table and no message at all — the message was gone. Here it was present but
disguised as absence. The pattern is the subject, so the test below asserts the
**element** and not the text: a test on the wording would pass again the day both
become the same grey line.
"""
from __future__ import annotations

import pytest

from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


# What the two kit macros render. `role="alert"` is the banner's; the empty state
# is a centred grey line. Asserting on these and not on the sentence is the point.
BANNER = 'role="alert"'
LEEG = 'text-gray-500 text-sm py-6 text-center'


def test_the_same_selection_totals_the_same_in_both_shapes(db_session, situation):
    """Koen's €1059, along both roads.

    If these differ, one of the two shapes is counting something else — and that
    would be the finding, not the empty cell.
    """
    from app.domains.reporting.api import Selection, build_pivot, run_validated

    tabel = run_validated(db_session,
                          Selection(object_keys=("payment_amount",)),
                          tenant_id=TENANT_A).rows[0]["payment_amount"]
    kruis = build_pivot(db_session,
                        Selection(object_keys=("payment_amount",),
                                  layout="pivot"),
                        tenant_id=TENANT_A)
    assert len(kruis.rows) == 1, "één cel"
    assert kruis.grand_total["payment_amount"] == tabel, (
        f"tabel {tabel}, draaitabel {kruis.grand_total['payment_amount']}")
    assert tabel, "er valt iets te tellen, anders meet deze test niets"


def test_a_refusal_is_drawn_as_a_banner(client, db_session, situation):
    """A pivot without a measure is still refused, and it has to look refused."""
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_payable_type"
        "&layout=pivot&pivot_column=payment_method")
    assert fragment.status_code == 200
    assert BANNER in fragment.text, (
        "een weigering hoort als foutmelding getekend te worden, niet als lege "
        "staat — anders leest een instructie als 'er staat niets'")


def test_nothing_chosen_yet_is_drawn_as_an_empty_state(client, db_session,
                                                       situation):
    """The other side of the distinction, so the fix is not "everything is an
    error now"."""
    login(client, db_session)
    fragment = client.get("/admin/rapporten/paneel")
    assert fragment.status_code == 200
    assert LEEG in fragment.text
    assert BANNER not in fragment.text, (
        "nog niets gekozen is geen fout; wie dit als foutmelding tekent, leert "
        "de gebruiker foutmeldingen negeren")


def test_a_result_with_no_rows_is_drawn_as_an_empty_state(client, db_session,
                                                          situation):
    """Zero rows means the question was fine and there is no data."""
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=membership_year"
        "&object=membership_households&filter=membership_year"
        "&op_membership_year=eq&v_membership_year=1999")
    assert fragment.status_code == 200
    assert BANNER not in fragment.text, (
        "geen rijen is geen weigering: de vraag klopt, er is alleen geen data")


def test_the_two_are_not_the_same_element(client, db_session, situation):
    """The counter-proof of this issue, and the reason it asserts elements.

    What was broken: the template's refusal branch was pointed back at
    `ui.empty_state`, the way it stood before #877. Both requests then returned
    the same centred grey line, `role="alert"` was nowhere, and
    `test_a_refusal_is_drawn_as_a_banner` went red. The branch was put back.

    A test on the wording would have stayed green through that, which is why this
    file never asserts a sentence.
    """
    login(client, db_session)
    weigering = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_payable_type"
        "&layout=pivot&pivot_column=payment_method").text
    leegte = client.get("/admin/rapporten/paneel").text

    assert BANNER in weigering and BANNER not in leegte
    assert LEEG in leegte
    assert (BANNER in weigering) != (BANNER in leegte), (
        "worden weigering en leegte weer hetzelfde element, dan bewijst dit "
        "bestand niets meer")
