"""Refuses a foreign key that crosses two database schemas · hard · since #397.

Geen cross-schema FK's (#396/#397, §8-handhaving 2): een FK die twee schema's
koppelt zou onafhankelijk deployen breken én de merge-redirect onmogelijk maken.

**One named exception since CR-12 (§B2.4):** a foreign key towards a code table
of a *foundation domain*. There are two of those, `mdm` (master data) and `auth`
(security vocabulary). Neither depends on a business domain — `auth` depends on
`mdm` only — so no cycle can arise, and every domain already imports `mdm.api`.

Without the exception a list that belongs in `mdm` (language, payment method)
would lose the database check that is the reason the list exists: a label row
with language `nl_BE` or `NL` would otherwise be a row nobody ever reads, with
nothing complaining. The exception is narrow on purpose: **only** towards
`<foundation>.<list>_codes`, never towards an ordinary table of those schemas.

**A second named exception since CR-20 (B4; Koen, 18 October 2026, Q&A nr. 03
question 1: "a"):** a foreign key towards the two identity tables of the
kernel, `mdm.tenants` and `mdm.parties` (CR-26). Every domain already depends on
a tenant — `tenant_id` is on every tenant table — and CR-20 gives that column
the key it never had; CR-26 does the same for the buyer of an order. Named one
by one, never "anything in mdm": `mdm.persons` stays refused (the proof below).
"""

from sqlalchemy import text

#: The schemas whose code tables may be the target of a cross-schema FK.
FOUNDATION_SCHEMAS = ("mdm", "auth")


#: The identity tables a cross-schema FK may point at (CR-20 B4), by name.
IDENTITY_TABLES = (("mdm", "tenants"), ("mdm", "parties"))


def _is_code_table_of_a_foundation(ref_schema: str, ref_table: str) -> bool:
    return ref_schema in FOUNDATION_SCHEMAS and ref_table.endswith("_codes")


def _is_an_identity_table(ref_schema: str, ref_table: str) -> bool:
    return (ref_schema, ref_table) in IDENTITY_TABLES


def _allowed(ref_schema: str, ref_table: str) -> bool:
    return _is_code_table_of_a_foundation(ref_schema, ref_table) or _is_an_identity_table(
        ref_schema, ref_table
    )


def test_no_cross_schema_foreign_keys(db_session):
    rows = db_session.execute(
        text("""
        SELECT tc.table_schema, tc.table_name, ccu.table_schema AS ref_schema, ccu.table_name AS ref_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.constraint_schema = ccu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema != ccu.table_schema
    """)
    ).fetchall()
    forbidden = [r for r in rows if not _allowed(r.ref_schema, r.ref_table)]
    assert forbidden == [], f"Cross-schema FK's gevonden: {forbidden}"


def test_the_exception_covers_code_tables_only():
    """The exception is narrow, and it has to stay narrow.

    Measured by violation (the #652 method): a foreign key towards `mdm.persons`
    — an ordinary table of a foundation domain — must still be forbidden.
    Without this test somebody could widen `_is_code_table_of_a_foundation` to
    "anything in mdm", and then the gate guards nothing at all.
    """
    assert _is_code_table_of_a_foundation("mdm", "language_codes")
    assert _is_code_table_of_a_foundation("auth", "role_codes")
    assert not _is_code_table_of_a_foundation("mdm", "persons")
    assert not _is_code_table_of_a_foundation("payment", "payment_status_codes")


def test_the_identity_exception_names_its_two_tables_only():
    """CR-20 B4: the second exception is two tables by name, not a schema.

    Proven red (put back): `_is_an_identity_table` widened to `ref_schema ==
    "mdm"` → the `mdm.persons` assertion below fails, and so does the gate on a
    key towards `mdm.persons` added to a model.
    """
    assert _allowed("mdm", "tenants")
    assert _allowed("mdm", "parties")
    assert not _allowed("mdm", "persons")
    assert not _allowed("mdm", "organizations")
    assert not _allowed("auth", "users")
