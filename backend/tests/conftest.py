"""Pytest-fixtures voor de backend-tests.

Draait tegen een echte PostgreSQL (zoals productie), niet tegen SQLite, zodat
de tests dezelfde engine en types gebruiken. De database-URL komt uit
TEST_DATABASE_URL; valt die weg, dan wordt een lokale Postgres verondersteld.

De schema's worden gebouwd via `alembic upgrade head` — daardoor testen de
tests meteen ook de volledige migratieketen. Per test draait alles in een
geneste transactie (SAVEPOINT) die achteraf teruggedraaid wordt, zodat tests
elkaar niet beïnvloeden ondanks de `db.commit()` in de endpoints.
"""

import os

# Moet vóór het importeren van app-modules gezet worden: app.database leest deze
# bij import. We gebruiken een aparte testdatabase.
BASE_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres@localhost:5432/raaktest",
)
# CR-29 F1: under pytest-xdist every worker runs on a database of its own. The name
# is chosen HERE and not in a fixture: `app.database` creates the engine at import,
# a few lines down, and a fixture runs long after that.
from tests._worker_db import fresh_worker_database, worker_database_url  # noqa: E402

TEST_DATABASE_URL = worker_database_url(
    BASE_DATABASE_URL, os.environ.get("PYTEST_XDIST_WORKER", "")
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "test-secret-key-which-is-long-enough-32+")
# Kernel-jobs scheduler niet in tests (#396): run_due_jobs wordt expliciet getest.
os.environ.setdefault("JOBS_ENABLED", "false")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.domains.auth.api import create_access_token
from app.main import app

# Bestaat in de seed-migratie 014; gebruiken we als ingelogde admin. Het is de
# placeholder-default van SEED_ADMIN_EMAILS — echte adressen staan nooit in deze
# publieke repo, ook niet in de tests.
SEEDED_ADMIN_EMAIL = "beheerder@example.com"


# Every domain's `tests/conftest.py` re-exports this fixture (CR-13 R15), and pytest
# keeps one session fixture per conftest that defines it — so without this flag the
# schemas would be dropped and rebuilt once per domain folder.
_SCHEMA_BUILT = False


@pytest.fixture(scope="session", autouse=True)
def _migrate_schema():
    """Bouw de schema's één keer via de echte migratieketen."""
    global _SCHEMA_BUILT
    if _SCHEMA_BUILT:
        yield
        return
    # CR-29 F1: a worker starts on an empty database of its own; without xdist this does nothing.
    fresh_worker_database(BASE_DATABASE_URL, TEST_DATABASE_URL)
    # Schemas hard resetten (v2.0, #398): drop_all kent alleen tabellen die nog
    # in de metadata leven — na verwijderde modellen (ideas) blijven wezen
    # achter en botst de keten. CASCADE veegt álles, ook alembic_version.
    with engine.begin() as conn:
        for schema in (
            "form",
            "workflow",
            "mail",
            "auth",
            "mdm",
            "payment",
            "membership",
            "activities",
            "cms",
            "ai",
            "media",
            "analytics",
            "reporting",
            "meetings",
            "newsletter",
            "designstudio",
            # CR-21 (the webshop, #1748): its four schemas, before the first
            # migration creates one — a schema left out here survives the reset.
            "product",
            "pricing",
            "stock",
            "sales",
            "public",
        ):
            conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
    # #951: eerst de keten lezen, dan pas draaien. Klopt ze niet, dan valt de
    # hele suite om op `MultipleHeads` — en dat leest als "alles is kapot" terwijl
    # het "één regel" is. De melding hoort te staan waar de schade ontstaat, niet
    # in een test die er toch niet meer aan toekomt.
    from tests._migratieketen import melding, problemen

    fouten = problemen()
    if fouten:
        pytest.exit(melding(fouten), returncode=1)

    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    command.upgrade(cfg, "head")
    _SCHEMA_BUILT = True
    yield


