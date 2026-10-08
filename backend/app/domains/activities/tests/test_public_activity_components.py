"""The public activity and photo pages on components (#1663; CR-11 pilot C, C1;
end state §2.7).

What the activity card, the activity page and the photo pages each wrote by hand
comes from `_public_macros.html` and one shared block of actions
(`_component_actions.html`) — with the same rendered picture: the DOM baseline
of #1605 holds that (`tests_e2e/test_measure_baselines.py`), this file holds
what a baseline of one seed cannot: the invariants of §2.7 render, each with
the right number of parts.

Red against master `a8c0e5a2`: no `_public_macros.html`; the tile was a `<div>`
without a `datetime`; the card's actions carried `-ml-[60px]`.
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.ui import templates
from tests.conftest import register_at_the_door

pytestmark = pytest.mark.ui_serverrendered

LONG = "Gezinsuitstap naar een voorbeeldpark met bus, picknick en een avondwandeling terug"


def _macro(call: str, **context) -> str:
    source = '{% import "_public_macros.html" as pub %}{{ ' + call + " }}"
    return templates.env.from_string(source).render(**context)


# ── The macros themselves ────────────────────────────────────────────────────


def test_the_date_tile_is_one_time_element_in_two_sizes():
    day = date(2026, 9, 5)
    card, page = _macro("pub.date_tile(d)", d=day), _macro('pub.date_tile(d, "page")', d=day)
    for html in (card, page):
        assert html.count("<time ") == 1 and html.count("</time>") == 1
        assert 'datetime="2026-09-05"' in html and "data-date-tile" in html
        assert ">05<" in html and ">sep<" in html.lower()
    # The card: 48 px, 56 px from 640 px. The page: 56 px, 64 px from 768 px.
    assert "w-12 h-12 sm:w-14 sm:h-14" in card and "text-xl" in card
    assert "w-14 h-14 md:w-16 md:h-16" in page and "text-2xl" in page


def test_the_year_heading_gets_air_only_further_down_the_list():
    first, later = _macro("pub.year_heading(2027)"), _macro("pub.year_heading(2027, first=False)")
    assert first.count("<h3 ") == 1 and ">2027</h3>" in first and "data-year-heading" in first
    assert "pt-2" not in first and "pt-2" in later


@pytest.mark.parametrize("count", [1, 3, 12])
def test_every_date_of_a_series_is_a_line_under_one_icon(count):
    """No folding and no fixed height: twelve dates are twelve lines."""
    dates = [
        SimpleNamespace(
            start_date=date(2026, 10, 1) + timedelta(days=7 * i),
            end_date=None,
            start_time=time(14, 0) if i % 2 else None,
            end_time=None,
        )
        for i in range(count)
    ]
    html = _macro('pub.activity_facts(dates, "Voorbeeldzaal", deadline, near)', dates=dates,
                  deadline=date(2026, 9, 28), near=True)  # fmt: skip
    block = html[: html.index("</div>\n</div>")]
    assert block.count("<span>") == count
    assert html.count("data-activity-dates") == 1 and html.count("<svg") == 3
    assert "Voorbeeldzaal" in html and "Inschrijven t/m" in html and "text-orange-600" in html
    assert "max-h-" not in html and "line-clamp" not in html and "<details" not in html


def test_the_facts_leave_out_what_an_activity_does_not_have():
    html = _macro("pub.activity_facts([])")
    assert html.count("<svg") == 1 and "Inschrijven t/m" not in html and "<p " not in html
    assert 'class="mt-1 ' in _macro('pub.activity_facts([], context="page")')
    assert 'class="mt-1 ' not in html


def test_the_public_way_back_is_one_form_the_chevron_and_the_origins_name():
    """#1664 (Z4): "‹ Activiteiten", "‹ Archief", "‹ Foto's" — the kit's chevron,
    14 px in the link colour. Red against C1: "← Alle activiteiten" and "← Terug
    naar alle albums", an arrow in the text and two forms."""
    seen = {}
    for origin, href, name in (
        ("activities", "/activiteiten", "Activiteiten"),
        ("archive", "/archief", "Archief"),
        ("photos", "/fotos", "Foto's"),
    ):
        html = _macro(f'pub.public_back_link("{origin}", "{href}")').replace("&#39;", "'")
        assert html.count("data-way-back") == 1 and html.count(f'href="{href}"') == 1
        assert f"<span>{name}</span>" in html, html
        # The chevron is the kit's icon, not a character in the text.
        assert html.count("<svg") == 1 and "m15 18-6-6 6-6" in html
        assert (
            "←" not in html and "&larr;" not in html and "Terug" not in html and "Alle " not in html
        )
        assert "text-sm" in html and "text-blue-500" in html
        # A larger hit area on a phone that takes no room.
        assert (
            "before:absolute" in html
            and "before:-inset-y-2.5" in html
            and "md:before:hidden" in html
        )
        seen[origin] = html.replace(href, "").replace(name, "")
    assert len(set(seen.values())) == 1, "the three origins do not share one form"
    assert 'class="text-sm leading-6 md:leading-5 pt-4"' in _macro(
        'pub.public_back_link("archive", "/x", cls="pt-4")'
    )


