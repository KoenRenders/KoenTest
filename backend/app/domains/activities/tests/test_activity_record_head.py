"""The activity's record head on `ui.record_header` (CR-11 block 5, #1557).

What the screen hands the macro — badges, facts, the primary, the actions — and
the frame around it: the way back as the list was left, the same head on every
tab, the edit state.
"""

import re
from datetime import date, time

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _activity(db, **fields):
    activity, _component, _product = seed_activity_with_product(db, price="10.00", is_free=False)
    for name, value in fields.items():
        setattr(activity, name, value)
    db.commit()
    return activity


def _head(html: str) -> str:
    start = html.index("<header data-record-head")
    return html[start : html.index("</header>", start)]


def _tabs(html: str) -> str:
    return html[html.index("<nav data-related-tabs") :].split("</nav>", 1)[0]


def _menu_labels(head: str) -> list[str]:
    return re.findall(r'role="menuitem"[^>]*>([^<]+)<', head[head.index("data-actions-menu") :])


# ── What the head shows ──────────────────────────────────────────────────────


def test_the_head_carries_one_primary_and_the_actions_as_a_menu(client, db_session):
    activity = _activity(db_session)
    _login(client)
    head = _head(client.get(f"/admin/activiteiten/{activity.id}").text)

    controls = head[head.index("data-head-controls") : head.index("data-actions-menu")]
    assert f'href="/admin/activiteiten/{activity.id}?bewerken=1"' in controls
    assert controls.count("data-actions-trigger") == 1
    # A published activity: the record actions, then the tools.
    assert _menu_labels(head) == [
        "Kopiëren",
        "Terug naar concept",
        "Foto&#39;s uploaden",
        "Design Studio",
    ]
    assert head.count("data-menu-divider") == 1


def test_a_draft_offers_publishing_in_the_state_slot(client, db_session):
    from app.domains.activities.models import ActivityStatus

    activity = _activity(db_session, status=ActivityStatus.DRAFT)
    _login(client)
    head = _head(client.get(f"/admin/activiteiten/{activity.id}").text)
    assert "Terug naar concept" not in _menu_labels(head)
    assert _menu_labels(head)[:2] == ["Kopiëren", "Publiceren"]
    assert "Kopiëren" in _menu_labels(head)


def test_the_facts_are_full_words_and_the_public_page_is_a_reference(client, db_session):
    """date · time · place · reference — "14:00–17:30", not "14u"; "Publieke
    pagina", not "Publiek". The same markup serves every width, so a phone reads
    the same words."""
    activity = _activity(db_session, location="Parochiezaal")
    first = activity.dates[0]  # the seed gives the activity one date
    first.start_date, first.start_time, first.end_time = (
        date(2031, 6, 14),
        time(14, 0),
        time(17, 30),
    )
    db_session.commit()
    _login(client)
    head = _head(client.get(f"/admin/activiteiten/{activity.id}").text)
    facts = head[head.index("data-facts") :]
    texts = [t.strip() for t in re.findall(r">([^<>]+)<", facts) if t.strip() and t.strip() != "·"]
    assert texts == ["zaterdag 14 juni 2031", "14:00–17:30", "Parochiezaal", "Publieke pagina"]
    assert "data-reference" in facts
    assert not re.search(r'class="[^"]*\bhidden\b', facts), (
        "nothing on the facts line is hidden at a width"
    )


def test_the_status_comes_first_then_the_audience_in_grey(client, db_session):
    activity = _activity(db_session, members_only=True)
    _login(client)
    head = _head(client.get(f"/admin/activiteiten/{activity.id}").text)
    badges = head[head.index("data-badges") : head.index("data-head-controls")]
    assert badges.index("Gepubliceerd") < badges.index("Enkel leden")


# ── The frame: the same head on every tab ────────────────────────────────────


