"""#677 — een select en een input zijn even hoog.

#659 trok de klassen gelijk (alles via `ui.label` en de control-macro's) en dat
was nodig, maar het hoogteverschil bleef. De oorzaak ligt een laag dieper: beide
controls dragen dezelfde padding, lettergrootte en regelhoogte, maar er stond geen
expliciete HOOGTE. Zonder die bepaalt de browser zelf hoe hoog een `<select>`
wordt — die krijgt intrinsieke ruimte voor zijn pijltje en een eigen
minimumhoogte, een `<input>` niet.

Enkele pixels verschil, en omdat de compacte vormen `items-end` gebruiken zakt het
LABEL boven de kortere kolom mee. Zelfde zichtbare fout als #656, andere oorzaak.

Een rendertest op klassen is hier zwak: de HTML klopte al. Dit meet wat de browser
ervan maakt. Eén meting op de "+ Product"-vorm dekt de hele kit, want de
maatvoering komt uit één gedeelde bron.

#1865: the first test builds the activity it measures — one component with one
product row — and removes it again. It used to open the seed's first activity,
so what it measured depended on the data it met: a product row brings the
segmented choice "Afrekening", whose radio is a visually hidden box of 1 px.

Broken on purpose (9 October 2026), each added and taken away again: the radio
measured again (the `:not([type=radio])` taken off the helper) → "p.N.settlement"
at 1 px beside the fields at 40; a rule added to the page that gives the product's
price field another height → that one field named at its own height.
"""

import os
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Activiteitdetail, controlhoogtes, login_als_admin  # noqa: E402


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, email, make_session_value(email))
        page.goto("/admin/activiteiten")
        if page.locator("main").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


COMPONENT = "#aa-group-components > [data-group-rows] > [data-group-row]"
NAME = "Veldhoogtetest met een product"


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


@pytest.fixture(scope="module")
def activity_with_product():
    """An activity with one component and one product row, made for this file
    and removed again: the e2e tests share their seed."""
    from app.domains.activities import service
    from app.domains.activities.api import Activity, ActivityProduct, ActivitySubRegistration

    db = _db()
    try:
        activity = Activity(name=NAME)
        db.add(activity)
        db.flush()
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name="Etentje",
            registration_type_code="INDIVIDUAL",
            price=0,
            is_free=True,
            sort_order=0,
        )
        db.add(component)
        db.flush()
        db.add(ActivityProduct(component_id=component.id, name="Soep", price=Decimal("5.00")))
        db.commit()
        activity_id = activity.id
    finally:
        db.close()
    yield activity_id
    db = _db()
    try:
        service.delete_activity(db, activity_id, actor="e2e-1865@example.com")
    finally:
        db.close()


def test_input_en_select_zijn_even_hoog(admin_page, activity_with_product):
    """A component in the editor: text, number and date fields and one select
    (the question form) in one grid, and under it a product row with its fields
    and the segmented choice "Afrekening"."""
    admin_page.goto(f"/admin/activiteiten/{activity_with_product}")
    admin_page.wait_for_selector("#aa-detail", timeout=5000)
    Activiteitdetail(admin_page).bewerk()
    expect(admin_page.locator(f"{COMPONENT} select").first).to_be_visible()
    # The case #1865 was about is on the page: the segmented choice and its radios.
    expect(admin_page.locator(f"{COMPONENT} [role=radiogroup]")).to_have_count(1)
    assert admin_page.locator(f"{COMPONENT} input[type=radio]").count() == 3

    hoogtes = controlhoogtes(admin_page, COMPONENT)
    assert any("form_id" in naam for naam in hoogtes), f"geen keuzelijst gemeten: {hoogtes}"
    assert any(naam.endswith(".price") for naam in hoogtes), f"no product field: {hoogtes}"
    assert not any("settlement" in naam for naam in hoogtes), f"a radio was measured: {hoogtes}"

    uniek = set(hoogtes.values())
    assert len(uniek) == 1, (
        "de velden in één vorm zijn niet even hoog — een select krijgt van de "
        f"browser een eigen minimumhoogte als die niet vastligt: {hoogtes}"
    )


def test_datum_en_tijdvelden_lopen_mee(admin_page):
    """`date` en `time` dragen in elke browser hun eigen intrinsieke maat, en ze
    staan op dit scherm direct naast gewone tekstvelden."""
    scherm = Activiteitdetail(admin_page)
    if not scherm.open_eerste():
        _ontbreekt("geen activiteit om te openen")
    scherm.bewerk()
    if scherm.datumregel().count() == 0:
        _ontbreekt("de activiteit heeft geen datumregel")
    expect(scherm.datumregel().locator("input[type=date]").first).to_be_visible()

    hoogtes = controlhoogtes(admin_page, "#aa-group-dates")
    assert any("time" in naam for naam in hoogtes), f"geen tijdveld gemeten: {hoogtes}"
    if len(hoogtes) < 2:
        _ontbreekt("de datumvorm toont geen velden om te meten")
    assert len(set(hoogtes.values())) == 1, (
        f"datum- en tijdvelden lopen niet gelijk met de rest: {hoogtes}"
    )
