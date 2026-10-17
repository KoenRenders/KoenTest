"""The list Activiteiten on the kit's table (#1930).

What can break: the five columns and their order, the Status cell (never empty:
one state badge, Volzet in place of Gepubliceerd, Enkel leden after it), the "—"
of an activity without a component, the first date with its start time, the
sort, the year and audience filters, the counts on the segments, the row link
that carries the list's state, and the fragment the toolbar swaps.

Each test names what it was made red by, in the one place it matters: the
Status rule, the sort and the filters each have a violation that turns exactly
their own test red.
"""

import re
from datetime import date, time, timedelta
from decimal import Decimal

from app.domains.activities.api import (
    Activity,
    ActivityDate,
    ActivityStatus,
    ActivitySubRegistration,
    Registration,
)
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.kernel.clock import belgian_today
from tests.conftest import SEEDED_ADMIN_EMAIL


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _activity(
    db,
    name,
    *,
    days=20,
    start=None,
    location="Zaal",
    members_only=False,
    cancelled=False,
    draft=False,
    audience=None,
):
    activity = Activity(
        name=name,
        location=location,
        members_only=members_only,
        is_cancelled=cancelled,
        status=ActivityStatus.DRAFT if draft else ActivityStatus.PUBLISHED,
        target_audience=audience,
    )
    db.add(activity)
    db.flush()
    db.add(
        ActivityDate(
            activity_id=activity.id,
            start_date=belgian_today() + timedelta(days=days),
            start_time=start,
        )
    )
    db.flush()
    return activity


def _component(db, activity, *, max_participants=None):
    component = ActivitySubRegistration(
        activity_id=activity.id,
        name="Deelname",
        registration_type_code="INDIVIDUAL",
        price=Decimal("0"),
        max_participants=max_participants,
    )
    db.add(component)
    db.flush()
    return component


def _fill(db, activity, component):
    db.add(
        Registration(
            phone="0470000000",
            activity_id=activity.id,
            registration_type="INDIVIDUAL",
            contact_name="deelnemer",
            contact_email="deelnemer@example.com",
            component_id=component.id,
        )
    )
    db.flush()


def _row(html: str, name: str) -> str:
    """The whole `<tr>` of the row that carries this name."""
    at = html.index(f">{name}</a>")
    start = html.rindex("<tr data-row", 0, at)
    return html[start : html.index("</tr>", at)]


def _cell(row: str, cell: str) -> str:
    return re.search(rf'data-cell="{cell}"[^>]*>(.*?)</td>', row, flags=re.S).group(1)


def _names(html: str) -> list[str]:
    return re.findall(r"data-row-link[^>]*>([^<]+)</a>", html)


def test_the_five_columns_stand_in_their_order(client, db_session):
    _activity(db_session, "Kolomtest")
    db_session.commit()
    _login(client)
    html = client.get("/admin/activiteiten").text
    heads = re.findall(r"data-column-head[^>]*>(.*?)</th>", html, flags=re.S)
    assert [re.sub(r"<[^>]+>", "", h).strip() for h in heads] == [
        "Activiteit",
        "Datum",
        "Locatie",
        "Inschrijvingen",
        "Status",
    ]
    cells = re.findall(r'<td data-cell="(\w+)"', _row(html, "Kolomtest"))
    assert cells == ["name", "moment", "context", "extra", "status"]


def test_the_status_cell_is_never_empty_and_names_one_state(client, db_session):
    """Broken on purpose: the Volzet branch of `_badges` removed → the full
    activity says Gepubliceerd and the second assertion fails."""
    _activity(db_session, "Gewoon")
    vol = _activity(db_session, "Helemaal vol")
    _fill(db_session, vol, _component(db_session, vol, max_participants=1))
    half = _activity(db_session, "Half vol")
    _component(db_session, half, max_participants=5)
    _activity(db_session, "Alleen leden", members_only=True)
    _activity(db_session, "Nog niet klaar", draft=True)
    _activity(db_session, "Afgelast", cancelled=True)
    db_session.commit()
    _login(client)
    html = client.get("/admin/activiteiten").text

    def badges(name):
        return re.findall(
            r"data-badge[^>]*>\s*([^<]+?)\s*</span>", _cell(_row(html, name), "status")
        )

    assert badges("Gewoon") == ["Gepubliceerd"]
    assert badges("Helemaal vol") == ["Volzet"], "Volzet takes the place of Gepubliceerd"
    assert badges("Half vol") == ["Gepubliceerd"], "one open place left is not Volzet"
    assert badges("Alleen leden") == ["Gepubliceerd", "Enkel leden"]
    assert badges("Nog niet klaar") == ["Concept"]
    assert badges("Afgelast") == ["Geannuleerd"]


def test_an_activity_without_a_component_says_a_dash_and_one_with_says_its_count(
    client, db_session
):
    _activity(db_session, "Zonder onderdeel")
    met = _activity(db_session, "Met onderdeel")
    _fill(db_session, met, _component(db_session, met))
    db_session.commit()
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert _cell(_row(html, "Zonder onderdeel"), "extra").strip() == "—"
    assert _cell(_row(html, "Met onderdeel"), "extra").strip() == "1"


