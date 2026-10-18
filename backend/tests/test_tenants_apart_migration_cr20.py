"""CR-20 (#1578) — the migration that pulls the tenant out of the organisation.

The suite builds its schema with the whole chain, so migration 313 runs on every
run — but on the seed only, where no tenant borrows another organisation's data
and no page names an account. This test runs the chain on a database of its own
up to 312, writes the cases the seed lacks, runs 313 and reads what it left:

- the tenants carry the ids their organisation rows had (C6 test 1's premise,
  C4.1), with account and shown organisation (F7);
- the organisation keeps the party, no tenant column and no role (test 9, test 2);
- a borrowed-data tenant's own row is soft-deleted with its address, the tenant
  stays (F7, C4.6);
- the meeting circle hangs on the party its tenant shows, with its ids (F11);
- the stored `{{tenants:<account code>}}` names a tenant (F10, test 13);
- settings, modules and roles keep their values and gain the key (test 8); a
  role or a setting on an account is removed (Koen, 18 October 2026: "1a");
- the four reporting views list the tenants (test 12);
- an organisation's address in the seam is still accepted (test 14).

Proven red (put back each time): step 7 of the migration without its
`UPDATE mdm.organizations SET deleted_at` → the borrowed row stays live and the
soft-delete assertion fails; step 6 without its `UPDATE … organization_persons`
→ the circle assertion fails.
"""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BEFORE = "312_2026_10_16_162902"
AFTER = "313_2026_10_18_180812"


@pytest.fixture(scope="module")
def migrated_url():
    from tests.conftest import TEST_DATABASE_URL

    url = make_url(TEST_DATABASE_URL)
    own = url.set(database=f"{url.database}_cr20")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{own.database}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{own.database}"')
    rendered = own.render_as_string(hide_password=False)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = rendered
    try:
        command.upgrade(cfg, BEFORE)
        engine = create_engine(rendered)
        with engine.begin() as conn:
            _write_the_cases(conn)
        command.upgrade(cfg, AFTER)
        yield engine
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{own.database}" WITH (FORCE)')
        admin.dispose()


def _one(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def _write_the_cases(conn) -> None:
    """A company account with a brand site that shows the company's data, a page
    that lists the company's sites, a circle on the platform row, a setting, a
    role and a module of the brand."""
    platform = _one(conn, "SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM'")
    conn.execute(
        text(
            "INSERT INTO mdm.organizations (org_type, code, name, is_active, created_at, "
            "updated_at) VALUES ('ACCOUNT', 'firma-cr20', 'Firma Twintig', true, now(), now())"
        )
    )
    firm = _one(conn, "SELECT id FROM mdm.organizations WHERE code = 'firma-cr20'")
    conn.execute(
        text(
            "INSERT INTO mdm.organizations (org_type, code, name, kind, parent_id, "
            "site_organization_id, site_name, is_active, created_at, updated_at) VALUES "
            "('UNIT', 'merk-cr20', 'Merk (leeg)', 'BEDRIJF', :firm, :firm, 'Merk Twintig', "
            "true, now(), now())"
        ),
        {"firm": firm},
    )
    brand = _one(conn, "SELECT id FROM mdm.organizations WHERE code = 'merk-cr20'")
    postal = _one(
        conn,
        "INSERT INTO mdm.postal_codes (postal_code, municipality, created_at, updated_at) "
        "VALUES ('9999', 'Twintigdorp', now(), now()) RETURNING id",
    )
    # The empty organisation row of the brand, with an address of its own — the
    # tenant_id is the owner, as `organization_service` writes it (the seam).
    conn.execute(
        text(
            "INSERT INTO mdm.addresses (tenant_id, organization_id, street, house_number, "
            "postal_code_id, created_at, updated_at) VALUES "
            "(:brand, :brand, 'Merkstraat', '1', :pc, now(), now())"
        ),
        {"brand": brand, "pc": postal},
    )
    conn.execute(
        text("INSERT INTO mdm.tenant_modules (tenant_id, module_code) VALUES (:brand, 'cms')"),
        {"brand": brand},
    )
    conn.execute(
        text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value) "
            "VALUES (:brand, 'tagline', 'Twintig')"
        ),
        {"brand": brand},
    )
    user = _one(
        conn,
        "INSERT INTO auth.users (email, is_active, created_at, updated_at) "
        "VALUES ('cr20@example.org', true, now(), now()) RETURNING id",
    )
    conn.execute(
        text(
            "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
            "VALUES (:user, 'ADMIN', :brand, now())"
        ),
        {"user": user, "brand": brand},
    )
    # A role and a setting on the account, as migration 127 put roles on Raak vzw.
    conn.execute(
        text(
            "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
            "VALUES (:user, 'ACCOUNT_ADMIN', :firm, now())"
        ),
        {"user": user, "firm": firm},
    )
    conn.execute(
        text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value) "
            "VALUES (:firm, 'tagline', 'Op het account')"
        ),
        {"firm": firm},
    )
    person = _one(
        conn,
        "INSERT INTO mdm.persons (tenant_id, first_name, last_name, created_at, updated_at) "
        "VALUES (2, 'Kring', 'Lid', now(), now()) RETURNING id",
    )
    conn.execute(
        text(
            "INSERT INTO mdm.organization_persons (tenant_id, organization_id, person_id, "
            "relation_type, start_date) VALUES (2, :platform, :person, 'BOARD_MEETING', "
            "current_date)"
        ),
        {"platform": platform, "person": person},
    )
    conn.execute(
        text(
            "INSERT INTO cms.cms_pages (tenant_id, title, slug, content, is_published, "
            "show_in_nav, is_home, sort_order, created_at, updated_at) VALUES "
            "(2, 'Sites', 'sites-cr20', '<p>{{tenants:firma-cr20}}</p>', true, false, false, "
            "0, now(), now())"
        )
    )


