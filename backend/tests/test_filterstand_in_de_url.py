"""#671 — de filterstand zit in de browser-URL en overleeft een mutatie.

`_view` las context/status/q uitsluitend uit `request.query_params`. Dat klopt
voor de GET van de filterbalk, maar een **mutatie** post naar een eigen endpoint
zonder die parameters: alles viel terug op de default en de volledige lijst kwam
terug, terwijl de balk de oude keuze bleef tonen (enkel het fragment wordt
geswapt).

De filterbalk merkt zich nu met `X-Raak-Filter`, de server zet `HX-Push-Url` op
het **paginapad** met dezelfde query, en `app.ui.filterparams()` leest die URL
weer uit `HX-Current-URL`. Eén helper voor de vier modules die hun filter zo
lezen — vier eigen varianten is precies hoe dit ontstond.

Niet `hx-push-url="true"` op de balk: dat duwt de URL van het VERZOEK, en vier van
de elf balken vragen een eigen `…/lijst`-route. Een F5 daarop geeft het kale
fragment zonder schil.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    gebruiker = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in gebruiker.roles):
        db.add(UserRole(user_id=gebruiker.id, role_code="FINANCE"))
        db.flush()
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _twee_records(db):
    lid = PaymentRecord(payable_type="membership", payable_id=6710,
                        amount=Decimal("20.00"), method="transfer", status="pending")
    insch = PaymentRecord(payable_type="registration", payable_id=6711,
                          amount=Decimal("35.00"), method="transfer", status="pending")
    db.add_all([lid, insch])
    db.commit()
    return lid, insch


def test_de_filterbalk_duwt_het_paginapad_niet_het_fragment(client, db_session):
    """De valkuil: een F5 op de fragment-URL geeft een pagina zonder schil."""
    _twee_records(db_session)
    _login(client, db_session)

    r = client.get("/admin/betalingen/lijst?context=membership",
                   headers={"HX-Request": "true", "X-Raak-Filter": "1"})
    assert r.status_code == 200
    assert r.headers.get("HX-Push-Url") == "/admin/betalingen?context=membership", (
        "de geduwde URL hoort het paginapad te zijn, niet /lijst")


def test_zonder_de_filterbalk_wordt_er_niets_geduwd(client, db_session):
    """Een detailfragment hoort de adresbalk niet te veranderen."""
    _twee_records(db_session)
    _login(client, db_session)

    r = client.get("/admin/betalingen/lijst?context=membership",
                   headers={"HX-Request": "true"})
    assert "HX-Push-Url" not in r.headers


@pytest.mark.parametrize("stand,verborgen", [
    ("context=membership", "35.00"),
    ("status=paid", "20.00"),
    ("q=zzz-bestaat-niet", "20.00"),
])
def test_de_filterstand_overleeft_een_mutatie(client, db_session, stand, verborgen):
    """Alle drie de filters lopen via dezelfde weg: werkt er één en de andere niet,
    dan is de fix half."""
    lid, _insch = _twee_records(db_session)
    csrf = _login(client, db_session)

    r = client.post(f"/admin/betalingen/{lid.id}/bevestigen",
                    headers={"X-CSRF-Token": csrf,
                             "HX-Request": "true",
                             "HX-Current-URL": f"http://testserver/admin/betalingen?{stand}"})
    assert r.status_code == 200
    assert verborgen not in r.text and verborgen.replace(".", ",") not in r.text, (
        f"met {stand} hoort {verborgen} niet in de lijst te staan")


def test_de_query_string_wint_van_de_huidige_url(client, db_session):
    """De filterbalk stuurt haar nieuwe keuze in de query-string; die is verser dan
    de URL waar de gebruiker vandaan komt."""
    _twee_records(db_session)
    _login(client, db_session)

    r = client.get("/admin/betalingen/lijst?context=all",
                   headers={"HX-Request": "true", "X-Raak-Filter": "1",
                            "HX-Current-URL": "http://testserver/admin/betalingen?context=membership"})
    assert "35.00" in r.text or "35,00" in r.text, (
        "de nieuwe keuze uit de query-string werd overruled door de oude URL")


def test_een_gewone_get_leest_nog_uit_de_query_string(client, db_session):
    """Zonder htmx is er geen HX-Current-URL — een gedeelde link of een F5."""
    _twee_records(db_session)
    _login(client, db_session)

    r = client.get("/admin/betalingen?context=membership")
    assert r.status_code == 200
    assert "35.00" not in r.text and "35,00" not in r.text


def test_de_filterbalk_draagt_de_markering():
    kit = open("app/ui/templates/_macros.html", encoding="utf-8").read()
    balk = kit[kit.index("{% macro filter_bar("):]
    balk = balk[:balk.index("{%- endmacro %}")]
    assert "X-Raak-Filter" in balk
    assert 'hx-push-url="true"' not in balk, (
        "hx-push-url op de balk duwt de fragment-URL; dat is precies de valkuil")
