"""CR-26 phase 3 (#2020) — the migration that hangs the rest on the party.

The suite runs migration 315 on the seed only, which has no persons. This test
runs the chain to 314 on a database of its own, writes a person and an
organisation with everything that hangs on them in the old shape, runs 315 and
reads what it left (F3, F13, C4.10):

- every address, contact, bank account, identification and member number points
  at its owner's party, and the counts are the same before and after;
- the pair and its CHECKs are gone, so are `organization_identifications` and the
  pointers of the history tables; a history row takes its owner's party, and one
  whose owner no longer exists keeps none;
- one living address per party, and the person's contact rule for every party:
  an organisation may hold two e-mail addresses, a second primary is refused;
- the reporting views that read the old columns still answer.

Proven red (put back each time): `_fill` given only the first column of each
table (`columns[:1]`) → the organisation's address finds no party and the
migration refuses, naming its id; `uq_contact_details_one_primary_per_type`
made a plain index → the second primary is not refused (DID NOT RAISE). An
index of one contact per type cannot be added to prove the first half: the
person's two addresses of this world refuse it at creation already.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._own_database import own_database

BEFORE = "314_2026_10_19_002214"
AFTER = "315_2026_10_19_051425"

TABLES = (
    "addresses",
    "contact_details",
    "bank_accounts",
    "external_numbers",
    "address_history",
    "contact_detail_history",
    "external_number_history",
)


def _one(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar_one()


@contextmanager
def _migrated(name: str, cases):
    """A database of its own: the chain to 314, `cases(conn)`, then 315."""
    with own_database(name) as (upgrade, engine):
        upgrade(BEFORE)
        with engine.begin() as conn:
            found = cases(conn)
        yield lambda: upgrade(AFTER), engine, found


def _party(conn, kind: str, account: int) -> int:
    return _one(
        conn,
        "INSERT INTO mdm.parties (account_id, kind, created_at, updated_at) "
        "VALUES (:a, :k, now(), now()) RETURNING id",
        a=account,
        k=kind,
    )


def _cases(conn) -> dict:
    """A person and an organisation of the seeded account, each with what hangs
    on it, in the shape before 315."""
    account = _one(conn, "SELECT account_id FROM mdm.tenants WHERE id = 2")
    ids: dict = {"account": account}
    ids["person_party"] = _party(conn, "PERSON", account)
    ids["person"] = _one(
        conn,
        "INSERT INTO mdm.persons (first_name, last_name, party_id, account_id, created_at, "
        "updated_at) VALUES ('Pieter', 'Partij', :p, :a, now(), now()) RETURNING id",
        p=ids["person_party"],
        a=account,
    )
    ids["org_party"] = _party(conn, "ORGANIZATION", account)
    ids["org"] = _one(
        conn,
        "INSERT INTO mdm.organizations (name, is_active, party_id, account_id, created_at, "
        "updated_at) VALUES ('Firma Pointer', true, :p, :a, now(), now()) RETURNING id",
        p=ids["org_party"],
        a=account,
    )
    postal = _one(
        conn,
        "INSERT INTO mdm.postal_codes (postal_code, municipality, created_at, updated_at) "
        "VALUES ('2601', 'Wijzerdorp', now(), now()) RETURNING id",
    )
    ids["postal"] = postal
    owners = {"p": ids["person"], "o": ids["org"], "a": account, "pc": postal}
    ids["person_address"] = _one(
        conn,
        "INSERT INTO mdm.addresses (person_id, account_id, street, house_number, "
        "postal_code_id, created_at, updated_at) "
        "VALUES (:p, :a, 'Persoonstraat', '1', :pc, now(), now()) RETURNING id",
        **owners,
    )
    ids["org_address"] = _one(
        conn,
        "INSERT INTO mdm.addresses (organization_id, account_id, street, house_number, "
        "postal_code_id, created_at, updated_at) "
        "VALUES (:o, :a, 'Firmastraat', '2', :pc, now(), now()) RETURNING id",
        **owners,
    )
    for owner, value, primary in (
        ("person_id", "pieter@example.org", True),
        ("person_id", "pieter.werk@example.org", False),
        ("organization_id", "firma@example.org", True),
    ):
        conn.execute(
            text(
                f"INSERT INTO mdm.contact_details ({owner}, account_id, contact_type_code, "
                "value, is_primary, created_at, updated_at) "
                f"VALUES (:{owner[0]}, :a, 'EMAIL', :v, :pr, now(), now())"
            ),
            {**owners, "v": value, "pr": primary},
        )
    conn.execute(
        text(
            "INSERT INTO mdm.bank_accounts (organization_id, account_id, iban, sort_order, "
            "created_at, updated_at) VALUES (:o, :a, 'BE00 0000 0000 0315', 0, now(), now())"
        ),
        owners,
    )
    conn.execute(
        text(
            "INSERT INTO mdm.organization_identifications (organization_id, scheme, value, "
            "country, sort_order, created_at, updated_at) "
            "VALUES (:o, 'VAT', 'BE0123456749', 'BE', 0, now(), now())"
        ),
        owners,
    )
    conn.execute(
        text(
            "INSERT INTO mdm.external_numbers (person_id, tenant_id, source, external_id, "
            "created_at, updated_at) VALUES (:p, 2, 'ledenadministratie', '31501', now(), now())"
        ),
        owners,
    )
    history = "operation, action, source, recorded_at"
    for person, organization in ((ids["person"], None), (None, ids["org"]), (999_999, None)):
        conn.execute(
            text(
                f"INSERT INTO mdm.address_history ({history}, address_id, person_id, "
                "organization_id, account_id) VALUES ('insert', 'recorded', 'test', now(), "
                "1, :p, :o, :a)"
            ),
            {"p": person, "o": organization, "a": account},
        )
    conn.execute(
        text(
            f"INSERT INTO mdm.contact_detail_history ({history}, contact_detail_id, person_id, "
            "account_id) VALUES ('insert', 'recorded', 'test', now(), 1, :p, :a)"
        ),
        owners,
    )
    conn.execute(
        text(
            f"INSERT INTO mdm.external_number_history ({history}, external_number_id, "
            "person_id, tenant_id) VALUES ('insert', 'recorded', 'test', now(), 1, :p, 2)"
        ),
        owners,
    )
    ids["counts"] = {t: _one(conn, f"SELECT count(*) FROM mdm.{t}") for t in TABLES}
    ids["counts"]["identifications"] = _one(
        conn, "SELECT count(*) FROM mdm.organization_identifications"
    )
    return ids


@pytest.fixture(scope="module")
def migrated():
    with _migrated("cr26_p3", _cases) as (upgrade, engine, ids):
        upgrade()
        yield engine, ids


def _parties(conn, table: str) -> set[int | None]:
    return set(conn.execute(text(f"SELECT party_id FROM mdm.{table}")).scalars())


def test_what_hangs_on_a_person_or_an_organisation_points_at_its_party(migrated):
    engine, ids = migrated
    person, org = ids["person_party"], ids["org_party"]
    with engine.connect() as conn:
        assert _parties(conn, "addresses") == {person, org}
        assert sorted(
            conn.execute(
                text("SELECT party_id, value FROM mdm.contact_details ORDER BY value")
            ).all()
        ) == sorted(
            [
                (org, "firma@example.org"),
                (person, "pieter.werk@example.org"),
                (person, "pieter@example.org"),
            ]
        )
        assert _parties(conn, "bank_accounts") == {org}
        assert _parties(conn, "party_identifications") == {org}
        assert _parties(conn, "external_numbers") == {person}


def test_the_counts_stay_and_the_old_pointers_are_gone(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        for table in TABLES:
            assert _one(conn, f"SELECT count(*) FROM mdm.{table}") == ids["counts"][table], table
        assert (
            _one(conn, "SELECT count(*) FROM mdm.party_identifications")
            == ids["counts"]["identifications"]
        )
        left = conn.execute(
            text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns "
                "WHERE table_schema = 'mdm' AND table_name = ANY(:t) "
                "AND column_name IN ('person_id', 'organization_id')"
            ),
            {"t": [*TABLES, "party_identifications"]},
        ).all()
        assert left == []
        assert _one(conn, "SELECT to_regclass('mdm.organization_identifications') IS NULL")
        checks = conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conname LIKE '%person_xor_organization'")
        ).all()
        assert checks == []


def test_a_history_row_takes_its_owners_party_or_none(migrated):
    engine, ids = migrated
    with engine.connect() as conn:
        assert sorted(_parties(conn, "address_history"), key=lambda p: p or 0) == [
            None,
            ids["person_party"],
            ids["org_party"],
        ]
        assert _parties(conn, "contact_detail_history") == {ids["person_party"]}
        assert _parties(conn, "external_number_history") == {ids["person_party"]}


def test_an_organisation_may_hold_two_addresses_of_one_kind_one_primary(migrated):
    engine, ids = migrated
    insert = text(
        "INSERT INTO mdm.contact_details (party_id, account_id, contact_type_code, value, "
        "is_primary, created_at, updated_at) VALUES (:p, :a, 'EMAIL', :v, :pr, now(), now())"
    )
    with engine.connect() as conn:
        with conn.begin() as tx:
            conn.execute(
                insert,
                {
                    "p": ids["org_party"],
                    "a": ids["account"],
                    "v": "tweede@example.org",
                    "pr": False,
                },
            )
            tx.rollback()
        with conn.begin(), pytest.raises(IntegrityError):
            conn.execute(
                insert,
                {"p": ids["org_party"], "a": ids["account"], "v": "derde@example.org", "pr": True},
            )


def test_one_living_address_per_party(migrated):
    engine, ids = migrated
    with engine.connect() as conn, conn.begin(), pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO mdm.addresses (party_id, account_id, street, house_number, "
                "postal_code_id, created_at, updated_at) "
                "VALUES (:p, :a, 'Tweede', '3', :pc, now(), now())"
            ),
            {"p": ids["person_party"], "a": ids["account"], "pc": ids["postal"]},
        )


def test_the_reporting_views_still_answer(migrated):
    engine, _ids = migrated
    with engine.connect() as conn:
        for view in ("d_address", "d_member"):
            assert _one(conn, f"SELECT count(*) >= 0 FROM reporting.{view}")
