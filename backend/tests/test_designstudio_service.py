"""Design Studio — the service with a database (CR-10 B8, #1007).

Facts stay on the activity and age the version; a version is all-or-nothing;
publishing goes through media's poster door; the AI budget refuses before a
call; the screens sit behind the admin door.

Renders and edited SVGs go through media (#1011: ``design_render`` — PDF,
PNG and SVG, the SVG cleaned by media's one allowlist).
"""
from __future__ import annotations

import re
import shutil
from datetime import date, time
from decimal import Decimal

import pytest

from app.config import settings
from app.domains.activities.api import (Activity, ActivityDate,
                                        ActivitySubRegistration)
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
from tests.test_designstudio_engine import PNG_2x2

INKSCAPE = shutil.which(render.INKSCAPE) is not None
needs_inkscape = pytest.mark.skipif(not INKSCAPE, reason="inkscape not installed")


@pytest.fixture
def activity(db_session):
    act = Activity(name="Stappen en Klappen", location="Miloheem")
    db_session.add(act)
    db_session.flush()
    for day in (date(2026, 10, 12), date(2026, 11, 9)):
        db_session.add(ActivityDate(activity_id=act.id, start_date=day, start_time=time(20, 0)))
    # #1053: de uiterste inschrijfdatum hoort bij het onderdeel. Eén onderdeel hier,
    # dus de affiche draagt die datum nog steeds — zie de test hieronder voor het
    # geval waarin de onderdelen het oneens zijn.
    db_session.add(ActivitySubRegistration(
        activity_id=act.id, name="Deelname", registration_type_code="INDIVIDUAL",
        registration_closes_on=date(2026, 10, 1)))
    db_session.flush()
    return act