def test_the_head_is_the_same_on_every_tab(client, db_session):
    """Title, badges, facts and controls do not change with the tab; only which
    tab is the current one does."""
    activity = _activity(db_session, location="Parochiezaal")
    _login(client)
    base = f"/admin/activiteiten/{activity.id}"
    heads, currents = [], []
    for tab in ("", "/inschrijvingen", "/betalingen"):
        html = client.get(base + tab).text
        heads.append(_head(html))
        tabs = _tabs(html)
        assert [
            label for label in ("Gegevens", "Inschrijvingen", "Betalingen") if label in tabs
        ] == [
            "Gegevens",
            "Inschrijvingen",
            "Betalingen",
        ]
        currents.append(re.search(r'href="([^"]+)" aria-current="page"', tabs).group(1))
    assert heads[0] == heads[1] == heads[2]
    assert currents == [base, base + "/inschrijvingen", base + "/betalingen"]


def test_the_page_draws_no_second_back_link(client, db_session):
    activity = _activity(db_session)
    _login(client)
    for tab in ("", "/inschrijvingen", "/betalingen"):
        html = client.get(f"/admin/activiteiten/{activity.id}{tab}").text
        assert html.count("data-way-back") == 1
        assert "Alle activiteiten" not in html


# ── The way back: the list as it was left ────────────────────────────────────


def test_a_card_hands_the_list_as_it_stands_to_the_record(client, db_session):
    activity = _activity(db_session, name="Zomerfeest op het plein")
    _login(client)
    html = client.get("/admin/activiteiten?scope=all&q=zomer").text
    link = re.search(rf'href="(/admin/activiteiten/{activity.id}\?terug=[^"]+)"', html).group(1)
    assert link.endswith("?terug=/admin/activiteiten%3Fscope%3Dall%26q%3Dzomer")

    head = _head(client.get(link).text)
    back = head[: head.index("</a>")]
    assert "data-way-back" in back
    assert 'href="/admin/activiteiten?scope=all&amp;q=zomer"' in back
    assert ">Activiteiten<" in back


def test_the_way_back_survives_a_tab_change_and_the_edit_state(client, db_session):
    activity = _activity(db_session)
    _login(client)
    keep = "terug=%2Fadmin%2Factiviteiten%3Fq%3Dzomer"
    html = client.get(f"/admin/activiteiten/{activity.id}?{keep}").text
    base = f"/admin/activiteiten/{activity.id}"
    assert f'href="{base}/inschrijvingen?{keep}"' in _tabs(html)
    assert f'href="{base}?bewerken=1&amp;{keep}"' in _head(html)

    on_tab = _head(client.get(f"{base}/inschrijvingen?{keep}").text)
    assert 'href="/admin/activiteiten?q=zomer"' in on_tab


def test_without_an_origin_the_way_back_is_the_list(client, db_session):
    activity = _activity(db_session)
    _login(client)
    head = _head(client.get(f"/admin/activiteiten/{activity.id}").text)
    assert re.search(r'data-way-back href="/admin/activiteiten"', head)
    assert ">Activiteiten<" in head


def test_an_origin_outside_the_site_falls_back_to_the_list(client, db_session):
    activity = _activity(db_session)
    _login(client)
    html = client.get(
        f"/admin/activiteiten/{activity.id}?terug=https%3A%2F%2Fevil.example%2Fx"
    ).text
    assert "evil.example" not in html
    assert re.search(r'data-way-back href="/admin/activiteiten"', _head(html))


# ── The edit state ───────────────────────────────────────────────────────────


def test_the_edit_state_shows_the_badge_and_no_primary(client, db_session):
    activity = _activity(db_session)
    _login(client)
    head = _head(client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text)
    badges = head[head.index("data-badges") : head.index("data-head-controls")]
    assert badges.index("Gepubliceerd") < badges.index(">Bewerken<")
    controls = head[head.index("data-head-controls") :]
    assert "?bewerken=1" not in controls
    assert "data-actions-trigger" in controls
