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
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres@localhost:5432/raaktest",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "test-secret-key-which-is-long-enough-32+")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import engine, Base
from app.main import app
from app.database import get_db
from app.auth import create_access_token


# Bestaat in de seed-migratie 014; gebruiken we als ingelogde admin.
SEEDED_ADMIN_EMAIL = "koen.renders@gmail.com"


@pytest.fixture(scope="session", autouse=True)
def _migrate_schema():
    """Bouw de schema's één keer via de echte migratieketen."""
    Base.metadata.drop_all(bind=engine)
    # Verwijder ook alembic_version zodat upgrade vanaf nul draait.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """De rate-limiters houden in-memory state per IP; in tests komt alles van
    hetzelfde IP. Reset ze per test zodat ze elkaars tellingen niet erven."""
    from app.limiter import registration_limiter, login_limiter, idea_limiter
    for lim in (registration_limiter, login_limiter, idea_limiter):
        lim._calls.clear()
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


@pytest.fixture
def admin_headers():
    """Authorization-header voor de in migratie 014 geseede admin."""
    token = create_access_token({"sub": SEEDED_ADMIN_EMAIL})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_mollie(monkeypatch):
    """Vervang de Mollie-provider zodat online betalingen geen netwerk raken."""
    from app.domains.payment_gateway.providers import mollie
    from app.domains.payment_gateway.providers.base import PaymentResult

    def fake_create_payment(self, amount, description, redirect_url, webhook_url, metadata):
        return PaymentResult(
            provider_payment_id="tr_test_123",
            checkout_url="https://mollie.test/checkout/tr_test_123",
            status="pending",
        )

    def fake_get_status(self, provider_payment_id):
        return "paid"

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", fake_create_payment)
    monkeypatch.setattr(mollie.MollieProvider, "get_payment_status", fake_get_status)


# ── Seed-helpers ──────────────────────────────────────────────────────────────

def seed_postal_code(db, code="2400", municipality="Mol"):
    from app.models.postal_codes import PostalCode
    pc = PostalCode(postal_code=code, municipality=municipality)
    db.add(pc)
    db.flush()
    return pc


def seed_activity_with_product(db, price="10.00", is_free=False, max_participants=None):
    """Maak een activiteit met één onderdeel en één (betalend) product."""
    from datetime import date, timedelta
    from decimal import Decimal
    from app.models.activity import Activity
    from app.models.activity_sub_registration import ActivitySubRegistration, ActivityProduct

    from app.models.activity import ActivityDate
    activity = Activity(name="Testactiviteit")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=30)))
    db.flush()
    comp = ActivitySubRegistration(
        activity_id=activity.id, name="Onderdeel", registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True, max_participants=max_participants,
    )
    db.add(comp)
    db.flush()
    product = ActivityProduct(
        component_id=comp.id, name="Testproduct",
        price=Decimal(price), is_free=is_free,
    )
    db.add(product)
    db.flush()
    return activity, comp, product
