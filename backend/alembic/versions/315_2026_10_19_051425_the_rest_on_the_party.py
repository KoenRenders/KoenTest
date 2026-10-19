"""the rest on the party

CR-26 phase 3 (#2020): what hangs on a person or an organisation hangs on its
party. Addresses, contact details, bank accounts, the organisation's
identifications and the member numbers get one `party_id`; the pair
`person_id` / `organization_id`, its two CHECKs and the partial indexes per
column go.

Why it is shaped this way:

- **One pointer per row** (F3, C4.10). A party is a person or an organisation,
  so the CHECK that exactly one of two columns is set has nothing left to guard.
  The indexes become one rule per party: one living address
  (`uq_addresses_party_id`), and the person's contact rule for every party —
  several contacts per type, one primary per type — so an organisation may hold
  two e-mail addresses from now on.
- **The identifications widen to the party** (F3): `organization_identifications`
  becomes `party_identifications`, on the account scope with the organisation's
  account. The schemes stay VAT and KBO.
- **The member number stays a fact per department** (F3, Q28): `external_numbers`
  keeps its `tenant_id`, and its `person_id` is replaced by the person's party.
- **The history rows take the pointer of their table** (F13, Q28), filled from
  the columns they had; a row whose person or organisation no longer exists keeps
  no pointer, as it named nothing that exists.
- **The reporting views that read the old columns** (`d_address`, `d_member`) are
  replaced in place before the columns go, with the same columns, so their
  comments stay.
- **Expand and contract in one release** (B4): the previous tag cannot run on the
  result; the safety is the checked dump and `raak restore-test`, as for
  migration 314.
"""

import logging

from alembic import op

# The id is a timestamp, not a sequence number (#951).
revision = "315_2026_10_19_051425"
down_revision = "314_2026_10_19_002214"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

#: The tables that point at a person or an organisation, and which of the two
#: columns each has today. Every one of them gets `party_id` in their place.
POINTERS = {
    "mdm.addresses": ("person_id", "organization_id"),
    "mdm.contact_details": ("person_id", "organization_id"),
    "mdm.bank_accounts": ("organization_id",),
    "mdm.party_identifications": ("organization_id",),
    "mdm.external_numbers": ("person_id",),
}
#: Their history tables (F13): the pointer is a plain column there, no key.
HISTORY = {
    "mdm.address_history": ("person_id", "organization_id"),
    "mdm.contact_detail_history": ("person_id", "organization_id"),
    "mdm.external_number_history": ("person_id",),
}
_OWNER = {"person_id": "mdm.persons", "organization_id": "mdm.organizations"}


def _count(sql: str) -> int:
    return op.get_bind().exec_driver_sql(sql).scalar() or 0


def _short(table: str) -> str:
    return table.split(".")[1]


def _fill(table: str, columns: tuple[str, ...]) -> None:
    """`party_id` from the person's or the organisation's party; soft-deleted
    owners count, a history row names what was."""
    for column in columns:
        op.execute(
            f"""
            UPDATE {table} x SET party_id = o.party_id
              FROM {_OWNER[column]} o
             WHERE x.party_id IS NULL AND o.id = x.{column}
            """
        )


def upgrade() -> None:
    # ── 1. The identifications widen to the party ─────────────────────────────
    op.execute(
        """
        ALTER TABLE mdm.organization_identifications RENAME TO party_identifications;
        -- The names of what came with the table follow it. Only names: where an
        -- environment holds another one, it is left as it is rather than refused.
        ALTER SEQUENCE IF EXISTS mdm.organization_identifications_id_seq
            RENAME TO party_identifications_id_seq;
        ALTER INDEX IF EXISTS mdm.organization_identifications_pkey
            RENAME TO party_identifications_pkey;
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_organization_identifications_scheme'
                          AND conrelid = 'mdm.party_identifications'::regclass) THEN
                ALTER TABLE mdm.party_identifications
                    RENAME CONSTRAINT fk_organization_identifications_scheme
                    TO fk_party_identifications_scheme;
            END IF;
        END $$;
        ALTER TABLE mdm.party_identifications ADD COLUMN account_id integer;
        UPDATE mdm.party_identifications i SET account_id = o.account_id
          FROM mdm.organizations o WHERE o.id = i.organization_id;
        ALTER TABLE mdm.party_identifications ALTER COLUMN account_id SET NOT NULL;
        ALTER TABLE mdm.party_identifications ADD CONSTRAINT fk_party_identifications_account
            FOREIGN KEY (account_id) REFERENCES mdm.parties (id);
        CREATE INDEX ix_party_identifications_account_id
            ON mdm.party_identifications (account_id);
        """
    )

    # ── 2. One `party_id` per row, filled from the pointer it replaces ───────
    for table, columns in {**POINTERS, **HISTORY}.items():
        op.execute(f"ALTER TABLE {table} ADD COLUMN party_id integer")
        _fill(table, columns)
    for table in POINTERS:
        missing = [
            row[0]
            for row in op.get_bind().exec_driver_sql(
                f"SELECT id FROM {table} WHERE party_id IS NULL ORDER BY id LIMIT 20"
            )
        ]
        if missing:
            raise RuntimeError(f"CR-26: rows of {table} point at no party: {missing}")
    for table in HISTORY:
        stray = _count(f"SELECT count(*) FROM {table} WHERE party_id IS NULL")
        if stray:
            log.warning("CR-26: %s rows of %s name no existing owner; no pointer", stray, table)

    # ── 3. The reporting views that read the old columns, replaced in place ──
    op.execute(D_ADDRESS)
    op.execute(D_MEMBER)

    # ── 4. The old pointers go, with their CHECKs, keys and partial indexes ──
    for table, columns in {**POINTERS, **HISTORY}.items():
        for column in columns:
            op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    for table in POINTERS:
        op.execute(
            f"""
            ALTER TABLE {table} ALTER COLUMN party_id SET NOT NULL;
            ALTER TABLE {table} ADD CONSTRAINT fk_{_short(table)}_party
                FOREIGN KEY (party_id) REFERENCES mdm.parties (id);
            CREATE INDEX ix_{_short(table)}_party_id ON {table} (party_id);
            """
        )
    for table in HISTORY:
        op.execute(f"CREATE INDEX ix_{_short(table)}_party_id ON {table} (party_id)")

    # ── 5. One rule per party ─────────────────────────────────────────────────
    op.execute(
        """
        CREATE UNIQUE INDEX uq_addresses_party_id ON mdm.addresses (party_id)
            WHERE deleted_at IS NULL;
        CREATE UNIQUE INDEX uq_contact_details_one_primary_per_type
            ON mdm.contact_details (party_id, contact_type_code)
            WHERE is_primary = true AND deleted_at IS NULL;
        """
    )


