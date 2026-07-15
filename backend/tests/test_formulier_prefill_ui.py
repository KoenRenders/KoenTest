"""Publiek formulier: voorinvullen van naam/e-mail voor een ingelogd lid (#454).
Een niet-ingelogde bezoeker krijgt lege velden; een ingelogd lid ziet zijn naam
en e-mail al ingevuld (zonder een reeds getypte waarde te overschrijven)."""
from tests.conftest import create_test_family
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.test_forms import _create_form


def test_form_prefilled_for_logged_in_member(client, admin_headers, db_session):
    form = _create_form(client, admin_headers, is_anonymous=False)
    create_test_family(db_session, email="lid@example.com")
    db_session.commit()

    client.cookies.set(SESSION_COOKIE, make_session_value("lid@example.com"))
    html = client.get(f"/formulier/{form['share_token']}").text
    # E-mail van het lid staat voorgevuld in het submitter_email-veld.
    assert 'id="submitter_email"' in html and 'value="lid@example.com"' in html
    # De naam van de testpersoon (Test Persoon) staat in submitter_name.
    assert 'value="Test Persoon"' in html


def test_form_not_prefilled_for_anonymous_visitor(client, admin_headers):
    form = _create_form(client, admin_headers, is_anonymous=False)
    html = client.get(f"/formulier/{form['share_token']}").text
    assert 'id="submitter_email"' in html
    assert 'value="lid@example.com"' not in html
