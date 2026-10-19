"""CR-26 phase 2 — the migration that makes `party_relationships` of `organization_persons`.

The suite runs migration 317 on the seed only, which has no circle. This test runs
the chain to 316 on a database of its own, writes three circle relations in the old
shape (an open one, an ended one, a soft-deleted one) beside a person of the
account, runs 317 and reads what it left (F4, F8, F14, C4.7):

- every relation has moved with **its id** (the meeting circle's routes and
  `CircleStartChosen` carry it), its kind, its dates, its soft delete and the
  account of its person; it now joins the person's party to the organisation's;
- the old table and its kind tables are gone, `ACTS_FOR` is a kind, and the
  sequence goes on after the highest id;
- the view `person_tenants` still shows the person at the tenant whose
  organisation the relation names;
- `sales_orders` has the buyer columns, all nullable, and the invoices module is
  accepted by the CHECK of the module codes while a made-up code still is not.

Proven red (put back each time): the copy given `NULL` for `deleted_at` -> the
soft-deleted relation comes back alive; the CHECK left without `invoices` -> the
module insert fails with the CHECK violation; the guard `to_regclass` left out of
`upgrade` -> the second run fails on the missing old table.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._own_database import own_database

BEFORE = "316_2026_10_19_095522"
AFTER = "317_2026_10_19_105524"


def _one(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar_one()


def _person(conn, account: int, first: str) -> tuple[int, int]:
    party = _one(
        conn,
        "INSERT INTO mdm.parties (account_id, kind, created_at, updated_at) "
        "VALUES (:a, 'PERSON', now(), now()) RETURNING id",
        a=account,
    )
    person = _one(
        conn,
        "INSERT INTO mdm.persons (first_name, last_name, party_id, account_id, created_at, "
        "updated_at) VALUES (:f, 'Kring', :p, :a, now(), now()) RETURNING id",
        f=first,
        p=party,
        a=account,
    )
    return person, party


def _run_again(engine) -> None:
    """The migration's `upgrade()` a second time on the migrated database: idempotent."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = next((Path(__file__).parent.parent / "alembic" / "versions").glob("317_2026_10_19_*.py"))
    spec = importlib.util.spec_from_file_location("migration_317", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def test_the_circle_moves_with_its_ids_and_the_buyer_columns_arrive():
    with own_database("rel317") as (upgrade, engine):
        upgrade(BEFORE)
        with engine.begin() as conn:
            account = _one(conn, "SELECT account_id FROM mdm.tenants WHERE id = 2")
            organisation = _one(conn, "SELECT organization_id FROM mdm.tenants WHERE id = 2")
            org_party = _one(
                conn, "SELECT party_id FROM mdm.organizations WHERE id = :o", o=organisation
            )
            cases = {}
            for first, extra, deleted in (
                ("Open", "", "NULL"),
                ("Ended", ", end_date", "NULL"),
                ("Deleted", "", "now()"),
            ):
                person, party = _person(conn, account, first)
                end = ", '2026-02-01'" if extra else ""
                relation = _one(
                    conn,
                    f"INSERT INTO mdm.organization_persons (tenant_id, organization_id, person_id, "
                    f"relation_type, start_date{extra}, deleted_at, created_at, updated_at) "
                    f"VALUES (2, :o, :p, 'BOARD_MEETING', '2026-01-01'{end}, {deleted}, now(), now()) "
                    "RETURNING id",
                    o=organisation,
                    p=person,
                )
                cases[first] = (relation, person, party, bool(extra), deleted != "NULL")
            highest = max(c[0] for c in cases.values())
        upgrade(AFTER)
        with engine.begin() as conn:
            for first, (relation, person, party, ended, deleted) in cases.items():
                row = conn.execute(
                    text(
                        "SELECT from_party_id, to_party_id, kind, start_date, end_date, "
                        "deleted_at IS NOT NULL, account_id FROM mdm.party_relationships WHERE id = :i"
                    ),
                    {"i": relation},
                ).one()
                assert (row[0], row[1], row[2]) == (party, org_party, "BOARD_MEETING"), first
                assert str(row[3]) == "2026-01-01" and (row[4] is not None) is ended, first
                assert row[5] is deleted, first
                assert row[6] == account, first
            total = _one(conn, "SELECT count(*) FROM mdm.party_relationships")
            assert total == 3
            assert _one(conn, "SELECT to_regclass('mdm.organization_persons')") is None, (
                "the old table is gone"
            )
            kinds = set(
                conn.execute(text("SELECT code FROM mdm.party_relationship_kind_codes")).scalars()
            )
            assert {"BOARD_MEETING", "ACTS_FOR"} <= kinds
            fresh = _one(
                conn,
                "INSERT INTO mdm.party_relationships (account_id, from_party_id, to_party_id, kind, "
                "created_at, updated_at) VALUES (:a, :f, :t, 'ACTS_FOR', now(), now()) RETURNING id",
                a=account,
                f=cases["Open"][2],
                t=org_party,
            )
            assert fresh > highest, "the sequence goes on after the highest id"
            seen = set(
                conn.execute(
                    text("SELECT tenant_id FROM mdm.person_tenants WHERE person_id = :p"),
                    {"p": cases["Open"][1]},
                ).scalars()
            )
            assert 2 in seen, "the person is still at the tenant its organisation belongs to"
            columns = {
                name: nullable
                for name, nullable in conn.execute(
                    text(
                        "SELECT column_name, is_nullable FROM information_schema.columns "
                        "WHERE table_schema = 'sales' AND table_name = 'sales_orders' "
                        "AND column_name LIKE 'buyer\\_%'"
                    )
                )
            }
            assert set(columns) == {
                "buyer_party_id",
                "buyer_name",
                "buyer_street",
                "buyer_house_number",
                "buyer_bus_number",
                "buyer_postal_code",
                "buyer_municipality",
                "buyer_country",
                "buyer_vat_number",
            }
            assert set(columns.values()) == {"YES"}
            conn.execute(text("INSERT INTO mdm.tenant_modules VALUES (2, 'invoices')"))
            duplicate = _one(
                conn,
                "SELECT count(*) FROM pg_indexes WHERE schemaname = 'mdm' AND "
                "tablename = 'party_relationships' AND indexname = 'ix_party_relationships_id'",
            )
            assert duplicate == 0, "the primary key's index is the only one on id"
        _run_again(engine)
        with engine.begin() as conn:
            assert _one(conn, "SELECT count(*) FROM mdm.party_relationships") == total + 1
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO mdm.tenant_modules VALUES (2, 'stamboom')"))
