"""E2E: Abonnees, Wijzigingen and AI-kosten on the kit's list page (#2109; end state §5.1).

Walked in the browser: per list the segment, the search and one filter narrow the
rows; "+ Adres" opens its page and the address lands on the list; the member
export downloads from the toolbar's ⋯; the month arrows of AI-kosten move the
calls. At 390 and 1 280 px no list scrolls sideways. When `E2E_PRINT_DIR` is
set a print of every list at both widths is taken (looked at by whoever hands
the work over).

Broken on purpose (18 October 2026, each put back): `status=` dropped from the
subscribers' `list_subscribers` call → the segment test is red; the `with_state`
of the export's menu item taken out → the download test is red; `capability=`
dropped from AI-kosten's `list_calls` call → the Onderdeel filter is red.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar, refusal_shown  # noqa: E402

ACTOR = "lijsten2109@example.com"


@pytest.fixture(scope="module")
def world():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.chatbot.api import sink_for
    from app.domains.mdm.api import Person, snapshot_person
    from app.domains.newsletter.models import Subscriber, SubscriberSource, SubscriberStatus
    from app.kernel.tenancy import DEFAULT_TENANT_ID
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    subscriber_ids, person_ids = [], []
    try:
        for name, status in (
            ("bevestigd", SubscriberStatus.CONFIRMED),
            ("wachtend", SubscriberStatus.PENDING),
            ("weg", SubscriberStatus.UNSUBSCRIBED),
        ):
            row = Subscriber(
                email=f"{name}-{tag}@example.com",
                first_name=name.capitalize(),
                status=status,
                source=SubscriberSource.ADMIN,
                unsubscribe_token=secrets.token_hex(16),
            )
            db.add(row)
            db.flush()
            subscriber_ids.append(row.id)
        for i in range(2):
            person = Person(first_name=f"Lijst{i}{tag}", last_name="Wijziging")
            db.add(person)
            db.flush()
            person_ids.append(person.id)
            snapshot_person(
                db,
                person,
                operation="insert",
                action="person_created",
                source="test",
                actor=ACTOR,
            )
        db.commit()
    finally:
        db.close()
    for capability, provider, model in (
        ("reporting", "mistral", f"rapport-{tag}"),
        ("image", "bfl", f"beeld-{tag}"),
    ):
        sink_for(ACTOR)(
            surface="admin",
            capability=capability,
            model=model,
            payload="geen",
            provider=provider,
            endpoint="chat.completions",
            duration_ms=900,
            usage={"prompt": 10, "completion": 2},
            tenant_id=DEFAULT_TENANT_ID,
        )
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield {"browser": browser, "tag": tag, "session": make_session_value(SEEDED_ADMIN_EMAIL)}
        browser.close()
    from sqlalchemy import text as sql_text

    db = SessionLocal()
    try:
        db.query(Subscriber).filter(
            (Subscriber.id.in_(subscriber_ids)) | (Subscriber.email.like(f"%-{tag}@example.com"))
        ).delete(synchronize_session=False)
        db.execute(sql_text("DELETE FROM ai.ai_call_log WHERE actor = :a"), {"a": ACTOR})
        db.commit()
    finally:
        db.close()


def _open(world, path, width=1280):
    page = world["browser"].new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, world["session"])
    page.goto(path)
    pagina_klaar(page)
    return page


def _print(page, name, width):
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": width, "height": max(900, min(height, 3000))})
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=os.path.join(folder, f"{name}-{width}.png"), caret="initial")


@pytest.mark.parametrize(
    "path",
    [
        "/admin/nieuwsbrieven/abonnees",
        "/admin/ledenwijzigingen?since=2000-01-01",
        "/admin/info/ai-kosten",
    ],
)
@pytest.mark.parametrize("width", [390, 1280])
def test_no_list_scrolls_sideways(world, path, width):
    page = _open(world, path, width)
    try:
        scroll = page.evaluate("document.documentElement.scrollWidth")
        frame = page.locator("[data-table-frame]").first.bounding_box()
        print(
            f"MEASURE {path} {width}: page {scroll}, frame {frame['x']:.0f}..{frame['x'] + frame['width']:.0f}"
        )
        if scroll != width:
            wide = page.evaluate(
                """(w) => [...document.querySelectorAll('body *')]
                    .filter(e => e.getBoundingClientRect().right > w + 1)
                    .slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 60)
                      + ' ' + Math.round(e.getBoundingClientRect().right))""",
                width,
            )
            print("WIDE", wide)
            print(
                "OVER",
                page.evaluate(
                    """() => [...document.querySelectorAll('body, body *')]
                    .filter(e => e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0)
                    .slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 50)
                      + ' ' + e.scrollWidth + '>' + e.clientWidth)"""
                ),
            )
        assert scroll == width, "the page scrolls sideways"
        assert frame["x"] + frame["width"] <= width + 1
        name = {"/admin/nieuwsbrieven/abonnees": "abonnees"}.get(
            path, "wijzigingen" if "wijzigingen" in path else "ai-kosten"
        )
        _print(page, name, width)
    finally:
        page.close()


def test_the_subscribers_segment_the_search_and_the_add_page(world):
    tag = world["tag"]
    page = _open(world, "/admin/nieuwsbrieven/abonnees")
    try:
        rows = page.locator("[data-subscriber-row]")
        expect(rows.filter(has_text=f"wachtend-{tag}")).to_have_count(1)
        page.locator("[data-status-filter] label", has_text="Wachten").click()
        expect(rows.filter(has_text=f"wachtend-{tag}")).to_have_count(1)
        expect(rows.filter(has_text=f"bevestigd-{tag}")).to_have_count(0)
        page.locator("[data-status-filter] label", has_text="Alle").click()
        page.fill("[data-toolbar-search] input", f"weg-{tag}")
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text(f"weg-{tag}")
        page.fill("[data-toolbar-search] input", "")
        # "+ Adres": the page of its own; a refusal stays on it, a success lands on the list.
        page.get_by_role("link", name="Adres", exact=True).click()
        page.wait_for_url("**/abonnees/nieuw")
        pagina_klaar(page)
        page.fill("#nb-nieuw-adres", f"bevestigd-{tag}@example.com")
        page.get_by_role("button", name="Toevoegen").first.click()
        refusal_shown(page)
        expect(page.locator("[data-save-refusal]")).to_contain_text("staat al op de lijst")
        page.fill("#nb-nieuw-adres", f"nieuw-{tag}@example.com")
        page.get_by_role("button", name="Toevoegen").first.click()
        page.wait_for_url("**/nieuwsbrieven/abonnees?toegevoegd=*")
        pagina_klaar(page)
        expect(page.locator("[data-subscriber-row]", has_text=f"nieuw-{tag}")).to_have_count(1)
        expect(page.locator("body")).to_contain_text("staat op de lijst")
    finally:
        page.close()


def test_the_changes_segment_the_actor_the_date_and_the_member_export(world):
    tag = world["tag"]
    page = _open(world, "/admin/ledenwijzigingen")
    try:
        rows = page.locator("[data-change]", has_text=f"Lijst0{tag}")
        expect(rows).to_have_count(1)
        page.locator("[data-status-filter] label", has_text="Activiteiten").click()
        expect(page.locator("[data-change]", has_text=f"Lijst0{tag}")).to_have_count(0)
        page.locator("[data-status-filter] label", has_text="Leden").click()
        expect(page.locator("[data-change]", has_text=f"Lijst0{tag}")).to_have_count(1)
        page.fill("[data-toolbar-search] input", "niemand@example.com")
        expect(page.locator("[data-change]")).to_have_count(0)
        page.fill("[data-toolbar-search] input", ACTOR)
        expect(page.locator("[data-change]", has_text=f"Lijst1{tag}")).to_have_count(1)
        # The date under Filters, then the export from ⋯ carrying that date.
        page.locator("[data-filters-button]").click()
        page.fill("#lw-since", "2020-01-01")
        page.locator("[data-filters-panel]").get_by_role("button", name="Toepassen").click()
        pagina_klaar(page)
        page.locator("[data-more-button]").click()
        with page.expect_download() as info:
            page.locator("[data-more-menu]").get_by_role("menuitem", name="Ledenexport").click()
        download = info.value
        print("MEASURE export:", download.suggested_filename)
        assert "vanaf-2020-01-01" in download.suggested_filename
    finally:
        page.close()


def test_the_ai_costs_filter_by_component_and_provider_and_move_by_month(world):
    tag = world["tag"]
    page = _open(world, "/admin/info/ai-kosten")
    try:
        rows = page.locator("[data-ai-call]")
        expect(rows.filter(has_text=f"rapport-{tag}")).to_have_count(1)
        expect(rows.filter(has_text=f"beeld-{tag}")).to_have_count(1)
        page.locator("[data-filters-button]").click()
        page.select_option("#ai-capability", "image")
        page.locator("[data-filters-panel]").get_by_role("button", name="Toepassen").click()
        expect(rows.filter(has_text=f"beeld-{tag}")).to_have_count(1)
        expect(rows.filter(has_text=f"rapport-{tag}")).to_have_count(0)
        page.locator("[data-filters-button]").click()
        page.select_option("#ai-capability", "")
        page.select_option("#ai-provider", "mistral")
        page.locator("[data-filters-panel]").get_by_role("button", name="Toepassen").click()
        expect(rows.filter(has_text=f"rapport-{tag}")).to_have_count(1)
        expect(rows.filter(has_text=f"beeld-{tag}")).to_have_count(0)
        # The month before has none of these calls — and the totals above follow it.
        page.get_by_role("link", name="‹ Vorige maand").click()
        pagina_klaar(page)
        expect(page.locator("[data-ai-call]", has_text=f"rapport-{tag}")).to_have_count(0)
        expect(page.locator("body")).to_contain_text("Geen AI-oproepen")
    finally:
        page.close()