def pytest_collection_modifyitems(config, items):
    """`TEST_SHUFFLE=<seed>` runs the suite in a shuffled order (CR-29 F3).

    A test that passes only because of the tests before it is found by running
    the suite in another order; the seed is printed, so a red run can be repeated.
    Without the variable the order is pytest's own. Every domain's conftest
    re-exports this hook, so it marks the config and shuffles once.
    """
    seed = os.environ.get("TEST_SHUFFLE")
    if not seed or getattr(config, "_cr29_shuffled", False):
        return
    config._cr29_shuffled = True
    import random

    random.Random(seed).shuffle(items)
    print(f"\nTEST_SHUFFLE={seed}: {len(items)} tests in a shuffled order")


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """De rate-limiters houden in-memory state per IP; in tests komt alles van
    hetzelfde IP. Reset ze per test zodat ze elkaars tellingen niet erven."""
    import app.limiter as limiters

    # Every limiter the module defines, derived and not listed (#1297): the list
    # this replaced named four of seven, and the newsletter's leaked its count
    # from one test into the next as soon as two tests posted to /nieuwsbrief.
    found = [v for v in vars(limiters).values() if isinstance(v, limiters.RateLimiter)]
    assert len(found) >= 7, f"only {len(found)} rate limiters found in app.limiter"
    for lim in found:
        lim._calls.clear()
    # Chatbot-dagbudget houdt eigen state per IP; reset zodat tests niet erven.
    from app.domains.chatbot.router import chat_char_budget

    chat_char_budget._usage.clear()
    yield


@pytest.fixture(autouse=True)
def job_queue_starts_empty(_migrate_schema):
    """No test inherits a job another test left in the queue (CR-29 F3).

    A test's writes are rolled back with its SAVEPOINT — except the ones the
    application makes in a transaction of its own. A failed mail plans its retry
    that way (`mail.service._enqueue_retry`), so a `mail.retry` row outlives the
    test that caused it, and `run_due_jobs` processes whatever is due: in a
    shuffled order the kernel's job test ran one job more than it had queued, and
    the newsletter's `batch=1` ran the stranger instead of its own job. In the
    usual order none happened to be due. Emptied before the test opens its
    connection; named without an underscore so the domains' `from tests.conftest
    import *` picks it up (CR-13 R15).

    Broken to check it can go red: a scratch test that calls `_enqueue_retry` and
    then `tests/test_kernel.py`, with the DELETE below replaced by a no-op → the
    two job tests fail on `2 == 1` and `1 == 0`, exactly as in the shuffled run.
    """
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM kernel_jobs")
    yield


#: What Inkscape answered for an input, kept for the length of the process (below).
_INKSCAPE_EXPORTS: dict[tuple, bytes] = {}
_INKSCAPE_QUERIES: dict[str, dict] = {}
_SVG_PREVIEWS: dict[tuple, bytes] = {}


@pytest.fixture
def one_render_per_input(monkeypatch):
    """Inkscape renders and measures each distinct input once per process (CR-29 R7).

    Every Design Studio test that makes a version starts Inkscape five times —
    one measurement, four exports — at seconds apiece, and most of them hand it
    the very same poster: the same fixture, or the same design saved four times
    in a row. Both calls are pure functions of what they are given (an SVG, a
    kind, a width), so the answer to an input already asked is the answer. Each
    distinct input still goes through the real binary; a test that needs a
    different poster gets a different render. Errors are not kept.

    Asked for by name (`pytest.mark.usefixtures`), not autouse: only the tests
    that reach Inkscape pay for the patch.
    """
    from pathlib import Path

    from app.domains.designstudio import render
    from app.domains.media import svg as media_svg

    real_export, real_query = render.export, render.query_all
    real_preview = media_svg.render_png

    def export(svg, kind, *, png_width_px=None):
        key = (svg, kind, png_width_px)
        if key not in _INKSCAPE_EXPORTS:
            _INKSCAPE_EXPORTS[key] = real_export(svg, kind, png_width_px=png_width_px)
        return _INKSCAPE_EXPORTS[key]

    def query_all(svg_path):
        key = Path(svg_path).read_text(encoding="utf-8")
        if key not in _INKSCAPE_QUERIES:
            _INKSCAPE_QUERIES[key] = real_query(svg_path)
        return dict(_INKSCAPE_QUERIES[key])

    def render_png(svg, width, height):
        key = (svg, width, height)
        if key not in _SVG_PREVIEWS:
            _SVG_PREVIEWS[key] = real_preview(svg, width, height)
        return _SVG_PREVIEWS[key]

    monkeypatch.setattr(render, "export", export)
    monkeypatch.setattr(render, "query_all", query_all)
    monkeypatch.setattr(media_svg, "render_png", render_png)
    yield


