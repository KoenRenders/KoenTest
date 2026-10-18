"""tenants apart from organisations

CR-20 (#1578): one row of `mdm.organizations` carried two things — a site (a
code, a kind, modules, settings, the name the site shows) and a party (a name,
a legal form, identifications, addresses, bank accounts). A site that showed
another organisation's data stood in the list of organisations as an empty
second company that could not be deleted. This migration pulls the two apart:
the site becomes a row of `mdm.tenants`, the organisation keeps the party.

Why it is shaped this way:

- **The same ids** (CR-20 C4.1). Every tenant table shares one thing, the
  integer in `tenant_id`. The tenants are created with the ids their
  organisation rows had, so no `tenant_id` anywhere changes value; the column
  only gains the foreign key it never had.
- **Expand and contract in one release** (CR-20 B4, Koen 4 October 2026): the
  previous tag cannot run on the result. The safety is the checked dump and
  `raak restore-test` before the deploy, and a deploy that stops instead of
  rolling back (#1203).
- **The keys cross schemas** by the one named exception of CR-20 B4 (Koen,
  18 October 2026, Q&A nr. 03 question 1: "a"). They are added NOT VALID and
  then validated, so a row with a tenant that does not exist fails here, with
  the table's name, instead of later. That is for the error, not for the lock:
  the migration is one transaction, so every lock is held until its commit;
  the deploy stops the backend anyway.
- **The `mdm` seam** (CR-20 F2, C4.8): addresses and contacts, with their
  history, get no key — an organisation's own rows carry the organisation's id
  in `tenant_id`, which is no tenant. CR-26 takes those tables out of the
  tenant scope. `organization_persons` carries the tenant that wrote the row
  and gets the key.
- **The meeting circle** (CR-20 F11) hangs on the party the current tenant
  shows. Until now every relation pointed at the PLATFORM row; each is
  repointed to the party its own tenant shows, and keeps its id.
- **The four reporting views** that enumerate the tenants by `org_type` are
  recreated on `mdm.tenants` first: Postgres refuses to drop a column a view
  reads.

What a builder measures before the deploy, on a PROD-sized dump (counts, no
identities): the rows this migration logs below, and the time of the
`VALIDATE CONSTRAINT` steps on the largest tenant tables.
"""

import logging

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "313_2026_10_18_180812"
down_revision = "312_2026_10_16_162902"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

#: Every table with `TenantMixin` on this revision, less the seam below:
#: these get the key to `mdm.tenants`. Written out rather than read from the
#: catalogue, so the migration does tomorrow what it did today.
KEYED = (
    "activities.activities",
    "activities.activity_date_history",
    "activities.activity_dates",
    "activities.activity_history",
    "activities.activity_organisers",
    "activities.activity_products",
    "activities.activity_sub_registrations",
    "activities.component_history",
    "activities.product_history",
    "activities.registration_history",
    "activities.registration_item_history",
    "activities.registration_items",
    "activities.registrations",
    "ai.ai_call_log",
    "ai.chatbot_info",
    "cms.cms_pages",
    "designstudio.design_highlights",
    "designstudio.design_logos",
    "designstudio.design_renditions",
    "designstudio.design_versions",
    "designstudio.designs",
    "designstudio.image_generations",
    "form.form_field_options",
    "form.form_fields",
    "form.form_sections",
    "form.form_submission_answers",
    "form.form_submissions",
    "form.forms",
    "mail.email_log",
    "mdm.external_number_history",
    "mdm.external_numbers",
    "mdm.member_history",
    "mdm.member_person_history",
    "mdm.member_persons",
    "mdm.members",
    "mdm.organization_persons",
    "mdm.person_history",
    "mdm.persons",
    "media.media_assets",
    "media.media_thumbs_up",
    "media.tags",
    "meetings.meeting_attendances",
    "meetings.meeting_extra_recipients",
    "meetings.meeting_files",
    "meetings.meeting_items",
    "meetings.meeting_sections",
    "meetings.meetings",
    "membership.membership_history",
    "membership.memberships",
    "newsletter.audience_activities",
    "newsletter.deliveries",
    "newsletter.drafting_messages",
    "newsletter.letter_events",
    "newsletter.letter_links",
    "newsletter.newsletters",
    "newsletter.subscribers",
    "payment.gateway_payments",
    "payment.payment_record_history",
    "payment.payment_records",
    "pricing.prices",
    "product.product_attachments",
    "product.product_variants",
    "product.products",
    "reporting.export_log",
    "reporting.saved_reports",
    "sales.sales_order_lines",
    "sales.sales_orders",
    "sales.shop_contacts",
    "sales.shop_settings",
    "stock.stock_locations",
    "stock.stock_movements",
    "stock.stock_reservations",
    "workflow.workflow_definitions",
    "workflow.workflow_instances",
    "workflow.workflow_tasks",
    # Not tenant-scoped by the mixin, keyed all the same (CR-20 F1).
    "public.kernel_tenant_settings",
    "auth.user_roles",
)

