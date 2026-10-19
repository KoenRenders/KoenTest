"""#1545 — a refused number shows on its field, and the Belgian VAT number is checked.

The refusal of #1517 worked (422, nothing stored), but its banner sits at the top
of a long form while Opslaan sits at the bottom: on the organisation screen it
read as "nothing happened". The reason now also stands below the field, linked
with `aria-describedby`. And a Belgian VAT number is the enterprise number with
`BE` in front, so it gets the same check and one stored form, `BE` and the ten
digits. Another country's number is not ours to check and is kept as typed.

Proven red: against master `c7785fe4` seven of the nine fail ("BE 0123.456.749"
stored as typed, "BE 0123.456.789" accepted, no reason below the field); the
spelling that is already the stored form and the foreign number held already.
With only the template reverted, the two screen tests fail.
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
    create_organization,
    organization_details,
    save_organization,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

# #1549 (Koen's text): one message per number for every structural refusal.
REFUSED = {
    "enterprise_number": "Dit ondernemingsnummer heeft niet de juiste structuur. Kijk het na.",
    "vat_number": "Dit btw-nummer heeft niet de juiste structuur. Kijk het na.",
}


@pytest.mark.parametrize(
    "spelling", ["BE 0123.456.749", "BE0123456749", "be0123456749", "0123 456 749"]
)
def test_a_belgian_vat_number_is_stored_as_be_and_ten_digits(db_session, spelling):
    account = create_organization(db_session, name="Bakkerij")
    save_organization(db_session, account.id, {"vat_number": spelling})
    assert organization_details(db_session, account.id)["vat_number"] == "BE0123456749"


def test_a_foreign_vat_number_is_kept_as_typed(db_session):
    account = create_organization(db_session, name="Bakkerij")
    save_organization(db_session, account.id, {"vat_number": "NL 123456789B01"})
    assert organization_details(db_session, account.id)["vat_number"] == "NL 123456789B01"


@pytest.mark.parametrize(
    "text",
    ["BE 0123.456.789", "BE 0123.456.abc", "BE 123", "BE 01234567490"],
    ids=["check-number", "letters", "too-short", "too-long"],
)
def test_a_bad_belgian_vat_number_is_refused_and_nothing_is_written(db_session, text):
    account = create_organization(db_session, name="Bakkerij")
    with pytest.raises(OngeldigeInstelling) as refused:
        save_organization(db_session, account.id, {"name": "Nieuwe naam", "vat_number": text})
    assert refused.value.fouten["vat_number"] == REFUSED["vat_number"]
    assert db_session.get(Organization, account.id).name == "Bakkerij"
    assert not organization_details(db_session, account.id)["vat_number"]


@pytest.mark.ui_serverrendered
@pytest.mark.parametrize(
    "field, text",
    [("enterprise_number", "123"), ("vat_number", "BE 0123.456.789")],
)
def test_the_reason_names_its_field(client, platform_workspace, db_session, field, text):
    account = create_organization(
        db_session, name="Bakkerijbakkerij-veld-{field.replace('_', '-')}"
    )
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db_session.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)

    answer = client.post(
        f"/admin/organisaties/{account.id}",
        data={"name": "Bakkerij", field: text},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )

    assert answer.status_code == 422
    html = answer.text
    # The answer is the kit's banner (#1932): the reason is a link to its field,
    # which `record-form.js` marks in the page and `aria-describedby`-links.
    link_at = html.index(f'data-error-for="{field}"')
    assert REFUSED[field] in html[link_at : html.index("</a>", link_at)]
    assert answer.headers["HX-Retarget"] == "#org-melding"
    # Only the refused field is named.
    assert html.count("data-error-for=") == 1