@pytest.fixture
def design(db_session, activity):
    d = create_design(db_session, activity_id=activity.id, duo_code="dark_green-golden_yellow", preset="beeld",
                      created_by="bestuur@example.com")
    from app.domains.media.api import MediaAsset

    photo = MediaAsset(kind="design_image", activity_id=activity.id, data=PNG_2x2, content_type="image/png",
                       thumbnail=PNG_2x2, thumb_content_type="image/png", width=2, height=2, byte_size=len(PNG_2x2),
                       title="proef", sort_order=0, is_active=True)
    db_session.add(photo)
    db_session.flush()
    save_design(db_session, d, {"duo_code": "dark_green-golden_yellow", "preset": "beeld", "subtitle": "samen wandelen",
                                "tagline": "Zet het in je agenda!", "main_image_id": str(photo.id)},
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


def test_a_poster_drops_the_deadline_when_the_components_disagree(db_session, design,
                                                                  activity):
    """#1053: one line cannot carry two dates, and a wrong date on paper is worse
    than none. So the poster only shows a deadline when every component has the
    same one.

    Broken to see it red: `_shared_deadline` returning the earliest date instead of
    the shared one — the poster then prints 1 October while the second component
    still takes registrations until the 8th.
    """
    db_session.add(ActivitySubRegistration(
        activity_id=activity.id, name="Cornhole",
        registration_type_code="INDIVIDUAL",
        registration_closes_on=date(2026, 10, 8)))
    db_session.flush()
    db_session.refresh(activity)

    assert facts_for(db_session, design)["deadline"] == ""


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
    # Name and mobile on one line, the address under it: the whole of it does
    # not fit in the band's column, and since 21 September it wraps instead of
    # shrinking.
    svg = render.merge(content, layout="print_a").svg
    assert "Test Persoon · 0470 00 00 00" in svg and "trekker@example.com" in svg


def test_the_activity_description_is_the_explanation_unless_the_design_types_its_own(db_session, design, activity):
    """#1016 on the poster: live fact, in the fingerprint; a typed
    explanation wins and is named as a deviation."""
    from app.domains.designstudio.api import warnings_for

    activity.description = "Een rustige tocht langs het kanaal."
    db_session.flush()
    facts = facts_for(db_session, design)
    assert content_for(db_session, design, facts).explanation_md == "Een rustige tocht langs het kanaal."
    before = fingerprint(facts)
    activity.description = "Een pittige tocht langs het kanaal."
    db_session.flush()
    assert fingerprint(facts_for(db_session, design)) != before
    design.explanation_md = "Eigen tekst."
    facts = facts_for(db_session, design)
    assert content_for(db_session, design, facts).explanation_md == "Eigen tekst."
    assert any("wijkt af" in w for w in warnings_for(design, facts))


def test_only_the_two_presets_exist_and_the_database_agrees(db_session, design):
    with pytest.raises(DesignError, match="opmaak"):
        save_design(db_session, design, {"duo_code": design.duo_code, "preset": "illustratie"}, highlights=[], logo_ids=[])
    save_design(db_session, design, {"duo_code": design.duo_code, "preset": "eenvoudig"}, highlights=[], logo_ids=[])
    assert design.preset == "eenvoudig"
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.execute(text("UPDATE designstudio.designs SET preset = 'reeks' WHERE id = :id"), {"id": design.id})
    db_session.rollback()


def test_without_a_ticked_organiser_the_band_shows_the_association_gsm_without_a_name(db_session, design):
    """Koen, 19 September 2026: the association's name stood next to its gsm;
    the band already names the association through website and e-mail."""
    facts = facts_for(db_session, design)
    facts = dict(facts, organisers=[], mobile="0470 00 00 00", association="Raak Millegem",
                 website="www.example.be", email="info@example.be")
    content = content_for(db_session, design, facts)
    assert content.contacts == () and content.association_mobile == "0470 00 00 00"
    svg = render.merge(content, layout="print_a").svg
    assert ">0470 00 00 00</text>" in svg and "info@example.be" in svg and "Raak Millegem · 0470" not in svg


def test_the_poster_gsm_comes_from_the_real_mobile_row(db_session, design):
    """#1160: het opschonen van de contactsoorten mag de affiche niet raken.

    De terugval hierboven wordt getoetst met een `mobile` die de test zelf in de
    feiten schrijft — die blijft dus groen als de echte rij nooit meer gelezen
    wordt. Deze test legt de bedrading erbij: een `MOBILE`-rij op de organisatie,
    door `facts_for` heen, tot in de voetbalk.

    Waarom dat nu telt: #1160 verhuist de vraag *"is deze contactsoort een
    sociaal netwerk?"* naar `contact_type_codes`, en haalt `MOBILE` uit de
    footer. De affiche leest langs een andere weg (`CONTACTVELDEN` in
    `organization_service`) en hoort niets te merken. Koen heeft de rij *Mobiel*
    bewust laten staan omdat een affiche zonder organisatoren anders geen enkele
    manier overhoudt om iemand te bereiken.

    Tegenproef: `CONTACTVELDEN` de regel `("mobile", "MOBILE")` afgenomen — dan
    faalt deze test met *"de feiten lezen het gsm-nummer niet uit de MOBILE-rij:
    \'\'"*. De eerdere terugvaltest blijft daarbij groen, want die schrijft het
    nummer zelf in de feiten.
    """
    from app.domains.mdm.api import ContactDetail, Organization
    from app.kernel.tenant_config import _actieve_tenant

    organisatie = (db_session.query(Organization)
                   .filter(Organization.id == _actieve_tenant(None))
                   .execution_options(include_all_tenants=True).one())
    db_session.add(ContactDetail(tenant_id=organisatie.id, organization_id=organisatie.id,
                                 contact_type_code="MOBILE", value="0470 55 44 33"))
    db_session.commit()

    facts = facts_for(db_session, design)
    assert facts["organisers"] == [], (
        "deze activiteit hoort geen organisatoren te hebben; anders toetst de "
        "test de terugval niet maar de gewone weg")
    assert facts["mobile"] == "0470 55 44 33", (
        f"de feiten lezen het gsm-nummer niet uit de MOBILE-rij: {facts['mobile']!r}")

    content = content_for(db_session, design, facts)
    assert content.contacts == () and content.association_mobile == "0470 55 44 33"
    assert ">0470 55 44 33</text>" in render.merge(content, layout="print_a").svg, (
        "het nummer staat niet in de voetbalk van de affiche")


def test_one_ticked_organiser_out_of_two_means_no_association_row(db_session, design, activity):
    """Koen, 19 September 2026: the association's gsm row appears only when
    nobody is ticked — never next to a ticked organiser."""
    from app.domains.activities.api import add_organiser, organisers_for, update_organiser
    from tests.conftest import create_test_family

    _m1, p1 = create_test_family(db_session, email="een@example.com")
    _m2, p2 = create_test_family(db_session, email="twee@example.com")
    add_organiser(db_session, activity.id, p1.id)
    add_organiser(db_session, activity.id, p2.id)
    rows = organisers_for(db_session, activity.id)
    update_organiser(db_session, activity.id, rows[0].id, {"is_contact": True, "mobile_override": "0470 11 11 11", "email_override": ""})
    update_organiser(db_session, activity.id, rows[1].id, {"is_contact": False, "mobile_override": "", "email_override": ""})
    facts = dict(facts_for(db_session, design), mobile="0499 99 99 99", email="raak@example.be")
    content = content_for(db_session, design, facts)
    assert len(content.contacts) == 1 and content.contacts[0].mobile == "0470 11 11 11"
    svg = render.merge(content, layout="print_a").svg
    assert "0499 99 99 99" not in svg and "raak@example.be" not in svg and 't-contact-1' not in svg


def test_title_splitting_rules():
    assert _title_lines("Stappen en Klappen") == (("STAPPEN", "KLAPPEN"), "EN")
    assert _title_lines("Bowlen") == (("BOWLEN",), "")
    assert _title_lines("Info- en gespreksavond vaderschap") == (("INFO- EN", "GESPREKSAVOND VADERSCHAP"), "")
    assert day_label(date(2026, 7, 13)) == "13 JULI"
    assert day_label(date(2026, 7, 13), weekday=True) == "MAANDAG 13 JULI"


def test_highlights_are_capped_and_icons_checked(db_session, design):
    with pytest.raises(DesignError, match="kernpunten"):
        save_design(db_session, design, {"duo_code": design.duo_code, "preset": design.preset},
                    highlights=[("smile", f"punt {i}", False) for i in range(5)], logo_ids=[])
    # Four own rows all reach the poster, next to the automatic ones.
    save_design(db_session, design, {"duo_code": design.duo_code, "preset": design.preset},
                highlights=[("smile", f"eigen punt {i}", False) for i in range(4)], logo_ids=[])
    content = content_for(db_session, design)  # the fixture has two dates: place + four own = 5
    assert len(content.highlights) == 5 and content.highlights[-1].text == "EIGEN PUNT 3"


def test_the_database_refuses_a_fifth_own_highlight(db_session, design):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    params = {"t": design.tenant_id, "d": design.id}
    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO designstudio.design_highlights (tenant_id, design_id, sort_order, icon_code, text, emphasis) "
                                "VALUES (:t, :d, 4, 'smile', 'vijfde', false)"), params)
    db_session.rollback()


