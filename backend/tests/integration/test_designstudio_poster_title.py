"""#1461 — a design's own poster title, else the activity's name.

Koen, 2 October 2026, making the poster for "Stappen en klappen": the
activity's name carries what the agenda needs ("maandelijks"), the poster
wants only "Stappen en klappen". A design may now name its own title; empty,
or the activity's name typed back, means the activity's name, as before.

A filled title differs on purpose, so it raises no fact-shadow warning — the
one aa6fff20 gave for the old `title_override` does not come back.

Proven red by breaking it on purpose: the poster back on `facts["title"]` and
the field out of the editor → the title test and the editor test fail. Against
master the module does not even import: there is no `poster_title`.
"""

from __future__ import annotations

import re
from datetime import date, time

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.designstudio.api import (
    DesignError,
    content_for,
    create_design,
    facts_for,
    save_design,
    warnings_for,
)
from app.domains.designstudio.service import MAX_POSTER_TITLE, copy_designs, merged_for
from app.kernel.codes import code_of
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

NAME = "Stappen en klappen maandelijks"


@pytest.fixture
def design(db_session):
    activity = Activity(name=NAME, location="Miloheem")
    db_session.add(activity)
    db_session.flush()
    db_session.add(
        ActivityDate(activity_id=activity.id, start_date=date(2026, 10, 12), start_time=time(9))
    )
    db_session.flush()
    return create_design(
        db_session,
        activity_id=activity.id,
        duo_code="dark_green-golden_yellow",
        preset="beeld",
        created_by="bestuur@example.com",
    )


def _save(db_session, design, **fields):
    form = {"duo_code": design.duo_code, "preset": code_of(design.preset), **fields}
    save_design(db_session, design, form, highlights=[], logo_ids=[])


def _title_on_the_poster(db_session, design) -> tuple[tuple[str, ...], str, str]:
    """The drawn title lines, their joiner, and the SVG's own <title>."""
    content = content_for(db_session, design)
    svg = merged_for(db_session, design, "print_a", facts=facts_for(db_session, design)).svg
    found = re.search(r"<title>(.*?)</title>", svg)
    assert found, "the poster SVG carries no <title>"
    return content.title_lines, content.title_joiner, found.group(1)


def test_without_a_poster_title_the_poster_carries_the_activity_name(db_session, design):
    lines, _joiner, svg_title = _title_on_the_poster(db_session, design)
    assert " ".join(lines) == NAME.upper()
    assert svg_title == NAME


def test_a_poster_title_wins_on_the_poster(db_session, design):
    _save(db_session, design, poster_title="  Stappen en klappen ", tagline="wandelen")
    assert design.poster_title == "Stappen en klappen"

    lines, joiner, svg_title = _title_on_the_poster(db_session, design)
    assert (lines, joiner) == (("STAPPEN", "KLAPPEN"), "EN")
    assert svg_title == "Stappen en klappen"
    assert content_for(db_session, design).tagline == "wandelen"
    assert facts_for(db_session, design)["title"] == NAME, "the activity keeps its name"


@pytest.mark.parametrize("typed", ["", "   ", NAME])
def test_clearing_the_field_or_typing_the_name_back_falls_back(db_session, design, typed):
    _save(db_session, design, poster_title="Stappen en klappen")
    _save(db_session, design, poster_title=typed)
    assert design.poster_title is None, "stored empty, so a renamed activity still reaches it"
    lines, _joiner, svg_title = _title_on_the_poster(db_session, design)
    assert " ".join(lines) == NAME.upper() and svg_title == NAME


def test_a_form_without_the_field_leaves_the_title_alone(db_session, design):
    _save(db_session, design, poster_title="Stappen en klappen")
    _save(db_session, design, tagline="wandelen")
    assert design.poster_title == "Stappen en klappen"


def test_a_title_longer_than_the_column_is_refused_before_anything_changes(db_session, design):
    _save(db_session, design, poster_title="Stappen en klappen")
    with pytest.raises(DesignError, match=f"Ten hoogste {MAX_POSTER_TITLE} tekens"):
        _save(db_session, design, poster_title="x" * (MAX_POSTER_TITLE + 1), tagline="weg")
    assert design.poster_title == "Stappen en klappen" and design.tagline is None
    assert MAX_POSTER_TITLE == 255


def test_a_poster_title_raises_no_shadow_warning(db_session, design):
    _save(db_session, design, poster_title="Stappen en klappen")
    assert warnings_for(design, facts_for(db_session, design)) == []


def test_a_copied_activity_keeps_the_poster_title(db_session, design):
    _save(db_session, design, poster_title="Stappen en klappen")
    copy = Activity(name=NAME)
    db_session.add(copy)
    db_session.flush()
    (copied,) = copy_designs(db_session, design.activity_id, copy.id, actor="bestuur@example.com")
    assert copied.poster_title == "Stappen en klappen"


def test_the_editor_offers_the_field_with_the_name_as_placeholder(client, db_session, design):
    db_session.commit()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)

    def field(html: str) -> str:
        found = re.search(r'<input[^>]*name="poster_title"[^>]*>', html)
        assert found, "the editor has no poster title field"
        return found.group(0)

    empty = field(client.get(f"/admin/ontwerpen/{design.id}").text)
    assert f'placeholder="{NAME}"' in empty and "value=" not in empty

    saved = client.post(
        f"/admin/ontwerpen/{design.id}",
        data={
            "duo_code": design.duo_code,
            "preset": code_of(design.preset),
            "layout": "print_a",
            "poster_title": "Stappen en klappen",
        },
        headers={"X-CSRF-Token": csrf_token_for(session)},
    )
    assert saved.status_code == 200
    assert 'value="Stappen en klappen"' in field(saved.text)