#: CR-20 F2: no key until CR-26.
SEAM = (
    "mdm.addresses",
    "mdm.address_history",
    "mdm.contact_details",
    "mdm.contact_detail_history",
)

#: The organisation's own details: soft-deleted with an organisation row that
#: was only a borrowed-data tenant (CR-20 F7, C4.4).
DETAILS = (
    "mdm.addresses",
    "mdm.contact_details",
    "mdm.bank_accounts",
    "mdm.organization_identifications",
)

# The three code-list dimensions: the same rows as migration 096 gave them.
_CODE_LISTS = {
    "d_payment_method": "('online','Online',1), ('transfer','Overschrijving',2), ('cash','Cash',3)",
    "d_payment_status": (
        "('pending','In afwachting',1), ('paid','Betaald',2), "
        "('failed','Mislukt',3), ('cancelled','Geannuleerd',4)"
    ),
    "d_membership_status": "('NEW','Nieuw',1), ('RENEWED','Vernieuwd',2), ('LAPSED','Vervallen',3)",
}

_MONTH = """CASE EXTRACT(month FROM d.day)::integer
            WHEN 1 THEN 'januari' WHEN 2 THEN 'februari' WHEN 3 THEN 'maart'
            WHEN 4 THEN 'april' WHEN 5 THEN 'mei' WHEN 6 THEN 'juni'
            WHEN 7 THEN 'juli' WHEN 8 THEN 'augustus' WHEN 9 THEN 'september'
            WHEN 10 THEN 'oktober' WHEN 11 THEN 'november' ELSE 'december'
        END"""

#: The tenants the reporting universe knows: every tenant but the platform, as
#: `org_type = 'UNIT'` said before.
_UNITS = "FROM mdm.tenants t {join} WHERE t.kind <> 'PLATFORM'"


def _count(sql: str) -> int:
    return op.get_bind().exec_driver_sql(sql).scalar() or 0


def _fk_name(table: str) -> str:
    return f"fk_{table.split('.')[1]}_tenant"


