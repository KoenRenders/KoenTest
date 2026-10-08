"""The screens of making an account and signing in (CR-22 S4b, #1708; R1, R3;
C9; the screen side of T4 and T5).

- **the sign-in screen has the second door**: the link "Account aanmaken", and
  it carries the page to return to;
- **`/account-aanmaken`** asks four fields — Voornaam, Achternaam, E-mail,
  Mobiel — each through the kit's field with the required asterisk, and no
  "Verplicht veld" legend; nothing else is asked (no address, birth date or
  gender);
- **each refusal stands under its own field**, the border in the danger tone,
  what was typed kept; nothing is made and no code is sent;
- **a good request is answered by the code step** — "We stuurden een code naar
  dit adres." with the button "Bevestigen" — and **the answer is the same for
  an address that already has an owner**; no person exists before the code;
- the code step keeps its button after a wrong code, and the right code makes
  the account, signs in and lands on the account page;
- the sign-in's own code step says the same sentence, with "Inloggen";
- **the route is limited per IP** like the sign-in (`login_limiter`).

Red (each restored after): the `error=` taken off the e-mail field → the
refusal is not under its field; `start_account` answered with a different
template for a known address → the two answers differ; the limiter taken off
the route → no 429; the hidden `nieuw` field taken out of the code step → the
button reads "Inloggen" after a wrong code. On master there is no route
`/account-aanmaken`.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth import login as auth_login
from app.domains.auth.api import SESSION_COOKIE, LoginToken
from app.domains.mdm.api import ContactDetail, Person
from app.limiter import login_limiter
from tests.conftest import create_test_person

pytestmark = pytest.mark.ui_serverrendered

PAGE = "/account-aanmaken"
CODE = "424242"
SENTENCE = "We stuurden een code naar dit adres."
GOOD = {
    "first_name": "Nora",
    "last_name": "Nieuw",
    "email": "nora-1708@example.org",
    "mobile": "0470 00 17 08",
}


@pytest.fixture(autouse=True)
def a_known_code_and_a_fresh_limiter(monkeypatch):
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: CODE)
    login_limiter._calls.clear()
    yield
    login_limiter._calls.clear()


@pytest.fixture(autouse=True)
def no_mail_leaves(monkeypatch):
    from app.domains.mail import service

    monkeypatch.setattr(service, "_send", lambda *a, **k: None)


def _field(html: str, name: str) -> str:
    """The kit's field of this name, up to the next field."""
    start = html.index(f'data-field="{name}"')
    following = html.find('data-field="', start + 1)
    end = following if following != -1 else html.find("</form>", start)
    return html[start : end if end != -1 else len(html)]


def _persons(db) -> int:
    db.expire_all()
    return db.query(Person).count()


# ── the sign-in screen ───────────────────────────────────────────────────────


def test_the_sign_in_screen_has_the_second_door(client):
    html = client.get("/aanmelden").text
    link = re.search(r"<p data-create-account[^>]*>(.*?)</p>", html, re.S)
    assert link, "no way to Account aanmaken on the sign-in screen"
    assert 'href="/account-aanmaken"' in link.group(1) and ">Account aanmaken</a>" in link.group(1)
    # The page that sent the visitor here travels to the second door too.
    there = client.get("/aanmelden", params={"terug": "/activiteiten/12"}).text
    assert 'href="/account-aanmaken?terug=/activiteiten/12"' in there
    # … and never an address outside this site.
    away = client.get("/aanmelden", params={"terug": "https://elders.example.org/"}).text
    assert "elders.example.org" not in away


def test_the_sign_in_code_step_says_the_one_sentence(client):
    step = client.post("/aanmelden", data={"email": "niemand-1708@example.org"}).text
    assert SENTENCE in step and "Als dit e-mailadres gekend is" not in step
    assert re.search(r"<button[^>]*>\s*(?:<[^>]+>\s*)*Inloggen", step), "the button is not Inloggen"
    assert 'name="nieuw"' not in step


# ── the form ─────────────────────────────────────────────────────────────────


def test_the_page_asks_four_required_fields_and_nothing_else(client):
    page = client.get(PAGE)
    assert page.status_code == 200
    html = page.text
    assert "<h1" in html and "Account aanmaken" in html and 'content="noindex"' in html
    form = html[html.index("data-create-account-form") : html.index("</form>")]
    fields = re.findall(r'data-field="([^"]+)"', form)
    assert fields == ["first_name", "last_name", "email", "mobile"], fields
    for name, label in (
        ("first_name", "Voornaam"),
        ("last_name", "Achternaam"),
        ("email", "E-mail"),
        ("mobile", "Mobiel"),
    ):
        part = _field(form, name)
        assert re.search(rf">\s*{label}\s*<span class=\"text-red-600\">\*</span>", part), (
            f"{name}: no label {label!r} with the required asterisk"
        )
        assert re.search(rf'<input[^>]*name="{name}"[^>]*required', part), f"{name} is not required"
        assert "aria-invalid" not in part
    assert "Verplicht veld" not in html
    assert 'type="email"' in _field(form, "email") and 'type="tel"' in _field(form, "mobile")
    assert 'href="/aanmelden"' in html[html.index("data-to-sign-in") :]


