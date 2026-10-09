"""E2E: the newsletter with its choices on the page and Raakje in the Assistent's panel (#1562, PR 2).

Decision 10 (Koen, 4 October 2026), rows 9–11 and 41. In a real browser, because
it is the page that takes a proposal:

- the letter's choices stand on the page in three groups with their counts; a
  chip takes an activity out, the picker puts one in, and the count follows
  without a page load;
- beside a draft the panel is the conversation with Raakje about that letter: the
  turns the draft keeps are loaded when it opens;
- an open proposal marks the fields it touches — Onderwerp, Voorbeeldtekst,
  Inhoud — with "Voorstel · nog niet toegepast";
- Toepassen fills all three in the form (the text through the editor, so undo
  works); a marked passage stays out unless "klopt, behouden" is ticked, which it
  is not by default; the page's own autosave stores the result;
- Negeren takes the marks away and the draft remembers it;
- "Kalender invoegen" places the calendar group; the preview text is a growing
  field with a limit of 200.

The e2e backend has no model key, so the proposal is seeded as the draft keeps
it (`DraftingMessage.proposal`, the shape `drafting.build_proposal` writes);
everything from there on — the conversation, Toepassen, the form — is real.
"""

import os
import sys
from datetime import date, timedelta

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    htmx_afgerond,
    htmx_stil,
    login_met_sessie,
    pagina_klaar,
)

BODY = "<div>Beste,</div>"
SENTENCE = "Er is een zaklopen-wedstrijd."
TEXT = f"Kom naar de wandeling.\n{SENTENCE}"
SUBJECT = "Het najaar in het dorp"
PREVIEW = "Ontdek wat er dit najaar te beleven valt."


def _seed() -> dict:
    """Four coming activities and three drafts, each with one open proposal for a
    whole letter that has one unsupported sentence."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.newsletter import api as nb
    from app.domains.newsletter.drafting import nb_snapshot
    from app.domains.newsletter.models import DraftingMessage, MessageRole, Newsletter
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db = SessionLocal()
    try:
        made = db.query(Newsletter).filter(Newsletter.subject.like("Paneelbrief%")).all()
        if len(made) == 3:
            return {"letters": sorted(letter.id for letter in made)}
        for n in range(1, 5):
            activity = Activity(name=f"Paneelwandeling {n}", location="Dorpsplein")
            db.add(activity)
            db.flush()
            db.add(
                ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=n))
            )
        db.commit()
        letters = []
        for n in (1, 2, 3):
            letter = nb.create_newsletter(db, created_by=SEEDED_ADMIN_EMAIL)
            nb.update_draft(db, letter, subject=f"Paneelbrief {n}", body_html=BODY, audience=None)
            db.add(
                DraftingMessage(
                    newsletter_id=letter.id, role=MessageRole.AUTHOR, text="Schrijf de brief."
                )
            )
            db.add(
                DraftingMessage(
                    newsletter_id=letter.id,
                    role=MessageRole.RAAKJE,
                    text="Voorstel klaar.",
                    proposal={
                        "kind": "letter",
                        "subject": SUBJECT,
                        "preview": PREVIEW,
                        "base_subject": letter.subject,
                        "base_preview": "",
                        "operations": [{"op": "letter", "index": 0, "text": TEXT}],
                        "marks": [
                            {
                                "id": 1,
                                "index": 0,
                                "quote": "zaklopen",
                                "sentence": SENTENCE,
                                "reason": "staat in geen enkele bron",
                            }
                        ],
                        "facts": [],
                        "snapshot": nb_snapshot(letter.body_html),
                        "names": {},
                        "status": "open",
                    },
                )
            )
            db.commit()
            letters.append(letter.id)
        return {"letters": letters}
    finally:
        db.close()


def _clean_up() -> None:
    """Take the seeded activities and drafts out again: the e2e tests share their
    database, and four published activities in the coming days would be the first
    cards of every public list another test measures (#1241)."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.activities.api import Activity
    from app.domains.newsletter.models import Newsletter

    db = SessionLocal()
    try:
        for letter in db.query(Newsletter).filter(Newsletter.created_by.isnot(None)).all():
            if letter.id in set(_SEEDED):
                db.delete(letter)
        db.commit()
        for activity in db.query(Activity).filter(Activity.name.like("Paneelwandeling %")).all():
            service.delete_activity(db, activity.id)
        db.commit()
    finally:
        db.close()


#: The ids of the drafts this module made, for `_clean_up`.
_SEEDED: list[int] = []


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    data = _seed()
    _SEEDED[:] = data["letters"]
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), data
        b.close()
    _clean_up()