#: Read by `tests/integration/test_reporting_address.py`, which breaks it on purpose.
D_ADDRESS = """
    CREATE OR REPLACE VIEW reporting.d_address AS
    SELECT pt.tenant_id,
        a.id AS address_id,
        p.id AS person_id,
        mp.member_id,
        a.street,
        a.house_number,
        NULLIF("substring"(a.house_number::text, '^\\d+'::text), ''::text)::integer AS house_number_num,
        regexp_replace(a.house_number::text, '^\\d+'::text, ''::text) AS house_number_rest,
        COALESCE(a.bus_number, ''::character varying) AS bus_number,
        TRIM(BOTH FROM ((a.street::text || ' '::text) || a.house_number::text) ||
            CASE
                WHEN COALESCE(a.bus_number, ''::character varying)::text <> ''::text THEN ' bus '::text || a.bus_number::text
                ELSE ''::text
            END) AS address_line,
        COALESCE(pc.postal_code, 'Onbekend'::character varying) AS postal_code,
        COALESCE(pc.municipality, 'Onbekend'::character varying) AS municipality
       FROM mdm.addresses a
         JOIN mdm.persons p ON p.party_id = a.party_id
         JOIN mdm.person_tenants pt ON pt.person_id = p.id
         LEFT JOIN mdm.postal_codes pc ON pc.id = a.postal_code_id
         LEFT JOIN LATERAL ( SELECT mp2.member_id
               FROM mdm.member_persons mp2
              WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
              ORDER BY (mp2.relation_type::text = 'HOOFDLID'::text) DESC, mp2.id
             LIMIT 1) mp ON true
      WHERE a.deleted_at IS NULL
    """

D_MEMBER = """
    CREATE OR REPLACE VIEW reporting.d_member AS
    SELECT t.tenant_id,
        m.id AS member_id,
        m.board_member_id,
        COALESCE(hoofd.name, ''::text) AS head_name,
        COALESCE(partner.name, ''::text) AS partner_name,
        COALESCE(sz.size, 0) AS household_size,
            CASE
                WHEN COALESCE(sz.size, 0) = 0 THEN 'Onbekend'::text
                WHEN sz.size = 1 THEN '1 persoon'::text
                WHEN sz.size = 2 THEN '2 personen'::text
                WHEN sz.size >= 3 AND sz.size <= 4 THEN '3-4 personen'::text
                ELSE '5 of meer'::text
            END AS household_size_group,
        COALESCE(pc.postal_code, 'Onbekend'::character varying) AS postal_code,
        COALESCE(pc.municipality, 'Onbekend'::character varying) AS municipality,
        ms.first_year AS member_since_year,
        m.created_at::date AS created_date
       FROM mdm.members m
         JOIN mdm.household_tenants t ON t.member_id = m.id
         LEFT JOIN LATERAL ( SELECT count(*)::integer AS size
               FROM mdm.member_persons mp
              WHERE mp.member_id = m.id AND mp.deleted_at IS NULL) sz ON true
         LEFT JOIN LATERAL ( SELECT (p.first_name::text || ' '::text) || p.last_name::text AS name
               FROM mdm.member_persons mp
                 JOIN mdm.persons p ON p.id = mp.person_id AND p.deleted_at IS NULL
              WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
              ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
             LIMIT 1) hoofd ON true
         LEFT JOIN LATERAL ( SELECT (p.first_name::text || ' '::text) || p.last_name::text AS name
               FROM mdm.member_persons mp
                 JOIN mdm.persons p ON p.id = mp.person_id AND p.deleted_at IS NULL
              WHERE mp.member_id = m.id AND mp.deleted_at IS NULL AND mp.relation_type::text = 'PARTNER'::text
              ORDER BY mp.id
             LIMIT 1) partner ON true
         LEFT JOIN LATERAL ( SELECT ad.postal_code_id
               FROM mdm.member_persons mp
                 JOIN mdm.persons p ON p.id = mp.person_id
                 JOIN mdm.addresses ad ON ad.party_id = p.party_id AND ad.deleted_at IS NULL
              WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
              ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
             LIMIT 1) addr ON true
         LEFT JOIN mdm.postal_codes pc ON pc.id = addr.postal_code_id
         LEFT JOIN LATERAL ( SELECT min(ms2.year) AS first_year
               FROM membership.memberships ms2
              WHERE ms2.member_id = m.id AND ms2.tenant_id = t.tenant_id
                AND ms2.deleted_at IS NULL) ms ON true
      WHERE m.deleted_at IS NULL
    """


def downgrade() -> None:
    # Not reversible in one step, like migration 314 under it: the way back is
    # the dump taken before the deploy (B4).
    raise NotImplementedError("CR-26: restore the dump taken before the deploy")
