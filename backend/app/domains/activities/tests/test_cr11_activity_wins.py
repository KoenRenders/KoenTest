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
    ActivityProduct,
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
    return re.findall(
        r"<details[^>]*data-(?:external-links|rare-settings).*?</details>", html, flags=re.S
    )


# ── W2 ───────────────────────────────────────────────────────────────────────


def test_the_external_links_are_folded_and_counted(client, db_session):
    """Broken on purpose: `<details open ...>` → the first assertion fails;
    the count dropped from the summary → the second."""
    a = _activity(db_session, "Kaas en wijn", poster_url="https://example.com/affiche.png")
    _component(db_session, a, "Leeg")
    _component(
        db_session,
        a,
        "Met links",
        external_register_url="https://example.com/in",
        info_url="https://example.com/info",
    )
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{a.id}?bewerken=1").text

    folds = _details(html)
    # The activity's fold (the kit's `rare_settings` since #1558), the
    # add-component fold and one per component.
    assert len(folds) == 4, len(folds)
    assert not any(re.match(r"<details[^>]*\bopen\b", f) for f in folds), "a fold starts open"
    summaries = [re.search(r"<summary.*?</summary>", f, flags=re.S).group(0) for f in folds]
    assert sum("2 externe links" in s for s in summaries) == 1
    assert sum("1 externe link<" in s for s in summaries) == 1, "the poster URL's fold"
    # Every external URL field lives inside a fold.
    outside = re.sub(
        r"<details[^>]*data-(?:external-links|rare-settings).*?</details>", "", html, flags=re.S
    )
    for name in ("external_register_url", "external_registrations_url", "info_url", "poster_url"):
        assert f'name="{name}"' not in outside, f"{name} outside the fold"


def test_a_component_fold_sits_under_the_attachment_with_full_width_fields(client, db_session):
    """Koen at the validation (1 October 2026): on a component the fold sits under
    "Info-bijlage", just above the buttons, and opened its three fields stand one
    under the other at full width. Proven red: the fold moved back above the
    attachment → the order assertion fails; `sm:w-72` put back → the width one."""
    a = _activity(db_session, "Volgorde W2")
    c = _component(db_session, a, external_register_url="https://example.com/in")
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{a.id}").text

    for form_start, form_end in (
        (f'<form id="aa-comp-{c.id}"', "</form>"),
        ('hx-post="/admin/activiteiten/' + str(a.id) + '/onderdelen" ', "</form>"),
    ):
        form = html[html.index(form_start) :]
        form = form[: form.index(form_end)]
        assert form.index("Info-bijlage") < form.index("data-external-links"), form_start
        fold = re.search(r"<details[^>]*data-external-links.*?</details>", form, flags=re.S).group(
            0
        )
        assert "sm:w-72" not in fold and 'class="mt-2 space-y-2"' in fold, form_start
        assert fold.count('<div class="w-full">') == 3, form_start


def test_the_new_activity_form_folds_the_poster_url(client, db_session):
    _login(client)
    html = client.get("/admin/activiteiten/nieuw").text
    folds = _details(html)
    assert len(folds) == 1 and 'name="poster_url"' in folds[0]
    assert "Design Studio" in folds[0]


# ── W12 ──────────────────────────────────────────────────────────────────────


def test_a_card_counts_registrations_only_when_there_is_a_component(client, db_session):
    """Broken on purpose: the `model_copy(... None)` in `_lijst_ctx` removed →
    the component-less card says "0 inschrijvingen" and the first assertion fails."""
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

    def card(name):
        start = html.index(name)
        return html[start : html.index("</a>", start)]

    assert "inschrijvingen" not in card("Zonder onderdeel W12")
    assert "· 3 inschrijvingen" in card("Gesloten onderdeel W12")


def test_the_tiles_say_what_they_count(client, db_session):
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert "Open inschrijving" in html
    assert "Volzette onderdelen" in html
    assert ">Open inschrijvingen<" not in html


# ── W15 ──────────────────────────────────────────────────────────────────────


def test_the_action_bars_sit_in_the_card_foot(client, db_session):
    """Broken on purpose: the component's bar put back beside the edit toggle →
    the head row holds a form="aa-comp-…" button again."""
    a = _activity(db_session, "Voetbalk")
    c = _component(db_session, a)
    p = ActivityProduct(component_id=c.id, name="Drankbon", price=Decimal("2"), is_free=False)
    db_session.add(p)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{a.id}").text

    feet = re.findall(r"<div[^>]*data-card-foot[^>]*>.*?</div>\s*</div>", html, flags=re.S)
    assert any(f'form="aa-comp-{c.id}"' in f for f in feet), "no component bar in a foot"
    assert any(f'form="aa-prod-{p.id}"' in f for f in feet), "no product bar in a foot"
    # The head row (title, arrows, edit toggle) carries no bar any more.
    head = html[html.index("<h3") : html.index(f'<form id="aa-comp-{c.id}"')]
    assert f'form="aa-comp-{c.id}"' not in head
