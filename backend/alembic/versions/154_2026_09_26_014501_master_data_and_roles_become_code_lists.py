"""master data and roles become code lists

CR-12 phase 2. Eight lists: five that master data already had in the *old*
shape, one that is new, and two that were already split but not quite in the
pattern. Plus the roles, which move out of `public` into `auth`.

**Why the old shape had to go.** `gender_codes`, `contact_type_codes`,
`relation_type_codes` and `legal_form_codes` keyed on `(code, language)` with a
uniqueness on the code alone. That fits exactly one language — it is the bug of
#929, and it is why migration 017 wiped every English label without anybody
noticing. The split is not a preference; it is what a second language needs.

**Two lists only look like they were already done.** `organization_relation_types`
and `identification_schemes` have the split of #924, but their code tables carry
neither `sort_order` nor `is_active`, and their names do not follow
`<list>_codes`. Both are fixed here: renamed and completed. A list that needs a
special case in every gate is not in the pattern.

**What the measurement changed, twice** (read on a freshly migrated database,
26 September 2026):

- **Gender `O` does not exist.** The catalogue says migration 001 seeded it and
  004 added `X`; in fact 004 *renamed* `O` to `X`
  (`UPDATE gender_codes SET code = 'X' ... WHERE code = 'O'`). The list is
  `M`, `F`, `U`, `X`, so only `U` is retired. The retirement below is written to
  tolerate either state, because an environment with older history may differ.
- **`role_codes` holds no relation types.** The catalogue says migrations 004
  and 017 wrongly seeded `HOOFDLID`/`PARTNER`/`KIND` into it; migration 017
  line 70 already *deletes* them. Nothing to drop. The delete below stays as a
  guard and logs what it found, which on a clean chain is zero.

Roles move to `auth` because **master data describes the world and security
vocabulary does not** (§B4.1). That makes `auth` the second foundation domain,
and `workflow.workflow_tasks.required_role` the second allowed cross-schema
foreign key.

`auth.user_roles.role_code` gets a foreign key it never had. The model said
"deliberately no FK, validity is enforced in the service layer" — true for the
old placement in `public`, and one layer too high for something an authorisation
check rests on.
"""
import logging

from alembic import op
import sqlalchemy as sa

from app.domains.auth.codes import ROLE_CODES
from app.domains.mdm.codes import (
    CONTACT_TYPE_CODES,
    GENDER_CODES,
    IDENTIFICATION_SCHEME_CODES,
    LEGAL_FORM_CODES,
    ORGANIZATION_RELATION_TYPE_CODES,
    ORGANIZATION_TYPE_CODES,
    RELATION_TYPE_CODES,
    SOCIAL_NETWORKS,
)
from app.kernel.codes import add_code_fk, create_code_list

logger = logging.getLogger("alembic.runtime.migration")


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick
# "the next number" at the same time pick the same one; two that get a
# timestamp cannot collide. The sequence number sits at the front of the
# FILE NAME, for readability and sorting — alembic does not look at it.
revision = '154_2026_09_26_014501'
down_revision = '153_2026_09_26_001941'
branch_labels = None
depends_on = None

#: The four lists that had the old shape: (list name, code length, seed).
TO_SPLIT = [
    ("gender", 10, GENDER_CODES),
    ("contact_type", 10, CONTACT_TYPE_CODES),
    ("relation_type", 10, RELATION_TYPE_CODES),
    ("legal_form", 30, LEGAL_FORM_CODES),
]