def upgrade() -> None:
    # ── 1. The tenants, with the ids their organisation rows had ─────────────
    op.execute(
        """
        CREATE TABLE mdm.tenants (
            id serial PRIMARY KEY,
            code varchar(50) NOT NULL CONSTRAINT uq_tenants_code UNIQUE,
            kind varchar(20) NOT NULL
                CONSTRAINT fk_tenants_kind_code REFERENCES mdm.tenant_kind_codes (code),
            account_id integer NOT NULL
                CONSTRAINT fk_tenants_account REFERENCES mdm.organizations (id),
            organization_id integer NOT NULL
                CONSTRAINT fk_tenants_organization REFERENCES mdm.organizations (id),
            site_name varchar(255),
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_tenants_account_id ON mdm.tenants (account_id)")
    op.execute("CREATE INDEX ix_tenants_organization_id ON mdm.tenants (organization_id)")
    # The account: the parent; a tenant without one is its own account, and the
    # platform's is the party it shows (CR-20 C4.7, #1542). The organisation
    # shown: the one it pointed at (#1550), else its own row. A soft-deleted
    # tenant row keeps its data in every tenant table, so it becomes an inactive
    # tenant rather than a missing one.
    op.execute(
        """
        INSERT INTO mdm.tenants
            (id, code, kind, account_id, organization_id, site_name, is_active,
             created_at, updated_at)
        SELECT o.id, o.code,
               COALESCE(o.kind, CASE WHEN o.org_type = 'PLATFORM' THEN 'PLATFORM'
                                     ELSE 'VERENIGING' END),
               COALESCE(o.parent_id, o.site_organization_id, o.id),
               COALESCE(o.site_organization_id, o.id),
               o.site_name,
               o.is_active AND o.deleted_at IS NULL,
               o.created_at, o.updated_at
          FROM mdm.organizations o
         WHERE o.org_type IN ('UNIT', 'PLATFORM')
        """
    )
    # Past the highest organisation id as well (dev2's read of #2155): until
    # CR-26 the seam rows of C4.8 carry an organisation's id in `tenant_id`, so a
    # new tenant must never take the id of an organisation that exists now. An
    # organisation made later can still take a tenant's id; CR-26 phase 1 closes
    # that window by taking those tables out of the tenant scope.
    op.execute(
        "SELECT setval(pg_get_serial_sequence('mdm.tenants', 'id'), "
        "GREATEST(COALESCE((SELECT max(id) FROM mdm.tenants), 1), "
        "COALESCE((SELECT max(id) FROM mdm.organizations), 1)))"
    )
    log.info("CR-20: %s tenants created", _count("SELECT count(*) FROM mdm.tenants"))

    # ── 2. The modules' key moves to the tenants ─────────────────────────────
    orphans = _count(
        "SELECT count(*) FROM mdm.tenant_modules WHERE tenant_id NOT IN (SELECT id FROM mdm.tenants)"
    )
    if orphans:
        log.warning("CR-20: %s rows of mdm.tenant_modules point at no tenant", orphans)
    op.execute(
        "ALTER TABLE mdm.tenant_modules DROP CONSTRAINT IF EXISTS tenant_modules_tenant_id_fkey"
    )
    op.execute(
        "ALTER TABLE mdm.tenant_modules ADD CONSTRAINT fk_tenant_modules_tenant "
        "FOREIGN KEY (tenant_id) REFERENCES mdm.tenants (id) ON DELETE CASCADE"
    )

    # ── 3. The four reporting views, on the tenants ──────────────────────────
    op.execute(
        f"""
        CREATE OR REPLACE VIEW reporting.d_date AS
        SELECT t.id AS tenant_id,
               d.day::date AS date_key,
               EXTRACT(year FROM d.day)::integer AS year,
               EXTRACT(quarter FROM d.day)::integer AS quarter,
               EXTRACT(month FROM d.day)::integer AS month,
               to_char(d.day, 'YYYY-MM') AS year_month,
               {_MONTH} AS month_label,
               ({_MONTH} || ' ') || EXTRACT(year FROM d.day)::integer::text AS month_year_label
          {
            _UNITS.format(
                join="CROSS JOIN generate_series('2015-01-01'::date, "
                "(CURRENT_DATE + interval '2 years')::date, interval '1 day') d(day)"
            )
        }
        """
    )
    for view, rows in _CODE_LISTS.items():
        op.execute(
            f"""
            CREATE OR REPLACE VIEW reporting.{view} AS
            SELECT t.id AS tenant_id, c.code, c.label, c.sort_order
              {_UNITS.format(join=f"CROSS JOIN (VALUES {rows}) c(code, label, sort_order)")}
            """
        )

    # ── 4. Every tenant table gets its key ───────────────────────────────────
    # A role or a setting on an id that is no tenant — migration 127 put roles
    # on the account Raak vzw — is removed, counted per role and per key (Koen,
    # 18 October 2026, to "Rollen op Raak vzw: kies je (a), (b) of (c)?": "1a").
    # It opened nothing: a role counts in the active workspace only, and that is
    # always a tenant. Measured that day: none on UAT and PROD, three on HDEV.
    for table, column in (("auth.user_roles", "role_code"), ("kernel_tenant_settings", "key")):
        rows = (
            op.get_bind()
            .exec_driver_sql(
                f"DELETE FROM {table} WHERE tenant_id IS NOT NULL "
                "AND tenant_id NOT IN (SELECT id FROM mdm.tenants) "
                f"RETURNING tenant_id, {column}"
            )
            .fetchall()
        )
        counted: dict[tuple, int] = {}
        for tenant_id, value in rows:
            counted[(tenant_id, value)] = counted.get((tenant_id, value), 0) + 1
        for (tenant_id, value), n in sorted(counted.items()):
            log.info(
                "CR-20: %s rows of %s removed: %s on %s, no tenant", n, table, value, tenant_id
            )
    # Any other row that points at no tenant is measured, not repaired: the
    # VALIDATE below names the table that holds one.
    for table in KEYED:
        orphans = _count(
            f"SELECT count(*) FROM {table} WHERE tenant_id IS NOT NULL "
            "AND tenant_id NOT IN (SELECT id FROM mdm.tenants)"
        )
        if orphans:
            log.warning("CR-20: %s rows of %s point at no tenant", orphans, table)
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {_fk_name(table)} "
            "FOREIGN KEY (tenant_id) REFERENCES mdm.tenants (id) NOT VALID"
        )
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {_fk_name(table)}")
    for table in SEAM:
        log.info(
            "CR-20: %s rows of %s carry a tenant_id that is no tenant (the seam, no key)",
            _count(
                f"SELECT count(*) FROM {table} WHERE tenant_id NOT IN (SELECT id FROM mdm.tenants)"
            ),
            table,
        )

    # ── 5. The sites placeholder names a tenant (CR-20 F10) ──────────────────
    # `{{tenants:<account code>}}` becomes `{{tenants:<code of that account's
    # first active tenant>}}`: it lists the sites of that tenant's account, the
    # same cards. An account without an active tenant rendered nothing and is
    # left as it is — an unknown code renders nothing too.
    op.execute(
        """
        CREATE TEMPORARY TABLE cr20_placeholders ON COMMIT DROP AS
        SELECT '{{tenants:' || a.code || '}}' AS old,
               '{{tenants:' || (
                   SELECT t.code FROM mdm.tenants t
                    WHERE t.account_id = a.id AND t.is_active AND t.kind <> 'PLATFORM'
                    ORDER BY t.id LIMIT 1
               ) || '}}' AS new
          FROM mdm.organizations a
         WHERE a.org_type = 'ACCOUNT'
        """
    )
    op.execute("DELETE FROM cr20_placeholders WHERE new IS NULL")
    for table, column, kind in (
        ("cms.cms_pages", "content", "text"),
        ("cms.page_translations", "draft_json", "jsonb"),
        ("cms.page_translations", "published_json", "jsonb"),
        ("cms.cms_page_history", "document", "jsonb"),
    ):
        as_text = column if kind == "text" else f"{column}::text"
        op.execute(
            f"""
            DO $$
            DECLARE p record; n integer := 0; changed integer;
            BEGIN
              FOR p IN SELECT old, new FROM cr20_placeholders LOOP
                UPDATE {table} SET {column} = replace({as_text}, p.old, p.new)::{kind}
                 WHERE strpos({as_text}, p.old) > 0;
                GET DIAGNOSTICS changed = ROW_COUNT;
                n := n + changed;
              END LOOP;
              RAISE NOTICE 'CR-20: % sites placeholders rewritten in {table}.{column}', n;
            END $$
            """
        )

    # ── 6. The meeting circle hangs on the party its tenant shows (F11) ───────
    moved = op.get_bind().exec_driver_sql(
        """
        UPDATE mdm.organization_persons r SET organization_id = t.organization_id
          FROM mdm.tenants t
         WHERE t.id = r.tenant_id AND r.organization_id <> t.organization_id
           AND r.relation_type = 'BOARD_MEETING'
        """
    )
    log.info("CR-20: %s circle relations moved to the party their tenant shows", moved.rowcount)
    log.info(
        "CR-20: %s open circle relations now stand twice for one person and one party",
        _count(
            "SELECT count(*) FROM (SELECT organization_id, person_id FROM mdm.organization_persons "
            "WHERE relation_type = 'BOARD_MEETING' AND end_date IS NULL AND deleted_at IS NULL "
            "GROUP BY 1, 2 HAVING count(*) > 1) d"
        ),
    )

    # ── 7. The organisation rows that were only a borrowed-data tenant ───────
    # (CR-20 F7, C4.6): a tenant that showed another party; its own row was an
    # empty second organisation. The tenant stays; the row is soft-deleted with
    # its details — unless a tenant still names it as its account or its shown
    # organisation (a sibling may have shown it, #1550).
    op.execute(
        """
        CREATE TEMPORARY TABLE cr20_borrowed ON COMMIT DROP AS
        SELECT t.id FROM mdm.tenants t
         WHERE t.organization_id <> t.id
           AND NOT EXISTS (SELECT 1 FROM mdm.tenants o
                            WHERE o.organization_id = t.id OR o.account_id = t.id)
           AND NOT EXISTS (SELECT 1 FROM mdm.organization_persons r
                            WHERE r.organization_id = t.id)
        """
    )
    log.info(
        "CR-20: %s organisation rows were only a borrowed-data tenant",
        _count("SELECT count(*) FROM cr20_borrowed"),
    )
    for table in DETAILS:
        gone = op.get_bind().exec_driver_sql(
            f"UPDATE {table} SET deleted_at = now() "
            "WHERE deleted_at IS NULL AND organization_id IN (SELECT id FROM cr20_borrowed)"
        )
        log.info("CR-20: %s rows of %s soft-deleted with their organisation", gone.rowcount, table)
    op.execute(
        "UPDATE mdm.organizations SET deleted_at = now() "
        "WHERE deleted_at IS NULL AND id IN (SELECT id FROM cr20_borrowed)"
    )

    # ── 8. The organisation keeps the party ──────────────────────────────────
    op.execute(
        "ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS organizations_parent_id_fkey"
    )
    op.execute(
        "ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS fk_organizations_site_organization"
    )
    op.execute(
        "ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS fk_organizations_org_type_code"
    )
    op.execute("ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS fk_organizations_kind_code")
    op.execute("ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS organizations_code_key")
    for column in ("parent_id", "site_organization_id", "org_type", "code", "kind", "site_name"):
        op.execute(f"ALTER TABLE mdm.organizations DROP COLUMN {column}")
    op.execute("DROP TABLE mdm.organization_type_labels")
    op.execute("DROP TABLE mdm.organization_type_codes")


def downgrade() -> None:
    # Not reversible: the tenant columns are gone from the organisations, and
    # which rows were soft-deleted here is no longer told apart from a delete by
    # hand. The way back is the dump taken before the deploy (CR-20 B4, C4.6).
    raise NotImplementedError("CR-20: restore the dump taken before the deploy")