@pytest.fixture(autouse=True)
def session_clock_ticks(monkeypatch):
    """The session layer's clock moves a second on every reading (#1348).

    A CSRF token signs the WHOLE session value, expiry included (`csrf_token_for`).
    A test that sets the cookie from one `make_session_value(...)` and signs its
    token from a second one passes as long as both calls fall in the same second,
    and fails — "CSRF-token ongeldig" — when a second boundary falls between them:
    once in a few hundred runs on CI (#1348, media's filter test). With this clock
    every such test fails every time, so the pattern cannot come back unnoticed;
    the way that holds is to sign the cookie the client carries
    (`csrf_token_for(client.cookies.get(SESSION_COOKIE))`, or keep the one value).

    Only the session module's `time` is replaced, not the stdlib's: nothing else
    in the application reads this clock. Named without an underscore so the
    domains' `from tests.conftest import *` picks it up (CR-13 R15).
    """
    import time as real_time

    from app.domains.auth import session as session_module

    class _Clock:
        def __init__(self) -> None:
            self.now = real_time.time()

        def time(self) -> float:
            self.now += 1.0
            return self.now

    monkeypatch.setattr(session_module, "time", _Clock())
    yield


@pytest.fixture
def db_session(_migrate_schema):
    """Een sessie met SAVEPOINT-isolatie die endpoint-commits overleeft."""
    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    yield session

    event.remove(session, "after_transaction_end", _restart_savepoint)
    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """TestClient die dezelfde geïsoleerde sessie deelt met de endpoints."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


PLATFORM_TEST_HOST = "platform.example.test"


@pytest.fixture
def platform_workspace(client, monkeypatch):
    """Requests from `client` land in the platform workspace (#1535).

    Platform administration — Tenants, Organisaties, a new account, the
    overview of every workspace — answers only there; on the default host a
    request is Raak Millegem's and those screens are a 404. This makes the test
    host a platform host and sends every request of `client` to it.
    """
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_TEST_HOST)
    invalidate_tenant_codes()
    client.headers["host"] = PLATFORM_TEST_HOST
    yield client
    invalidate_tenant_codes()


@pytest.fixture
def workspace_host(monkeypatch):
    """For a test that walks a list of admin paths of both kinds (#1535): a
    function giving the headers that put a path in its own workspace — the
    platform host for platform administration, nothing for a tenant's screens.
    Which paths are the platform's comes from the menu (`PLATFORM_ONLY_ITEMS`)."""
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes
    from app.ui import PLATFORM_ONLY_ITEMS

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_TEST_HOST)
    invalidate_tenant_codes()

    def headers(path: str) -> dict[str, str]:
        base = path.split("?")[0]
        on_platform = any(base == p or base.startswith(p + "/") for p in PLATFORM_ONLY_ITEMS)
        return {"host": PLATFORM_TEST_HOST} if on_platform else {}

    yield headers
    invalidate_tenant_codes()


@pytest.fixture
def admin_headers():
    """Authorization-header voor de in migratie 014 geseede admin."""
    token = create_access_token({"sub": SEEDED_ADMIN_EMAIL})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_mollie(monkeypatch):
    """Vervang de Mollie-provider zodat online betalingen geen netwerk raken."""
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult, PaymentStatusResult

    def fake_create_payment(self, amount, description, redirect_url, webhook_url, metadata):
        return PaymentResult(
            provider_payment_id="tr_test_123",
            checkout_url="https://mollie.test/checkout/tr_test_123",
            status="pending",
        )

    # Geen bedrag teruggeven → de bedragverificatie (#92) wordt overgeslagen en het
    # gedrag blijft als voorheen (paid → activeren). De mismatch-test patcht dit zelf.
    def fake_get_details(self, provider_payment_id):
        return PaymentStatusResult(status="paid", amount=None, currency=None)

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", fake_create_payment)
    monkeypatch.setattr(mollie.MollieProvider, "get_payment_details", fake_get_details)


def send_queued_mail(db) -> None:
    """Send what the code under test queued (CR-13 phase 4).

    A mail handler queues a job and the job sends; in the tests the scheduler is off
    (`JOBS_ENABLED=false`), so a test that expects a mail runs the queue itself —
    where it used to rely on a background task running after the response.
    """
    from app.kernel.jobs import run_due_jobs

    run_due_jobs(db)


# ── Factories (#130) ───────────────────────────────────────────────────────────
# Generieke bouwstenen voor testdata; overschrijf velden via kwargs.


def create_test_person(db, **kwargs):
    from datetime import date

    from app.domains.mdm.api import Person

    # `gender_code` hoort erbij sinds #681: geboortedatum én geslacht zijn verplicht
    # voor élk lid, dus een testpersoon zonder geslacht is geen geldig lid meer en
    # zou op elke bewerkweg afketsen.
    defaults = {
        "first_name": "Test",
        "last_name": "Persoon",
        "date_of_birth": date(1990, 1, 1),
        "gender_code": "M",
    }
    person = Person(**{**defaults, **kwargs})
    db.add(person)
    db.flush()
    return person


def create_test_member(db, **kwargs):
    from app.domains.mdm.api import Member

    member = Member(**kwargs)
    db.add(member)
    db.flush()
    return member


def create_test_family(db, *, email="hoofdlid@example.com", relation_type="HOOFDLID", mobile=None):
    """Eén gezin met één persoon (als hoofdlid) en een EMAIL-contact.

    `mobile` gives that person a mobile number: the one save of "Mijn gezin"
    refuses a main member without one (#1590), so a test that saves through the
    portal passes it."""
    from app.domains.mdm.api import ContactDetail, MemberPerson

    member = create_test_member(db)
    person = create_test_person(db)
    db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type=relation_type))
    db.add(
        ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email, is_primary=True)
    )
    if mobile:
        db.add(
            ContactDetail(
                person_id=person.id, contact_type_code="MOBILE", value=mobile, is_primary=True
            )
        )
    db.flush()
    return member, person