def test_the_date_comes_with_its_start_time_when_there_is_one(client, db_session):
    _activity(db_session, "Met uur", days=30, start=time(14, 30))
    _activity(db_session, "Zonder uur", days=31)
    db_session.commit()
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert re.fullmatch(r"\d\d-\d\d-\d{4} 14:30", _cell(_row(html, "Met uur"), "moment").strip())
    assert re.fullmatch(r"\d\d-\d\d-\d{4}", _cell(_row(html, "Zonder uur"), "moment").strip())


def test_the_sort_follows_the_first_date_then_the_last_first_then_the_name(client, db_session):
    """Broken on purpose: the `reverse=` of `-datum` taken out → the second
    assertion fails."""
    _activity(db_session, "Beta", days=10)
    _activity(db_session, "Alfa", days=30)
    _activity(db_session, "Gamma", days=20)
    db_session.commit()
    _login(client)

    assert _names(client.get("/admin/activiteiten").text) == ["Beta", "Gamma", "Alfa"]
    assert _names(client.get("/admin/activiteiten?sort=-datum").text) == ["Alfa", "Gamma", "Beta"]
    assert _names(client.get("/admin/activiteiten?sort=naam").text) == ["Alfa", "Beta", "Gamma"]
    assert _names(client.get("/admin/activiteiten?sort=-naam").text) == ["Gamma", "Beta", "Alfa"]
    assert _names(client.get("/admin/activiteiten?sort=onzin").text) == ["Beta", "Gamma", "Alfa"]


def test_the_year_and_the_audience_filter_the_list(client, db_session):
    """Broken on purpose: the audience comparison removed → both audiences come
    back and the last assertion fails."""
    volgend_jaar = belgian_today().year + 1
    _activity(db_session, "Dit jaar", days=2, audience="adults")
    later = _activity(db_session, "Volgend jaar", days=2, audience="children")
    db_session.add(ActivityDate(activity_id=later.id, start_date=date(volgend_jaar, 12, 30)))
    db_session.query(ActivityDate).filter(
        ActivityDate.activity_id == later.id, ActivityDate.start_date < date(volgend_jaar, 1, 1)
    ).delete()
    db_session.commit()
    _login(client)

    assert set(_names(client.get("/admin/activiteiten?scope=all").text)) >= {
        "Dit jaar",
        "Volgend jaar",
    }
    names = _names(client.get(f"/admin/activiteiten?scope=all&jaar={volgend_jaar}").text)
    assert "Volgend jaar" in names and "Dit jaar" not in names
    names = _names(client.get("/admin/activiteiten?scope=all&doelpubliek=adults").text)
    assert "Dit jaar" in names and "Volgend jaar" not in names
    names = _names(client.get("/admin/activiteiten?scope=all&doelpubliek=onzin").text)
    assert {"Dit jaar", "Volgend jaar"} <= set(names), "an unknown audience filters nothing"


def test_the_segments_carry_their_counts_and_alles_none(client, db_session):
    _activity(db_session, "Komt eraan", days=10)
    _activity(db_session, "Komt ook", days=12)
    _activity(db_session, "Was er", days=-10)
    db_session.commit()
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert re.search(r"Komende\s*<span[^>]*>\((\d+)\)</span>", html)
    komend = int(re.search(r"Komende\s*<span[^>]*>\((\d+)\)</span>", html).group(1))
    archief = int(re.search(r"Archief\s*<span[^>]*>\((\d+)\)</span>", html).group(1))
    assert komend >= 2 and archief >= 1
    assert not re.search(r"Alles\s*<span", html), "Alles carries no count"
    assert "Was er" not in _names(html), "the archive stays out of Komende"


def test_the_row_link_carries_the_lists_state(client, db_session):
    a = _activity(db_session, "Zomerfeest", audience="adults")
    db_session.commit()
    _login(client)
    html = client.get(
        "/admin/activiteiten?scope=all&q=zomer&jaar=" + str(belgian_today().year)
    ).text
    link = re.search(rf'href="(/admin/activiteiten/{a.id}\?terug=[^"]+)"', html).group(1)
    assert "scope%3Dall" in link and "q%3Dzomer" in link and "jaar%3D" in link


def test_the_toolbar_swaps_a_fragment_that_brings_the_counts_along(client, db_session):
    _activity(db_session, "Fragmentje")
    db_session.commit()
    _login(client)
    page = client.get("/admin/activiteiten").text
    fragment = client.get("/admin/activiteiten?q=fragmentje", headers={"HX-Request": "true"}).text
    assert "<html" in page and "<html" not in fragment
    assert "Fragmentje" in fragment
    assert 'id="aa-filter-count"' in fragment and 'hx-swap-oob="true"' in fragment


def test_an_empty_list_says_why(client, db_session):
    _login(client)
    zoek = client.get("/admin/activiteiten?q=bestaat-niet-ooit").text
    assert "Geen activiteiten gevonden." in zoek
    assert "<tr data-row" not in zoek


def test_the_page_is_cut_into_pages(client, db_session):
    for i in range(27):
        _activity(db_session, f"Pagina {i:02d}", days=10 + i)
    db_session.commit()
    _login(client)
    first = _names(client.get("/admin/activiteiten?per_page=25").text)
    second = _names(client.get("/admin/activiteiten?per_page=25&page=2").text)
    assert len(first) == 25 and len(second) >= 2
    assert not set(first) & set(second)
    far = client.get("/admin/activiteiten?per_page=25&page=99")
    assert far.status_code == 200 and _names(far.text) == second, "a page past the end is clamped"
