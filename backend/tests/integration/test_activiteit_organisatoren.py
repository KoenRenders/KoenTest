"""Organisers of an activity, as many as it has (#1004, CR-10 §3.9; #1429).

Until #1429 an activity had at most three: the service refused the fourth and a
CHECK `sort_order IN (0, 1, 2)` was the net. The quiz has six (Koen, 1 October
2026); the three belonged to the Design Studio poster, which still names three
(`designstudio.api.POSTER_CONTACT_ROWS`). The database keeps `sort_order >= 0`
and the UNIQUE on (activity_id, sort_order).

The confirmation for unticking the LAST contact person is a server rule too: a
dialog in one screen cannot stop a script, and a poster without a contact person
silently falls back to Raak's own details.

Broken to see them red (measured):
- (#1429) the old `MAX_ORGANISERS` check back in `add_organiser` → the fourth
  is refused; the old CHECK back (master `5f436cb5`) → sort_order 5 is refused;
- the override ignored in `organisers_for` → the poster shows the member's own
  address;
- the `is_member` check out of `add_organiser` → a non-member becomes organiser;
- the `bevestigd` check out of the route → the last tick disappears silently.
"""

from datetime import date

import pytest
from sqlalchemy import text as sql_text

from app.domains.activities.api import (
    add_organiser,
    get_activity,
    organisers_for,
    remove_organiser,
    update_organiser,
)
from app.domains.activities.models import ActiviteitFout, Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _persoon(db, voornaam, achternaam, *, lid=True, email=None, gsm=None):
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=voornaam, last_name=achternaam
    )
    db.add(person)
    db.flush()
    if lid:
        gezin = Member()
        db.add(gezin)
        db.flush()
        db.add(MemberPerson(member_id=gezin.id, person_id=person.id, relation_type="HOOFDLID"))
    if email:
        db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
    if gsm:
        db.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=gsm))
    db.flush()
    return person


@pytest.fixture
def activiteit(db_session):
    a = Activity(name="Quiz met trekkers")
    db_session.add(a)
    db_session.flush()
    return a


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


# ── No limit on the activity (#1429) ──────────────────────────────────────────


def test_an_activity_takes_six_organisers_in_their_order(db_session, activiteit):
    """The quiz: six organisers, none refused, each after the one before."""
    ids = [_persoon(db_session, f"Lid{i}", "Drager").id for i in range(6)]
    for person_id in ids:
        add_organiser(db_session, activiteit.id, person_id)

    rows = organisers_for(db_session, activiteit.id)
    assert [r.person_id for r in rows] == ids
    assert [r.sort_order for r in rows] == [0, 1, 2, 3, 4, 5]


def _raw_insert(db, activity_id, person_id, sort_order):
    """A row that never passed the service, as a script or an import writes it."""
    db.execute(
        sql_text(
            "INSERT INTO activities.activity_organisers "
            "(tenant_id, activity_id, person_id, sort_order, is_contact) "
            "VALUES (2, :a, :p, :o, false)"
        ),
        {"a": activity_id, "p": person_id, "o": sort_order},
    )
    db.flush()


def test_the_database_accepts_sort_order_five(db_session, activiteit):
    """Red against master: the CHECK of migration 133 allowed only 0, 1 and 2."""
    _raw_insert(db_session, activiteit.id, _persoon(db_session, "Zes", "Rechtstreeks").id, 5)
    assert [r.sort_order for r in organisers_for(db_session, activiteit.id)] == [5]