# ── Seed-helpers ──────────────────────────────────────────────────────────────


def seed_postal_code(db, code="2400", municipality="Mol"):
    from app.domains.mdm.api import PostalCode

    pc = PostalCode(postal_code=code, municipality=municipality)
    db.add(pc)
    db.flush()
    return pc


def nieuw_lid_velden(db=None, **overrides) -> dict:
    """De velden die het beheer-aanmaakscherm verstuurt (#1110).

    Eén formulier met `m<i>_`-velden voor de personen plus het adres, en het
    hoofdlid heeft e-mail en gsm nodig — dezelfde regel als publiek. Hier op één
    plaats, zodat een volgende wijziging aan dat formulier niet in acht
    testbestanden overgetypt moet worden. Geef `db` mee om de postcode te seeden.
    """
    if db is not None:
        from app.domains.mdm.api import PostalCode

        if db.query(PostalCode).filter(PostalCode.postal_code == "2400").first() is None:
            seed_postal_code(db)
    velden = {
        "m0_first_name": "Nieuw",
        "m0_last_name": "Lid",
        "m0_date_of_birth": "1980-01-01",
        "m0_gender_code": "M",
        "m0_email": "nieuw@example.com",
        "m0_mobile": "0470000000",
        "m0_relation_type": "HOOFDLID",
        "street": "Nieuwstraat",
        "house_number": "7",
        "bus_number": "",
        "postal_code": "2400",
    }
    velden.update(overrides)
    return {k: v for k, v in velden.items() if v is not None}


def signup_fields(
    db=None, *others: dict, emails: tuple = ("nieuw@example.com",), **changes
) -> dict:
    """The fields the public Word lid page sends (#1590) — the contract of
    `membership.signup_form`: the household as a repeating group, the address
    and the payment method.

    The main member is row `n0` with one e-mail row per address in `emails`
    (`n0e`, `n0e1`, …; the first is marked as the main address). Each dict in
    `others` is one more person, as row `n1`, `n2`, …: complete by default, and
    what the dict names replaces it (`relation_type` is only sent when named).
    `changes` replace or add a field by its form name; `None` takes it out.

    A value that is a list is a repeated field (`h_order`), which is how the
    test client sends it. Pass `db` to seed postal code 2400.
    """
    if db is not None:
        from app.domains.mdm.api import PostalCode

        if db.query(PostalCode).filter(PostalCode.postal_code == "2400").first() is None:
            seed_postal_code(db)
    fields: dict = {
        "h_order": ["n0"],
        "h.n0.first_name": "Nieuw",
        "h.n0.last_name": "Lid",
        "h.n0.date_of_birth": "1980-01-01",
        "h.n0.gender_code": "M",
        "h.n0.mobile": "0470000000",
        "e_order.n0": [],
        "e_primary.n0": "n0e",
        "address.street": "Nieuwstraat",
        "address.house_number": "7",
        "address.bus_number": "",
        "address.postal_code": "2400",
        "payment_method": "transfer",
    }
    for n, address in enumerate(emails):
        key = "n0e" if n == 0 else f"n0e{n}"
        fields["e_order.n0"].append(key)
        fields[f"e.{key}.value"] = address
    for n, person in enumerate(others, start=1):
        row = {
            "first_name": f"Persoon{n}",
            "last_name": "Lid",
            "date_of_birth": "2000-01-01",
            "gender_code": "M",
            **person,
        }
        fields["h_order"].append(f"n{n}")
        fields.update({f"h.n{n}.{name}": value for name, value in row.items()})
    fields.update(changes)
    return {name: value for name, value in fields.items() if value is not None}


