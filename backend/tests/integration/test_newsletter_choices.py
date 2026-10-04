"""What a newsletter is about, in three groups — and its place in the Assistent's panel (#1562).

Decision 10, row 41 (Koen, 4 October 2026): the letter's choices stand on the
page in three groups — *Voorbije activiteiten*, *Uitgelicht* (at most three,
each an activity block) and *In de kalender* (one block; the featured ones are in
it) — and Raakje's proposal, "Activiteit invoegen" and "Kalender invoegen" read
the same three.

The storage (decided with the master CLI): the JSON column that held one list of
ids holds the three groups. One reader takes both forms; **a letter nobody
touches is not rewritten** — the release before this one cannot read the new
form, so only a choice changes it.

Broken on purpose, each seen red: `choices_of` writing the groups back while
reading (the untouched letter changes form); the limit of three dropped from
`set_choice`; a featured activity not joining the calendar; the newsletter
branch left out of `context_for` (the
draft's page gets the dimmed "Raakje kent deze gegevens nog niet").
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from app.domains.activities.models import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.newsletter import api as nb
from app.domains.newsletter.models import Audience, LetterStatus, Newsletter
from app.domains.reporting.assistant_context import context_for
from app.kernel.tenancy import DEFAULT_TENANT_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _activity(db, name: str, days: int) -> Activity:
    activity = Activity(name=name, location="Dorpsplein", slug=name.lower().replace(" ", "-"))
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=days)))
    db.flush()
    return activity


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture
def world(db_session):
    past = _activity(db_session, "Dorpscafe", -10)
    # Days 1–5: before every activity the test database is seeded with, so
    # these five are the first five to come.
    coming = [_activity(db_session, f"Activiteit {n}", n) for n in range(1, 6)]
    db_session.commit()
    return {"past": past, "coming": coming}


# ── The data ─────────────────────────────────────────────────────────────────


def test_a_new_letter_starts_with_three_groups(db_session, world):
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    chosen = nb.choices_of(db_session, letter)
    coming = [a.id for a in world["coming"]]
    assert chosen.past == (world["past"].id,)
    assert chosen.featured == tuple(coming[:3]), "the first three, soonest first"
    assert chosen.calendar[:5] == tuple(coming), "the calendar holds the featured ones too"
    assert isinstance(letter.draft_activity_ids, dict), "a new letter is written in the new form"
    assert nb.FEATURED_MAX == 3 and nb.CALENDAR_DEFAULT == 9


def test_the_calendar_of_a_new_letter_takes_the_next_nine(db_session):
    made = [_activity(db_session, f"Reeks {n}", 1 + n) for n in range(12)]
    db_session.commit()
    chosen = nb.choices_of(db_session, nb.create_newsletter(db_session, created_by="s@example.org"))
    assert chosen.calendar == tuple(a.id for a in made[:9])


def test_an_older_letter_with_one_list_is_read_and_not_rewritten(db_session, world):
    """The one reader takes the single list of a letter from before #1562 — and
    leaves the row as it is: reading is no reason to change a stored form."""
    ids = [world["coming"][3].id, world["past"].id, world["coming"][0].id, world["coming"][1].id]
    letter = Newsletter(
        created_by="s@example.org", subject="", body_html="", draft_activity_ids=ids
    )
    db_session.add(letter)
    db_session.commit()

    chosen = nb.choices_of(db_session, letter)
    coming = [world["coming"][i].id for i in (0, 1, 3)]
    assert chosen.past == (world["past"].id,)
    assert chosen.featured == tuple(coming) and chosen.calendar == tuple(coming)

    db_session.expire_all()
    assert db_session.get(Newsletter, letter.id).draft_activity_ids == ids, (
        "not rewritten by reading"
    )
    assert not db_session.dirty

    # The first choice writes the three groups.
    nb.set_choice(db_session, letter, "calendar", world["coming"][4].id, chosen=True)
    db_session.expire_all()
    stored = db_session.get(Newsletter, letter.id).draft_activity_ids
    assert set(stored) == {"past", "featured", "calendar"}
    assert stored["calendar"] == [*coming, world["coming"][4].id]


def test_at_most_three_are_featured_and_a_featured_one_joins_the_calendar(db_session, world):
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    fourth, fifth = world["coming"][3], world["coming"][4]
    with pytest.raises(nb.NewsletterError, match="hoogstens drie"):
        nb.set_choice(db_session, letter, "featured", fourth.id, chosen=True)
    assert len(nb.choices_of(db_session, letter).featured) == 3

    nb.set_choice(db_session, letter, "featured", world["coming"][0].id, chosen=False)
    nb.set_choice(db_session, letter, "calendar", fifth.id, chosen=False)
    chosen = nb.set_choice(db_session, letter, "featured", fifth.id, chosen=True)
    assert fifth.id in chosen.featured and fifth.id in chosen.calendar
    assert list(chosen.featured) == sorted(
        chosen.featured, key=[a.id for a in world["coming"]].index
    )
    assert world["coming"][0].id in chosen.calendar, (
        "leaving the featured group leaves the calendar alone"
    )

    with pytest.raises(nb.NewsletterError):
        nb.set_choice(db_session, letter, "elders", fifth.id, chosen=True)


def test_a_sent_letter_keeps_its_choices(db_session, world):
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    letter.audience = Audience.MEMBERS
    letter.status = LetterStatus.SENT
    db_session.commit()
    with pytest.raises(nb.NewsletterError):
        nb.set_choice(db_session, letter, "past", world["past"].id, chosen=False)


def test_a_copy_takes_the_three_groups_as_its_own(db_session, world):
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    copy = nb.copy_newsletter(db_session, letter, created_by="t@example.org")
    assert nb.choices_of(db_session, copy) == nb.choices_of(db_session, letter)
    nb.set_choice(db_session, copy, "past", world["past"].id, chosen=False)
    assert nb.choices_of(db_session, letter).past == (world["past"].id,), "two rows, two sets"


# ── The page ─────────────────────────────────────────────────────────────────


def _group(html: str, key: str) -> str:
    start = html.index(f'data-choice-group="{key}"')
    end = html.find("data-choice-group=", start + 20)
    return html[start : end if end != -1 else html.index("</div>\n</div>", start)]


def test_the_page_shows_three_groups_with_their_counts(client, db_session, world):
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    html = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    assert html.index('id="nb-keuzes"') < html.index('id="nb-formulier"'), "above the form"
    titles = re.findall(
        r"data-choice-title>([^<]+)</span> <span data-choice-count[^>]*>\((\d+)\)", html
    )
    assert [(title, count) for title, count in titles[:2]] == [
        ("Voorbije activiteiten", "1"),
        ("Uitgelicht", "3"),
    ]
    assert titles[2][0] == "In de kalender" and int(titles[2][1]) >= 5
    featured = _group(html, "featured")
    assert featured.count("data-choice=") == 3
    assert "data-choice-add" not in featured, "three are featured: no fourth to add"
    assert "data-choice-add" in _group(html, "calendar")
    assert 'id="nb-raakje"' not in html, "no column of Raakje on the page"


def test_a_choice_changes_its_group_and_answers_with_the_groups(client, db_session, world):
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    first = world["coming"][0]
    answer = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/keuzes/featured/{first.id}/weg", headers=headers
    )
    assert answer.status_code == 200 and "data-letter-choices" in answer.text
    assert "<html" not in answer.text, "the groups alone"
    featured = _group(answer.text, "featured")
    assert f'data-choice="{first.id}"' not in featured and "data-choice-add" in featured

    for extra in (world["coming"][3], first):
        answer = client.post(
            f"/admin/nieuwsbrieven/{letter.id}/keuzes/featured",
            headers=headers,
            data={"activity_id": str(extra.id)},
        )
    assert "hoogstens drie" in answer.text, "the refusal stands with the groups"
    assert len(nb.choices_of(db_session, letter).featured) == 3


def test_activiteit_invoegen_offers_the_featured_ones(client, db_session, world):
    """ "Activiteit invoegen" reads the same groups the page shows."""
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    picker = client.get(f"/admin/nieuwsbrieven/{letter.id}/activiteiten?purpose=insert").text
    offered = re.findall(r"/invoegen/activiteit/(\d+)", picker)
    assert [int(i) for i in offered] == [a.id for a in world["coming"][:3]]
    assert 'type="search"' not in picker, "the featured ones, no search through everything"

    for activity in world["coming"][:3]:
        nb.set_choice(db_session, letter, "featured", activity.id, chosen=False)
    empty = client.get(f"/admin/nieuwsbrieven/{letter.id}/activiteiten?purpose=insert").text
    assert "Nog geen uitgelichte activiteiten" in empty


def test_the_preview_text_is_a_growing_field_with_its_limit(client, db_session):
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    html = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    field = re.search(r'<textarea[^>]*id="nb-voorbeeldtekst"[^>]*>', html).group(0)
    assert 'maxlength="200"' in field and 'name="preview_text"' in field
    for name in ("subject", "preview_text", "body_html"):
        assert f'data-field="{name}"' in html, f"{name} is a field a proposal can name"


# ── The Assistent's panel ────────────────────────────────────────────────────


def test_a_draft_is_a_context_of_the_panel_and_a_sent_letter_is_not(db_session, world):
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    nb.update_draft(db_session, letter, subject="Het najaar", body_html="", audience=None)

    def ctx(path: str):
        return context_for(db_session, f"http://testserver{path}", tenant_id=DEFAULT_TENANT_ID)

    draft = ctx(f"/admin/nieuwsbrieven/{letter.id}")
    assert draft.available and draft.can_ask
    assert draft.key == f"newsletter:{letter.id}"
    assert draft.label == "over de nieuwsbrief “Het najaar”"
    assert draft.post_url == f"/admin/nieuwsbrieven/{letter.id}/raakje/vraag"
    assert draft.history_url == f"/admin/nieuwsbrieven/{letter.id}/raakje/gesprek"
    assert draft.include == "#nb-inhoud" and "nbSelectie" in draft.vals
    assert len(draft.suggestions) == 3

    # The list of letters and the settings are no draft: the rule of the
    # reporting universe decides there, and the newsletter is not in it.
    assert not ctx("/admin/nieuwsbrieven").available
    letter.audience = Audience.MEMBERS
    letter.status = LetterStatus.SENT
    db_session.commit()
    assert not ctx(f"/admin/nieuwsbrieven/{letter.id}").available


def test_the_panel_of_a_draft_sends_the_text_along_and_loads_its_conversation(
    client, db_session, monkeypatch
):
    # Both switches on: the environment's and the tenant's.
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    panel = client.get(
        "/admin/rapporten/raakje/paneel",
        headers={"HX-Current-URL": f"http://testserver/admin/nieuwsbrieven/{letter.id}"},
    )
    assert panel.status_code == 200, panel.text[:200]
    form = re.search(r"<form data-raakje-form[^>]*>", panel.text, re.S).group(0)
    assert f'hx-post="/admin/nieuwsbrieven/{letter.id}/raakje/vraag"' in form
    assert 'hx-include="#nb-inhoud"' in form and "hx-vals='js:{selection:" in form
    talk = re.search(r"<div[^>]*data-panel-conversation[^>]*>", panel.text, re.S).group(0)
    assert f'hx-get="/admin/nieuwsbrieven/{letter.id}/raakje/gesprek"' in talk
    assert 'hx-trigger="load"' in talk
    assert 'name="historie"' not in panel.text, "this conversation is kept with the draft"

    empty = client.get(f"/admin/nieuwsbrieven/{letter.id}/raakje/gesprek")
    assert empty.status_code == 200 and "Zo ziet een markering eruit." in empty.text