def test_each_refusal_stands_under_its_own_field_and_nothing_is_made(client, db_session):
    before, tokens = _persons(db_session), db_session.query(LoginToken).count()
    answer = client.post(
        PAGE, data={"first_name": " ", "last_name": "Nieuw", "email": "geen-adres", "mobile": ""}
    )
    assert answer.status_code == 200
    html = answer.text
    assert "data-create-account-form" in html and SENTENCE not in html
    for name, message in (
        ("first_name", "Vul je voornaam in."),
        ("email", "Vul een geldig e-mailadres in."),
        ("mobile", "Vul je mobiel nummer in."),
    ):
        part = _field(html, name)
        assert message in part, f"{name}: its refusal is not under the field"
        assert 'aria-invalid="true"' in part and "border-red-700" in part
    good = _field(html, "last_name")
    assert "aria-invalid" not in good and 'value="Nieuw"' in good
    assert 'value="geen-adres"' in _field(html, "email"), "what was typed is gone"
    assert html.count("Vul je voornaam in.") == 1, "a refusal stands twice"
    assert _persons(db_session) == before
    assert db_session.query(LoginToken).count() == tokens


def test_a_good_request_gets_the_code_step_and_no_person_yet(client, db_session):
    before = _persons(db_session)
    step = client.post(PAGE, data={**GOOD, "terug": "/activiteiten/12"})
    assert step.status_code == 200
    html = step.text
    assert SENTENCE in html and "data-create-account-form" not in html
    assert f'name="email" value="{GOOD["email"]}"' in html
    assert 'name="nieuw" value="1"' in html and 'name="terug" value="/activiteiten/12"' in html
    assert re.search(r"<button[^>]*>\s*(?:<[^>]+>\s*)*Bevestigen", html), (
        "the button is not Bevestigen"
    )
    assert 'hx-post="/aanmelden/code"' in html
    assert _persons(db_session) == before, "a person exists before the code"
    assert db_session.query(LoginToken).filter_by(email=GOOD["email"]).count() == 1


def test_an_address_with_an_owner_gets_the_same_answer(client, db_session):
    owner = create_test_person(db_session, first_name="Otto", last_name="Eigenaar")
    from app.domains.mdm.api import new_contact_detail

    db_session.add(
        new_contact_detail(db_session, owner, "EMAIL", "otto-1708@example.org", is_primary=True)
    )
    db_session.commit()
    before = _persons(db_session)
    free = client.post(PAGE, data=GOOD)
    taken = client.post(PAGE, data={**GOOD, "email": "otto-1708@example.org"})
    assert free.status_code == taken.status_code == 200
    assert free.text.replace(GOOD["email"], "x") == taken.text.replace("otto-1708@example.org", "x")
    assert _persons(db_session) == before, "the answer made a person"


def test_the_code_makes_the_account_and_a_wrong_code_keeps_the_button(client, db_session):
    client.post(PAGE, data=GOOD)
    wrong = client.post(
        "/aanmelden/code", data={"email": GOOD["email"], "code": "000000", "nieuw": "1"}
    )
    assert "Ongeldige of verlopen code." in wrong.text
    assert re.search(r"<button[^>]*>\s*(?:<[^>]+>\s*)*Bevestigen", wrong.text), (
        "the step lost its button's word after a wrong code"
    )
    assert 'name="nieuw" value="1"' in wrong.text and SESSION_COOKIE not in wrong.cookies

    before = _persons(db_session)
    done = client.post("/aanmelden/code", data={"email": GOOD["email"], "code": CODE, "nieuw": "1"})
    assert done.headers.get("HX-Redirect") == "/mijn" and SESSION_COOKIE in done.cookies
    assert _persons(db_session) == before + 1
    person = (
        db_session.query(Person)
        .join(ContactDetail, ContactDetail.person_id == Person.id)
        .filter(ContactDetail.value == GOOD["email"])
        .one()
    )
    assert (person.first_name, person.last_name) == ("Nora", "Nieuw")
    assert (person.date_of_birth, person.gender_code, person.address) == (None, None, None)
    assert not person.member_persons, "an account got a household"


def test_the_route_is_limited_per_ip_like_the_sign_in(client, db_session):
    answers = [
        client.post(PAGE, data={**GOOD, "email": f"n{i}-1708@example.org"}) for i in range(7)
    ]
    codes = [a.status_code for a in answers]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429], codes
    # The page itself stays open: only sending is counted.
    assert client.get(PAGE).status_code == 200
