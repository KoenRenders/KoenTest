"""Design Studio — the service with a database (CR-10 B8, #1007).

Facts stay on the activity and age the version; a version is all-or-nothing;
publishing goes through media's poster door; the AI budget refuses before a
call; the screens sit behind the admin door.

Tests marked ``needs_media_kinds`` depend on #1005 (media kinds
``design_image`` / ``design_render``, SVG accepted for renders). They are
strict xfails: the day #1005 lands on master they turn red here, which is the
signal to drop the marker — a test that passes silently under xfail proves
nothing.
"""
from __future__ import annotations

import shutil
from datetime import date, time
from decimal import Decimal

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.designstudio import imaging, render
from app.domains.designstudio.api import (
    DesignError,
    ImagingError,
    check_design,
    content_for,
    create_design,
    facts_for,
    fingerprint,
    is_stale,
    make_version,
    save_design,
)
from app.domains.designstudio.models import ImageGeneration
from app.domains.designstudio.service import _title_lines, day_label
from app.kernel.jobs import KernelJob
from tests.conftest import SEEDED_ADMIN_EMAIL

INKSCAPE = shutil.which(render.INKSCAPE) is not None
needs_inkscape = pytest.mark.skipif(not INKSCAPE, reason="inkscape not installed")
needs_media_kinds = pytest.mark.xfail(strict=True, reason="#1005: media kinds design_image/design_render not on master yet")


@pytest.fixture
def activity(db_session):
    act = Activity(name="Stappen en Klappen", location="Miloheem", registration_closes_on=date(2026, 10, 1))
    db_session.add(act)
    db_session.flush()
    for day in (date(2026, 10, 12), date(2026, 11, 9)):
        db_session.add(ActivityDate(activity_id=act.id, start_date=day, start_time=time(20, 0)))
    db_session.flush()
    return act


@pytest.fixture
def design(db_session, activity):
    d = create_design(db_session, activity_id=activity.id, duo_code="dark_green-golden_yellow", preset="reeks",
                      created_by="bestuur@example.com")
    save_design(db_session, d, {"duo_code": "dark_green-golden_yellow", "preset": "reeks", "subtitle": "samen wandelen",
                                "tagline": "Zet het in je agenda!", "welcome_line": "ook zonder lidkaart"},
                highlights=[("users", "Gezellig samen wandelen en praten", False),
                            ("coffee", "Nadien ene drinken", False)],
                logo_ids=[])
    return d


# ── Designs and facts ───────────────────────────────────────────────────────

def test_a_design_needs_an_existing_activity_and_an_enabled_duo(db_session, activity):
    with pytest.raises(DesignError, match="Activiteit"):
        create_design(db_session, activity_id=999_999, duo_code="dark_green-golden_yellow")
    with pytest.raises(DesignError, match="duo"):
        create_design(db_session, activity_id=activity.id, duo_code="hot_pink-indigo")  # permitted, not enabled
    with pytest.raises(ValueError):
        create_design(db_session, activity_id=activity.id, duo_code="hot_pink-golden_yellow")  # not permitted


def test_facts_come_from_the_activity_and_the_design_never_copies_them(db_session, design, activity):
    facts = facts_for(db_session, design)
    assert facts["title"] == "Stappen en Klappen"
    assert facts["location"] == "Miloheem"
    assert [d["date"] for d in facts["dates"]] == ["2026-10-12", "2026-11-09"]
    assert facts["deadline"] == "2026-10-01"
    content = content_for(db_session, design, facts)
    assert content.title_lines == ("STAPPEN", "KLAPPEN") and content.title_joiner == "EN"
    assert content.dates == ("12 OKTOBER", "9 NOVEMBER") and content.dates_heading == "DATA IN 2026"
    assert any(h.text == "MILOHEEM" for h in content.highlights)
    assert content.bar_text == "SAMEN WANDELEN"
    # Nothing of the activity lives on the design row.
    assert not any(v == "Stappen en Klappen" for v in vars(design).values())


def test_the_fingerprint_changes_when_a_fact_changes(db_session, design, activity):
    before = fingerprint(facts_for(db_session, design))
    activity.location = "Kerkplein"
    db_session.flush()
    assert fingerprint(facts_for(db_session, design)) != before
    activity.location = "Miloheem"
    db_session.flush()
    assert fingerprint(facts_for(db_session, design)) == before


def test_a_ticked_organiser_lands_on_the_poster_and_an_unticked_one_does_not(db_session, design, activity):
    """#1004 through its facade: the contact line follows the tick and the
    override; nobody ticked → the association's own line."""
    from app.domains.activities.api import add_organiser, organisers_for, update_organiser
    from tests.conftest import create_test_family

    _member, person = create_test_family(db_session, email="trekker@example.com")
    add_organiser(db_session, activity.id, person.id)
    organiser = organisers_for(db_session, activity.id)[0]
    facts = facts_for(db_session, design)
    assert facts["organisers"] == []
    update_organiser(db_session, activity.id, organiser.id,
                     {"is_contact": True, "mobile_override": "0470 00 00 00", "email_override": ""})
    facts = facts_for(db_session, design)
    assert facts["organisers"] == [{"name": "Test Persoon", "mobile": "0470 00 00 00", "email": "trekker@example.com"}]
    content = content_for(db_session, design, facts)
    assert content.contacts[0].name == "Test Persoon" and content.contacts[0].mobile == "0470 00 00 00"
    assert "Test Persoon 0470 00 00 00" in render.merge(content, layout="print_a").svg


