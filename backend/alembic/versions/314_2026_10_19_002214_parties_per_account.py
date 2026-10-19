"""parties per account

CR-26 phase 1 (#2020): a person, a household and an organisation exist once per
account — the customer of the platform — and what is per tenant is the fact: a
membership of the household at a department, a registration, an order, a
relation. This migration gives every person and organisation a party in the new
`mdm.parties`, moves the party tables from the tenant scope to the account scope
and points the tenant's `account_id` at the account's own party.

Why it is shaped this way:

- **One key for the account** (C4.9). `parties.account_id` is the account's own
  party, itself for an account; `tenants.account_id` is repointed from the
  organisation to that party, so every `account_id` holds the same kind of id.
- **The persons' parties are made first**, then the organisations'. A party id
  and an organisation id are keys of two tables; made in the other order, the
  seeded organisations would get parties with their own ids, and code that
  confused the two would still pass its tests.
- **An organisation's account** (F1, Q26): the account of the tenants that name
  it, as account or as the organisation they show; itself for an account; the
  platform's account for one that no tenant names (an organisation the operator
  made in Organisaties). One named by tenants of two accounts has no account to
  take, and the migration refuses with its ids (measured: none on HDEV, UAT and
  PROD; the refusal is the net, not a path).
- **Addresses and contacts follow what they hang on**, the person's or the
  organisation's account, and so do their history rows. That ends CR-20's seam
  (CR-20 F2, C4.8): no `tenant_id` holds an organisation's id any more.
- **Visibility by fact** (F9, C4.3) is two views: `mdm.household_tenants` — a
  household is at a tenant through a membership row there, an ended or a
  deleted one too, so a household whose years the board removed stays under
  "opgezegd" as before (the master CLI, 19 October 2026) — and `mdm.person_tenants`
  — a person is at a tenant through such a household, or a registration, an
  order or a relation there. `mdm.facts` and the reporting views read them, so
  the rule has one home.
- **One household per person** (F5): a partial unique index on
  `member_persons (person_id)` over the living rows (measured: no person has
  two). **Two departments in one year** (F5): the membership index gains the
  tenant.
- **Expand and contract in one release** (B4, Koen: "a, maar wel in één
  release"): the previous tag cannot run on the result; the safety is the
  checked dump and `raak restore-test` before the deploy.
"""

import logging

from alembic import op

# The id is a timestamp, not a sequence number (#951).
revision = "314_2026_10_19_002214"
down_revision = "313_2026_10_18_180812"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

#: The tables that leave the tenant scope (F1, F5, F13), and how each finds its
#: account: through its tenant, or through what it hangs on.
BY_TENANT = (
    "mdm.members",
    "mdm.member_persons",
    "mdm.person_history",
    "mdm.member_history",
    "mdm.member_person_history",
)
BY_OWNER = (
    "mdm.addresses",
    "mdm.contact_details",
    "mdm.address_history",
    "mdm.contact_detail_history",
)
#: Every table that gets `account_id`, the parties themselves first.
ACCOUNT_SCOPED = (
    "mdm.parties",
    "mdm.persons",
    "mdm.organizations",
    *BY_TENANT,
    *BY_OWNER,
    "mdm.bank_accounts",
)
#: The tables whose `tenant_id` goes.
LEAVING_THE_TENANT = ("mdm.persons", *BY_TENANT, *BY_OWNER)


def _count(sql: str) -> int:
    return op.get_bind().exec_driver_sql(sql).scalar() or 0


def _short(table: str) -> str:
    return table.split(".")[1]


