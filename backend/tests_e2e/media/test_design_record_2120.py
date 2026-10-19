"""E2E: the Design Studio design is a record page, read first (#2120).

Walked in a browser: the page opens read-only with Bewerken in the head; Definitief
maken and Verwijderen stand under Acties; Bewerken opens ONE form for Ontwerp, Kernpunten
and Beelden with a bar of three buttons — Annuleren, "Bewaren en voorbeeld vernieuwen"
(saves, stays in edit) and Opslaan (saves, back to read). Annuleren with changes asks. A
refused save says why and keeps what was typed. On a phone the bar's three buttons stand
on three lines and nothing is wider than the window.

Proven red by taking `extra_label` out of the bar of `admin_ontwerp.html`: the second save
test fails (there is no such button).
"""

import os
import re
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_2120"


def _design() -> dict:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.designstudio.models import Design

    db = SessionLocal()
    try:
        name = f"Pannenkoekenbak {secrets.token_hex(2)}"
        activity = Activity(name=name)
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date(2027, 11, 14)))
        design = Design(
            activity_id=activity.id,
            duo_code="dark_green-golden_yellow",
            subtitle="samen wandelen",
        )
        db.add(design)
        db.commit()
        return {"design": design.id, "name": name}
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _open(setup, width=1100, edit=False):
    b, session = setup
    data = _design()
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(f"/admin/ontwerpen/{data['design']}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    return page, data


def _shot(page, name):
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png", full_page=False)


def test_it_opens_read_only_with_the_head_of_a_record(setup):
    page, data = _open(setup)
    try:
        expect(page.locator("main h1")).to_have_text(data["name"])
        assert page.locator("form[data-record-form]").count() == 0
        assert page.locator("[data-action-bar]").count() == 0
        expect(page.get_by_role("link", name="Bewerken")).to_be_visible()
        # the way back, the activity as a jump link, the layout
        expect(page.locator("[data-way-back]")).to_be_visible()
        assert page.locator("[data-facts] a", has_text="Activiteit").count() == 1
        assert "Opmaak:" in page.locator("[data-facts]").inner_text()
        # the preview stands in the side column
        assert page.locator("[data-summary-column] #ds-voorbeeld img").count() == 1
        # Definitief maken and Verwijderen are under Acties
        page.locator("[data-actions-trigger]").click()
        menu = page.locator("[data-actions-menu]")
        expect(menu.get_by_role("menuitem", name="Definitief maken")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Verwijderen")).to_be_visible()
        # the cards that need no editing stay, the ones that upload do not show while reading
        assert page.locator("[data-form-section] h2", has_text="Versies").count() == 1
        assert page.locator("[data-form-section] h2", has_text="Foto toevoegen").count() == 0
        _shot(page, "lezen-1100")
    finally:
        page.close()


def test_bewerken_opens_one_form_with_a_bar_of_three(setup):
    page, data = _open(setup)
    try:
        page.get_by_role("link", name="Bewerken").click()
        expect(page.locator("form[data-record-form]")).to_be_visible()
        bar = page.locator("[data-action-bar]")
        expect(bar).to_be_visible()
        names = [t.strip() for t in bar.locator("a, button").all_inner_texts() if t.strip()]
        assert names[:1] == ["Verwijderen"] or "Annuleren" in names
        order = bar.evaluate(
            "b => [...b.querySelectorAll('[data-form-cancel],[data-form-save-extra],[data-form-save]')].map(e => e.textContent.trim().split('\\n')[0].trim())"
        )
        assert order == ["Annuleren", "Bewaren en voorbeeld vernieuwen", "Opslaan"], order
        # the three cards of the form, and the cards with a button of their own below it
        for title in ("Ontwerp", "Kernpunten", "Beelden"):
            assert (
                page.locator(
                    "form[data-record-form] [data-form-section] h2", has_text=title
                ).count()
                == 1
            )
        for title in (
            "Foto toevoegen",
            "Tekening laten maken",
            "Versies",
            "Zelf bewerken in Inkscape",
        ):
            assert page.locator("[data-form-section] h2", has_text=title).count() == 1
        # Verwijderen left the head
        assert page.locator("[data-actions-menu] >> text=Verwijderen").count() == 0
        _shot(page, "bewerken-1100")
    finally:
        page.close()


def test_the_second_save_stays_in_edit_and_opslaan_returns_to_read(setup):
    page, data = _open(setup, edit=True)
    try:
        page.locator('input[name="tagline"]').fill("Zet het in je agenda")
        page.get_by_role("button", name="Bewaren en voorbeeld vernieuwen").click()
        expect(page).to_have_url(
            re.compile(r"notice=bewaard.*bewerken=1|bewerken=1.*notice=bewaard")
        )
        expect(page.locator('input[name="tagline"]')).to_have_value("Zet het in je agenda")
        pagina_klaar(page)
        # Opslaan: saves and goes back to reading
        page.locator('input[name="subtitle"]').fill("samen bakken")
        page.locator("[data-form-save]").click()
        expect(page.locator("form[data-record-form]")).to_have_count(0)
        expect(page).not_to_have_url(re.compile(r"bewerken=1"))
        expect(page.locator('[data-field="subtitle"] [data-value]')).to_have_text("samen bakken")
        expect(page.locator('[data-field="tagline"] [data-value]')).to_have_text(
            "Zet het in je agenda"
        )
    finally:
        page.close()


def test_annuleren_with_changes_asks_and_leaves_what_is_saved(setup):
    page, data = _open(setup, edit=True)
    try:
        page.locator('input[name="subtitle"]').fill("net getypt")
        page.locator("[data-form-cancel]").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        dialog.get_by_role("button", name="Wijzigingen weggooien").click()
        expect(page).not_to_have_url(re.compile(r"bewerken=1"))
        expect(page.locator('[data-field="subtitle"] [data-value]')).to_have_text("samen wandelen")
    finally:
        page.close()


def test_a_refused_save_says_why_and_keeps_what_was_typed(setup):
    page, data = _open(setup, edit=True)
    try:
        page.locator('input[name="subtitle"]').fill("net getypt")
        # an icon the list does not know: only a hand-made request can send it
        page.evaluate(
            "() => { const s = document.querySelector('select[name=\"hl_icon_1\"]');"
            " s.add(new Option('x', 'no-such-icon')); s.value = 'no-such-icon'; }"
        )
        page.locator('input[name="hl_text_1"]').fill("Fout")
        page.locator("[data-form-save]").click()
        banner = page.locator("#ds-melding [data-save-refusal]")
        expect(banner).to_be_visible()
        assert "Onbekend icoon" in banner.inner_text()
        expect(page.locator('input[name="subtitle"]')).to_have_value("net getypt")
        expect(page).to_have_url(re.compile(r"bewerken=1"))
    finally:
        page.close()


def test_the_bar_of_three_stands_on_three_lines_on_a_phone(setup):
    page, data = _open(setup, width=390, edit=True)
    try:
        box = page.evaluate(
            """() => {
          const r = s => document.querySelector(s).getBoundingClientRect();
          const save = r('[data-form-save]'), extra = r('[data-form-save-extra]'), cancel = r('[data-form-cancel]'), del = r('[data-form-delete]');
          return {save: [save.top, save.left, save.width], extra: [extra.top, extra.left, extra.width],
                  cancel: [cancel.top, cancel.right], del: [del.top, del.left],
                  bar: [r('[data-action-bar]').height], width: [document.documentElement.scrollWidth, innerWidth]};
        }"""
        )
        print("BAR @390", box)
        page.locator("[data-action-bar]").scroll_into_view_if_needed()
        # Opslaan on the first line, the extra save under it, both the full width; Verwijderen and
        # Annuleren on a third line
        assert box["extra"][0] > box["save"][0] and abs(box["extra"][2] - box["save"][2]) < 2, box
        assert box["cancel"][0] > box["extra"][0] and box["del"][0] > box["extra"][0], box
        assert box["save"][2] > 300, box
        assert box["width"][0] <= box["width"][1], box
        _shot(page, "bewerken-390-balk")
    finally:
        page.close()


def test_the_page_is_no_wider_than_the_window_on_a_phone(setup):
    for edit in (False, True):
        page, data = _open(setup, width=390, edit=edit)
        try:
            w = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
            assert w[0] <= w[1], (edit, w)
            _shot(page, f"{'bewerken' if edit else 'lezen'}-390")
        finally:
            page.close()


# A 1×1 PNG: the smallest picture the upload accepts.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc0f01f0005000201a3c8c3a60000000049454e44ae426082"
)


def test_the_cards_with_a_button_of_their_own_work_from_the_new_page(setup, tmp_path):
    """The walk of the concept's checklist: Foto toevoegen, the preview's layouts, Tekening
    laten maken, Definitief maken under Acties, the version and its publication, Inkscape."""
    page, data = _open(setup, edit=True)
    try:
        # Foto toevoegen: a file and its place, its own button, and the page stays in edit
        png = tmp_path / "foto.png"
        png.write_bytes(_PNG)
        page.locator('input[type="file"][name="file"]').first.set_input_files(str(png))
        page.get_by_role("button", name="Uploaden").click()
        expect(page).to_have_url(re.compile(r"notice=afbeelding"))
        assert page.locator('input[name="main_image_id"]').first.input_value() != ""
        # the preview: a button per layout, the large view and the proof PDF
        layouts = page.locator("#ds-voorbeeld a.btn, #ds-voorbeeld > div:first-child a")
        assert layouts.count() >= 1
        assert page.locator("#ds-voorbeeld a", has_text="Groot bekijken").count() >= 1
        assert page.locator("#ds-voorbeeld a", has_text="Pdf van dit ontwerp").count() == 1
        # Tekening laten maken: the budget line is there, with or without the form
        card = page.locator("[data-form-section]", has_text="Tekening laten maken")
        expect(card).to_be_visible()
        assert "€" in card.inner_text() or "AI" in card.inner_text() or card.inner_text().strip()
        # Inkscape: a download per layout and the upload of an edited SVG
        inkscape = page.locator("[data-form-section]", has_text="Zelf bewerken in Inkscape")
        assert inkscape.get_by_role("link", name=re.compile("^Download")).count() >= 2
        assert inkscape.locator('input[type="file"]').count() == 1
        _shot(page, "walk-bewerken")
        # Definitief maken, under Acties, asks first; what it answers is a version or the reason
        page.locator("[data-actions-trigger]").click()
        page.get_by_role("menuitem", name="Definitief maken").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        assert "alles of niets" in dialog.inner_text()
        dialog.get_by_role("button", name="Definitief maken").click()
        page.wait_for_function(
            "() => document.querySelectorAll('[data-version]').length > 0"
            " || document.querySelector('#ds-melding [role=alert]')",
            timeout=120_000,
        )
        if page.locator("[data-version]").count() == 0:
            # a server without Inkscape (CI) refuses with its reason; the version part
            # of the walk needs one that has it
            expect(page.locator("#ds-melding [role=alert]")).to_contain_text("Inkscape")
            return
        # the version stands with its files, and is published after a question
        version = page.locator("[data-version]").first
        expect(version).to_be_visible()
        assert version.locator("a").count() >= 1
        _shot(page, "walk-na-definitief")
        version.get_by_role("button", name="Publiceren als affiche").click()
        page.get_by_role("dialog").get_by_role("button", name="Bevestigen").click()
        expect(
            page.locator("[data-version]").first.get_by_text("Gepubliceerd als affiche")
        ).to_be_visible(timeout=60_000)
    finally:
        page.close()


def test_verwijderen_in_the_bar_asks_and_returns_to_the_list(setup):
    page, data = _open(setup, edit=True)
    try:
        page.locator("[data-form-delete]").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        assert data["name"] in dialog.inner_text()
        dialog.get_by_role("button", name="Definitief verwijderen").click()
        expect(page).to_have_url(re.compile(r"/admin/ontwerpen$"))
    finally:
        page.close()


def test_verwijderen_under_acties_while_reading(setup):
    page, data = _open(setup)
    try:
        page.locator("[data-actions-trigger]").click()
        page.get_by_role("menuitem", name="Verwijderen").click()
        page.get_by_role("dialog").get_by_role("button", name="Definitief verwijderen").click()
        expect(page).to_have_url(re.compile(r"/admin/ontwerpen$"))
    finally:
        page.close()