def _page(setup, letter: int, width: int = 1920):
    b, session, data = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 1000})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, session, BASE)
    page.goto(f"/admin/nieuwsbrieven/{data['letters'][letter]}")
    pagina_klaar(page)
    page.wait_for_function(
        "document.getElementById('nb-trix') && document.getElementById('nb-trix').editor"
    )
    return page


def _open_panel(page):
    trigger = page.locator("[data-raakje-trigger]")
    trigger.wait_for(state="visible")
    if page.locator(".raakje-panel").is_hidden():
        trigger.click()
    page.locator(".raakje-panel [data-context-key]").wait_for(state="visible")
    page.locator(".raakje-panel [data-newsletter-turn]").first.wait_for()
    htmx_stil(page)


def _stored(letter_id: int) -> dict:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.newsletter.models import DraftingMessage, Newsletter

    db = SessionLocal()
    try:
        letter = db.get(Newsletter, letter_id)
        message = (
            db.query(DraftingMessage)
            .filter(
                DraftingMessage.newsletter_id == letter_id, DraftingMessage.proposal.isnot(None)
            )
            .one()
        )
        return {
            "subject": letter.subject,
            "preview": letter.preview_text,
            "body": letter.body_html,
            "status": message.proposal["status"],
        }
    finally:
        db.close()


_GROUPS = """() => [...document.querySelectorAll('[data-choice-group]')].map(g => ({
  key: g.dataset.choiceGroup, title: g.querySelector('[data-choice-title]').innerText,
  count: g.querySelector('[data-choice-count]').innerText, chips: g.querySelectorAll('[data-choice]').length,
  add: !!g.querySelector('[data-choice-add]')}))"""

_FIELDS = """() => ['subject', 'preview_text', 'body_html'].map(name => { const f = document.querySelector(`[data-field="${name}"]`);
  const note = f.querySelector('[data-proposal-note]');
  return {name, proposed: f.hasAttribute('data-proposed'), applied: f.hasAttribute('data-proposal-applied'), note: note ? note.innerText : ''}; })"""

TEXT_OF = "() => document.getElementById('nb-trix').editor.getDocument().toString()"


# ── The choices on the page ──────────────────────────────────────────────────


def test_the_three_groups_stand_on_the_page_and_a_choice_follows_without_a_page_load(setup):
    page = _page(setup, 0)
    groups = page.evaluate(_GROUPS)
    print("MEASURE newsletter groups", groups)
    assert [g["title"] for g in groups] == ["Voorbije activiteiten", "Uitgelicht", "In de kalender"]
    featured, calendar = groups[1], groups[2]
    assert featured["count"] == "(3)" and featured["chips"] == 3 and not featured["add"], (
        "three are featured: no fourth to add"
    )
    assert calendar["chips"] >= 4 and calendar["count"] == f"({calendar['chips']})"
    assert page.locator("#nb-raakje").count() == 0, "no column of Raakje on the page"
    above = page.evaluate(
        "document.getElementById('nb-keuzes').getBoundingClientRect().bottom <= document.getElementById('nb-formulier').getBoundingClientRect().top"
    )
    assert above

    loads = []
    page.on("load", lambda _p: loads.append(1))
    first = page.locator('[data-choice-group="featured"] [data-choice]').first
    name = first.inner_text().strip()
    with htmx_afgerond(page):
        first.click()
    after = page.evaluate(_GROUPS)[1]
    assert after["count"] == "(2)" and after["chips"] == 2 and after["add"]
    assert loads == [], "the groups alone were swapped"

    # put it back through the picker under the group
    with htmx_afgerond(page):
        page.click('[data-choice-group="featured"] [data-choice-add]')
    row = page.locator('[data-picker="featured"] div.flex').filter(has_text=name).first
    with htmx_afgerond(page):
        row.get_by_role("button", name="Kiezen").click()
    assert page.evaluate(_GROUPS)[1]["count"] == "(3)"
    assert page.errors == []
    page.close()


