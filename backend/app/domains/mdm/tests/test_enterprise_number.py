"""#1517 — the enterprise number is checked and stored in one form.

A Belgian enterprise number (KBO/BCE) has ten digits, starts with 0 or 1, and
its last two digits are 97 minus the first eight modulo 97. "123" was accepted
and saved. Now the usual spellings are read and stored as the ten digits of ISO
6523 ICD 0208, and anything else is refused on the field, with the reason —
before anything of the form is written.

Proven red: against master `f0323657` the module does not import (there is no
`enterprise_number`). On this branch, the check taken out of the save path fails
the five save and screen tests ("123" saved as typed); the check placed after
the name is written fails the "nothing is written" test — a refusal left the
name changed in the session.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.domains.mdm.api import (
    OngeldigeInstelling,
    Organization,
    create_account,
    organization_details,
    save_organization,
)
from app.domains.mdm.enterprise_number import (
    EnterpriseNumber,
    InvalidEnterpriseNumber,
    WrongCheckDigits,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

VALID = "0123456749"  # 97 - 01234567 % 97 = 49


@pytest.mark.parametrize(
    "spelling",
    [
        "0123.456.749",
        "0123456749",
        "BE0123456749",
        "be 0123 456 749",
        "0123-456-749",
        "123.456.749",
    ],
)
def test_every_usual_spelling_reads_as_the_ten_digits(spelling):
    assert EnterpriseNumber.parse(spelling).digits == VALID
    assert str(EnterpriseNumber.parse(spelling)) == "0123.456.749"


@pytest.mark.parametrize(
    "text", ["123", "", "2123456749", "01234567490", "0123.456.74x", "NL0123456749"]
)
def test_what_is_not_an_enterprise_number_is_refused(text):
    with pytest.raises(InvalidEnterpriseNumber) as refused:
        EnterpriseNumber.parse(text)
    assert not isinstance(refused.value, WrongCheckDigits)


def test_a_wrong_check_number_is_told_apart():
    with pytest.raises(WrongCheckDigits):
        EnterpriseNumber.parse("0123.456.789")


@pytest.mark.parametrize("spelling", ["0123.456.749", "BE0123456749"])
def test_a_valid_number_is_stored_as_its_ten_digits(db_session, spelling):
    account = create_account(db_session, name="Bakkerij", code=f"bakkerij-{len(spelling)}")
    save_organization(db_session, account.id, {"enterprise_number": spelling})
    assert organization_details(db_session, account.id)["enterprise_number"] == VALID


@pytest.mark.parametrize(
    ("text", "reason"),
    [("123", "tien cijfers"), ("0123.456.789", "controlegetal klopt niet")],
)
def test_a_bad_number_is_refused_and_nothing_is_written(db_session, text, reason):
    account = create_account(db_session, name="Bakkerij", code="bakkerij-1517")
    with pytest.raises(OngeldigeInstelling) as refused:
        save_organization(
            db_session, account.id, {"name": "Nieuwe naam", "enterprise_number": text}
        )
    assert reason in refused.value.fouten["enterprise_number"]
    # Refused first of all: nothing of the form touched the organisation, not
    # even in this session.
    assert db_session.get(Organization, account.id).name == "Bakkerij"
    assert not organization_details(db_session, account.id)["enterprise_number"]


@pytest.mark.ui_serverrendered
def test_the_screen_names_the_field_and_the_reason(client, db_session):
    account = create_account(db_session, name="Bakkerij", code="bakkerij-scherm")
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db_session.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)

    answer = client.post(
        f"/admin/organisaties/{account.id}",
        data={"name": "Bakkerij", "enterprise_number": "123"},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )

    assert "Ondernemingsnummer: Een ondernemingsnummer heeft tien cijfers" in answer.text
    assert 'value="123"' in answer.text, "what was typed stays in the field"