def form_fields(html: str, form_id: str) -> dict:
    """What a browser would send for the form `form_id` on this page, untouched.

    Every named control inside the form: text-like and hidden inputs with their
    value, the checked radio of a group, the selected option of a select (its
    first when none is marked). What stands in a `<template>` is not sent — that
    is a row nobody added. The order field of a repeating group
    (`data-row-order`) is a list, one key per row, also when there is one row;
    every other field is a string.

    Reading the page instead of typing the names keeps a test on the form's
    real contract: a field the template renames is then missing from the post.
    """
    from html.parser import HTMLParser

    start = html.index(f'<form id="{form_id}"')
    block = html[start : html.index("</form>", start)]
    fields: dict = {}

    class Reader(HTMLParser):
        template = 0
        select = None  # [name, chosen, first]

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "template":
                self.template += 1
            if self.template or "disabled" in a:
                return
            if tag == "input" and a.get("name"):
                kind = a.get("type", "text")
                if kind in ("radio", "checkbox") and "checked" not in a:
                    return
                if "data-row-order" in a:
                    fields.setdefault(a["name"], []).append(a.get("value") or "")
                elif kind != "file":
                    fields[a["name"]] = a.get("value") or ""
            elif tag == "select" and a.get("name"):
                self.select = [a["name"], None, None]
            elif tag == "option" and self.select is not None:
                value = a.get("value") or ""
                if self.select[2] is None:
                    self.select[2] = value
                if "selected" in a:
                    self.select[1] = value

        def handle_endtag(self, tag):
            if tag == "template":
                self.template -= 1
            elif tag == "select" and self.select is not None:
                name, chosen, first = self.select
                fields[name] = chosen if chosen is not None else (first or "")
                self.select = None

    Reader().feed(block)
    assert fields, f"the form {form_id} has no fields — is this test still looking?"
    return fields


def household_fields(client) -> dict:
    """The fields "Mijn gezin" sends when the signed-in member opens the edit
    mode and saves without touching anything (#1590): read from the page itself,
    so a test changes or adds what it is about and posts the rest as the page
    would (`POST /leden/gezin`)."""
    page = client.get("/leden/gezin?bewerken=1")
    assert page.status_code == 200, f"/leden/gezin?bewerken=1 → {page.status_code}"
    return form_fields(page.text, "gezin-form")


def form_guard_fields() -> dict:
    """The guard fields of a public form a person loaded five seconds ago (#1297).

    Every public way in drops a submission without them — silently, with the
    ordinary thanks — so a test that posts to one and expects a row adds these.

    Five seconds and not a minute: a quick person with a short message. A guard
    made stricter than that fails every test that posts a person's form, which is
    the point — a refusal is silent, so a too-strict limit must show up here.
    """
    import time

    from app.kernel.form_guard import HONEYPOT_FIELD, TOKEN_FIELD, issue_token

    return {HONEYPOT_FIELD: "", TOKEN_FIELD: issue_token(now=time.time() - 5)}