#: The person view currently reads `gender_codes.value` and
#: `relation_type_codes.value` with a `language = 'nl'` filter. After the split
#: those texts live in the label tables, so the view has to follow — and it has
#: to follow before the columns disappear, or Postgres refuses the change.
#:
#: `CREATE OR REPLACE` and not `DROP`: the column list stays identical, only the
#: joins change. That leaves `reporting.f_registrations` — which is built on
#: this view — untouched, and also keeps the comment that the schema gate
#: requires on every view. A DROP would take both along and would give this
#: migration a second copy of two view definitions, exactly the duplication
#: that `CLAUDE.md` names as the bug.
D_PERSON = """
CREATE OR REPLACE VIEW reporting.d_person AS
SELECT
    p.tenant_id,
    p.id                                        AS person_id,
    COALESCE(p.gender_code, 'X')                AS gender_code,
    COALESCE(gl.value, 'Onbekend')              AS gender_label,
    EXTRACT(YEAR FROM p.date_of_birth)::int     AS birth_year,
    CASE
        WHEN p.date_of_birth IS NULL THEN 'Onbekend'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 6 THEN '0-5'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 13 THEN '6-12'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 18 THEN '13-17'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 26 THEN '18-25'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 41 THEN '26-40'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 61 THEN '41-60'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 76 THEN '61-75'
        ELSE '76 of ouder'
    END                                         AS age_group,
    COALESCE(mp.relation_type, 'ONBEKEND')      AS relation_type_code,
    COALESCE(rl.value, mp.relation_type, 'Onbekend') AS relation_type_label,
    mp.member_id,
    p.first_name,
    p.last_name,
    TRIM(CONCAT_WS(' ', p.first_name, p.last_name)) AS person_name
FROM mdm.persons p
LEFT JOIN mdm.gender_labels gl
       ON gl.code = p.gender_code AND gl.language = 'nl'
LEFT JOIN LATERAL (
    SELECT mp2.member_id, mp2.relation_type
    FROM mdm.member_persons mp2
    WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
    ORDER BY (mp2.relation_type = 'HOOFDLID') DESC, mp2.id
    LIMIT 1
) mp ON TRUE
LEFT JOIN mdm.relation_type_labels rl
       ON rl.code = mp.relation_type AND rl.language = 'nl'
WHERE p.deleted_at IS NULL AND p.superseded_by_id IS NULL
"""


def _has_table(schema, name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name, schema=schema)


def _columns(schema: str, table: str) -> set:
    return {c["name"]
            for c in sa.inspect(op.get_bind()).get_columns(table, schema=schema)}


def _create_label_table(name: str, length: int, codes) -> None:
    """The label table next to an existing code table, filled from the declaration.

    **The texts come from the declaration and not from the old table**, because
    those are the labels Koen approved in §B5.3. One difference is real and
    worth naming: the old table wrote `(Meerderjarig) kind` with a capital,
    `ui/__init__.py:_RELATIE_LABELS` wrote `(meerderjarig) kind` with a lower
    case letter. Two places, two spellings; the CR chose the one from the
    dropdown (#779), and that is what a screen shows today.
    """
    bind = op.get_bind()
    if not _has_table("mdm", f"{name}_labels"):
        op.create_table(
            f"{name}_labels",
            sa.Column("code", sa.String(length), primary_key=True),
            sa.Column("language", sa.String(5), primary_key=True),
            sa.Column("value", sa.String(150), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["language"], ["mdm.language_codes.code"],
                                    name=f"fk_{name}_labels_language"),
            schema="mdm",
        )
    for seed in codes:
        for language in ("nl", "en"):
            bind.execute(sa.text(
                f"INSERT INTO mdm.{name}_labels "
                f"(code, language, value, description, created_at, updated_at) "
                f"VALUES (:c, :l, :v, :d, now(), now()) "
                f"ON CONFLICT (code, language) "
                f"DO UPDATE SET value = EXCLUDED.value"),
                {"c": seed.code, "l": language, "v": seed.label(language),
                 "d": seed.description(language)})