def test_saving_twice_with_the_same_highlights_and_logos_works(db_session, design):
    """HDEV, 19 September 2026: the second save of a design with highlights
    (or logos) died on the unique (design, sort_order) — the new rows were
    inserted before the old ones were deleted. Nothing of the form arrived,
    the preset included."""
    form = {"duo_code": design.duo_code, "preset": "tekst"}
    hls = [("users", "Eerste", False), ("coffee", "Tweede", True)]
    save_design(db_session, design, form, highlights=hls, logo_ids=[41, 42])
    save_design(db_session, design, form, highlights=hls, logo_ids=[42, 41])
    db_session.refresh(design)
    assert [h.text for h in design.highlights] == ["Eerste", "Tweede"]
    assert [lg.media_asset_id for lg in design.logos] == [42, 41]
    assert design.preset == "tekst"


def test_check_design_reports_per_layout_without_inkscape(db_session, design):
    problems = check_design(db_session, design)
    assert set(problems) == {"print_a", "feed_portrait"}
    assert problems["print_a"] == []


# ── Versions ────────────────────────────────────────────────────────────────

@needs_inkscape
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
    activity.name = "EEN ONMOGELIJK LANGE ACTIVITEITSTITEL DIE NERGENS OP PAST OF DE AFFICHE"
    db_session.flush()
    with pytest.raises(DesignError) as exc:
        make_version(db_session, design)
    assert any("Titelregel" in m for m in exc.value.messages)
    assert [v.number for v in design.versions] == [1]


@needs_inkscape
@needs_inkscape
def test_a_downloaded_file_is_named_after_the_activity(db_session, design, activity):
    """Koen, 21 September 2026, after downloading his first finished poster:
    "waarom niet iets zoals bowlen-v1-a4.pdf, en bowlen-v1-portrait.png voor
    Instagram?"

    The old name, `ontwerp-6-v1-print_a-a4.pdf`, said our table and our
    layout code. A finished poster leaves the application — it is mailed and
    filed next to twenty others — so it carries the activity's name and the
    shape of the thing.

    Broken on purpose to check this can go red: the slug back to
    `ontwerp-{design.id}` → the first assert names the file it found.
    """
    from app.domains.media.api import MediaAsset

    activity.name = "Bowlen"
    db_session.flush()
    version = make_version(db_session, design)
    names = sorted(db_session.query(MediaAsset.title)
                   .filter(MediaAsset.id.in_([r.media_asset_id for r in version.renditions]))
                   .all())
    assert [n for (n,) in names] == [
        "bowlen-v1-a3.pdf", "bowlen-v1-a3.png", "bowlen-v1-a3.svg",
        "bowlen-v1-a4.pdf", "bowlen-v1-portrait.png", "bowlen-v1-portrait.svg",
    ]