def test_the_tenants_carry_the_ids_of_their_rows(migrated_url):
    with migrated_url.connect() as conn:
        brand = conn.execute(
            text(
                "SELECT t.id, t.kind, t.site_name, t.account_id, t.organization_id, a.name "
                "FROM mdm.tenants t JOIN mdm.organizations a ON a.id = t.account_id "
                "WHERE t.code = 'merk-cr20'"
            )
        ).one()
        firm = _one(conn, "SELECT id FROM mdm.organizations WHERE name = 'Firma Twintig'")
        assert (brand.kind, brand.site_name, brand.name) == (
            "BEDRIJF",
            "Merk Twintig",
            "Firma Twintig",
        )
        assert brand.account_id == firm and brand.organization_id == firm
        # The seed's own tenants: each its own party, the same id.
        millegem = conn.execute(
            text("SELECT id, organization_id FROM mdm.tenants WHERE code = 'raakmillegem'")
        ).one()
        assert millegem.organization_id == millegem.id
        assert _one(conn, "SELECT count(*) FROM mdm.tenants WHERE kind = 'PLATFORM'") == 1


def test_the_organisation_keeps_the_party_only(migrated_url):
    with migrated_url.connect() as conn:
        columns = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'mdm' AND table_name = 'organizations'"
                )
            )
        }
        assert "name" in columns and "legal_form" in columns
        assert not columns & {
            "org_type",
            "role",
            "code",
            "kind",
            "parent_id",
            "site_organization_id",
            "site_name",
        }
        assert _one(conn, "SELECT to_regclass('mdm.organization_type_codes')") is None


def test_a_borrowed_data_row_is_soft_deleted_with_its_address(migrated_url):
    with migrated_url.connect() as conn:
        row = conn.execute(
            text(
                "SELECT o.deleted_at IS NOT NULL AS gone FROM mdm.organizations o "
                "JOIN mdm.tenants t ON t.id = o.id WHERE t.code = 'merk-cr20'"
            )
        ).one()
        assert row.gone, "the brand's empty organisation row is soft-deleted"
        assert (
            _one(
                conn,
                "SELECT count(*) FROM mdm.addresses WHERE street = 'Merkstraat' "
                "AND deleted_at IS NOT NULL",
            )
            == 1
        )
        # The tenant itself stays, active.
        assert _one(conn, "SELECT is_active FROM mdm.tenants WHERE code = 'merk-cr20'") is True


