"""CR-11 W17 (#1391): the member nudge on the public registration.

One sentence, unconditional, above the contact fields — since CR-22 S5 (#1709;
A3, Q39) *"Heb je een account of ben je lid? Log je eerst aan."*; it was *"Lid
van RAAK? Log je eerst aan: dan staat de inschrijving bij je gezin."* — with a sign-in link that
returns to the page. Never on recognition of an address (the form looks nothing
up, and a hint would leak whether an address is a member's). A signed-in member
does not see it.

Since #1590 "Word lid" has no nudge (end state §2.6: the page is for who is not
a member yet); the sentence stays on the public registration. The first test
asks both: there on the registration, not there on Word lid — the same sentence
looked for in the same way, so the one finding proves the other is looking.

Proven red: the `{% if not (gebruiker and gebruiker.is_member) %}` guard removed
→ the member test fails; the `if return_to: dest = return_to` removed from the
sign-in → the return test fails; `veilige_terug` bypassed → the //evil test fails.
"""

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import quote

import pytest

from app.domains.activities.api import Activity, ActivityDate, ActivitySubRegistration
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

SENTENCE_START = "Heb je een account of ben je lid?"


def _registration_page(db):
    a = Activity(name="Kwis W17", location="Zaal")
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=14)))
    c = ActivitySubRegistration(
        activity_id=a.id, name="Ploeg", registration_type_code="INDIVIDUAL", price=Decimal("0")
    )
    db.add(c)
    db.commit()
    return f"/activiteiten/{a.id}/inschrijven/{c.id}"


def test_an_anonymous_visitor_sees_the_nudge_with_a_link_back(client, db_session):
    path = _registration_page(db_session)
    html = client.get(path).text
    assert SENTENCE_START in html
    assert f'href="/aanmelden?terug={quote(path)}"' in html
    # Above the contact fields.
    assert html.index("data-member-nudge") < html.index('type="email"')

    signup = client.get("/lid-worden")
    assert signup.status_code == 200 and 'id="lid-worden-form"' in signup.text
    assert SENTENCE_START not in signup.text and "data-member-nudge" not in signup.text


def test_a_signed_in_member_does_not_see_it(client, db_session):
    path = _registration_page(db_session)
    assert SENTENCE_START in client.get(path).text, "the anonymous half of the pair"
    create_test_family(db_session, email="lid-w17@example.com")
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value("lid-w17@example.com"))
    assert SENTENCE_START not in client.get(path).text


def _sign_in(client, monkeypatch, email, return_to):
    from app.domains.auth import login as auth_login

    monkeypatch.setattr(auth_login, "_generate_otp", lambda: "424242")
    first = client.get("/aanmelden", params={"terug": return_to})
    step = client.post("/aanmelden", data={"email": email, "terug": return_to})
    done = client.post(
        "/aanmelden/code", data={"email": email, "code": "424242", "terug": return_to}
    )
    return first.text, step.text, done


def test_the_sign_in_returns_to_the_page(client, db_session, monkeypatch):
    path = _registration_page(db_session)
    create_test_family(db_session, email="terug-w17@example.com")
    db_session.commit()
    first, step, done = _sign_in(client, monkeypatch, "terug-w17@example.com", path)
    assert f'name="terug" value="{path}"' in first, "the first step drops the page"
    assert f'name="terug" value="{path}"' in step, "the code step drops the page"
    assert done.headers.get("HX-Redirect") == path


def test_a_foreign_address_is_not_followed(client, db_session, monkeypatch):
    create_test_family(db_session, email="evil-w17@example.com")
    db_session.commit()
    first, _step, done = _sign_in(client, monkeypatch, "evil-w17@example.com", "//evil.example/x")
    assert 'name="terug"' not in first
    # CR-22 (#1707): a member lands on the account page, no longer on Mijn gezin.
    assert done.headers.get("HX-Redirect") == "/mijn", "the landing by role"