def test_the_album_card_is_the_kits_card_as_a_link():
    html = _macro(
        'pub.photo_card("Zomerfeest", "/activiteiten/7/fotos", "/thumb/1", d)', d=date(2025, 7, 1)
    )
    assert html.count("<a ") == 1 and 'href="/activiteiten/7/fotos"' in html
    assert "data-photo-card" in html and 'alt="Zomerfeest"' in html and "aspect-video" in html
    # The kit's linked card: no padding of its own, the shadow on hover.
    plain = templates.env.from_string(
        '{% import "_macros.html" as ui %}{% call ui.card() %}x{% endcall %}'
    ).render()
    assert plain.startswith("<div ") and "p-6" in plain and "<a " not in plain
    assert "p-6" not in html.split(">")[0] and "hover:shadow-md" in html
    # No raw grey left in it: the tokens of the same value.
    assert "gray-100" not in html and "gray-500" not in html


def test_the_tokens_that_replaced_the_raw_greys_have_the_same_value():
    """The photo templates wrote `gray-100`, `gray-500` and `gray-600`; they take
    `surface-2` and `ink-soft` now. In the public shell those are the same
    colours — read from the shell's own token block, so a token that moves away
    from its grey makes this red (and is then a visible change, for C2)."""
    from pathlib import Path

    css = (Path(__file__).resolve().parents[5] / "scripts" / "build-css.sh").read_text()
    blocks = [b.split("}")[0] for b in css.split('body[data-shell="site"]{')[1:]]
    blocks = [b for b in blocks if "--c-gray-100:" in b]
    assert blocks, "no token block of the public shell carries the greys — the test looks nowhere"
    for whole in blocks:
        block = whole + ";"

        def token(name: str, block: str = block) -> str:
            found = re.findall(rf"--c-{name}:([0-9 ]+);", block)
            assert len(found) == 1, (name, found)
            return found[0].strip()

        assert token("gray-100") == token("surface-2")
        assert token("gray-500") == token("gray-600") == token("ink-soft")
        assert token("gray-200") == token("line")


# ── The pages, with the invariants of §2.7 ───────────────────────────────────


def _activity(db, name, days, *, components=("Onderdeel",), **fields):
    from app.domains.activities.api import Activity, ActivityDate, ActivitySubRegistration

    activity = Activity(name=name, **fields)
    db.add(activity)
    db.flush()
    for offset in days:
        db.add(
            ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=offset))
        )
    made = []
    for order, (component, extra) in enumerate(
        (c if isinstance(c, tuple) else (c, {})) for c in components
    ):
        made.append(
            ActivitySubRegistration(
                activity_id=activity.id,
                name=component,
                registration_type_code="INDIVIDUAL",
                price=Decimal("0"),
                is_free=True,
                sort_order=order,
                **extra,
            )
        )
        db.add(made[-1])
    db.flush()
    return activity, made


def _cards(html: str) -> dict[str, str]:
    """name → the card's HTML, cut at the card's opening tag."""
    parts = re.split(r'(?=<div id="[^"]+" class="bg-white rounded-2xl shadow-sm)', html)
    cards = {}
    for part in parts[1:]:
        title = re.search(r"data-card-title[^>]*>\s*<a [^>]*>([^<]+)</a>", part)
        cards[title.group(1).strip()] = part
    return cards


@pytest.fixture
def world(db_session):
    yesterday = date.today() - timedelta(days=1)
    one, _ = _activity(db_session, "Meet een datum", [20])
    three, _ = _activity(db_session, "Meet drie datums", [21, 22, 28], location="Voorbeeldzaal")
    twelve, _ = _activity(
        db_session,
        LONG,
        [30 + 7 * i for i in range(12)],
        components=("Volwassenen", "Kinderen", "Helpers"),
        members_only=True,
    )
    closed, _ = _activity(
        db_session,
        "Meet afgesloten",
        [23],
        components=(("Onderdeel", {"registration_closes_on": yesterday}),),
    )
    cancelled, _ = _activity(db_session, "Meet geannuleerd", [24], is_cancelled=True)
    db_session.commit()
    return SimpleNamespace(one=one, three=three, twelve=twelve, closed=closed, cancelled=cancelled)


