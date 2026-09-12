"""#882 — media ordering is arrows again, not a number field.

Koen: *"I notice numbers can now be entered for the media to set the order. In my
recollection that numbering used to be invisible and this worked with arrows."*

His memory is right. v1.14 had `moveAsset(idx, dir)`: arrows that swap two items and then
renumber `sort_order` **to the position** — self-healing, and the number invisible. The
React exit turned that into a bare number field, and a number field guards nothing: two
photos can carry the same number (then the id decides, which nobody can see), gaps can
appear, and putting one photo first means revising all the others by hand.

This screen was also the only one left: the UI kit has `reorder(...)` and four other
screens use it.

**The group boundary is the point most likely to be got wrong.** Media hangs off an
activity, off a component, or is a sponsor. A shift may only renumber within the item's own
group — otherwise editing one album renumbers the sponsor logos, and the screen shows the
photos of all activities mixed together when unfiltered.

Broken on purpose to check that these tests can go red:

- `move_sibling` replaced by a plain swap of two `sort_order` values → the closed-sequence
  test falls over as soon as the values start out equal, which is the state fresh uploads
  are in.
- the group filter in `move_media` reduced to `kind` only → the boundary test falls over
  with the other activity's album renumbered.
- `sort_order` put back in the update payload → the last test falls over: saving a title
  resets the order to 0, which is the regression this change would otherwise have
  introduced.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.media.models import MediaAsset
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


def _asset(db, *, kind="activity_photo", activity_id=None, title="foto",
           sort_order=0):
    asset = MediaAsset(kind=kind, activity_id=activity_id, title=title,
                       sort_order=sort_order, is_active=True,
                       content_type="image/jpeg", byte_size=10, width=10, height=10,
                       data=b"x", thumbnail=b"x")
    db.add(asset)
    db.flush()
    return asset


def _order(db, **filters):
    query = db.query(MediaAsset)
    for veld, waarde in filters.items():
        query = query.filter(getattr(MediaAsset, veld) == waarde)
    return [(a.title, a.sort_order) for a in
            query.order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc()).all()]


def _move(client, headers, asset, richting="omhoog"):
    return client.post(f"/admin/media/{asset.id}/verplaats", headers=headers,
                       data={"richting": richting, "kind": asset.kind,
                             "q": "", "filter_activity_id": ""})


def test_moving_a_photo_up_swaps_it_with_the_previous_one(client, db_session):
    headers = _login(client, db_session)
    eerste = _asset(db_session, activity_id=1, title="een", sort_order=0)
    tweede = _asset(db_session, activity_id=1, title="twee", sort_order=1)

    resp = _move(client, headers, tweede, "omhoog")

    assert resp.status_code == 200, resp.text[:200]
    db_session.expire_all()
    assert [t for t, _ in _order(db_session, activity_id=1)] == ["twee", "een"]
    assert eerste.sort_order == 1 and tweede.sort_order == 0


def test_after_a_move_the_numbers_are_a_closed_sequence(client, db_session):
    """De test die dit issue draagt: dat is precies wat het nummerveld niet garandeerde.

    De opzet is de toestand van verse uploads — allemaal dezelfde `sort_order` — plus een
    gat en een duplicaat. `move_sibling` normaliseert eerst naar 0..n en wisselt dan, dus
    één verschuiving herstelt de reeks.
    """
    headers = _login(client, db_session)
    _asset(db_session, activity_id=2, title="a", sort_order=0)
    _asset(db_session, activity_id=2, title="b", sort_order=0)
    _asset(db_session, activity_id=2, title="c", sort_order=7)
    laatste = _asset(db_session, activity_id=2, title="d", sort_order=7)

    _move(client, headers, laatste, "omhoog")

    db_session.expire_all()
    nummers = sorted(nr for _t, nr in _order(db_session, activity_id=2))
    assert nummers == [0, 1, 2, 3], (
        f"de reeks is niet sluitend: {nummers} — gaten of duplicaten zijn gebleven")


def test_the_top_item_cannot_go_up_and_the_bottom_cannot_go_down(client, db_session):
    headers = _login(client, db_session)
    boven = _asset(db_session, activity_id=3, title="boven", sort_order=0)
    onder = _asset(db_session, activity_id=3, title="onder", sort_order=1)

    _move(client, headers, boven, "omhoog")
    _move(client, headers, onder, "omlaag")

    db_session.expire_all()
    assert [t for t, _ in _order(db_session, activity_id=3)] == ["boven", "onder"], (
        "buiten bereik verschoof er toch iets")


def test_the_group_boundary_holds(client, db_session):
    """De grens die het issue benoemt: één album herschikken mag een ander album en de
    sponsors niet aanraken."""
    headers = _login(client, db_session)
    _asset(db_session, activity_id=4, title="a1", sort_order=0)
    tweede = _asset(db_session, activity_id=4, title="a2", sort_order=1)
    _asset(db_session, activity_id=5, title="b1", sort_order=3)
    _asset(db_session, activity_id=5, title="b2", sort_order=9)
    _asset(db_session, kind="sponsor", title="s1", sort_order=4)
    _asset(db_session, kind="sponsor", title="s2", sort_order=8)

    _move(client, headers, tweede, "omhoog")

    db_session.expire_all()
    assert _order(db_session, activity_id=5) == [("b1", 3), ("b2", 9)], (
        "het andere album is hernummerd")
    assert _order(db_session, kind="sponsor") == [("s1", 4), ("s2", 8)], (
        "de sponsorlogo's zijn hernummerd door het bewerken van een album")


def test_saving_a_title_does_not_reset_the_order(client, db_session):
    """Het veld is weg uit het formulier, dus de route mag `sort_order` niet meer
    aannemen — anders zet elke keer opslaan de volgorde op de default 0, en dat is een
    stillere regressie dan de oorspronkelijke."""
    headers = _login(client, db_session)
    _asset(db_session, activity_id=6, title="eerste", sort_order=0)
    tweede = _asset(db_session, activity_id=6, title="tweede", sort_order=1)

    resp = client.post(f"/admin/media/{tweede.id}", headers=headers,
                       data={"kind": "activity_photo", "title": "tweede bis",
                             "link_url": "", "is_active": "1",
                             "q": "", "filter_activity_id": ""})

    assert resp.status_code == 200, resp.text[:200]
    db_session.expire_all()
    assert _order(db_session, activity_id=6) == [("eerste", 0), ("tweede bis", 1)], (
        "opslaan heeft de volgorde veranderd")


def test_the_number_field_is_gone_from_the_screen(client, db_session):
    """En de pijltjes staan er wél — anders is er niets om op te klikken."""
    headers = _login(client, db_session)
    _asset(db_session, activity_id=7, title="foto", sort_order=0)

    # Mét het activiteitenfilter: sinds #891 toont dit scherm bij activiteitenfoto's
    # niets tot er een activiteit gekozen is, precies omdat een ongefilterde lijst geen
    # groep is om in te sorteren.
    html = client.get("/admin/media?kind=activity_photo&activity_id=7").text

    assert 'name="sort_order"' not in html, "het nummerveld staat er nog"
    assert "/verplaats" in html, "er zijn geen pijltjes"
    assert 'aria-label="Naar boven"' in html, (
        "de pijltjes dragen geen aria-label — de lint-poort uit "
        "test_ui_conventions_gate.py eist dat bij symboolknoppen")