def upgrade() -> None:
    # ── 1. The guard: an organisation named by tenants of two accounts ───────
    op.execute(
        """
        CREATE TEMP TABLE cr26_named ON COMMIT DROP AS
        SELECT account_id AS organization_id, account_id AS account_org FROM mdm.tenants
        UNION
        SELECT organization_id, account_id FROM mdm.tenants
        """
    )
    twice = [
        row[0]
        for row in op.get_bind().exec_driver_sql(
            "SELECT organization_id FROM cr26_named GROUP BY organization_id "
            "HAVING count(DISTINCT account_org) > 1 ORDER BY organization_id"
        )
    ]
    if twice:
        raise RuntimeError(
            "CR-26: these organisations are named by tenants of two accounts and have "
            f"no account to take: {twice}. Give each tenant an organisation of its own "
            "account first."
        )

    # ── 2. The party kinds, a code list in CR-12's shape ─────────────────────
    op.execute(
        """
        CREATE TABLE mdm.party_kind_codes (
            code varchar(20) PRIMARY KEY,
            sort_order integer NOT NULL DEFAULT 0,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE mdm.party_kind_labels (
            code varchar(20) NOT NULL REFERENCES mdm.party_kind_codes (code),
            language varchar(5) NOT NULL REFERENCES mdm.language_codes (code),
            value varchar(150) NOT NULL,
            description varchar(255),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (code, language)
        );
        INSERT INTO mdm.party_kind_codes (code, sort_order) VALUES
            ('PERSON', 1), ('ORGANIZATION', 2);
        INSERT INTO mdm.party_kind_labels (code, language, value) VALUES
            ('PERSON', 'nl', 'Persoon'), ('PERSON', 'en', 'Person'),
            ('ORGANIZATION', 'nl', 'Organisatie'), ('ORGANIZATION', 'en', 'Organisation');
        """
    )

    # ── 3. A party for every person, then for every organisation ─────────────
    op.execute(
        """
        CREATE TABLE mdm.parties (
            id serial PRIMARY KEY,
            account_id integer,
            kind varchar(20) NOT NULL
                CONSTRAINT fk_parties_kind_code REFERENCES mdm.party_kind_codes (code),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        );
        CREATE INDEX ix_parties_deleted_at ON mdm.parties (deleted_at);
        ALTER TABLE mdm.persons ADD COLUMN party_id integer;
        ALTER TABLE mdm.organizations ADD COLUMN party_id integer;
        """
    )
    for table, kind in (("mdm.persons", "PERSON"), ("mdm.organizations", "ORGANIZATION")):
        op.execute(
            f"""
            WITH ordered AS (SELECT id FROM {table} ORDER BY id)
            UPDATE {table} x SET party_id = nextval('mdm.parties_id_seq')
              FROM ordered WHERE ordered.id = x.id
            """
        )
        op.execute(
            f"""
            INSERT INTO mdm.parties (id, kind, created_at, updated_at, deleted_at)
            SELECT party_id, '{kind}', created_at, updated_at, deleted_at FROM {table}
            """
        )

    # ── 4. Each organisation's account (F1, Q26) ─────────────────────────────
    op.execute(
        """
        CREATE TEMP TABLE cr26_org_account ON COMMIT DROP AS
        SELECT DISTINCT organization_id, account_org FROM cr26_named
        """
    )
    unnamed = _count(
        "SELECT count(*) FROM mdm.organizations o "
        "WHERE o.id NOT IN (SELECT organization_id FROM cr26_org_account)"
    )
    log.info("CR-26: %s organisations no tenant names go to the platform's account", unnamed)
    if unnamed and not _count("SELECT count(*) FROM mdm.tenants WHERE kind = 'PLATFORM'"):
        raise RuntimeError("CR-26: organisations no tenant names, and no platform to take them")
    op.execute(
        """
        INSERT INTO cr26_org_account (organization_id, account_org)
        SELECT o.id, (SELECT account_id FROM mdm.tenants WHERE kind = 'PLATFORM')
          FROM mdm.organizations o
         WHERE o.id NOT IN (SELECT organization_id FROM cr26_org_account)
        """
    )
    op.execute("ALTER TABLE mdm.organizations ADD COLUMN account_id integer")
    op.execute(
        """
        UPDATE mdm.organizations o SET account_id = ao.party_id
          FROM cr26_org_account m JOIN mdm.organizations ao ON ao.id = m.account_org
         WHERE m.organization_id = o.id
        """
    )

    # ── 5. The tenant's account is the account's party (C4.9) ────────────────
    op.execute("ALTER TABLE mdm.tenants DROP CONSTRAINT fk_tenants_account")
    op.execute(
        """
        UPDATE mdm.tenants t SET account_id = o.party_id
          FROM mdm.organizations o WHERE o.id = t.account_id
        """
    )
    op.execute(
        "ALTER TABLE mdm.tenants ADD CONSTRAINT fk_tenants_account "
        "FOREIGN KEY (account_id) REFERENCES mdm.parties (id)"
    )

    # ── 6. Every party table gets its account ────────────────────────────────
    for table in ACCOUNT_SCOPED:
        if table not in ("mdm.parties", "mdm.organizations"):
            op.execute(f"ALTER TABLE {table} ADD COLUMN account_id integer")
    op.execute(
        """
        UPDATE mdm.persons p SET account_id = t.account_id
          FROM mdm.tenants t WHERE t.id = p.tenant_id
        """
    )
    for table in ("mdm.persons", "mdm.organizations"):
        op.execute(
            f"""
            UPDATE mdm.parties pa SET account_id = x.account_id
              FROM {table} x WHERE x.party_id = pa.id
            """
        )
    for table in BY_TENANT:
        op.execute(
            f"""
            UPDATE {table} x SET account_id = t.account_id
              FROM mdm.tenants t WHERE t.id = x.tenant_id
            """
        )
    for table in BY_OWNER:
        op.execute(
            f"""
            UPDATE {table} x SET account_id = p.account_id
              FROM mdm.persons p WHERE p.id = x.person_id
            """
        )
        op.execute(
            f"""
            UPDATE {table} x SET account_id = o.account_id
              FROM mdm.organizations o
             WHERE x.account_id IS NULL AND o.id = x.organization_id
            """
        )
    # A history row may name neither (written before #1885 gave it the
    # organisation's id): its tenant_id is a tenant, or an organisation's id on
    # an organisation's row (CR-20 C4.8).
    for table in ("mdm.address_history", "mdm.contact_detail_history"):
        op.execute(
            f"""
            UPDATE {table} x SET account_id = t.account_id
              FROM mdm.tenants t WHERE x.account_id IS NULL AND t.id = x.tenant_id
            """
        )
        op.execute(
            f"""
            UPDATE {table} x SET account_id = o.account_id
              FROM mdm.organizations o WHERE x.account_id IS NULL AND o.id = x.tenant_id
            """
        )
        stray = _count(f"SELECT count(*) FROM {table} WHERE account_id IS NULL")
        if stray:
            log.warning("CR-26: %s rows of %s owned by nobody go to the platform", stray, table)
            op.execute(
                f"""
                UPDATE {table} SET account_id = (
                    SELECT account_id FROM mdm.tenants WHERE kind = 'PLATFORM')
                 WHERE account_id IS NULL
                """
            )
    op.execute(
        """
        UPDATE mdm.bank_accounts b SET account_id = o.account_id
          FROM mdm.organizations o WHERE o.id = b.organization_id
        """
    )
    for table in ACCOUNT_SCOPED:
        missing = _count(f"SELECT count(*) FROM {table} WHERE account_id IS NULL")
        if missing:
            raise RuntimeError(f"CR-26: {missing} rows of {table} found no account")
        op.execute(
            f"""
            ALTER TABLE {table} ALTER COLUMN account_id SET NOT NULL;
            ALTER TABLE {table} ADD CONSTRAINT fk_{_short(table)}_account
                FOREIGN KEY (account_id) REFERENCES mdm.parties (id);
            CREATE INDEX ix_{_short(table)}_account_id ON {table} (account_id);
            """
        )
    for table in ("persons", "organizations"):
        op.execute(
            f"""
            ALTER TABLE mdm.{table} ALTER COLUMN party_id SET NOT NULL;
            ALTER TABLE mdm.{table} ADD CONSTRAINT fk_{table}_party
                FOREIGN KEY (party_id) REFERENCES mdm.parties (id);
            ALTER TABLE mdm.{table} ADD CONSTRAINT uq_{table}_party_id UNIQUE (party_id);
            """
        )

    # ── 7. Visibility by fact, one view (F9, C4.3) ───────────────────────────
    op.execute(
        """
        CREATE VIEW mdm.household_tenants AS
        SELECT DISTINCT tenant_id, member_id
          FROM membership.memberships;
        CREATE VIEW mdm.person_tenants AS
        SELECT ht.tenant_id, mp.person_id
          FROM mdm.member_persons mp
          JOIN mdm.household_tenants ht ON ht.member_id = mp.member_id
         WHERE mp.deleted_at IS NULL
        UNION
        SELECT reg.tenant_id, reg.person_id
          FROM activities.registrations reg
         WHERE reg.person_id IS NOT NULL AND reg.deleted_at IS NULL
        UNION
        SELECT so.tenant_id, so.person_id
          FROM sales.sales_orders so
         WHERE so.person_id IS NOT NULL AND so.deleted_at IS NULL
        UNION
        SELECT op.tenant_id, op.person_id
          FROM mdm.organization_persons op
         WHERE op.deleted_at IS NULL;
        COMMENT ON VIEW mdm.person_tenants IS
            'CR-26 F9: the persons at a tenant by fact. A new kind of fact (an invoice, '
            'a webshop customer) adds a branch here; a person without one is simply not '
            'at the tenant (mdm CONTRACT.md).';
        """
    )

    # ── 8. The reporting views read the facts, not the party's tenant ────────
    # Replaced, not dropped: the columns stay as they were, and so do the
    # comments on the views and their columns (what each view excludes, which
    # column holds a name — the reporting gates read them).
    for sql in _VIEW_SQL:
        op.execute(sql)
    for table in LEAVING_THE_TENANT:
        op.execute(f"ALTER TABLE {table} DROP COLUMN tenant_id")

    # ── 9. One household per person; two departments in one year (F5) ───────
    # Counted first, so a refusal names the persons instead of an index error
    # (measured: none on HDEV, UAT and PROD).
    two = [
        row[0]
        for row in op.get_bind().exec_driver_sql(
            "SELECT person_id FROM mdm.member_persons WHERE deleted_at IS NULL "
            "GROUP BY person_id HAVING count(*) > 1 ORDER BY person_id"
        )
    ]
    if two:
        raise RuntimeError(
            f"CR-26: these persons are in more than one living household: {two}. "
            "One household per person (F5): end the other link first."
        )
    op.execute(
        "CREATE UNIQUE INDEX uq_member_persons_one_household ON mdm.member_persons "
        "(person_id) WHERE deleted_at IS NULL"
    )
    op.execute("DROP INDEX IF EXISTS membership.uq_memberships_member_year")
    op.execute(
        "CREATE UNIQUE INDEX uq_memberships_tenant_member_year ON membership.memberships "
        "(tenant_id, member_id, year) WHERE deleted_at IS NULL"
    )