def test_the_list_renders_every_invariant_with_its_parts(client, world):
    html = client.get("/activiteiten").text
    cards = _cards(html)
    for name in ("Meet een datum", "Meet drie datums", LONG, "Meet afgesloten", "Meet geannuleerd"):
        assert name in cards, sorted(cards)
    # One tile, one block of dates per card — a `<time>` from the macro.
    for name, card in cards.items():
        assert card.count("<time data-date-tile") == 1, name
        assert card.count("data-activity-dates") == 1, name
        assert 'class="grid grid-cols-[auto_minmax(0,1fr)]' in card, name

    def dates(card: str) -> int:
        return card[card.index("data-activity-dates") :].split("</div>\n</div>")[0].count("<span>")

    assert dates(cards["Meet een datum"]) == 1
    assert dates(cards["Meet drie datums"]) == 3
    assert dates(cards[LONG]) == 12, "a date of the series is not shown"
    # Several components: each by its name, in one block of actions.
    long_card = cards[LONG]
    assert long_card.count("data-component-actions") == 1
    assert all(n in long_card for n in ("Volwassenen", "Kinderen", "Helpers"))
    assert long_card.count("Inschrijven</a>") == 3 and "enkel leden" in long_card
    # One component: its name is left out.
    assert "Onderdeel" not in cards["Meet een datum"]
    assert "Afgesloten" in cards["Meet afgesloten"]
    # A cancelled activity shows no actions at all.
    assert "data-component-actions" not in cards["Meet geannuleerd"]
    # The phone's full width comes from the grid, not from a negative margin.
    assert "-ml-[" not in html
    assert html.count("col-span-full sm:col-span-1 sm:col-start-2") == html.count(
        "data-component-actions"
    )


def test_a_full_component_says_so_on_the_card(client, db_session):
    from tests.conftest import seed_activity_with_product

    _, comp, product = seed_activity_with_product(db_session, max_participants=2)
    done = register_at_the_door(
        client,
        comp.activity_id,
        json={
            "contact_name": "An Voorbeeld",
            "phone": "0470000000",
            "contact_email": "vol@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": 2}],
        },
    )
    assert done.status_code in (200, 201), done.text
    card = _cards(client.get("/activiteiten").text)["Testactiviteit"]
    assert "Volzet" in card and card.count("<time data-date-tile") == 1


def test_the_page_of_an_activity_without_a_poster(client, world):
    for activity, lines in ((world.one, 1), (world.three, 3), (world.twelve, 12)):
        response = client.get(f"/activiteiten/{activity.id}", follow_redirects=True)
        assert response.status_code == 200, activity.name
        html = response.text
        main = html[html.index('<main id="main"') : html.index("</main>")]
        assert main.count("<time data-date-tile") == 1 and "md:w-16 md:h-16" in main
        assert main.count("<h1 data-page-title") == 1
        # The title role of the public shell gives the size: no local size class.
        title = re.search(r"<h1 data-page-title class=\"([^\"]*)\"", main).group(1)
        assert not re.search(r"\btext-(?:2xl|3xl)\b", title), title
        block = main[main.index("data-activity-dates") :].split("</div>\n</div>")[0]
        assert block.count("<span>") == lines
        assert main.count("data-way-back") == 1 and "<span>Activiteiten</span>" in main
        assert "data-activity-poster" not in main and "md:mx-auto" not in main
        assert main.count("data-component-actions") == 1 and 'class="mt-6 space-y-3"' in main


def test_an_empty_list_says_so_and_draws_no_part(client, db_session):
    """The archive of a database in which no activity is over."""
    from app.domains.activities.api import ActivityDate

    over = db_session.query(ActivityDate).filter(ActivityDate.start_date < date.today()).count()
    assert over == 0, "this test needs a database without an activity that is over"
    html = client.get("/archief").text
    main = html[html.index('<main id="main"') : html.index("</main>")]
    assert "Geen activiteiten gevonden." in main
    assert "data-date-tile" not in main and "data-year-heading" not in main
    assert "data-component-actions" not in main


def test_an_activity_that_is_over_leads_back_to_the_archive(client, db_session):
    """#1664 (Z4): from an archived activity the way back goes to the archive and
    says so."""
    past, _ = _activity(db_session, "Meet voorbij", [-40])
    db_session.commit()
    html = client.get(f"/activiteiten/{past.id}", follow_redirects=True).text
    main = html[html.index('<main id="main"') : html.index("</main>")]
    way = main[main.index("data-way-back") : main.index("</nav>")]
    assert "<span>Archief</span>" in way and "/activiteiten/archief" in way


def test_no_public_page_names_an_association_in_its_browser_title():
    """#1664 (Z7): "<page> · <the site's name>" — `site_name`, never a literal.
    Fifteen public pages carry the site's name in their title, twelve of which
    said "— Raak" or "— Raak Millegem" until now. Red by putting `— Raak` back in
    `fotos.html`."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[3]
    titles = {}
    for path in app.rglob("templates/*.html"):
        text = path.read_text()
        if not re.search(r'{%-?\s*extends\s+"site_base\.html"', text):
            continue
        block = re.search(r"{% block title %}(.*?){% endblock %}", text, re.S)
        if block:
            titles[path.name] = block.group(1)
    assert len(titles) >= 18, f"only {len(titles)} public titles found — the check looks nowhere"
    literal = {name: t for name, t in titles.items() if re.search(r"\bRaak\b", t)}
    assert not literal, f"a public title names an association: {literal}"
    with_site = {name: t for name, t in titles.items() if "site_name" in t}
    assert len(with_site) >= 15, sorted(with_site)
    wrong = {
        name: t for name, t in with_site.items() if not t.rstrip().endswith(" · {{ site_name }}")
    }
    assert not wrong, f"not '<page> · <site name>': {wrong}"