def test_the_file_name_survives_accents_punctuation_and_a_nameless_activity():
    """The slug is a file name, so it may not carry an accent, a slash or a
    space — and an activity without a usable name keeps the fallback."""
    from app.domains.designstudio.api import file_slug

    assert file_slug("Bowlen", "x") == "bowlen"
    assert file_slug("Café & Koffie: 't ontbijt", "x") == "cafe-koffie-t-ontbijt"
    assert file_slug("Stappen en Klappen", "x") == "stappen-en-klappen"
    assert file_slug("", "ontwerp-6") == "ontwerp-6"
    assert file_slug("!!! ???", "ontwerp-6") == "ontwerp-6"
    long = file_slug("Een titel die veel te lang is om nog in een bestandsnaam te passen", "x")
    assert len(long) <= 40 and not long.endswith("-")


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

    monkeypatch.setattr(settings, "designstudio_ai_images_enabled", False)
    monkeypatch.setattr(settings, "bfl_api_key", "test-key")
    with pytest.raises(ImagingError, match="kill switch"):
        request_images(db_session, design, "two people walking a forest path")
    monkeypatch.setattr(settings, "designstudio_ai_images_enabled", True)
    monkeypatch.setattr(settings, "bfl_api_key", None)  # switch on, no key: still off
    with pytest.raises(ImagingError, match="kill switch"):
        request_images(db_session, design, "two people walking a forest path")
    monkeypatch.setattr(settings, "bfl_api_key", "test-key")
    monkeypatch.setattr(settings, "designstudio_ai_monthly_budget_eur", 0.10)
    with pytest.raises(ImagingError, match="maandbudget"):
        request_images(db_session, design, "two people walking a forest path")
    assert db_session.query(ImageGeneration).count() == 0
    assert db_session.query(KernelJob).filter(KernelJob.name == "designstudio.generate").count() == 0


def test_one_click_reserves_four_variants_and_queues_four_jobs(monkeypatch, db_session, design):
    from app.domains.designstudio.api import request_images

    monkeypatch.setattr(settings, "designstudio_ai_images_enabled", True)
    monkeypatch.setattr(settings, "bfl_api_key", "test-key")
    monkeypatch.setattr(settings, "designstudio_ai_monthly_budget_eur", 50.0)
    with pytest.raises(ImagingError, match="minstens"):
        request_images(db_session, design, "kids")
    key = request_images(db_session, design, "two adults and two children walking a forest path",
                         requested_by="bestuur@example.com")
    rows = db_session.query(ImageGeneration).filter(ImageGeneration.request_key == key).all()
    assert len(rows) == 4 and all(r.status == "requested" and r.reserved_cents > 0 for r in rows)
    assert all(r.scene.startswith("two adults") and r.style == "lijn" for r in rows)
    jobs = db_session.query(KernelJob).filter(KernelJob.name == "designstudio.generate").all()
    assert len(jobs) == 4 and all(j.payload["prompt"].endswith(imaging.STYLE_SUFFIX) for j in jobs)
    # The reservation counts against the next click.
    from app.domains.designstudio.api import budget

    assert budget(db_session).reserved_eur == Decimal(rows[0].reserved_cents * 4) / 100


def test_a_second_click_while_the_first_runs_is_refused(monkeypatch, db_session, design):
    """Four rows and four jobs, not eight: the reservation guards the budget,
    this guards the click."""
    from app.domains.designstudio.api import request_images

    monkeypatch.setattr(settings, "designstudio_ai_images_enabled", True)
    monkeypatch.setattr(settings, "bfl_api_key", "test-key")
    monkeypatch.setattr(settings, "designstudio_ai_monthly_budget_eur", 50.0)
    request_images(db_session, design, "two adults and two children walking a forest path")
    with pytest.raises(DesignError, match="loopt al"):
        request_images(db_session, design, "two adults and two children walking a forest path")
    assert db_session.query(ImageGeneration).count() == 4


