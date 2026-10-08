"""#870 (F from #529) — logging out, and where you land after logging in.

Two uncovered spots in `auth/ui.py` on this tree:

- **`/afmelden` (85-91)** is called by no test at all. A session that survives a logout is
  something nobody would notice: the button disappears, the screen looks logged out, and
  the cookie still works. That half is authorisation.
- **the role-dependent landing (69-72)**. Only the ADMIN/OPERATOR branch was tested; the
  FINANCE-only branch (→ `/admin/betalingen`, because the workbench would 403) and the
  plain-member branch (→ `/leden/gezin`; since CR-22, #1707, the account page `/mijn`)
  were not.

The hermeting called those landings optional — *"inconvenience, not a leak"*. Koen took them
anyway, and that is defensible: three tests of five lines, and a landing that ends up
somewhere else after a release is exactly the kind of thing nobody reports and everybody is
annoyed by.

Broken on purpose to check that these tests can go red: `clear_session_cookie` skipped in
`/afmelden` → the logout test falls over with a session that still works; and the
FINANCE-only branch changed to the workbench → that landing test falls over with the 403
Koen would have hit.
"""

import pytest

from app.domains.auth.api import User, UserRole
from tests.conftest import sent_to_sign_in

pytestmark = pytest.mark.ui_serverrendered


def _user_with(db, email, *roles):
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.flush()
    return user


def _login_through_the_screen(client, db, email, monkeypatch):
    from app.domains.auth import login as auth_login

    monkeypatch.setattr(auth_login, "_generate_otp", lambda: "424242")
    client.post("/aanmelden", data={"email": email})
    return client.post("/aanmelden/code", data={"email": email, "code": "424242"})


def test_logging_out_really_ends_the_session(client, db_session, monkeypatch):
    """Niet "de knop is weg" maar "de cookie werkt niet meer".

    Een sessie die een uitlog overleeft ziet er uitgelogd uit en is het niet — dat merkt
    niemand, en het is de helft van dit issue die over autorisatie gaat.

    **Inloggen gaat hier door het échte scherm**, en dat is geen omweg. De eerste versie
    plantte de cookie met `client.cookies.set()` en faalde: zo'n handmatige cookie draagt
    geen domein, terwijl de `Set-Cookie` van het antwoord dat wél doet, en dan zijn het
    voor de cookiejar twee verschillende regels — het uitloggen verwijdert de ene en laat
    de andere staan. De server deed het goed; de opzet deugde niet. Een test die dat
    "oplost" door de `Set-Cookie`-header te controleren in plaats van het effect, toetst
    de melding en niet het uitloggen.
    """
    _user_with(db_session, "uitloggen@example.com", "ADMIN")
    _login_through_the_screen(client, db_session, "uitloggen@example.com", monkeypatch)
    assert client.get("/admin/werkbank").status_code == 200, "opzet klopt niet (#678)"

    resp = client.get("/afmelden", follow_redirects=False)

    assert resp.status_code == 302 and resp.headers["location"] == "/"
    assert sent_to_sign_in(client, "/admin/werkbank"), "de sessie werkt nog na het uitloggen"


@pytest.mark.parametrize(
    "rollen,doel",
    [
        # #1740 (Koen, 8 October 2026): the door decides, not the role. These rows
        # said the workbench and payments; a board user who signs in on the site
        # lands on the site like everyone else, and finds Admin in his menu.
        (("ADMIN",), "/"),
        (("FINANCE",), "/"),
        # CR-22 (#1707): this user has no role and is no person on this tenant, so
        # he has no account page — he lands on the site. Until then this row said
        # `/leden/gezin`, a page that sent him straight back to the sign-in. Who
        # signs in AS a person lands on `/mijn`: `test_account_sign_in_1707.py`.
        ((), "/"),
    ],
)
def test_you_land_on_the_site_whatever_your_role(client, db_session, monkeypatch, rollen, doel):
    """#1740: nobody lands in the back office by signing in on the site. (#530 sent
    FINANCE to payments because the workbench refused them; that knowledge is the
    back office's now — `back_office_home`, held in `test_landing_by_door_1740.py`.)

    #530: FINANCE-only hoort op betalingen uit te komen, want de werkbank zou 403'en.

    Alleen de ADMIN-tak was getest. Een landing die na een release ergens anders uitkomt,
    meldt niemand — en een FINANCE-gebruiker die op een 403 landt, denkt dat hij geen
    toegang meer heeft.
    """
    email = f"landing-{'-'.join(rollen) or 'lid'}@example.com"
    _user_with(db_session, email, *rollen)

    resp = _login_through_the_screen(client, db_session, email, monkeypatch)

    assert resp.status_code == 200, resp.text[:200]
    assert resp.headers.get("HX-Redirect") == doel, (
        f"{rollen or 'geen rol'} landt op {resp.headers.get('HX-Redirect')} in plaats van {doel}"
    )


def test_an_invalid_e_mail_address_is_refused_before_anything_is_sent(client, db_session):
    """De derde ongedekte regel (`auth/ui.py:40`): geen `@` betekent geen poging."""
    resp = client.post("/aanmelden", data={"email": "geen-adres"})

    assert resp.status_code == 200
    assert "geldig e-mailadres" in resp.text
