"""CR-26 phase 1 (#2020) — the migration that gives every person and organisation a party per account.

The suite builds its schema with the whole chain, so migration 314 runs on every
run — but on the seed only, which has no persons and one account. This test runs
the chain on a database of its own up to 313, writes the cases the seed lacks,
runs 314 and reads what it left (C6 T3):

- every person and every organisation has one party, the persons' made first,
  so a party id is no organisation id (C4.9);
- a person's account is its tenant's; an organisation's is the account of the
  tenants that name it, itself for an account, the platform's for one no
  tenant names (F1, Q26); the tenant names the account's party;
- an organisation's address, contact and bank account, and the history rows,
  take the account of what they hang on, so CR-20's seam ends (F1, F13);
- the counts are the same before and after, and the party tables carry no
  `tenant_id` any more;
- an organisation named by tenants of two accounts makes the migration refuse,
  with its id (the as-built guard; none on HDEV, UAT and PROD).

Proven red, additively (put back each time): an `UPDATE` added after step 4
giving every unnamed organisation tenant 2's account → the free organisation's
test fails; `twice = []` added before the guard's `if` → the refusal test
fails (DID NOT RAISE).
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BEFORE = "313_2026_10_18_180812"
AFTER = "314_2026_10_19_002214"


def _one(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar_one()


@contextmanager
def _migrated(name: str, cases):
    """A database of its own: the chain to 313, `cases(conn)`, then 314."""
    from tests.conftest import TEST_DATABASE_URL

    url = make_url(TEST_DATABASE_URL)
    own = url.set(database=f"{url.database}_{name}")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{own.database}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{own.database}"')
    rendered = own.render_as_string(hide_password=False)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = rendered
    engine = create_engine(rendered)
    try:
        command.upgrade(cfg, BEFORE)
        with engine.begin() as conn:
            found = cases(conn)
        yield lambda: command.upgrade(cfg, AFTER), engine, found
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{own.database}" WITH (FORCE)')
        admin.dispose()


def _org(conn, name: str) -> int:
    return _one(
        conn,
        "INSERT INTO mdm.organizations (name, is_active, created_at, updated_at) "
        "VALUES (:n, true, now(), now()) RETURNING id",
        n=name,
    )


def _tenant(conn, code: str, account: int, shown: int) -> int:
    return _one(
        conn,
        "INSERT INTO mdm.tenants (code, kind, account_id, organization_id, is_active, "
        "created_at, updated_at) VALUES (:c, 'BEDRIJF', :a, :s, true, now(), now()) RETURNING id",
        c=code,
        a=account,
        s=shown,
    )


def _person(conn, name: str, tenant: int) -> int:
    return _one(
        conn,
        "INSERT INTO mdm.persons (first_name, last_name, tenant_id, created_at, updated_at) "
        "VALUES (:n, 'Partij', :t, now(), now()) RETURNING id",
        n=name,
        t=tenant,
    )


def _cases(conn) -> dict:
    """Two departments of the seeded account with a person each and a
    household, a company account with a site and a person, an organisation no
    tenant names, and the rows that hang on them."""
    ids = {
        "raak": _one(conn, "SELECT account_id FROM mdm.tenants WHERE id = 2"),
        "platform_account": _one(
            conn, "SELECT account_id FROM mdm.tenants WHERE kind = 'PLATFORM'"
        ),
        "a": _person(conn, "Anna", 2),
        "b": _person(conn, "Bert", 3),
    }
    ids["firm"] = _org(conn, "Firma Zesentwintig")
    ids["firm_tenant"] = _tenant(conn, "firma-cr26", ids["firm"], ids["firm"])
    ids["f"] = _person(conn, "Fien", ids["firm_tenant"])
    ids["free"] = _org(conn, "Vrije Organisatie")
    ids["household"] = _one(
        conn,
        "INSERT INTO mdm.members (tenant_id, created_at, updated_at) "
        "VALUES (2, now(), now()) RETURNING id",
    )
    conn.execute(
        text(
            "INSERT INTO mdm.member_persons (member_id, person_id, relation_type, tenant_id, "
            "created_at, updated_at) VALUES (:m, :p, 'HOOFDLID', 2, now(), now())"
        ),
        {"m": ids["household"], "p": ids["a"]},
    )
    conn.execute(
        text(
            "INSERT INTO membership.memberships (member_id, year, is_active, tenant_id, "
            "created_at, updated_at) VALUES (:m, 2026, true, 2, now(), now())"
        ),
        {"m": ids["household"]},
    )
    postal = _one(
        conn,
        "INSERT INTO mdm.postal_codes (postal_code, municipality, created_at, updated_at) "
        "VALUES ('2600', 'Partijdorp', now(), now()) "
        "RETURNING id",
    )
    conn.execute(
        text(
            "INSERT INTO mdm.addresses (person_id, street, house_number, postal_code_id, "
            "tenant_id, created_at, updated_at) "
            "VALUES (:p, 'Persoonstraat', '1', :pc, 2, now(), now())"
        ),
        {"p": ids["a"], "pc": postal},
    )
    # CR-20's seam: an organisation's own rows carry its id in `tenant_id`.
    conn.execute(
        text(
            "INSERT INTO mdm.addresses (organization_id, street, house_number, postal_code_id, "
            "tenant_id, created_at, updated_at) "
            "VALUES (:o, 'Firmastraat', '2', :pc, :o, now(), now())"
        ),
        {"o": ids["firm"], "pc": postal},
    )
    conn.execute(
        text(
            "INSERT INTO mdm.contact_details (organization_id, contact_type_code, value, "
            "is_primary, tenant_id, created_at, updated_at) "
            "VALUES (:o, 'EMAIL', 'vrij@example.org', true, :o, now(), now())"
        ),
        {"o": ids["free"]},
    )
    conn.execute(
        text(
            "INSERT INTO mdm.bank_accounts (organization_id, iban, sort_order, created_at, "
            "updated_at) VALUES (:o, 'BE00 0000 0000 0026', 0, now(), now())"
        ),
        {"o": ids["firm"]},
    )
    for person, organization, tenant in (
        (ids["a"], None, 2),
        (None, ids["firm"], ids["firm"]),
        (None, None, 3),
    ):
        conn.execute(
            text(
                "INSERT INTO mdm.address_history (operation, action, source, recorded_at, "
                "address_id, person_id, organization_id, tenant_id) VALUES ('insert', "
                "'recorded', 'test', now(), 1, :p, :o, :t)"
            ),
            {"p": person, "o": organization, "t": tenant},
        )
    ids["counts"] = {
        table: _one(conn, f"SELECT count(*) FROM mdm.{table}")
        for table in ("persons", "organizations", "members", "member_persons", "addresses")
    }
    return ids


@pytest.fixture(scope="module")
def migrated():
    with _migrated("cr26", _cases) as (upgrade, engine, ids):
        upgrade()
        yield engine, ids


def _party_account(conn, table: str, row_id: int) -> tuple[int, int]:
    """(the row's party, its party's account)."""
    return tuple(
        conn.execute(
            text(
                f"SELECT pa.id, pa.account_id FROM mdm.{table} x "
                "JOIN mdm.parties pa ON pa.id = x.party_id WHERE x.id = :i"
            ),
            {"i": row_id},
        ).one()
    )


def test_every_person_and_organisation_has_one_party(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        persons = _one(conn, "SELECT count(*) FROM mdm.persons")
        organizations = _one(conn, "SELECT count(*) FROM mdm.organizations")
        assert _one(conn, "SELECT count(*) FROM mdm.parties") == persons + organizations
        assert _one(conn, "SELECT count(*) FROM mdm.parties WHERE kind = 'PERSON'") == persons
        assert (
            _one(
                conn,
                "SELECT min(o.party_id) - max(p.party_id) FROM mdm.organizations o, mdm.persons p",
            )
            > 0
        ), "the persons' parties come first, so no party id leans on an organisation id"


def test_the_counts_stay_and_the_tenant_column_is_gone(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        for table, before in ids["counts"].items():
            assert _one(conn, f"SELECT count(*) FROM mdm.{table}") == before, table
        left = conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = 'mdm' "
                "AND column_name = 'tenant_id' AND table_name IN ('persons', 'members', "
                "'member_persons', 'addresses', 'contact_details', 'address_history')"
            )
        ).all()
        assert left == []


def test_a_tenant_names_its_accounts_party(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        raak_party, raak_account = _party_account(conn, "organizations", ids["raak"])
        assert raak_account == raak_party, "an account is its own account"
        for tenant in (2, 3):
            assert _one(conn, "SELECT account_id FROM mdm.tenants WHERE id = :t", t=tenant) == (
                raak_party
            )
        firm_party, _ = _party_account(conn, "organizations", ids["firm"])
        assert (
            _one(conn, "SELECT account_id FROM mdm.tenants WHERE id = :t", t=ids["firm_tenant"])
            == firm_party
        )


def test_a_person_takes_its_tenants_account(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        raak_party, _ = _party_account(conn, "organizations", ids["raak"])
        firm_party, _ = _party_account(conn, "organizations", ids["firm"])
        for key, account in (("a", raak_party), ("b", raak_party), ("f", firm_party)):
            assert _party_account(conn, "persons", ids[key])[1] == account, key
            assert (
                _one(conn, "SELECT account_id FROM mdm.persons WHERE id = :i", i=ids[key])
                == account
            )
        assert (
            _one(conn, "SELECT account_id FROM mdm.members WHERE id = :i", i=ids["household"])
            == raak_party
        )


def test_an_organisation_no_tenant_names_goes_to_the_platforms_account(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        platform_org = ids["platform_account"]
        platform_party, _ = _party_account(conn, "organizations", platform_org)
        _free_party, free_account = _party_account(conn, "organizations", ids["free"])
        assert free_account == platform_party
        assert (
            _one(
                conn,
                "SELECT account_id FROM mdm.contact_details WHERE organization_id = :o",
                o=ids["free"],
            )
            == platform_party
        ), "its contact follows it"


def test_what_hangs_on_a_party_takes_its_account(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        raak_party, _ = _party_account(conn, "organizations", ids["raak"])
        firm_party, _ = _party_account(conn, "organizations", ids["firm"])
        assert (
            _one(conn, "SELECT account_id FROM mdm.addresses WHERE person_id = :p", p=ids["a"])
            == raak_party
        )
        assert (
            _one(
                conn,
                "SELECT account_id FROM mdm.addresses WHERE organization_id = :o",
                o=ids["firm"],
            )
            == firm_party
        ), "the seam row takes its organisation's account"
        assert (
            _one(
                conn,
                "SELECT account_id FROM mdm.bank_accounts WHERE organization_id = :o",
                o=ids["firm"],
            )
            == firm_party
        )
        history = dict(
            conn.execute(
                text(
                    "SELECT coalesce(person_id::text, organization_id::text, 'none'), account_id "
                    "FROM mdm.address_history"
                )
            ).all()
        )
        assert history == {
            str(ids["a"]): raak_party,
            str(ids["firm"]): firm_party,
            "none": raak_party,
        }


def _named_twice(conn) -> dict:
    """The firm is an account, and a tenant of the seeded account shows it."""
    firm = _org(conn, "Firma Twee Keer")
    _tenant(conn, "firma-twee-cr26", firm, firm)
    raak = _one(conn, "SELECT account_id FROM mdm.tenants WHERE id = 2")
    _tenant(conn, "leent-cr26", raak, firm)
    return {"firm": firm}


def test_an_organisation_named_by_two_accounts_stops_the_migration():
    with _migrated("cr26_twice", _named_twice) as (upgrade, _engine, ids):
        with pytest.raises(Exception, match=r"named by tenants of two accounts") as refused:
            upgrade()
        assert f"[{ids['firm']}]" in str(refused.value)