def test_the_circle_hangs_on_the_party_its_tenant_shows(migrated_url):
    with migrated_url.connect() as conn:
        relation = conn.execute(
            text(
                "SELECT r.organization_id, t.organization_id AS shown FROM mdm.organization_persons r "
                "JOIN mdm.tenants t ON t.id = r.tenant_id JOIN mdm.persons p ON p.id = r.person_id "
                "WHERE p.first_name = 'Kring'"
            )
        ).one()
        assert relation.organization_id == relation.shown


def test_the_sites_placeholder_names_a_tenant(migrated_url):
    with migrated_url.connect() as conn:
        content = _one(conn, "SELECT content FROM cms.cms_pages WHERE slug = 'sites-cr20'")
        assert content == "<p>{{tenants:merk-cr20}}</p>"


def test_settings_modules_and_roles_keep_their_tenant_and_gain_the_key(migrated_url):
    with migrated_url.connect() as conn:
        brand = _one(conn, "SELECT id FROM mdm.tenants WHERE code = 'merk-cr20'")
        assert (
            _one(
                conn,
                "SELECT value FROM kernel_tenant_settings WHERE tenant_id = :t AND key = 'tagline'",
                t=brand,
            )
            == "Twintig"
        )
        assert (
            _one(conn, "SELECT count(*) FROM mdm.tenant_modules WHERE tenant_id = :t", t=brand) == 1
        )
        assert _one(conn, "SELECT count(*) FROM auth.user_roles WHERE tenant_id = :t", t=brand) == 1
        keyed = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT conrelid::regclass::text FROM pg_constraint "
                    "WHERE contype = 'f' AND confrelid = 'mdm.tenants'::regclass"
                )
            )
        }
        assert {"kernel_tenant_settings", "auth.user_roles", "mdm.tenant_modules"} <= keyed
        assert "activities.registrations" in keyed and "mdm.persons" in keyed
        assert "mdm.addresses" not in keyed, "the seam carries no key (C4.8)"


def test_a_role_and_a_setting_on_an_account_are_removed(migrated_url):
    """Koen, 18 October 2026: "1a" — they opened nothing, and they would refuse
    the key. The brand's own role and setting stay (the test above)."""
    with migrated_url.connect() as conn:
        firm = _one(conn, "SELECT id FROM mdm.organizations WHERE name = 'Firma Twintig'")
        assert _one(conn, "SELECT count(*) FROM auth.user_roles WHERE tenant_id = :f", f=firm) == 0
        assert (
            _one(conn, "SELECT count(*) FROM kernel_tenant_settings WHERE tenant_id = :f", f=firm)
            == 0
        )


def test_the_reporting_views_list_the_tenants(migrated_url):
    with migrated_url.connect() as conn:
        departments = {
            r[0] for r in conn.execute(text("SELECT id FROM mdm.tenants WHERE kind <> 'PLATFORM'"))
        }
        for view in ("d_payment_method", "d_payment_status", "d_membership_status"):
            listed = {
                r[0] for r in conn.execute(text(f"SELECT DISTINCT tenant_id FROM reporting.{view}"))
            }
            assert listed == departments, view
        assert _one(conn, "SELECT count(DISTINCT tenant_id) FROM reporting.d_date") == len(
            departments
        )


def test_an_organisation_address_in_the_seam_is_still_accepted(migrated_url):
    with migrated_url.begin() as conn:
        firm = _one(conn, "SELECT id FROM mdm.organizations WHERE name = 'Firma Twintig'")
        postal = _one(conn, "SELECT id FROM mdm.postal_codes ORDER BY id LIMIT 1")
        conn.execute(
            text(
                "INSERT INTO mdm.addresses (tenant_id, organization_id, street, house_number, "
                "postal_code_id, created_at, updated_at) VALUES "
                "(:firm, :firm, 'Firmastraat', '2', :pc, now(), now())"
            ),
            {"firm": firm, "pc": postal},
        )