def test_kalender_invoegen_places_the_calendar_group(setup):
    page = _page(setup, 0)
    expected = page.locator('[data-choice-group="calendar"] [data-choice]').count()
    page.locator("#nb-trix").click()
    with page.expect_response(lambda r: "/invoegen/kalender" in r.url):
        page.get_by_role("button", name="Kalender invoegen").click()
    page.wait_for_function(
        "document.getElementById('nb-trix').editor.getDocument().toString().includes('Paneelwandeling 1')"
    )
    lines = page.evaluate("document.querySelectorAll('#nb-trix li').length")
    assert lines == expected, "one line per activity of the calendar group"
    assert page.locator("[data-picker]").count() == 0, "no second choice in a picker"
    page.close()


def test_the_preview_text_grows_and_stops_at_200(setup):
    page = _page(setup, 0)
    field = page.locator("#nb-voorbeeldtekst")
    one_line = field.bounding_box()["height"]
    field.fill("Een voorbeeldtekst die lang genoeg is om over meer dan één regel te lopen. " * 4)
    value = field.input_value()
    assert len(value) == 200, "the field's own limit"
    grown = field.bounding_box()["height"]
    print("MEASURE preview field", one_line, grown)
    assert grown > one_line, "a growing field: nothing is cut off"
    assert page.locator("[data-preview-count]").inner_text() == "200 / 200"
    page.close()


# ── The conversation in the panel ────────────────────────────────────────────


def test_beside_a_draft_the_panel_is_the_conversation_about_that_letter(setup):
    """Proven red by leaving the newsletter branch out of `context_for`: the
    trigger is dimmed and the panel says "Raakje kent deze gegevens nog niet"."""
    page = _page(setup, 0)
    _open_panel(page)
    panel = page.locator(".raakje-panel")
    assert (
        panel.locator("[data-panel-context]").inner_text() == "over de nieuwsbrief “Paneelbrief 1”"
    )
    talk = panel.locator("[data-panel-conversation]").inner_text()
    assert talk.index("Schrijf de brief.") < talk.index("Voorstel klaar."), (
        "the turns the draft keeps"
    )
    block = panel.locator("[data-form-proposal]")
    assert block.locator("[data-proposal-summary]").inner_text() == "3 velden ingevuld als voorstel"
    assert (
        block.locator("[data-proposal-labels]").inner_text()
        == "Onderwerp · Voorbeeldtekst · Inhoud"
    )
    assert SENTENCE in block.locator("[data-proposal-mark]").inner_text()
    assert not block.locator('input[name="keep"]').is_checked(), "kept only when ticked"

    fields = page.evaluate(_FIELDS)
    print("MEASURE newsletter proposal offered", fields)
    assert all(f["proposed"] and f["note"] == "Voorstel · nog niet toegepast" for f in fields)
    assert page.locator("#nb-onderwerp").input_value() == "Paneelbrief 1", "offered is not filled"
    assert page.errors == []
    page.close()


