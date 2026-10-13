"""CR-11 phase 1 on the activity screens (#1391): W2, W12 and W15.

W2 — the external links of a component and the poster URL of an activity fold
away in a closed <details>, whose summary counts what is filled in.
W12 — the tile says what it counts, and a card without a single component says
nothing about registrations.
W15 — a component's and a product's action bar sit in the card's foot, not in
the head row beside the title.

The 390 px geometry was measured in a browser for the handover; here the markup
that produces it is pinned. Each test was proven red by its own breakage (named
in its docstring).
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from app.domains.activities.api import (
    Activity,
    ActivityDate,
    ActivitySubRegistration,
    Registration,
)
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _activity(db, name, *, poster_url=None):
    a = Activity(name=name, location="Zaal", poster_url=poster_url)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=20)))
    db.flush()
    return a


def _component(db, activity, name="Deelname", **extra):
    c = ActivitySubRegistration(
        activity_id=activity.id,
        name=name,
        registration_type_code="INDIVIDUAL",
        price=Decimal("0"),
        **extra,
    )
    db.add(c)
    db.flush()
    return c


def _details(html: str) -> list[str]:
    """The closed lines of external links on the page itself — not the one in the
    template a new component is made from."""
    page = re.sub(r"<template\b.*?</template>", "", html, flags=re.S)
    return re.findall(r"<details[^>]*data-rare-line.*?</details>", page, flags=re.S)


# ── W2 ───────────────────────────────────────────────────────────────────────


def test_the_external_links_are_folded_and_counted(client, db_session):
    """Since #1900 the external links stand with their object (end state §3.4 as
    revised): a closed line in the card Activiteit for the poster address, and one
    in every component's card for its three links — each counting what is filled.

    Broken on purpose: `<details open ...>` → "the line starts open"; the count
    dropped from the summary → the counts differ."""
    a = _activity(db_session, "Kaas en wijn", poster_url="https://example.com/affiche.png")
    empty = _component(db_session, a, "Leeg")
    filled = _component(
        db_session,
        a,
        "Met links",
        external_register_url="https://example.com/in",
        info_url="https://example.com/info",
    )
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{a.id}?bewerken=1").text

    lines = _details(html)
    assert len(lines) == 3, f"{len(lines)} closed lines: one for the activity, one per component"
    assert "data-rare-settings" not in html, "the last section of links is back"

    def counted(line: str) -> str:
        summary = re.search(r"<summary.*?</summary>", line, flags=re.S).group(0)
        return " ".join(re.sub(r"<[^>]+>", " ", summary).split())

    by_field = {}
    for line in lines:
        assert not re.match(r"<details[^>]*\bopen\b", line), "the line starts open"
        for name in re.findall(r'name="([^"]+)"', line):
            by_field[name] = counted(line)
    assert by_field["poster_url"] == "Externe koppelingen · 1 ingevuld"
    assert by_field[f"c.{filled.id}.info_url"] == "Externe koppelingen · 2 ingevuld"
    assert by_field[f"c.{empty.id}.info_url"] == "Externe koppelingen", "an empty line counts"
    # Each line stands in the card of its object.
    activity_card = html[html.index('id="aa-section-activity"') :].split("</section>", 1)[0]
    assert 'name="poster_url"' in activity_card
    for component in (empty, filled):
        card = html[html.index(f'data-row-key="{component.id}"') :]
        card = card[: card.index(f'data-repeating-group="p_order.{component.id}"')]
        assert f'name="c.{component.id}.external_register_url"' in card
    # Every external URL field lives inside a closed line.
    outside = re.sub(r"<details[^>]*data-rare-line.*?</details>", "", html, flags=re.S)
    for name in ("external_register_url", "external_registrations_url", "info_url", "poster_url"):
        assert f'.{name}"' not in outside and f'name="{name}"' not in outside, (
            f"{name} outside its closed line"
        )


def test_the_new_activity_form_folds_the_poster_url(client, db_session):
    _login(client)
    html = client.get("/admin/activiteiten/nieuw").text
    lines = _details(html)
    assert len(lines) == 1 and 'name="poster_url"' in lines[0]
    assert "Design Studio" in lines[0]


# ── W12 ──────────────────────────────────────────────────────────────────────


def test_a_card_counts_registrations_only_when_there_is_a_component(client, db_session):
    """Broken on purpose: the `model_copy(... None)` in `_lijst_ctx` removed →
    the component-less row says 0 instead of "—" and the first assertion fails."""
    _activity(db_session, "Zonder onderdeel W12")
    closed = _activity(db_session, "Gesloten onderdeel W12")
    c = _component(db_session, closed, registration_closes_on=date.today() - timedelta(days=1))
    for i in range(3):
        db_session.add(
            Registration(
                phone="0470000000",
                activity_id=closed.id,
                registration_type="INDIVIDUAL",
                contact_name=f"deelnemer{i}",
                contact_email=f"deelnemer{i}@example.com",
                component_id=c.id,
            )
        )
    db_session.commit()
    _login(client)
    html = client.get("/admin/activiteiten").text

    def registrations(name):
        """The text of the Inschrijvingen cell of the row of this activity (#1930)."""
        start = html.index(name)
        row = html[start : html.index("</tr>", start)]
        return re.search(r'data-cell="extra"[^>]*>([^<]*)</td>', row).group(1).strip()

    assert registrations("Zonder onderdeel W12") == "—"
    assert registrations("Gesloten onderdeel W12") == "3"


def test_the_tiles_say_what_they_count(client, db_session):
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert ">Open activiteiten<" in html
    assert ">Volzet onderdeel<" in html
    assert "Open inschrijving" not in html


# ── W15 ──────────────────────────────────────────────────────────────────────