def _incoming_fks(name: str) -> list[tuple[str, str, str, str]]:
    """(schema, table, column, constraint name) of every FK to this code table.

    Looked up rather than listed: the names differ per migration that created
    them (`persons_gender_code_fkey` versus `fk_member_persons_relation_type`),
    and a hand-written list is exactly where one goes missing.
    """
    return [tuple(row) for row in op.get_bind().execute(sa.text("""
        SELECT n.nspname, c.relname, a.attname, con.conname
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = con.conrelid
                           AND a.attnum = con.conkey[1]
        WHERE con.contype = 'f'
          AND con.confrelid = to_regclass(:doel)
    """), {"doel": f"mdm.{name}_codes"}).all()]


def _reshape_code_table(name: str, length: int, codes) -> None:
    """The code table into the shape of §B4.2, in place.

    In place and not drop-and-recreate: foreign keys hang on it
    (`persons.gender_code`, `contact_details.contact_type_code`,
    `member_persons.relation_type`), and so does a view. Dropping would take
    all of them along, and recreating them afterwards means rewriting their
    definition here — a second copy of something that already lives elsewhere.
    """
    bind = op.get_bind()
    table = f"mdm.{name}_codes"
    columns = _columns("mdm", f"{name}_codes")
    if "language" in columns:
        # Keep one row per code. The old shape had one per (code, language);
        # which row stays does not matter, because everything but `code` goes.
        bind.execute(sa.text(
            f"DELETE FROM {table} a USING {table} b "
            f"WHERE a.code = b.code AND a.language > b.language"))
        for constraint in (f"{name}_codes_pkey", f"uq_{name}_codes_code"):
            bind.execute(sa.text(
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"))
        for column in ("language", "value", "description", "updated_at"):
            if column in columns:
                op.drop_column(f"{name}_codes", column, schema="mdm")
        bind.execute(sa.text(
            f"ALTER TABLE {table} ADD CONSTRAINT {name}_codes_pkey "
            f"PRIMARY KEY (code)"))
    for column, type_, default in (("sort_order", sa.Integer(), "0"),
                                   ("is_active", sa.Boolean(), sa.true())):
        if column not in _columns("mdm", f"{name}_codes"):
            op.add_column(f"{name}_codes",
                          sa.Column(column, type_, nullable=False,
                                    server_default=default), schema="mdm")
    for seed in codes:
        bind.execute(sa.text(
            f"INSERT INTO {table} (code, sort_order, is_active, created_at) "
            f"VALUES (:c, :s, :a, now()) ON CONFLICT (code) DO UPDATE SET "
            f"sort_order = EXCLUDED.sort_order, is_active = EXCLUDED.is_active"),
            {"c": seed.code, "s": seed.sort_order, "a": seed.is_active})


def _social_flag_per_code(bind) -> dict[str, bool]:
    """`is_social_network` per code, from the table as it stands now (#1160).

    **Why this is more than one SELECT.** `mdm.contact_type_codes` currently
    has a composite key `(code, language)`, and `is_social_network` sits on
    that row — so the flag is stored per LANGUAGE while it means something per
    CODE. With two language rows for one code, a dictionary keyed on the code
    would let the second row silently overwrite the first, and which one that
    is depends on the order Postgres returns.

    After this migration that can no longer happen: the labels move to the
    label table and the code table keeps one row per code. The gap is exactly
    in the TRANSITION — here, at the moment the old rows are read. So this
    counts instead of assuming: on a conflict between language rows the
    migration aborts with the codes in the message, instead of letting one of
    them win. If it finds nothing, THAT goes into the log, because "checked and
    found nothing" is a measurement and a silent assumption is not.
    """
    if "is_social_network" not in _columns("mdm", "contact_type_codes"):
        logger.info("154: contact_type_codes has no is_social_network yet; "
                    "the values come from the declaration")
        return {}
    rows = [(r.code, bool(r.is_social_network)) for r in bind.execute(sa.text(
        "SELECT code, language, is_social_network "
        "FROM mdm.contact_type_codes ORDER BY code, language")).all()]
    return flag_from_rows(rows)


def flag_from_rows(rows: list[tuple[str, bool]]) -> dict[str, bool]:
    """The count itself, separate from the database so it can be tested.

    Public (no underscore) because `tests/test_codes_phase2.py` calls it: a
    guard that can only fire during a real migration is a guard nobody knows
    works.
    """
    flag: dict[str, bool] = {}
    conflicting: dict[str, set[bool]] = {}
    for code, value in rows:
        if code in flag and flag[code] != value:
            conflicting.setdefault(code, {flag[code]}).add(value)
        flag[code] = flag.get(code, value) or value
    if conflicting:
        names = ", ".join(f"{code} ({sorted(values)})"
                          for code, values in sorted(conflicting.items()))
        raise RuntimeError(
            f"154: is_social_network contradicts itself across the language "
            f"rows of {len(conflicting)} code(s): {names}. The flag belongs to "
            f"the code and not to the language, so there is no right choice to "
            f"make here — make the rows agree and run again.")
    logger.info("154: is_social_network read for %d code(s) from %d row(s); "
                "no conflict between language rows", len(flag), len(rows))
    return flag


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. The two lists that almost had the shape (#924) ───────────────────
    for old, new in (("organization_relation_types",
                      "organization_relation_type_codes"),
                     ("identification_schemes", "identification_scheme_codes")):
        if _has_table("mdm", old):
            op.rename_table(old, new, schema="mdm")
        for column, type_, default in (("sort_order", sa.Integer(), "0"),
                                       ("is_active", sa.Boolean(), sa.true())):
            if column not in _columns("mdm", new):
                op.add_column(new, sa.Column(column, type_, nullable=False,
                                             server_default=default),
                              schema="mdm")

    # The helper fills in what is missing: the `en` labels of the
    # identification schemes, which never existed.
    for name, codes, length in (
            ("organization_relation_type", ORGANIZATION_RELATION_TYPE_CODES, 30),
            ("identification_scheme", IDENTIFICATION_SCHEME_CODES, 20)):
        create_code_list(op, schema="mdm", name=name, codes=codes,
                         code_length=length)
        for seed in codes:
            bind.execute(sa.text(
                f"UPDATE mdm.{name}_codes SET sort_order = :s WHERE code = :c"),
                {"s": seed.sort_order, "c": seed.code})
        # The language FK was missing on these two: they predate the language
        # list. Without it a label row can hold any spelling of a language
        # code, which is exactly what the language list rules out.
        fk_name = f"fk_{name}_labels_language"
        if fk_name not in {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(
                f"{name}_labels", schema="mdm")}:
            op.create_foreign_key(fk_name, f"{name}_labels", "language_codes",
                                  ["language"], ["code"],
                                  source_schema="mdm", referent_schema="mdm")

    # ── 2. The label tables, before the code tables ─────────────────────────
    # In this order because the person view below needs the label tables, and
    # the view in turn has to make way before the code columns go.
    for name, length, codes in TO_SPLIT:
        _create_label_table(name, length, codes)

    # ── 3. The view switches over to the labels ─────────────────────────────
    op.execute(D_PERSON)

    # ── 4. Only now the code tables themselves ──────────────────────────────
    social = _social_flag_per_code(bind)

    for name, length, codes in TO_SPLIT:
        # The incoming foreign keys depend on the uniqueness we are replacing,
        # so they come off first and go back on afterwards — with the guard of
        # `add_code_fk`, which first counts whether the data fits.
        incoming = _incoming_fks(name)
        for schema, table, _column, constraint in incoming:
            op.drop_constraint(constraint, table, schema=schema,
                               type_="foreignkey")
        _reshape_code_table(name, length, codes)
        op.create_foreign_key(f"fk_{name}_labels_code", f"{name}_labels",
                              f"{name}_codes", ["code"], ["code"],
                              source_schema="mdm", referent_schema="mdm")
        for schema, table, column, _constraint in incoming:
            add_code_fk(op, f"{schema}.{table}.{column}", "mdm", name)

    if "is_social_network" not in _columns("mdm", "contact_type_codes"):
        op.add_column("contact_type_codes",
                      sa.Column("is_social_network", sa.Boolean(), nullable=True),
                      schema="mdm")
    # Restore the preserved property (#1160), and for a fresh environment the
    # value from the declaration — so both end up with the same result.
    for seed in CONTACT_TYPE_CODES:
        value = social.get(seed.code, seed.code in SOCIAL_NETWORKS)
        bind.execute(sa.text(
            "UPDATE mdm.contact_type_codes SET is_social_network = :v "
            "WHERE code = :c"), {"v": bool(value), "c": seed.code})

    # ── 5. Gender: retire what no longer belongs ────────────────────────────
    # `U` is retired by its own `CodeSeed` (`is_active=False`) — one source,
    # and the declaration is where a reader looks for it. What happens here is
    # the COUNTING the issue asks for, plus the one case that has no seed:
    # `O`. It does not exist — migration 004 renamed it to `X`, contrary to
    # what §B5.3 note 2 says — but an environment with older history may still
    # carry it, so this is written tolerantly rather than conditionally.
    for code in ("U", "O"):
        count = bind.execute(sa.text(
            "SELECT count(*) FROM mdm.persons WHERE gender_code = :c"),
            {"c": code}).scalar_one()
        exists = bind.execute(sa.text(
            "SELECT count(*) FROM mdm.gender_codes WHERE code = :c"),
            {"c": code}).scalar_one()
        print(f"[CR-12 §B5.3 note 2] gender {code!r}: {exists} row(s) in the "
              f"code table, {count} person(s) carry it")
    bind.execute(sa.text(
        "UPDATE mdm.gender_codes SET is_active = false WHERE code = 'O'"))

    # ── 6. The organisation type, new ───────────────────────────────────────
    create_code_list(op, schema="mdm", name="organization_type",
                     codes=ORGANIZATION_TYPE_CODES,
                     fk_from=("mdm.organizations.org_type",), code_length=20)
    # Same reason as for `ck_payment_records_type` in phase 1: the CHECK says
    # what the FK says, and with it in place a fourth type costs a row AND a
    # migration.
    if "ck_org_type" in {c["name"] for c in sa.inspect(bind).get_check_constraints(
            "organizations", schema="mdm")}:
        op.drop_constraint("ck_org_type", "organizations", schema="mdm",
                           type_="check")

    # ── 7. The legal form finally gets its FK ───────────────────────────────
    add_code_fk(op, "mdm.organizations.legal_form", "mdm", "legal_form")

    # ── 8. The roles to auth ────────────────────────────────────────────────
    removed = bind.execute(sa.text(
        "DELETE FROM role_codes WHERE code IN ('HOOFDLID','PARTNER','KIND') "
        "RETURNING code")).all() if _has_table(None, "role_codes") else []
    print(f"[CR-12 §B5.3 note 4] relation types in public.role_codes: "
          f"{len(removed)} deleted")

    create_code_list(op, schema="auth", name="role", codes=ROLE_CODES,
                     fk_from=("auth.user_roles.role_code",
                              "workflow.workflow_tasks.required_role"),
                     code_length=20)

    if _has_table(None, "role_codes"):
        op.drop_table("role_codes")


def downgrade() -> None:
    # Schema, not data. The labels this migration writes are the approved
    # texts of §B5.3; going back restores the old, single-language shape but
    # not the old English labels, because those were already gone — migration
    # 017 had wiped them. That is exactly why this migration exists, so a
    # "complete" reversal would restore a state nobody wants.
    raise NotImplementedError(
        "CR-12 phase 2 cannot be reversed without restoring the single-language "
        "shape that #929 names as the bug. Roll back to the tag before the "
        "release and restore the database from the backup.")
