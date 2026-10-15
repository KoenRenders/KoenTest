"""A number answer of a form reads as a plain number: "8", "39,78" (#1977).

The answer is stored as `Numeric(12,2)` and was printed as the database gave it
("8.00"); the results turned the average, minimum and maximum into floats ("39.78",
"8.0"). `kernel.meetwaarden.plain_number` is the one form: at most two decimals,
rounded half up, needless zeros dropped, the nl-BE comma, no thousands separator
(like the other formats). It is no member of `FORMATTERS`: the reporting universe
declares no such format and its gate keeps the two equal.

Read from the rendered pages: the submission's detail (`/inzendingen`) and the
results; and from the export's table, which shares `values_per_field` with the
detail and so follows the same form (its cells are text, as before).

Red proof (14 October 2026, each put back): `plain_number(avg)` in `results.py`
replaced by `str(avg)` -> the results case fails; `plain_number` in `forms/api.py`
back to the stored text -> the submission case fails; the same in `export.py` ->
the export case fails; the comma taken out of `plain_number` -> the unit cases with
decimals and the three page cases fail.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.forms.models import (
    Form,
    FormField,
    FormSection,
    FormSubmission,
    FormSubmissionAnswer,
)
from app.kernel.meetwaarden import plain_number
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import SEEDED_ADMIN_EMAIL


@pytest.mark.parametrize(
    "given,shown",
    [
        (8, "8"),
        (Decimal("8.00"), "8"),
        (Decimal("8.50"), "8,5"),
        (Decimal("39.775"), "39,78"),
        (Decimal("39.8333333333"), "39,83"),
        (1250, "1250"),
        (0, "0"),
        (Decimal("-0.00"), "0"),
        (Decimal("-3.5"), "-3,5"),
        (Decimal("0.5"), "0,5"),
        ("8.00", "8"),
        ("geen getal", "geen getal"),
    ],
)
def test_the_plain_number(given, shown):
    assert plain_number(given) == shown


@pytest.fixture
def form(db_session):
    f = Form(
        tenant_id=TENANT_MILLEGEM_ID,
        title="Aantal personen",
        share_token="plain-number-1977",
        status="open",
    )
    db_session.add(f)
    db_session.flush()
    section = FormSection(tenant_id=TENANT_MILLEGEM_ID, form_id=f.id, title="Deel", position=0)
    db_session.add(section)
    db_session.flush()
    field = FormField(
        tenant_id=TENANT_MILLEGEM_ID,
        form_id=f.id,
        section_id=section.id,
        field_type="number",
        label="Aantal personen",
        position=0,
    )
    db_session.add(field)
    db_session.flush()
    for number, amount in enumerate(("8.00", "90.00", "21.50")):
        sub = FormSubmission(
            tenant_id=TENANT_MILLEGEM_ID,
            form_id=f.id,
            submitter_name="Proef",
            submitter_email=f"proef-{number}@example.org",
            submitted_at=datetime(2026, 9, 1, 10, number, tzinfo=timezone.utc),
        )
        db_session.add(sub)
        db_session.flush()
        db_session.add(
            FormSubmissionAnswer(
                tenant_id=TENANT_MILLEGEM_ID,
                submission_id=sub.id,
                field_id=field.id,
                value_number=Decimal(amount),
            )
        )
    db_session.commit()
    return f


def _text(html: str) -> str:
    """The visible text of a page: tags gone, whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_the_results_show_the_average_minimum_and_maximum_as_plain_numbers(client, form):
    _login(client)

    page = client.get(f"/admin/formulieren/{form.id}/resultaten").text

    assert "Gemiddelde: 39,83 · min: 8 · max: 90" in _text(page)
    for raw in ("39.83", "8.0", "90.0", "8.00"):
        assert raw not in page, f"the raw {raw} reaches the results"


def test_a_submission_shows_its_number_answers_as_plain_numbers(client, form):
    _login(client)

    page = client.get(f"/admin/formulieren/{form.id}/inzendingen").text

    text = _text(page)
    assert re.search(r"Aantal personen\W+8(?![\d.,])", text), text[:600]
    assert re.search(r"Aantal personen\W+21,5(?![\d.])", text), text[:600]
    for raw in ("8.00", "21.50", "90.00"):
        assert raw not in page, f"the stored {raw} reaches the submissions"


def test_the_export_table_follows_the_same_form(db_session, form):
    from app.domains.forms.export import _build_table

    _headers, rows = _build_table(db_session, form)

    assert [row[3] for row in rows] == ["8", "90", "21,5"]