def sent_to_sign_in(client, path: str) -> bool:
    """Does a signed-out browser that opens `path` land on the sign-in page,
    carrying `path` back as `terug`? (#1458)

    What a back-office screen does without a session since #1458: a 303, not a
    401 a browser shows as bare JSON. The `terug` is asserted too, so the test
    also fails when the redirect forgets the page it came from.
    """
    from urllib.parse import quote

    answer = client.get(path, follow_redirects=False)
    return answer.status_code == 303 and answer.headers.get("location") == (
        f"/aanmelden?terug={quote(path, safe='/')}"
    )


def person_proof():
    """The same, as the `Proof` a service takes when a test calls it directly."""
    from app.kernel.form_guard import Proof

    return Proof.from_values(form_guard_fields())


def seed_activity_with_product(db, price="10.00", is_free=False, max_participants=None):
    """Maak een activiteit met één onderdeel en één (betalend) product."""
    from datetime import date, timedelta
    from decimal import Decimal

    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
    )

    activity = Activity(name="Testactiviteit")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=30)))
    db.flush()
    comp = ActivitySubRegistration(
        activity_id=activity.id,
        name="Onderdeel",
        registration_type_code="INDIVIDUAL",
        price=Decimal("0"),
        is_free=True,
        max_participants=max_participants,
    )
    db.add(comp)
    db.flush()
    product = ActivityProduct(
        component_id=comp.id,
        name="Testproduct",
        price=Decimal(price),
        is_free=is_free,
    )
    db.add(product)
    db.flush()
    return activity, comp, product


def register_through_the_service(
    activity_id: int,
    component_id: int,
    product_id: int,
    *,
    quantity: int,
    name: str,
    email: str,
) -> int:
    """A registration as the public form makes it — the registration service, in a
    session of its own, committed — for a test that needs one to exist before it
    opens a screen. Returns the registration's id.

    CR-13 phase 4b (#1251): two browser tests made theirs through the JSON route
    `POST /api/v1/activities/{id}/register`, which had no other caller. `app.main`
    is imported so the event subscribers are there (the confirmation mail is
    queued by one): a service called without them loses its consequences silently.
    """
    from fastapi import BackgroundTasks

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import register_for_activity
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    db = SessionLocal()
    try:
        result = register_for_activity(
            db,
            activity_id,
            RegistrationCreate(
                contact_name=name,
                contact_email=email,
                phone="0470000000",
                component_id=component_id,
                payment_method="transfer",
                items=[RegistrationItemCreate(product_id=product_id, quantity=quantity)],
            ),
            BackgroundTasks(),
        )
        return result["id"] if isinstance(result, dict) else result.id
    finally:
        db.close()


def seed_question_form(db, title="Sint 2026", **settings):
    """A form a component can ask (CR-14): open, one section, three questions —
    "Tijdslot" (checkbox, required, with "Andere…"), "Verhaal" (textarea, required)
    and "Opmerkingen" (textarea, optional). `settings` overrides the form's own
    (status, is_anonymous, max_submissions); `sections=2` adds a second section."""
    import secrets

    from app.domains.forms.models import Form, FormField, FormFieldOption, FormSection

    sections = settings.pop("sections", 1)
    form = Form(title=title, share_token=f"tok-{secrets.token_hex(6)}", status="open")
    for key, value in settings.items():
        setattr(form, key, value)
    db.add(form)
    db.flush()
    first = None
    for n in range(sections):
        section = FormSection(form_id=form.id, title=f"Deel {n + 1}", position=n)
        db.add(section)
        db.flush()
        first = first or section
    slot = FormField(
        form_id=form.id,
        section_id=first.id,
        field_type="checkbox",
        label="Tijdslot",
        required=True,
        position=0,
    )
    db.add(slot)
    db.flush()
    for n, label in enumerate(["Voormiddag", "Namiddag"]):
        db.add(FormFieldOption(field_id=slot.id, label=label, position=n))
    db.add(FormFieldOption(field_id=slot.id, label="Andere", position=2, is_other=True))
    db.add(
        FormField(
            form_id=form.id,
            section_id=first.id,
            field_type="textarea",
            label="Verhaal",
            required=True,
            position=1,
        )
    )
    db.add(
        FormField(
            form_id=form.id,
            section_id=first.id,
            field_type="textarea",
            label="Opmerkingen",
            position=2,
        )
    )
    db.commit()
    db.refresh(form)
    return form


#: A host from `PLATFORM_HOSTS` in a test: where a tenant is reached by its path
#: prefix, as on PROD (#889). Moved here with #1509.
PLATFORM_HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()
