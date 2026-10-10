"""The public Lid worden says the rule's sentence, never the library's (#1831).

The schema of a household that signs up (`FamilyCreate`) words two rules itself:
a main member has an e-mail address, and a mobile number. On the board's "Nieuw
lid" those sentences reached the banner with the library's "Value error, " in
front until #1831. The public page reads its form first and says both itself, so
it showed them clean — measured before the change; this test holds that, and
that whatever the schema still refuses there goes through the same table of
words now (`mdm.api.schema_refusal_words`).

These pass before and after #1831 on purpose: the public page did not change in
what a visitor can send.
"""

from __future__ import annotations

import pytest

from tests.conftest import form_guard_fields, signup_fields

pytestmark = pytest.mark.ui_serverrendered


@pytest.mark.parametrize(
    ("changes", "sentence"),
    [
        ({"h.n0.mobile": ""}, "Mobiel nummer is verplicht voor het hoofdgezinslid."),
        ({"e.n0e.value": ""}, "E-mailadres is verplicht voor het hoofdgezinslid."),
        ({"e.n0e.value": "geen-adres"}, "Vul een geldig e-mailadres in."),
    ],
)
def test_the_public_sign_up_says_the_sentence_without_the_librarys_prefix(
    client, db_session, changes, sentence
):
    answer = client.post(
        "/lid-worden", data={**form_guard_fields(), **signup_fields(db_session, **changes)}
    )

    assert answer.status_code == 422
    assert sentence in answer.text
    assert "Value error" not in answer.text


def test_what_the_schema_alone_refuses_is_said_in_the_same_words():
    """The fallback of the public form's reader and the board's "Nieuw lid" read
    one table: a schema rule is passed on without the library's prefix."""
    from pydantic import ValidationError

    from app.domains.mdm.api import schema_refusal_words
    from app.domains.membership.api import FamilyCreate, FamilyMemberCreate

    with pytest.raises(ValidationError) as refusal:
        FamilyCreate(
            street="S",
            house_number="1",
            postal_code="2400",
            members=[FamilyMemberCreate(first_name="A", last_name="B", relation_type="HOOFDLID")],
        )

    assert str(refusal.value.errors()[0]["msg"]).startswith("Value error, ")
    assert (
        schema_refusal_words(refusal.value) == "E-mailadres is verplicht voor het hoofdgezinslid."
    )
