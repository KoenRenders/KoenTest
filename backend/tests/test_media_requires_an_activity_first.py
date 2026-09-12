"""#891 — the media screen shows nothing until an activity is chosen.

Koen: *"When you land in Media there is a big list of photos from activities that you can
start sorting. That is pointless. I would put there that you first have to select an
activity before you see photos."*

**Sorting has no meaning there.** The order of a photo holds within its own album; across
activities there is no order to set. So you were looking at arrows that do something you
cannot see on that screen.

That is not a coincidence: in #882 the group boundary had to hang on the asset itself
(`kind` + `activity_id` + `component_id`) and **not** on the displayed list, precisely because
an unfiltered list is not a usable group. This removes that contradiction instead of working
around it.

**Only for activity photos.** Sponsors and component info do not hang off an activity, and
there the full list is exactly right — `test_sponsors_are_unchanged` is what keeps this
restriction from grabbing too wide.

Broken on purpose to check that these tests can go red: the `kind == "activity_photo"`
condition dropped from `kies_eerst` → the sponsor test falls over with an empty sponsor list,
which would be the restriction grabbing everything; and the condition inverted → the first
test falls over with the mixed list back.
"""
import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.media.models import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _asset(db, *, kind="activity_photo", activity_id=None, title="iets"):
    asset = MediaAsset(kind=kind, activity_id=activity_id, title=title, sort_order=0,
                       is_active=True, content_type="image/jpeg", byte_size=10,
                       width=10, height=10, data=b"x", thumbnail=b"y")
    db.add(asset)
    db.flush()
    return asset


def test_activity_photos_stay_hidden_until_an_activity_is_chosen(client, db_session):
    _login(client, db_session)
    _asset(db_session, activity_id=11, title="album-elf")
    _asset(db_session, activity_id=12, title="album-twaalf")

    zonder = client.get("/admin/media?kind=activity_photo").text

    assert "album-elf" not in zonder and "album-twaalf" not in zonder, (
        "de foto's van alle activiteiten staan nog door elkaar")
    assert "Kies eerst een activiteit" in zonder, (
        "er staat geen lege staat die zegt wat er van je verwacht wordt")

    met = client.get("/admin/media?kind=activity_photo&activity_id=11").text

    assert "album-elf" in met, "na het kiezen verschijnt het album niet"
    assert "album-twaalf" not in met, "het filter toont ook andere albums"


def test_sponsors_are_unchanged(client, db_session):
    """De test die uitsluit dat de beperking te breed grijpt. Sponsors hangen niet aan
    een activiteit, dus daar is de volle lijst juist de bedoeling."""
    _login(client, db_session)
    _asset(db_session, kind="sponsor", title="logo-een")

    html = client.get("/admin/media?kind=sponsor").text

    assert "logo-een" in html, "de sponsorlijst is leeggevallen"
    assert "Kies eerst een activiteit" not in html


def test_an_activity_without_photos_gives_the_empty_state_and_not_an_error(client, db_session):
    """Een beginpunt en geen weigering: kiezen van een activiteit zonder foto's hoort een
    lege lijst te geven, geen fout."""
    _login(client, db_session)

    resp = client.get("/admin/media?kind=activity_photo&activity_id=999")

    assert resp.status_code == 200
    assert "Kies eerst een activiteit" not in resp.text, (
        "er ís gekozen; dan hoort de gewone lege staat te verschijnen")
    assert "Geen media gevonden" in resp.text or "Nog geen media" in resp.text


def test_the_filter_survives_a_mutation(client, db_session):
    """Bestaand gedrag dat hier niet mag sneuvelen: het filter wordt als verborgen veld
    meegestuurd, zodat het na een mutatie blijft staan."""
    from app.domains.auth.api import csrf_token_for

    _login(client, db_session)
    foto = _asset(db_session, activity_id=13, title="blijft-staan")
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)

    resp = client.post(f"/admin/media/{foto.id}", headers={"X-CSRF-Token": csrf_token_for(waarde)},
                       data={"kind": "activity_photo", "title": "hernoemd",
                             "link_url": "", "is_active": "1",
                             "q": "", "filter_activity_id": "13"})

    assert resp.status_code == 200, resp.text[:200]
    assert "hernoemd" in resp.text, "de lijst toont het album niet meer na de mutatie"
    assert "Kies eerst een activiteit" not in resp.text, (
        "het filter is weggevallen na het opslaan, dus je staat weer op het beginpunt")