def test_the_database_still_refuses_a_negative_place_and_a_shared_one(db_session, activiteit):
    """What stays: `sort_order >= 0` (migration 179) and the UNIQUE (133)."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        _raw_insert(db_session, activiteit.id, _persoon(db_session, "Min", "Een").id, -1)
    db_session.rollback()

    a = Activity(name="Gedeelde plaats")
    db_session.add(a)
    db_session.flush()
    _raw_insert(db_session, a.id, _persoon(db_session, "Eerste", "Plaats").id, 4)
    with pytest.raises(IntegrityError):
        _raw_insert(db_session, a.id, _persoon(db_session, "Tweede", "Plaats").id, 4)
    db_session.rollback()


def test_the_same_person_is_not_added_twice(db_session, activiteit):
    person = _persoon(db_session, "Twee", "Keer")
    add_organiser(db_session, activiteit.id, person.id)
    with pytest.raises(ActiviteitFout):
        add_organiser(db_session, activiteit.id, person.id)


def test_a_freed_place_is_used_again(db_session, activiteit):
    eerste = add_organiser(db_session, activiteit.id, _persoon(db_session, "A", "Een").id)
    add_organiser(db_session, activiteit.id, _persoon(db_session, "B", "Twee").id)
    remove_organiser(db_session, activiteit.id, eerste.id)

    add_organiser(db_session, activiteit.id, _persoon(db_session, "C", "Drie").id)
    add_organiser(db_session, activiteit.id, _persoon(db_session, "D", "Vier").id)
    assert [o.sort_order for o in organisers_for(db_session, activiteit.id)] == [0, 1, 2]


# ── Wat er op een affiche komt ───────────────────────────────────────────────


def test_an_override_wins_and_clearing_it_gives_the_member_value_back(db_session, activiteit):
    person = _persoon(db_session, "Els", "Contact", email="els@example.org", gsm="0470 00 00 00")
    rij = add_organiser(db_session, activiteit.id, person.id)

    [uit_fiche] = organisers_for(db_session, activiteit.id)
    assert (uit_fiche.email, uit_fiche.mobile) == ("els@example.org", "0470 00 00 00")

    update_organiser(
        db_session,
        activiteit.id,
        rij.id,
        {"email_override": "quiz@example.org", "mobile_override": "0470 11 11 11"},
    )
    [met_override] = organisers_for(db_session, activiteit.id)
    assert (met_override.email, met_override.mobile) == ("quiz@example.org", "0470 11 11 11")

    update_organiser(
        db_session, activiteit.id, rij.id, {"email_override": "", "mobile_override": "  "}
    )
    [terug] = organisers_for(db_session, activiteit.id)
    assert (terug.email, terug.mobile) == ("els@example.org", "0470 00 00 00")


def test_nobody_is_a_contact_person_until_ticked(db_session, activiteit):
    rij = add_organiser(db_session, activiteit.id, _persoon(db_session, "Jan", "Drager").id)
    assert organisers_for(db_session, activiteit.id)[0].is_contact is False

    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    assert organisers_for(db_session, activiteit.id)[0].is_contact is True


# ── Alleen leden, via de route ───────────────────────────────────────────────


def test_only_members_can_become_organiser(client, db_session, activiteit):
    """Through the route: the picker only SHOWS members, and a post skips it."""
    geen_lid = _persoon(db_session, "Nina", "Ondersteuner", lid=False)
    csrf = _login(client)

    resp = client.post(
        f"/admin/activiteiten/{activiteit.id}/organisatoren",
        data={"person_id": geen_lid.id},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 200
    assert "Alleen leden" in resp.text
    assert organisers_for(db_session, activiteit.id) == []


def test_the_picker_offers_members_and_skips_who_is_already_there(client, db_session, activiteit):
    lid = _persoon(db_session, "Mia", "Zoekbaar")
    _persoon(db_session, "Nina", "Zoekbaar", lid=False)
    _login(client)

    html = client.get(
        f"/admin/activiteiten/{activiteit.id}/organisatoren",
        params={"organiser_q": "zoekbaar"},
        headers={"HX-Request": "true"},
    ).text
    assert "Mia" in html and "Nina" not in html

    add_organiser(db_session, activiteit.id, lid.id)
    html = client.get(
        f"/admin/activiteiten/{activiteit.id}/organisatoren",
        params={"organiser_q": "zoekbaar"},
        headers={"HX-Request": "true"},
    ).text
    assert "Geen lid gevonden" in html


# ── De bevestiging bij het laatste vinkje, via de route ──────────────────────


def _post_vinkje(client, csrf, activiteit, organiser_id, **extra):
    data = {"email_override": "", "mobile_override": ""}
    data.update(extra)
    return client.post(
        f"/admin/activiteiten/{activiteit.id}/organisatoren/{organiser_id}",
        data=data,
        headers={"X-CSRF-Token": csrf},
    )


def test_the_last_tick_needs_a_confirmation(client, db_session, activiteit):
    rij = add_organiser(db_session, activiteit.id, _persoon(db_session, "Els", "Contact").id)
    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    csrf = _login(client)

    zonder = _post_vinkje(client, csrf, activiteit, rij.id)
    assert zonder.status_code == 200
    assert "Zonder contactpersoon" in zonder.text
    db_session.expire_all()
    assert organisers_for(db_session, activiteit.id)[0].is_contact is True, (
        "het vinkje verdween zonder bevestiging"
    )

    met = _post_vinkje(client, csrf, activiteit, rij.id, bevestigd="1")
    assert met.status_code == 200
    db_session.expire_all()
    assert organisers_for(db_session, activiteit.id)[0].is_contact is False


def test_unticking_one_of_two_needs_no_confirmation(client, db_session, activiteit):
    eerste = add_organiser(db_session, activiteit.id, _persoon(db_session, "A", "Een").id)
    tweede = add_organiser(db_session, activiteit.id, _persoon(db_session, "B", "Twee").id)
    for rij in (eerste, tweede):
        update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    csrf = _login(client)

    _post_vinkje(client, csrf, activiteit, eerste.id)

    db_session.expire_all()
    aangevinkt = [o.is_contact for o in organisers_for(db_session, activiteit.id)]
    assert aangevinkt == [False, True]


# ── De publieke kant verandert niet ──────────────────────────────────────────


def test_the_public_activity_page_shows_nothing_of_this(client, db_session, activiteit):
    from datetime import date, timedelta

    from app.domains.activities.api import ActivityDate

    db_session.add(
        ActivityDate(activity_id=activiteit.id, start_date=date.today() + timedelta(days=30))
    )
    # Namen die nergens anders in een pagina voorkomen: "Els" zit toevallig in
    # "snelder" in een scriptregel, en dan meet je de paginatekst, niet het lek.
    person = _persoon(
        db_session, "Zwaluwke", "Kontaktnaam", email="kontakt-1004@example.org", gsm="0470 12 34 56"
    )
    rij = add_organiser(db_session, activiteit.id, person.id)
    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})

    html = client.get(f"/activiteiten/{activiteit.id}").text
    assert get_activity(db_session, activiteit.id) is not None
    for geheim in (
        "Zwaluwke",
        "Kontaktnaam",
        "kontakt-1004@example.org",
        "0470 12 34 56",
        "organisator",
    ):
        assert geheim.lower() not in html.lower(), geheim


# ── Wat er van een contactpersoon op de affiche komt (#1032) ─────────────────
#
# Een lege override betekent "neem de ledenwaarde", niet "toon niets". Wie wel
# bereikbaar wil zijn op gsm maar zijn privé-adres niet op een publiek affiche
# wil, had geen uitweg. Twee vlaggen dus, standaard AAN: er verandert niets aan
# wat er vandaag gedrukt wordt, en weglaten is een bewuste handeling.
#
# Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
# twee regels in `organisers_for` omgedraaid — eerst de vlag, dan de override —
# → twee tests vallen om: `test_an_override_does_not_leak_when_the_tick_is_off`
# (de ingevulde override komt er alsnog uit, exact het lek dat dit issue
# voorkomt) en `test_an_override_wins_and_clearing_it_gives_the_member_value_back`
# van #1004, want met die volgorde wint de ledenwaarde van de override.


def _contactpersoon(db, activiteit, **velden):
    person = _persoon(db, "Els", "Bereikbaar", email="els@example.org", gsm="0470 00 00 00")
    rij = add_organiser(db, activiteit.id, person.id)
    update_organiser(db, activiteit.id, rij.id, {"is_contact": True, **velden})
    return organisers_for(db, activiteit.id)[0]


def test_by_default_both_details_go_on_the_poster(db_session, activiteit):
    zicht = _contactpersoon(db_session, activiteit)

    assert (zicht.show_email, zicht.show_mobile) == (True, True)
    assert (zicht.email, zicht.mobile) == ("els@example.org", "0470 00 00 00")


def test_a_tick_off_keeps_that_detail_off_the_poster(db_session, activiteit):
    zicht = _contactpersoon(db_session, activiteit, show_email=False)

    assert zicht.email == "", "het e-mailadres staat toch op de affiche"
    assert zicht.mobile == "0470 00 00 00", "het gsm-nummer hoort er wél op"
    assert zicht.show_email is False


def test_an_override_does_not_leak_when_the_tick_is_off(db_session, activiteit):
    """De volgorde is de regel: eerst de override, dan pas het vinkje.

    Andersom zou een ingevulde override er alsnog doorkomen — en dan is het
    vinkje een knop die niets doet zodra je een ander adres invult.
    """
    zicht = _contactpersoon(
        db_session, activiteit, email_override="quiz@example.org", show_email=False
    )

    assert zicht.email == "", "de override lekte langs het uitgezette vinkje"
    assert zicht.email_override == "quiz@example.org", (
        "de ingevulde waarde blijft bewaard — ze wordt alleen niet getoond"
    )


def test_the_screen_shows_the_two_ticks_and_saves_them(client, db_session, activiteit):
    person = _persoon(db_session, "Els", "Bereikbaar", email="els@example.org")
    rij = add_organiser(db_session, activiteit.id, person.id)
    csrf = _login(client)

    html = client.get(f"/admin/activiteiten/{activiteit.id}").text
    assert "e-mailadres op de affiche" in html and "gsm-nummer op de affiche" in html

    # Zoals het scherm post: aangevinkt komt mee, uitgevinkt komt níet mee.
    resp = client.post(
        f"/admin/activiteiten/{activiteit.id}/organisatoren/{rij.id}",
        data={
            "is_contact": "1",
            "email_override": "",
            "mobile_override": "",
            "show_mobile": "1",
            "bevestigd": "1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 200
    db_session.expire_all()
    [zicht] = organisers_for(db_session, activiteit.id)
    assert (zicht.show_email, zicht.show_mobile) == (False, True)
    assert zicht.email == "" and zicht.is_contact is True


def test_who_is_no_contact_person_shows_nothing_anyway(db_session, activiteit):
    """De vlaggen zijn alleen zinvol bij een contactpersoon — het scherm toont ze
    daar dan ook naar. Wie niet aangevinkt staat, komt sowieso niet op de affiche."""
    person = _persoon(db_session, "Jan", "Drager", email="jan@example.org")
    add_organiser(db_session, activiteit.id, person.id)

    [zicht] = organisers_for(db_session, activiteit.id)
    assert zicht.is_contact is False
    assert (zicht.show_email, zicht.show_mobile) == (True, True), (
        "de vlaggen staan standaard aan; het vinkje 'contactpersoon' beslist eerst"
    )


# ── Lees- en bewerkmodus (#1033) ────────────────────────────────────────────
#
# Twee bevindingen van Koen op ditzelfde blok. "Bewaren" leek niets te doen: het
# blok had geen lees/bewerk-modus, dus het bleef open en de POST hertekende
# dezelfde velden — het scherm zag er identiek uit. De kaart erboven klapt wél
# dicht, en twee blokken op één scherm die anders reageren op dezelfde handeling
# is een inconsistentie, geen smaakkwestie. En de rij sprong: alles in één
# `flex-wrap` breekt per schermbreedte én per naamlengte ergens anders.
#
# Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
# `x-show="edit"` en de `style="display: none"` van de bewerkvorm weggehaald →
# beide tests hieronder vallen om, want dan staat de vorm meteen open.


def _rij_html(client, activiteit) -> str:
    return client.get(f"/admin/activiteiten/{activiteit.id}").text


def test_de_leesregel_toont_geen_invoervelden(client, db_session, activiteit):
    person = _persoon(db_session, "Els", "Bereikbaar", email="els@example.org")
    rij = add_organiser(db_session, activiteit.id, person.id)
    update_organiser(db_session, activiteit.id, rij.id, {"is_contact": True})
    _login(client)

    html = _rij_html(client, activiteit)

    assert "Els Bereikbaar" in html and "contactpersoon" in html
    assert "els@example.org" in html, "de leesregel zegt wat er op de affiche komt"
    # De invoervelden bestaan wel in de DOM, maar in een blok dat dicht begint.
    vorm = html.split(
        'hx-post="/admin/activiteiten/%d/organisatoren/%d"' % (activiteit.id, rij.id)
    )[0]
    assert 'x-show="edit" style="display: none"' in html, (
        "de bewerkvorm begint niet dicht; dan verandert er niets zichtbaar na "
        "Bewaren — de melding van #1033"
    )
    assert "org-mail-" not in vorm, "een invoerveld staat buiten de bewerkvorm"


def test_na_bewaren_komt_de_rij_dicht_terug(client, db_session, activiteit):
    """Het antwoord op Bewaren is hetzelfde fragment, en dat rendert dicht.

    Daarom is dit te toetsen zonder browser: de server bepaalt de beginstand.
    """
    person = _persoon(db_session, "Els", "Bereikbaar", email="els@example.org")
    rij = add_organiser(db_session, activiteit.id, person.id)
    csrf = _login(client)

    antwoord = client.post(
        f"/admin/activiteiten/{activiteit.id}/organisatoren/{rij.id}",
        data={
            "is_contact": "1",
            "email_override": "",
            "mobile_override": "",
            "show_email": "1",
            "show_mobile": "1",
            "bevestigd": "1",
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert antwoord.status_code == 200
    assert 'x-show="edit" style="display: none"' in antwoord.text, (
        "de rij komt open terug; dan lijkt Bewaren niets te doen"
    )
    assert "contactpersoon" in antwoord.text, "en de leesregel toont de nieuwe stand"


# ── The order, changed with arrows (#1433) ────────────────────────────────────


def _six_contacts(db, activiteit):
    ids = []
    for i in range(6):
        row = add_organiser(db, activiteit.id, _persoon(db, f"Trekker{i}", "Kwis").id)
        update_organiser(db, activiteit.id, row.id, {"is_contact": True})
        ids.append(row.id)
    return ids


def test_the_fourth_moved_up_twice_is_second_and_makes_the_poster(db_session, activiteit):
    """Red against master: there was no `move_organiser`."""
    from app.domains.activities.api import move_organiser
    from app.domains.designstudio.api import on_the_poster

    ids = _six_contacts(db_session, activiteit)
    assert move_organiser(db_session, activiteit.id, ids[3], "omhoog")
    assert move_organiser(db_session, activiteit.id, ids[3], "omhoog")

    rows = organisers_for(db_session, activiteit.id)
    assert [r.id for r in rows] == [ids[0], ids[3], ids[1], ids[2], ids[4], ids[5]]
    assert [r.sort_order for r in rows] == [0, 1, 2, 3, 4, 5]
    assert [r.id for r in on_the_poster(rows)] == [ids[0], ids[3], ids[1]]


def test_the_first_up_and_the_last_down_change_nothing(db_session, activiteit):
    from app.domains.activities.api import move_organiser

    ids = _six_contacts(db_session, activiteit)
    assert not move_organiser(db_session, activiteit.id, ids[0], "omhoog")
    assert not move_organiser(db_session, activiteit.id, ids[-1], "omlaag")
    assert [r.id for r in organisers_for(db_session, activiteit.id)] == ids


def test_a_copy_keeps_the_changed_order(db_session, activiteit):
    from app.domains.activities.api import copy_activity, move_organiser

    ids = _six_contacts(db_session, activiteit)
    move_organiser(db_session, activiteit.id, ids[5], "omhoog")
    original = [r.person_id for r in organisers_for(db_session, activiteit.id)]
    copy = copy_activity(db_session, activiteit.id, first_date=date(2027, 5, 1))
    assert [r.person_id for r in organisers_for(db_session, copy.id)] == original


def test_the_card_marks_the_poster_three_and_carries_44_px_arrows(client, db_session, activiteit):
    """The first three contacts read "op de affiche", a fourth contact says why
    it is not; the arrows are the kit's `reorder` at touch size, the first one's
    "up" and the last one's "down" disabled."""
    import re

    _six_contacts(db_session, activiteit)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{activiteit.id}").text
    card = html[html.index("Organisatoren") :]
    assert card.count(">op de affiche<") == 3
    assert card.count("niet op de affiche: alleen de eerste drie") == 3
    arrows = re.findall(r'<button type="button" class="[^"]*min-w-11 min-h-11[^"]*"[^>]*>', card)
    assert len(arrows) == 12, len(arrows)
    # The attribute, not the `disabled:opacity-30` in the class.
    assert sum(bool(re.search(r'"\s+disabled[\s>]', b)) for b in arrows) == 2
