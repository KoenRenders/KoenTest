"""#2195: the chain from the revision before 212 to the head, with a sent letter in it.

PROD's v2.17.0 deploy died in migration 212 on a sent letter: the migration rendered it with
the app's code of the head on the schema of 212. CI never saw it, because its chain runs on
an empty database and a test of one migration's function runs at the head. This runs the
whole stretch on a database of its own, with the letters written in the schema *before*
212 (`body_html`, no `body_document`), as PROD held them.

Broken on purpose (21 October 2026): the freeze put back into 212 (rendering there) → the
upgrade stops with `relation "mdm.tenants" does not exist`; the `current_tenant_id.set`
taken out of 320 → `NoTenantContext`; the CHECK left out of 320 → the CHECK test is red.
"""

import pytest
from sqlalchemy import text

from tests._own_database import own_database

BEFORE = "211_2026_10_16_021737"

LETTER = (
    "<div>Beste leden, het lidmaatschap loopt tot {{membership_valid_until}} "
    "en kost {{membership_price_full}}.</div><div>[[kalender]]</div><div>[[afsluiting]]</div>"
)


@pytest.fixture(scope="module")
def migrated():
    from app import database
    from app.kernel import clock
    from app.kernel.tenancy import current_tenant_id, forget_tenant_accounts

    # The migration is a call outside any tenant: the clock's real seam, as in production.
    # Nothing kept from the suite's database: production starts with a cold process, and
    # a tenant's account kept here answers without the query that fails on the old schema.
    forget_tenant_accounts()
    clock.forget_time_zones()
    original = clock.tenant_of_the_call
    clock.tenant_of_the_call = current_tenant_id.get
    try:
        with own_database("letters_2195") as (upgrade, engine):
            upgrade(BEFORE)
            application = (database.engine, database.SessionLocal.kw["bind"])
            # The application of the migration's own database, as in production: the render
            # reads the settings and the tenants over it, not over the suite's.
            database.engine = database.SessionLocal.kw["bind"] = engine
            with engine.begin() as conn:
                tenant = conn.execute(
                    text(
                        "SELECT id FROM mdm.organizations WHERE kind = 'VERENIGING' ORDER BY id LIMIT 1"
                    )
                ).scalar_one()
                for subject, body, status, audience, base in (
                    ("sent", LETTER, "sent", "members", "https://raak.example"),
                    ("no-link", "<div>Zonder link</div>", "sent", "members", None),
                    ("draft", "<div>Nog niet</div>", "draft", None, None),
                ):
                    conn.execute(
                        text(
                            "INSERT INTO newsletter.newsletters "
                            "(tenant_id, subject, body_html, status, audience, link_base) "
                            "VALUES (:t, :s, :b, :st, :a, :l)"
                        ),
                        {
                            "t": tenant,
                            "s": subject,
                            "b": body,
                            "st": status,
                            "a": audience,
                            "l": base,
                        },
                    )
            try:
                upgrade("head")
            finally:
                database.engine, database.SessionLocal.kw["bind"] = application
            with engine.begin() as conn:
                rows = {
                    r.subject: r
                    for r in conn.execute(
                        text("SELECT subject, sent_body_html FROM newsletter.newsletters")
                    )
                }
                check = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE "
                        "conname = 'ck_newsletter_sent_has_body'"
                    )
                ).scalar_one()
            yield rows, check
    finally:
        clock.tenant_of_the_call = original


def test_a_sent_letter_with_values_is_frozen_by_the_chain(migrated):
    rows, _ = migrated
    body = rows["sent"].sent_body_html
    assert "Beste leden" in body and "{{" not in body, body
    assert "€" in body, "the membership price of its own tenant stands in the body"
    assert "Het bestuur van" in body, "the closing is built"


def test_a_sent_letter_without_a_link_base_is_frozen_too(migrated):
    rows, _ = migrated
    assert "Zonder link" in rows["no-link"].sent_body_html


def test_a_draft_is_left_and_the_check_stands(migrated):
    rows, check = migrated
    assert rows["draft"].sent_body_html is None
    assert check == 1
