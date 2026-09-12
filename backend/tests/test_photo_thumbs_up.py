"""#883 — one thumbs-up per visitor per photo.

Koen wants visitors to be able to give a thumbs-up **per photo** — not one per album, and at
most one per photo.

**"One per visitor" does not exist without identity.** Without logging in you can only
recognise a visitor by something in their browser, so: a cookie, which anybody clears in ten
seconds. That is accepted and deliberate — this is a nicety on a village album, not an
election. Requiring a login would break the feature: whoever gets a link in WhatsApp is not
going to create an account first.

Four properties are load-bearing and each has its own test here:

1. **the uniqueness holds in the DATABASE**, not only in the service — two quick clicks
   cross each other, and then both check "does a row exist?" before either insert lands;
2. **clicking again removes it**, which is what makes the cookie approach fair: whoever
   clears their cookies loses their thumbs instead of being able to double them;
3. **never a name or a token in the output** — only a count. That is what separates this
   from a small social network;
4. **a thumb on tenant A's photo does not show up at tenant B.**

Broken on purpose to check that these tests can go red:

- the `UniqueConstraint` dropped from the model and two rows written for the same pair →
  the database no longer refuses and the uniqueness test falls over. Done the other way
  round as well: with the constraint in place, writing the second row directly raises
  `IntegrityError`, which is what that test asserts.
- the delete branch removed from `toggle_thumb` → the toggle test falls over with the
  counter stuck at 1.
- the visitor token rendered into the fragment → the privacy test falls over.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.media.models import MediaAsset, MediaThumbsUp

pytestmark = pytest.mark.ui_serverrendered

COOKIE = "raak_duim"


def _photo(db, *, activity_id=901, title="foto"):
    # Mét een échte activiteit: sinds #884 geeft een album van een onbestaande activiteit
    # een 404 (dat pad accepteert nu ook een slug, en dan is "niet gevonden" het enige
    # juiste antwoord). Een test die een los asset maakte, leunde op de oude 200.
    from datetime import date

    from app.domains.activities.api import Activity, ActivityDate

    if db.query(Activity).filter(Activity.id == activity_id).first() is None:
        activiteit = Activity(id=activity_id, name=f"Album {activity_id}")
        db.add(activiteit)
        db.flush()
        db.add(ActivityDate(activity_id=activity_id, start_date=date(2026, 7, 1)))
        db.flush()
    asset = MediaAsset(kind="activity_photo", activity_id=activity_id, title=title,
                       sort_order=0, is_active=True, content_type="image/jpeg",
                       byte_size=10, width=100, height=100, data=b"x", thumbnail=b"y")
    db.add(asset)
    db.flush()
    return asset


def _count(db, asset_id):
    return db.query(MediaThumbsUp).filter(
        MediaThumbsUp.asset_id == asset_id).count()


def test_clicking_twice_from_one_browser_leaves_one_thumb(client, db_session):
    """Het gevraagde gedrag, via de echte route — inclusief de cookie die de eerste klik
    zet."""
    foto = _photo(db_session)

    eerste = client.post(f"/fotos/{foto.id}/duim")
    assert eerste.status_code == 200, eerste.text[:200]
    assert COOKIE in eerste.cookies or client.cookies.get(COOKIE), (
        "er is geen bezoekerstoken gezet, dus 'één per bezoeker' bestaat niet")
    assert ">1<" in eerste.text.replace(" ", ""), eerste.text

    # Zelfde browser: de client draagt de cookie mee. Dit is dus de tweede klik van
    # dezelfde bezoeker en hoort het duimpje weg te halen, niet te verdubbelen.
    tweede = client.post(f"/fotos/{foto.id}/duim")

    db_session.expire_all()
    assert _count(db_session, foto.id) == 0, (
        "nog eens klikken haalde het duimpje niet weg")
    assert ">0<" in tweede.text.replace(" ", "")


def test_the_cookie_is_only_set_on_a_click_and_not_on_a_page_view(client, db_session):
    """De kern van de cookie-afweging: opslag is het gevolg van een handeling die de
    bezoeker zelf vraagt.

    Zou het token bij elk paginabezoek gezet worden, dan sla je iets op bij iemand die
    niets gevraagd heeft — een heel andere vraag, juridisch én qua betamelijkheid.
    """
    foto = _photo(db_session, activity_id=902)

    resp = client.get(f"/activiteiten/902/fotos")

    assert resp.status_code == 200
    assert COOKIE not in resp.cookies, (
        "het bezoekerstoken wordt gezet bij het BEKIJKEN van een album")
    assert client.cookies.get(COOKIE) is None
    assert f"/fotos/{foto.id}/duim" in resp.text, "er is geen duimpje om op te klikken"


def test_the_uniqueness_holds_in_the_database(db_session):
    """Niet alleen in de service: twee snelle kliks kruisen elkaar, en dan antwoorden
    beide "bestaat er al een rij?" met nee vóór er één geland is.

    Dit is de proef die het issue vraagt: twee rijen voor hetzelfde paar wegschrijven, en
    de databank weigert.
    """
    foto = _photo(db_session, activity_id=903)
    db_session.add(MediaThumbsUp(asset_id=foto.id, visitor_token="token-a"))
    db_session.flush()

    db_session.add(MediaThumbsUp(asset_id=foto.id, visitor_token="token-a"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_two_visitors_count_as_two(db_session):
    """De tegenproef bij de uniciteit: zonder haar zou "altijd één" ook groen staan."""
    from app.domains.media.api import toggle_thumb

    foto = _photo(db_session, activity_id=904)

    aantal_a, aan_a = toggle_thumb(db_session, foto.id, "bezoeker-1")
    aantal_b, aan_b = toggle_thumb(db_session, foto.id, "bezoeker-2")

    assert (aantal_a, aan_a) == (1, True)
    assert (aantal_b, aan_b) == (2, True)


def test_never_a_name_or_a_token_in_the_output(client, db_session):
    """Wat dit van een sociaal netwerkje onderscheidt: alleen een aantal.

    Het token staat in een HttpOnly-cookie en mag nergens in de HTML belanden — niet in
    het fragment, niet in de albumpagina.
    """
    foto = _photo(db_session, activity_id=905)

    fragment = client.post(f"/fotos/{foto.id}/duim")
    token = client.cookies.get(COOKIE)
    pagina = client.get("/activiteiten/905/fotos")

    assert token, "opzet klopt niet: er is geen token"
    assert token not in fragment.text, "het bezoekerstoken staat in het fragment"
    assert token not in pagina.text, "het bezoekerstoken staat in de albumpagina"
    assert "visitor_token" not in pagina.text


def test_a_thumb_of_another_tenant_does_not_show_up(client, db_session):
    """De tenantgrens. De tabel draagt `tenant_id` via de kernel-mixin, dus de globale
    filter hoort dit af te dekken — maar dat is precies het soort eigenschap dat je niet
    aan het model afleest."""
    from app.kernel.tenancy import current_tenant_id

    foto = _photo(db_session, activity_id=906)
    db_session.add(MediaThumbsUp(asset_id=foto.id, visitor_token="van-tenant-a"))
    db_session.flush()

    token = current_tenant_id.set(7)  # een andere afdeling
    try:
        from app.domains.media.api import thumb_counts

        assert thumb_counts(db_session, [foto.id]) == {}, (
            "de duimpjes van een andere afdeling worden meegeteld")
    finally:
        current_tenant_id.reset(token)