#: The households of a tenant: a membership row there (`mdm.household_tenants`).
_HOUSEHOLDS = "mdm.household_tenants t"

#: Read by `tests/integration/test_reporting_address.py`, which breaks it on purpose.
D_ADDRESS = """
    CREATE OR REPLACE VIEW reporting.d_address AS
    SELECT pt.tenant_id,
        a.id AS address_id,
        a.person_id,
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
         JOIN mdm.person_tenants pt ON pt.person_id = a.person_id
         LEFT JOIN mdm.postal_codes pc ON pc.id = a.postal_code_id
         LEFT JOIN LATERAL ( SELECT mp2.member_id
               FROM mdm.member_persons mp2
              WHERE mp2.person_id = a.person_id AND mp2.deleted_at IS NULL
              ORDER BY (mp2.relation_type::text = 'HOOFDLID'::text) DESC, mp2.id
             LIMIT 1) mp ON true
      WHERE a.deleted_at IS NULL
    """

_VIEW_SQL = (
    """
    CREATE OR REPLACE VIEW reporting.d_person AS
    SELECT pt.tenant_id,
        p.id AS person_id,
        COALESCE(p.gender_code, 'X'::character varying) AS gender_code,
        COALESCE(gl.value, 'Onbekend'::character varying) AS gender_label,
        EXTRACT(year FROM p.date_of_birth)::integer AS birth_year,
        CASE
            WHEN p.date_of_birth IS NULL THEN 'Onbekend'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 6::double precision THEN '0-5'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 13::double precision THEN '6-12'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 18::double precision THEN '13-17'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 26::double precision THEN '18-25'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 41::double precision THEN '26-40'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 61::double precision THEN '41-60'::text
            WHEN date_part('year'::text, age(CURRENT_DATE::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 76::double precision THEN '61-75'::text
            ELSE '76 of ouder'::text
        END AS age_group,
        COALESCE(mp.relation_type, 'ONBEKEND'::character varying) AS relation_type_code,
        COALESCE(rl.value, mp.relation_type, 'Onbekend'::character varying) AS relation_type_label,
        mp.member_id,
        p.first_name,
        p.last_name,
        TRIM(BOTH FROM concat_ws(' '::text, p.first_name, p.last_name)) AS person_name
       FROM mdm.persons p
         JOIN mdm.person_tenants pt ON pt.person_id = p.id
         LEFT JOIN mdm.gender_labels gl ON gl.code::text = p.gender_code::text AND gl.language::text = 'nl'::text
         LEFT JOIN LATERAL ( SELECT mp2.member_id,
                mp2.relation_type
               FROM mdm.member_persons mp2
              WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
              ORDER BY (mp2.relation_type::text = 'HOOFDLID'::text) DESC, mp2.id
             LIMIT 1) mp ON true
         LEFT JOIN mdm.relation_type_labels rl ON rl.code::text = mp.relation_type::text AND rl.language::text = 'nl'::text
      WHERE p.deleted_at IS NULL AND p.superseded_by_id IS NULL
    """,
    D_ADDRESS,
    f"""
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
         JOIN {_HOUSEHOLDS} ON t.member_id = m.id
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
                 JOIN mdm.addresses ad ON ad.person_id = mp.person_id AND ad.deleted_at IS NULL
              WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
              ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
             LIMIT 1) addr ON true
         LEFT JOIN mdm.postal_codes pc ON pc.id = addr.postal_code_id
         LEFT JOIN LATERAL ( SELECT min(ms2.year) AS first_year
               FROM membership.memberships ms2
              WHERE ms2.member_id = m.id AND ms2.tenant_id = t.tenant_id
                AND ms2.deleted_at IS NULL) ms ON true
      WHERE m.deleted_at IS NULL
    """,
    f"""
    CREATE OR REPLACE VIEW reporting.d_board_member AS
    SELECT DISTINCT t.tenant_id,
        p.id AS board_member_id,
        (p.first_name::text || ' '::text) || p.last_name::text AS board_member_name
       FROM mdm.members m
         JOIN {_HOUSEHOLDS} ON t.member_id = m.id
         JOIN mdm.persons p ON p.id = m.board_member_id AND p.deleted_at IS NULL
      WHERE m.deleted_at IS NULL
    """,
    f"""
    CREATE OR REPLACE VIEW reporting.f_members AS
    SELECT t.tenant_id,
        m.id AS member_id,
        m.created_at,
        m.created_at::date AS date_key,
        hoofd.person_id AS head_person_id,
        (EXISTS ( SELECT 1
               FROM membership.memberships ms
              WHERE ms.member_id = m.id AND ms.tenant_id = t.tenant_id
                AND ms.deleted_at IS NULL)) AS was_ever_member,
        (EXISTS ( SELECT 1
               FROM membership.memberships ms
              WHERE ms.member_id = m.id AND ms.tenant_id = t.tenant_id AND ms.deleted_at IS NULL
                AND ms.is_active AND ms.valid_from IS NOT NULL AND ms.valid_to IS NOT NULL
                AND CURRENT_DATE >= ms.valid_from AND CURRENT_DATE <= ms.valid_to)) AS is_valid_today
       FROM mdm.members m
         JOIN {_HOUSEHOLDS} ON t.member_id = m.id
         LEFT JOIN LATERAL ( SELECT mp.person_id
               FROM mdm.member_persons mp
              WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
              ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
             LIMIT 1) hoofd ON true
      WHERE m.deleted_at IS NULL
    """,
    """
    CREATE OR REPLACE VIEW reporting.f_membership_persons AS
    SELECT DISTINCT ON (ms.tenant_id, mp.person_id, ms.year) ms.tenant_id,
        mp.person_id,
        ms.member_id,
        ms.year,
        ms.membership_id,
        (EXISTS ( SELECT 1
               FROM mdm.member_persons mp2
                 JOIN membership.memberships v ON v.member_id = mp2.member_id AND v.deleted_at IS NULL
              WHERE mp2.person_id = mp.person_id AND mp2.deleted_at IS NULL
                AND v.tenant_id = ms.tenant_id AND v.is_active
                AND v.valid_from IS NOT NULL AND v.valid_to IS NOT NULL
                AND v.valid_from <= CURRENT_DATE AND CURRENT_DATE <= v.valid_to)) AS is_valid_today,
        make_date(ms.year, 1, 1) AS date_key
       FROM ( SELECT memberships.tenant_id,
                memberships.member_id,
                memberships.year,
                min(memberships.id) AS membership_id
               FROM membership.memberships
              WHERE memberships.deleted_at IS NULL
              GROUP BY memberships.tenant_id, memberships.member_id, memberships.year) ms
         JOIN mdm.member_persons mp ON mp.member_id = ms.member_id AND mp.deleted_at IS NULL
         JOIN mdm.persons p ON p.id = mp.person_id AND p.deleted_at IS NULL AND p.superseded_by_id IS NULL
      ORDER BY ms.tenant_id, mp.person_id, ms.year, ms.member_id
    """,
    """
    CREATE OR REPLACE VIEW reporting.f_registrations AS
    SELECT tenant_id,
        registration_id,
        registration_line_id,
        activity_id,
        component_id,
        component_name,
        product_id,
        product_name,
        quantity,
        person_id,
        registered_at,
        date_key,
        registration_type,
        method_code,
        has_team,
        has_contact,
        is_free,
        pay_on_site,
        is_member,
        unit_price,
        contact_name,
        registrant_name,
        registrant_source,
            CASE
                WHEN is_free OR pay_on_site THEN 0::numeric(12,2)
                ELSE (unit_price * quantity::numeric)::numeric(12,2)
            END AS line_amount
       FROM ( SELECT reg.tenant_id,
                reg.id AS registration_id,
                ri.id AS registration_line_id,
                reg.activity_id,
                reg.component_id,
                COALESCE(comp.name, 'Onbekend'::character varying) AS component_name,
                ri.product_id,
                COALESCE(prod.name, 'Geen product'::character varying) AS product_name,
                COALESCE(ri.quantity, 0) AS quantity,
                reg.person_id,
                reg.registered_at,
                reg.registered_at::date AS date_key,
                reg.registration_type,
                COALESCE(reg.payment_method, 'online'::character varying) AS method_code,
                reg.team_name IS NOT NULL AND reg.team_name::text <> ''::text AS has_team,
                reg.contact_email IS NOT NULL AND reg.contact_email::text <> ''::text AS has_contact,
                COALESCE(prod.is_free, true) AS is_free,
                COALESCE(prod.pay_on_site, false) AS pay_on_site,
                mem.is_member,
                    CASE
                        WHEN prod.id IS NULL THEN 0::numeric(12,2)
                        WHEN mem.is_member AND prod.member_price IS NOT NULL AND prod.member_price >= 0::numeric THEN prod.member_price
                        ELSE prod.price
                    END AS unit_price,
                reg.contact_name,
                COALESCE(NULLIF(dp.person_name, ''::text), NULLIF(TRIM(BOTH FROM COALESCE(reg.contact_name, ''::character varying)), ''::text), ''::text) AS registrant_name,
                    CASE
                        WHEN COALESCE(dp.person_name, ''::text) <> ''::text THEN 'Lid'::text
                        WHEN TRIM(BOTH FROM COALESCE(reg.contact_name, ''::character varying)) <> ''::text THEN 'Contactgegeven'::text
                        ELSE 'Onbekend'::text
                    END AS registrant_source
               FROM activities.registrations reg
                 LEFT JOIN activities.registration_items ri ON ri.registration_id = reg.id AND ri.deleted_at IS NULL
                 LEFT JOIN activities.activity_products prod ON prod.id = ri.product_id AND prod.deleted_at IS NULL
                 LEFT JOIN activities.activity_sub_registrations comp ON comp.id = reg.component_id AND comp.deleted_at IS NULL
                 LEFT JOIN reporting.d_person dp ON dp.person_id = reg.person_id AND dp.tenant_id = reg.tenant_id
                 LEFT JOIN LATERAL ( SELECT (EXISTS ( SELECT 1
                               FROM mdm.member_persons mp
                                 JOIN membership.memberships mms ON mms.member_id = mp.member_id AND mms.deleted_at IS NULL
                              WHERE mp.person_id = reg.person_id AND mp.deleted_at IS NULL
                                AND mms.tenant_id = reg.tenant_id AND mms.is_active
                                AND mms.valid_from IS NOT NULL AND mms.valid_to IS NOT NULL
                                AND mms.valid_from <= reg.registered_at::date AND reg.registered_at::date <= mms.valid_to)) AS is_member) mem ON true
              WHERE reg.deleted_at IS NULL) x
    """,
)


def downgrade() -> None:
    # Not reversible: the persons' tenant is gone, and a person's tenant is not
    # derivable from an account. The way back is the dump taken before the
    # deploy (B4, as for CR-20).
    raise NotImplementedError("CR-26: restore the dump taken before the deploy")