def test_design_text_that_shadows_a_fact_is_named_not_blocked(db_session, design, activity):
    from app.domains.designstudio.api import warnings_for

    activity.description = "Samen wandelen."
    db_session.flush()
    facts = facts_for(db_session, design)
    assert warnings_for(design, facts) == []
    design.explanation_md = "Eigen tekst."
    assert any("wijkt af" in w for w in warnings_for(design, facts))
    assert check_design(db_session, design)["print_a"] == []  # a warning is not a violation


def test_omschrijving_anders_stores_nothing_when_it_equals_the_activity_description(db_session, design, activity):
    """The field shows the activity's description; unchanged means "use the
    activity's", stored as NULL so it stays live (Koen, 19 September 2026)."""
    activity.description = "Samen wandelen."
    db_session.flush()
    form = {"duo_code": design.duo_code, "preset": design.preset, "explanation_md": "Samen wandelen."}
    save_design(db_session, design, form, highlights=[], logo_ids=[])
    assert design.explanation_md is None
    form["explanation_md"] = "Samen wandelen, en nadien iets drinken."
    save_design(db_session, design, form, highlights=[], logo_ids=[])
    assert design.explanation_md == "Samen wandelen, en nadien iets drinken."
    form["explanation_md"] = ""
    save_design(db_session, design, form, highlights=[], logo_ids=[])
    assert design.explanation_md is None


def test_an_emptied_description_field_stays_empty_on_the_screen(client, db_session, design, activity):
    """Koen, 21 September 2026: "ik maakte Omschrijving anders leeg en drukte
    op Bewaren en voorbeeld vernieuwen. De Omschrijving anders is niet leeg."

    It was not a save that failed: the field used to be filled with the
    activity's description whenever nothing of its own was stored, so
    emptying it put that text straight back and the screen looked unchanged.
    The activity's text is a hint in the empty field now, so what the poster
    prints is still visible while the field itself says what it holds.

    Broken on purpose to check this can go red: the view-model back on
    `design.explanation_md or facts["description"]` → the textarea carries
    the activity's text as its value again and the second assert fails.
    """
    from app.domains.auth.api import csrf_token_for

    activity.description = "Samen bowlen met het hele gezin."
    design.explanation_md = "Een eigen tekst voor op de affiche."
    db_session.flush()
    db_session.commit()

    sess = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, sess)
    data = {"duo_code": design.duo_code, "preset": design.preset, "layout": "print_a",
            "explanation_md": ""}
    page = client.post(f"/admin/ontwerpen/{design.id}", data=data,
                       headers={"X-CSRF-Token": csrf_token_for(sess)})
    assert page.status_code == 200
    field = re.search(r'<textarea[^>]*name="explanation_md"[^>]*>(.*?)</textarea>', page.text, re.S)
    assert field is not None and field.group(1).strip() == ""
    # The activity's description is still in sight, as a hint, and still on
    # the poster.
    assert "Samen bowlen met het hele gezin." in page.text
    db_session.refresh(design)
    assert design.explanation_md is None
    assert content_for(db_session, design).explanation_md == "Samen bowlen met het hele gezin."


def test_members_only_reaches_the_poster(db_session, design, activity):
    activity.members_only = True
    db_session.flush()
    facts = facts_for(db_session, design)
    assert facts["members_only"] is True
    assert "ENKEL LEDEN" in render.merge(content_for(db_session, design, facts), layout="print_a").svg


@needs_inkscape
def test_an_uploaded_svg_survives_media_cleaning_replaces_the_merge_and_ages_with_the_facts(db_session, design, activity):
    """Download → edit → upload: media cleans the file (#1011, one allowlist);
    what a poster needs — text, layers, photos, filters — must come back,
    and the edited file then counts for that layout."""
    from app.domains.designstudio.api import edited_svg_for, upload_edited_svg
    from app.domains.designstudio.service import merged_for

    svg = merged_for(db_session, design, "print_a", facts=facts_for(db_session, design)).svg
    edited = svg.replace("SAMEN WANDELEN", "HANDMATIG BEWERKT")
    assert upload_edited_svg(db_session, design, "print_a", edited.encode()) == []
    stored = merged_for(db_session, design, "print_a").svg
    for kept in ("HANDMATIG BEWERKT", "feTurbulence", "<pattern", "data:image/png", "inkscape:label", "t-title-0"):
        assert kept in stored, kept
    assert stored.count("<text") == svg.count("<text")
    scripted = edited.replace("</svg>", "<script>alert(1)</script></svg>")
    upload_edited_svg(db_session, design, "print_a", scripted.encode())
    assert "<script" not in merged_for(db_session, design, "print_a").svg
    row = edited_svg_for(db_session, design, "print_a")
    assert row is not None and row.facts_fingerprint == fingerprint(facts_for(db_session, design))
    activity.location = "Kerkplein"
    db_session.flush()
    assert row.facts_fingerprint != fingerprint(facts_for(db_session, design))  # stale until re-uploaded
    with pytest.raises(DesignError, match="paginaformaat"):
        upload_edited_svg(db_session, design, "feed_portrait", edited.encode())


