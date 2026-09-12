"""#884 — an optional friendly URL next to the number URL.

Koen: *"Would it be possible to optionally define a friendly URL next to the current one
(e.g. `/activiteiten/7/fotos`)?"*

Follows the pattern the CMS pages already use: a `slug`, unique **per tenant**. Optional —
without a slug everything behaves exactly as today.

**The dangerous part is the least visible one, and it is a decision, not an implementation
detail.** Somebody shares `/activiteiten/zomerfeest-2026/fotos` in a WhatsApp group; a month
later a board member renames the activity, the slug follows, and every shared link is dead —
without anybody noticing, because whoever clicks it is not a board member.

**So the slug does not follow the name.** At creation one is proposed from the name; after
that it stays, rename or no rename. A board member may edit it, and the screen says on the
spot that earlier shared links will stop working. `test_renaming_does_not_move_the_slug` is
the test that holds this, and it is here because **a slug that silently follows the name is
the default assumption for this kind of work** — it is the behaviour that creeps in
unnoticed.

**Exactly one of the two addresses is canonical.** Otherwise Google indexes both and splits
the value over two pages — you weaken precisely what you set out to strengthen. The slug is
canonical; the number URL points at it.

Broken on purpose to check that these tests can go red:

- `slug` added to the fields `update_activity` derives from the name → two fall over: the
  rename test with the slug moved along (exactly the silent breakage above), and the
  collision test, because a derived slug never passes the check.
- the `canonical_url` line removed from the album route → two fall over, one per address
  form; both then claim to be the original, or neither says anything at all.
- `_controleer_slug` made to append a number on a collision instead of refusing → the
  collision test falls over: the board member then gets an address they never chose and
  never see.
"""
from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _activity(db, *, name="Zomerfeest 2026", slug=None):
    activity = Activity(name=name, slug=slug)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2026, 7, 1)))
    db.flush()
    return activity


def test_both_addresses_reach_the_same_album(client, db_session):
    activity = _activity(db_session, slug="zomerfeest-2026")

    op_nummer = client.get(f"/activiteiten/{activity.id}/fotos")
    op_slug = client.get("/activiteiten/zomerfeest-2026/fotos")

    assert op_nummer.status_code == 200, op_nummer.text[:200]
    assert op_slug.status_code == 200, op_slug.text[:200]
    assert "Zomerfeest 2026" in op_slug.text


def test_the_number_url_keeps_working_without_a_slug(client, db_session):
    """De test die verhindert dat iemand de nummer-URL later opruimt omdat "alles nu de
    slug gebruikt". Er staan nummer-URL's in verstuurde e-mails en in de zoekmachine."""
    activity = _activity(db_session, name="Zonder adres", slug=None)

    resp = client.get(f"/activiteiten/{activity.id}/fotos")

    assert resp.status_code == 200
    assert "Zonder adres" in resp.text


def test_exactly_one_address_is_canonical(client, db_session):
    """Bestaat dezelfde pagina op twee adressen zonder dat je zegt welke de echte is, dan
    indexeert Google ze allebei en verdeelt hij de waarde."""
    activity = _activity(db_session, slug="kerstmarkt-2026")

    van_nummer = client.get(f"/activiteiten/{activity.id}/fotos").text
    van_slug = client.get("/activiteiten/kerstmarkt-2026/fotos").text

    for html, bron in ((van_nummer, "de nummer-URL"), (van_slug, "de slug-URL")):
        canonical = html.split('rel="canonical" href="', 1)[1].split('"', 1)[0]
        assert canonical.endswith("/activiteiten/kerstmarkt-2026/fotos"), (
            f"{bron} wijst niet naar de slug als canoniek adres: {canonical}")


def test_renaming_does_not_move_the_slug(client, db_session):
    """**De test die dit issue draagt.**

    Een slug die zwijgend meeverandert met de naam is de standaardaanname bij dit soort
    werk. Hier is ze fout: dan sterft elke gedeelde link bij een hernoeming, en dat merkt
    niemand — wie op zo'n link klikt is geen bestuurder en meldt het dus nooit.
    """
    headers = _login(client, db_session)
    activity = _activity(db_session, name="Zomerfeest", slug="zomerfeest-2026")

    resp = client.post(f"/admin/activiteiten/{activity.id}", headers=headers,
                       data={"name": "Zomerfeest editie 2", "location": "",
                             "poster_url": "", "slug": "zomerfeest-2026"})

    assert resp.status_code == 200, resp.text[:200]
    db_session.refresh(activity)
    assert activity.name == "Zomerfeest editie 2", "de naam is niet gewijzigd"
    assert activity.slug == "zomerfeest-2026", (
        "de slug is meeveranderd met de naam — dan is elke gedeelde link dood")
    assert client.get("/activiteiten/zomerfeest-2026/fotos").status_code == 200


def test_a_collision_is_refused_visibly(client, db_session):
    """Zichtbaar weigeren en niet stil een cijfer erachter zetten: dan krijgt de
    bestuurder een adres dat hij niet gekozen heeft en nergens ziet."""
    headers = _login(client, db_session)
    _activity(db_session, name="Eerste", slug="zelfde-adres")
    tweede = _activity(db_session, name="Tweede", slug=None)

    resp = client.post(f"/admin/activiteiten/{tweede.id}", headers=headers,
                       data={"name": "Tweede", "location": "", "poster_url": "",
                             "slug": "zelfde-adres"})

    assert "al in gebruik" in resp.text, resp.text[:300]
    db_session.refresh(tweede)
    assert tweede.slug is None, "de botsende slug is toch bewaard"


def test_two_tenants_may_share_a_slug(db_session):
    """De uniciteit is PER TENANT, net als bij de CMS-pagina's. Twee afdelingen zijn
    andere verenigingen op andere adressen; een globale regel zou de eerste die een naam
    gebruikt hem van alle andere afpakken."""
    from app.domains.activities.api import slug_is_vrij
    from app.kernel.tenancy import current_tenant_id

    _activity(db_session, name="Bij afdeling A", slug="buurtfeest")
    db_session.flush()

    token = current_tenant_id.set(7)
    try:
        assert slug_is_vrij(db_session, "buurtfeest"), (
            "de slug van een andere afdeling blokkeert deze afdeling")
    finally:
        current_tenant_id.reset(token)


def test_an_activity_without_a_slug_behaves_as_today(client, db_session):
    """De tegenproef: zonder slug verandert er niets — geen canonieke omleiding naar een
    adres dat niet bestaat."""
    activity = _activity(db_session, name="Gewoon", slug=None)

    html = client.get(f"/activiteiten/{activity.id}/fotos").text

    canonical = html.split('rel="canonical" href="', 1)[1].split('"', 1)[0]
    assert canonical.endswith(f"/activiteiten/{activity.id}/fotos"), canonical


def test_the_proposal_comes_from_the_name_at_creation(db_session):
    """Bij het AANMAKEN wel een voorstel — daarna nooit meer."""
    from app.domains.activities import service

    nieuw = service.create_activity(db_session, name="Quiz van de Buurt 2026",
                                    actor="test")

    assert nieuw.slug == "quiz-van-de-buurt-2026", nieuw.slug


def test_an_unknown_slug_is_a_404(client, db_session):
    assert client.get("/activiteiten/bestaat-niet/fotos").status_code == 404
