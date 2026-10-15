"""The average of a rating question reads with a comma, "4,33" (#2014).

Same fault as #1977, one place further: the results printed
`round(weighted / total, 2)`, a float ("4.33"). The average is a Decimal to the end
and goes through `plain_number`. Read from the rendered results page, for ratings
4, 4, 5 ("4,33"), 4, 4 ("4"), and 4, 5 ("4,5").

Red proof (15 October 2026, put back): the line in `results.py` back to
`round(weighted / total, 2)` -> the three cases fail on "4.33", "4.0" and "4.5".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.forms.models import (
    Form,
    FormField,
    FormSection,
    FormSubmission,
    FormSubmissionAnswer,
)
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import SEEDED_ADMIN_EMAIL


def _form(db_session, ratings: list[int]) -> Form:
    f = Form(
        tenant_id=TENANT_MILLEGEM_ID,
        title="Tevredenheid",
        share_token=f"rating-2014-{len(ratings)}-{sum(ratings)}",
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
        field_type="rating",
        label="Score",
        position=0,
        rating_max=5,
    )
    db_session.add(field)
    db_session.flush()
    for number, rating in enumerate(ratings):
        sub = FormSubmission(
            tenant_id=TENANT_MILLEGEM_ID,
            form_id=f.id,
            submitter_name="Proef",
            submitter_email=f"rating-{number}@example.org",
            submitted_at=datetime(2026, 9, 1, 10, number, tzinfo=timezone.utc),
        )
        db_session.add(sub)
        db_session.flush()
        db_session.add(
            FormSubmissionAnswer(
                tenant_id=TENANT_MILLEGEM_ID,
                submission_id=sub.id,
                field_id=field.id,
                value_rating=rating,
            )
        )
    db_session.commit()
    return f


@pytest.mark.parametrize(
    "ratings,shown",
    [([4, 4, 5], "4,33"), ([4, 4], "4"), ([4, 5], "4,5")],
)
def test_the_average_of_a_rating_reads_as_a_plain_number(client, db_session, ratings, shown):
    form = _form(db_session, ratings)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    page = client.get(f"/admin/formulieren/{form.id}/resultaten").text

    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    assert f"Gemiddelde: {shown} " in text + " ", text[:500]