def test_title_splitting_rules():
    class D:
        title_breaks = None
        title_override = None

    assert _title_lines(D(), "Stappen en Klappen") == (("STAPPEN", "KLAPPEN"), "EN")
    assert _title_lines(D(), "Bowlen") == (("BOWLEN",), "")
    assert _title_lines(D(), "Info- en gespreksavond vaderschap") == (("INFO- EN", "GESPREKSAVOND VADERSCHAP"), "")
    d = D()
    d.title_breaks = "Zo vader / zo zoon"
    assert _title_lines(d, "whatever") == (("ZO VADER", "ZO ZOON"), "")
    assert day_label(date(2026, 7, 13)) == "13 JULI"
    assert day_label(date(2026, 7, 13), weekday=True) == "MAANDAG 13 JULI"


def test_highlights_are_capped_and_icons_checked(db_session, design):
    with pytest.raises(DesignError, match="kernpunten"):
        save_design(db_session, design, {"duo_code": design.duo_code, "preset": design.preset},
                    highlights=[("smile", f"punt {i}", False) for i in range(7)], logo_ids=[])
    with pytest.raises(DesignError, match="icoon"):
        save_design(db_session, design, {"duo_code": design.duo_code, "preset": design.preset},
                    highlights=[("no-such-icon", "x", False)], logo_ids=[])
    with pytest.raises(DesignError, match="logo"):
        save_design(db_session, design, {"duo_code": design.duo_code, "preset": design.preset},
                    highlights=[], logo_ids=[1, 2, 3])


def test_check_design_reports_per_layout_without_inkscape(db_session, design):
    problems = check_design(db_session, design)
    assert set(problems) == {"print_a", "feed_portrait"}
    assert problems["print_a"] == []


# ── Versions ────────────────────────────────────────────────────────────────

@needs_inkscape
@needs_media_kinds
def test_a_version_is_all_or_nothing_and_ages_with_the_facts(db_session, design, activity):
    version = make_version(db_session, design, created_by="bestuur@example.com")
    assert version.number == 1
    kinds = {(r.layout_code, r.variant, r.size_code) for r in version.renditions}
    assert {("print_a", "pdf", "a3"), ("print_a", "pdf", "a4"), ("print_a", "png", "a3"), ("print_a", "svg", "a3"),
            ("feed_portrait", "png", "feed"), ("feed_portrait", "svg", "feed")} <= kinds
    assert not is_stale(db_session, version)
    activity.location = "Kerkplein"
    db_session.flush()
    assert is_stale(db_session, version)

    # A title that cannot fit: no version, and the old one untouched.
    design.title_override = "EEN ONMOGELIJK LANGE ACTIVITEITSTITEL DIE NERGENS OP PAST"
    with pytest.raises(DesignError) as exc:
        make_version(db_session, design)
    assert any("Titelregel" in m for m in exc.value.messages)
    assert [v.number for v in design.versions] == [1]


@needs_inkscape
@needs_media_kinds
def test_at_most_three_versions_and_the_published_one_survives(db_session, design):
    v1 = make_version(db_session, design)
    design.published_version_id = v1.id
    for _ in range(3):
        make_version(db_session, design)
    numbers = sorted(v.number for v in design.versions)
    assert len(numbers) == 3 and 1 in numbers


# ── AI images ───────────────────────────────────────────────────────────────

def test_the_budget_refuses_before_any_call(monkeypatch, db_session, design):
    from app.domains.designstudio.api import request_images

    monkeypatch.delenv(imaging.ENV_ENABLED, raising=False)
    with pytest.raises(ImagingError, match="kill switch"):
        request_images(db_session, design, "two people walking a forest path")
    monkeypatch.setenv(imaging.ENV_ENABLED, "true")
    monkeypatch.setenv(imaging.ENV_KEY, "test-key")
    monkeypatch.setenv(imaging.ENV_BUDGET, "0.10")
    with pytest.raises(ImagingError, match="maandbudget"):
        request_images(db_session, design, "two people walking a forest path")
    assert db_session.query(ImageGeneration).count() == 0
    assert db_session.query(KernelJob).filter(KernelJob.name == "designstudio.generate").count() == 0