@needs_inkscape
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


def test_a_redo_on_a_variant_carries_the_change_and_the_style(monkeypatch, db_session, design):
    """"Wat wil je anders?": the new prompt keeps the scene, names the change
    and the chosen style; the reference image goes with the job."""
    from app.domains.designstudio.api import request_images

    monkeypatch.setattr(settings, "designstudio_ai_images_enabled", True)
    monkeypatch.setattr(settings, "bfl_api_key", "test-key")
    monkeypatch.setattr(settings, "designstudio_ai_monthly_budget_eur", 50.0)
    request_images(db_session, design, "a family on bicycles along a country road", style="kleur",
                   change="add a dog running along", reference_asset_id=design.main_image_id)
    job = db_session.query(KernelJob).filter(KernelJob.name == "designstudio.generate").first()
    assert job.payload["reference_asset_id"] == design.main_image_id
    assert "change only this: add a dog running along" in job.payload["prompt"]
    assert "flat colours" in job.payload["prompt"] and "no shading" in job.payload["prompt"]
    with pytest.raises(ImagingError, match="stijl"):
        imaging.build_prompt("a family on bicycles", style="olie")


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


def test_a_refused_save_shows_what_was_typed(client, db_session, design):
    """Round 5: a wrong icon in one row must not cost the other rows and the
    subtitle the person just typed."""
    from app.domains.auth.api import csrf_token_for

    sess = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, sess)
    data = {"duo_code": design.duo_code, "preset": "beeld", "subtitle": "net getypt", "layout": "print_a",
            "hl_icon_0": "users", "hl_text_0": "Eerste kernpunt net getypt", "hl_icon_1": "no-such-icon", "hl_text_1": "Fout"}
    page = client.post(f"/admin/ontwerpen/{design.id}", data=data, headers={"X-CSRF-Token": csrf_token_for(sess)})
    assert page.status_code == 200 and "Onbekend icoon" in page.text
    assert 'value="net getypt"' in page.text and 'value="Eerste kernpunt net getypt"' in page.text
    db_session.refresh(design)
    assert design.subtitle == "samen wandelen"  # nothing saved


def test_the_list_and_the_editor_render_for_an_admin(client, db_session, design):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get("/admin/ontwerpen")
    assert page.status_code == 200 and "Stappen en Klappen" in page.text
    editor = client.get(f"/admin/ontwerpen/{design.id}")
    assert editor.status_code == 200
    assert "Miloheem" in editor.text and 'name="hl_text_0"' in editor.text
    variants = client.get(f"/admin/ontwerpen/{design.id}/varianten", headers={"X-Raak-Filter": "1"})
    assert variants.status_code == 200 and 'id="ds-varianten"' in variants.text and "hx-trigger" not in variants.text
    svg = client.get(f"/admin/ontwerpen/{design.id}/svg/print_a")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")
    assert "STAPPEN" in svg.text and "ref100mm" in svg.text


def test_annuleren_brengt_de_bewaarde_waarde_terug(client, db_session, design):
    """#1089: the cancel button had no destination and did nothing.

    The behaviour, not the button: type something, follow "Annuleren", and the
    screen shows what is saved again — not what was typed.
    """
    import re as _re

    from app.domains.auth.api import csrf_token_for

    sess = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, sess)
    data = {"duo_code": design.duo_code, "preset": "beeld", "subtitle": "net getypt",
            "layout": "print_a", "hl_icon_0": "no-such-icon", "hl_text_0": "Fout"}
    typed = client.post(f"/admin/ontwerpen/{design.id}", data=data,
                        headers={"X-CSRF-Token": csrf_token_for(sess)})
    assert 'value="net getypt"' in typed.text

    hrefs = _re.findall(r'href="([^"]+)"[^>]*>\s*Annuleren', typed.text)
    assert hrefs, "Annuleren heeft geen bestemming — hij doet dan niets (#1089)"
    back = client.get(hrefs[0])
    assert back.status_code == 200
    assert 'value="samen wandelen"' in back.text and "net getypt" not in back.text
