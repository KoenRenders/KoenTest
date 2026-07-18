"""React-exit 405-b: ledenportaal (/leden/gezin) + login-pariteit (htmx)."""
from datetime import date, timedelta

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person
from tests.conftest import create_test_family, seed_postal_code


def _login_as(client, email):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_gezin_redirect_zonder_sessie(client):
    resp = client.get("/leden/gezin", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"] == "/aanmelden"


def test_gezin_portaal_toont_leden_en_muteert(client, db_session):
    member, person = create_test_family(db_session, email="portaal@example.com")
    csrf = _login_as(client, "portaal@example.com")

    page = client.get("/leden/gezin")
    assert page.status_code == 200 and "Mijn gezin" in page.text and person.first_name in page.text

    resp = client.post(f"/leden/gezin/personen/{person.id}",
                       data={"first_name": "Aangepast", "last_name": person.last_name,
                             "email": "portaal@example.com"},  # #511: veldnaam `email`
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Aangepast" in resp.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name == "Aangepast"

    nieuw = client.post("/leden/gezin/personen",
                        data={"first_name": "Kindje", "last_name": "Persoon"},
                        headers={"X-CSRF-Token": csrf})
    assert nieuw.status_code == 200 and "Kindje" in nieuw.text


def test_gezin_mutatie_zonder_csrf(client, db_session):
    member, person = create_test_family(db_session, email="csrfloos@example.com")
    _login_as(client, "csrfloos@example.com")
    resp = client.post(f"/leden/gezin/personen/{person.id}",
                       data={"first_name": "X", "last_name": "Y"})
    assert resp.status_code == 403


def test_home_word_lid_wordt_mijn_gezin_voor_ingelogd_lid(client, db_session):
    """#499: op de homepage ziet een ingelogd lid 'Mijn gezin' (→ /leden/gezin)
    i.p.v. de 'Word lid'-knop naar het lege registratieformulier."""
    # Anoniem → 'Word lid' naar /lid-worden (die link staat enkel in de home-CTA).
    assert 'href="/lid-worden"' in client.get("/").text
    # Ingelogd lid → CTA wijst naar /leden/gezin, geen /lid-worden meer.
    create_test_family(db_session, email="home-lid@example.com")
    _login_as(client, "home-lid@example.com")
    html = client.get("/").text
    assert 'href="/leden/gezin"' in html
    assert 'href="/lid-worden"' not in html


def test_coverage_telt_al_betaald_volgend_jaar(db_session):
    """#496: een al betaald volgend jaar telt mee voor de dekking ('geldig tot'), en
    de vernieuwknop verbergt zich dan i.p.v. op een 409 'al vernieuwd' te botsen."""
    from app.domains.membership.api import Membership
    from app.domains.membership.service import (
        membership_coverage_until, renewal_available, valid_membership_until)

    member, person = create_test_family(db_session, email="cov@example.com")
    y = date.today().year
    db_session.add(Membership(member_id=member.id, year=y,
                              valid_from=date(y, 1, 1), valid_to=date(y, 12, 31), is_active=True))
    db_session.add(Membership(member_id=member.id, year=y + 1,
                              valid_from=date(y + 1, 1, 1), valid_to=date(y + 1, 12, 31), is_active=True))
    db_session.commit()
    db_session.expire_all()
    person = db_session.get(Person, person.id)

    ref = date(y, 6, 1)
    # 'Geldig vandaag' blijft dit jaar (ledenprijzen ongemoeid); de dekking incl.
    # toekomst reikt tot volgend jaar.
    assert valid_membership_until(person, ref) == date(y, 12, 31)
    assert membership_coverage_until(person, ref) == date(y + 1, 12, 31)
    # Al gedekt voor volgend jaar → geen vernieuwknop (dus geen 409-val).
    assert renewal_available(date(y + 1, 12, 31), ref) is False
    # Geen dekking → knop wél.
    assert renewal_available(None, ref) is True


def test_vernieuwen_via_overschrijving(db_session):
    """#497: vernieuwen met overschrijving maakt een transfer-charge (met OGM) en
    vereist géén online checkout (i.p.v. geforceerd online)."""
    from app.domains.membership.household_router import renew_membership
    from app.domains.payment.api import PaymentRecord

    _member, person = create_test_family(db_session, email="renew-transfer@example.com")
    result = renew_membership(person=person, db=db_session, payment_method="transfer")
    assert result["checkout_url"] is None and result["payment_method"] == "transfer"
    charge = (db_session.query(PaymentRecord)
              .filter(PaymentRecord.payable_type == "membership")
              .order_by(PaymentRecord.id.desc()).first())
    assert charge is not None and charge.method == "transfer"
    assert charge.structured_communication  # OGM gezet voor de overschrijving


def test_login_redirects_naar_aanmelden(client):
    for pad in ("/login", "/leden/login"):
        resp = client.get(pad, follow_redirects=False)
        assert resp.status_code == 302 and resp.headers["location"] == "/aanmelden"


def test_login_verify_zet_sessie_en_stuurt_door(client, db_session):
    from app.domains.auth.models import LoginToken
    from datetime import datetime, timezone

    create_test_family(db_session, email="magiclink@example.com")
    token = "testtoken-magic-123"
    db_session.add(LoginToken(email="magiclink@example.com", token=token,
                              expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
    db_session.flush()

    resp = client.get(f"/login/verify?token={token}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/leden/gezin"
    assert SESSION_COOKIE in resp.cookies

    verlopen = client.get("/login/verify?token=bestaat-niet", follow_redirects=False)
    assert verlopen.status_code == 401


def test_magic_link_landing_per_rol(client, db_session):
    """#530: de magic-link-landing volgt de rol — een FINANCE-only account gaat naar
    /admin/betalingen (werkbank zou 403'en), ADMIN naar /admin/werkbank; voorheen
    ging iedereen met ADMIN of FINANCE naar werkbank."""
    from app.domains.auth.models import LoginToken, User, UserRole
    from datetime import datetime, timezone

    def _token(email, *roles):
        u = User(email=email, is_active=True)
        db_session.add(u)
        db_session.flush()
        for r in roles:
            db_session.add(UserRole(user_id=u.id, role_code=r))
        tok = f"tok-{email}"
        db_session.add(LoginToken(email=email, token=tok,
                                  expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
        db_session.flush()
        return tok

    fin = _token("fin-magic@example.com", "FINANCE")
    r_fin = client.get(f"/login/verify?token={fin}", follow_redirects=False)
    assert r_fin.headers["location"] == "/admin/betalingen"

    adm = _token("adm-magic@example.com", "ADMIN")
    r_adm = client.get(f"/login/verify?token={adm}", follow_redirects=False)
    assert r_adm.headers["location"] == "/admin/werkbank"