def test_one_click_reserves_four_variants_and_queues_four_jobs(monkeypatch, db_session, design):
    from app.domains.designstudio.api import request_images

    monkeypatch.setenv(imaging.ENV_ENABLED, "true")
    monkeypatch.setenv(imaging.ENV_KEY, "test-key")
    monkeypatch.setenv(imaging.ENV_BUDGET, "50")
    with pytest.raises(ImagingError, match="minstens"):
        request_images(db_session, design, "kids")
    key = request_images(db_session, design, "two adults and two children walking a forest path",
                         requested_by="bestuur@example.com")
    rows = db_session.query(ImageGeneration).filter(ImageGeneration.request_key == key).all()
    assert len(rows) == 4 and all(r.status == "requested" and r.reserved_cents > 0 for r in rows)
    jobs = db_session.query(KernelJob).filter(KernelJob.name == "designstudio.generate").all()
    assert len(jobs) == 4 and all(j.payload["prompt"].endswith(imaging.STYLE_SUFFIX) for j in jobs)
    # The reservation counts against the next click.
    from app.domains.designstudio.api import budget

    assert budget(db_session).reserved_eur == Decimal(rows[0].reserved_cents * 4) / 100


def test_a_second_click_while_the_first_runs_is_refused(monkeypatch, db_session, design):
    """Four rows and four jobs, not eight: the reservation guards the budget,
    this guards the click."""
    from app.domains.designstudio.api import request_images

    monkeypatch.setenv(imaging.ENV_ENABLED, "true")
    monkeypatch.setenv(imaging.ENV_KEY, "test-key")
    monkeypatch.setenv(imaging.ENV_BUDGET, "50")
    request_images(db_session, design, "two adults and two children walking a forest path")
    with pytest.raises(DesignError, match="loopt al"):
        request_images(db_session, design, "two adults and two children walking a forest path")
    assert db_session.query(ImageGeneration).count() == 4


def test_design_text_that_shadows_a_fact_is_named_not_blocked(db_session, design):
    from app.domains.designstudio.api import warnings_for

    facts = facts_for(db_session, design)
    assert warnings_for(design, facts) == []
    design.title_override = "Wandelen met Raak"
    assert any("wijkt af" in w for w in warnings_for(design, facts))
    assert check_design(db_session, design)["print_a"] == []  # a warning is not a violation


@needs_inkscape
@needs_media_kinds
def test_an_uploaded_svg_replaces_the_merge_and_ages_with_the_facts(db_session, design, activity):
    from app.domains.designstudio.api import edited_svg_for, upload_edited_svg
    from app.domains.designstudio.service import merged_for

    svg = merged_for(db_session, design, "print_a", facts=facts_for(db_session, design)).svg
    edited = svg.replace("SAMEN WANDELEN", "HANDMATIG BEWERKT")
    assert upload_edited_svg(db_session, design, "print_a", edited.encode()) == []
    assert "HANDMATIG BEWERKT" in merged_for(db_session, design, "print_a").svg
    row = edited_svg_for(db_session, design, "print_a")
    assert row is not None and row.facts_fingerprint == fingerprint(facts_for(db_session, design))
    activity.location = "Kerkplein"
    db_session.flush()
    assert row.facts_fingerprint != fingerprint(facts_for(db_session, design))  # stale until re-uploaded
    with pytest.raises(DesignError, match="paginaformaat"):
        upload_edited_svg(db_session, design, "feed_portrait", edited.encode())


@needs_inkscape
@needs_media_kinds
@pytest.mark.anyio
async def test_publishing_an_older_version_restores_that_poster(db_session, design, activity):
    from fastapi import BackgroundTasks

    from app.domains.designstudio.api import publish
    from app.domains.media.api import list_media

    v1 = make_version(db_session, design)
    design.subtitle = "tweede versie"
    v2 = make_version(db_session, design)
    await publish(db_session, design, v2, BackgroundTasks())
    await publish(db_session, design, v1, BackgroundTasks())
    assert design.published_version_id == v1.id
    posters = list_media(db_session, kind="activity_poster", activity_id=activity.id)
    assert len(posters) == 1 and posters[0]["content_type"] == "application/pdf"


def test_budget_check_names_the_platform_cap():
    b = imaging.Budget(enabled=True, monthly_eur=Decimal("50"), platform_eur=Decimal("10"),
                       spent_eur=Decimal("0"), reserved_eur=Decimal("0"))
    with pytest.raises(ImagingError, match="platformplafond"):
        imaging.check_budget(b, platform_spent_eur=Decimal("9.99"), cost_eur=Decimal("0.17"))
    imaging.check_budget(b, platform_spent_eur=Decimal("5"), cost_eur=Decimal("0.17"))


# ── Screens ─────────────────────────────────────────────────────────────────

def test_the_screens_sit_behind_the_admin_door(client):
    for path in ("/admin/ontwerpen", "/admin/ontwerpen/nieuw", "/admin/ontwerpen/1",
                 "/admin/ontwerpen/1/voorbeeld.png", "/admin/ontwerpen/1/svg/print_a"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (302, 303, 401, 403), path


def test_the_list_and_the_editor_render_for_an_admin(client, db_session, design):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get("/admin/ontwerpen")
    assert page.status_code == 200 and "Stappen en Klappen" in page.text
    editor = client.get(f"/admin/ontwerpen/{design.id}")
    assert editor.status_code == 200
    assert "Miloheem" in editor.text and 'name="hl_text_0"' in editor.text
    svg = client.get(f"/admin/ontwerpen/{design.id}/svg/print_a")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")
    assert "STAPPEN" in svg.text and "ref100mm" in svg.text