def test_toepassen_fills_subject_preview_and_text_and_leaves_the_marked_sentence_out(setup):
    """Proven red by ticking nothing and dropping the keep filter from the
    apply: the unsupported sentence lands in the letter."""
    b, _s, data = setup
    letter = data["letters"][0]
    page = _page(setup, 0)
    _open_panel(page)
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    page.locator(".raakje-panel [data-proposal-apply]").click()
    page.wait_for_function("document.getElementById('nb-onderwerp').value !== 'Paneelbrief 1'")
    htmx_stil(page)

    assert page.locator("#nb-onderwerp").input_value() == SUBJECT
    assert page.locator("#nb-voorbeeldtekst").input_value() == PREVIEW
    assert page.locator("[data-preview-count]").inner_text() == f"{len(PREVIEW)} / 200", (
        "the counter heard the change"
    )
    text = page.evaluate(TEXT_OF)
    assert "Kom naar de wandeling." in text and "zaklopen" not in text
    fields = page.evaluate(_FIELDS)
    assert all(f["applied"] and f["note"] == "Ingevuld door Assistent" for f in fields), fields
    result = page.locator(".raakje-panel [data-proposal-result]").last
    expect(result).to_have_text("3 velden ingevuld.")
    assert any(u.endswith("/toepassen") for u in posts)

    # the page's own autosave stores what the form took
    page.wait_for_function(
        "document.getElementById('nb-bewaard').innerText.trim().length > 0", timeout=10_000
    )
    page.locator("#nb-onderwerp").blur()
    expect(page.locator("#nb-bewaard")).to_contain_text("ewaard", timeout=10_000)
    stored = _stored(letter)
    assert stored["status"] == "applied"
    assert stored["subject"] == SUBJECT and stored["preview"] == PREVIEW
    assert "Kom naar de wandeling." in stored["body"] and "zaklopen" not in stored["body"]

    # undo takes the text back: it went in through the editor
    page.evaluate("document.getElementById('nb-trix').editor.undo()")
    assert "Kom naar de wandeling." not in page.evaluate(TEXT_OF)
    assert page.errors == []
    page.close()


def test_a_ticked_passage_is_kept_and_an_applied_proposal_offers_nothing(setup):
    b, _s, data = setup
    letter = data["letters"][1]
    page = _page(setup, 1)
    _open_panel(page)
    block = page.locator(".raakje-panel [data-form-proposal]")
    if _stored(letter)["status"] == "open":
        block.locator('input[name="keep"]').check()
        block.locator("[data-proposal-apply]").click()
        page.wait_for_function(
            "document.getElementById('nb-trix').editor.getDocument().toString().includes('zaklopen')"
        )
    assert "zaklopen" in page.evaluate(TEXT_OF), "ticked: the sentence stays"
    assert _stored(letter)["status"] == "applied"
    page.close()

    # a reload: the applied proposal offers nothing any more
    again = _page(setup, 1)
    _open_panel(again)
    closed = again.locator(".raakje-panel [data-form-proposal]")
    assert closed.locator("[data-proposal-apply]").count() == 0
    assert "Toegepast." in closed.locator("[data-proposal-result]").inner_text()
    assert not any(f["proposed"] for f in again.evaluate(_FIELDS)), (
        "a closed proposal marks nothing"
    )
    again.close()


def test_negeren_takes_the_marks_away_and_the_draft_remembers_it(setup):
    b, _s, data = setup
    letter = data["letters"][2]
    page = _page(setup, 2)
    _open_panel(page)
    block = page.locator(".raakje-panel [data-form-proposal]")
    if _stored(letter)["status"] == "open":
        assert any(f["proposed"] for f in page.evaluate(_FIELDS))
        with page.expect_response(lambda r: r.url.endswith("/weigeren")) as answer:
            block.locator("[data-proposal-dismiss]").click()
        assert answer.value.status == 204
    assert not any(f["proposed"] or f["applied"] for f in page.evaluate(_FIELDS))
    assert page.locator("#nb-onderwerp").input_value() == "Paneelbrief 3", "nothing was filled"
    assert "Beste," in page.evaluate(TEXT_OF)
    assert _stored(letter)["status"] == "dismissed"
    page.close()

    again = _page(setup, 2)
    _open_panel(again)
    result = again.locator(".raakje-panel [data-form-proposal] [data-proposal-result]")
    assert "Voorstel genegeerd." in result.inner_text()
    again.close()
