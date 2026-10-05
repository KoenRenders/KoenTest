"""#1327 — after a refusal, "Word lid" still shows every person, with their values.

Found with #1321: when "Word lid" refused a registration — an unknown postal code,
a missing birth date — the page came back with the head of household only.
Everyone else the visitor had typed was gone, their relation and extra e-mail
addresses with them. The repair then was to render every row again from what
was submitted.

Since #1590 the page is not rendered again at all: a refusal answers the banner
alone, for the page's message line (`app.ui.refusal_response`), and the form
stays in the browser as it was typed. So "every person is still there" is true
by construction — as long as the answer really is the banner alone and names
the refused fields by the names the page sent, because that is how the page
finds the row to mark. That is what is proven here; that the rows are still on
the screen after the swap is the browser's, and the e2e test's.
"""

import re

import pytest

from app.domains.mdm.api import Person, RelationType
from tests.conftest import signup_fields

pytestmark = pytest.mark.ui_serverrendered

KIND = RelationType.ADULT_CHILD.value
PARTNER = RelationType.PARTNER.value


def _places(answer) -> list[str]:
    return re.findall(r'data-error-for="([^"]+)"', answer.text)


def test_a_refusal_answers_the_banner_alone_and_stores_nobody(client, db_session):
    """Three persons, an extra address, and a postal code that was not chosen:
    the answer is for the message line only, so nothing of the form is replaced."""
    form = signup_fields(
        db_session,
        {"first_name": "Pieter", "last_name": "Terugkeer", "relation_type": PARTNER},
        {"first_name": "Lotte", "last_name": "Terugkeer", "relation_type": KIND},
        **{
            "address.postal_code": "",
            "e_order.n2": ["n2e"],
            "e.n2e.value": "lotte.extra@example.com",
        },
    )
    answer = client.post("/lid-worden", data=form)

    assert answer.status_code == 422
    assert answer.headers["HX-Retarget"] == "#lid-worden-melding"
    assert answer.headers["HX-Reswap"].startswith("innerHTML")
    assert answer.headers["HX-Reselect"] == "[data-save-refusal]"
    body = answer.text
    assert "<html" not in body.lower(), "the whole page came back: the rows are redrawn"
    assert 'name="h_order"' not in body and "<form" not in body
    assert body.count("data-save-refusal") == 1
    assert "Verzenden kan nog niet: controleer 1 veld." in body
    assert _places(answer) == ["address.postal_code"]
    stored = db_session.query(Person).filter(Person.last_name.in_(("Lid", "Terugkeer"))).count()
    assert stored == 0, "a refused sign-up stored somebody"


def test_a_refusal_names_the_rows_by_the_keys_the_page_sent(client, db_session):
    """Rows `n1` and `n3` are sent — row `n2` was removed in the browser. A
    refusal on the last one must say `n3`, the key that row carries on the page,
    not its position among the rows that were sent."""
    form = signup_fields(db_session, {"first_name": "Pieter", "relation_type": PARTNER})
    form["h_order"] = ["n0", "n1", "n3"]
    form.update(
        {
            "h.n3.first_name": "Lotte",
            "h.n3.last_name": "Terugkeer",
            "h.n3.date_of_birth": "",
            "h.n3.gender_code": "F",
            "h.n3.relation_type": KIND,
            "e_order.n3": ["x9"],
            "e.x9.value": "lotte@",
        }
    )
    answer = client.post("/lid-worden", data=form)

    assert answer.status_code == 422
    assert _places(answer) == ["h.n3.date_of_birth", "e.x9.value"]
    assert "Verzenden kan nog niet: controleer 2 velden." in answer.text
