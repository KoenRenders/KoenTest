"""Geen cross-schema FK's (#396/#397, §8-handhaving 2): een FK die twee schema's
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
"""
from sqlalchemy import text

#: The schemas whose code tables may be the target of a cross-schema FK.
FOUNDATION_SCHEMAS = ("mdm", "auth")


def _is_code_table_of_a_foundation(ref_schema: str, ref_table: str) -> bool:
    return ref_schema in FOUNDATION_SCHEMAS and ref_table.endswith("_codes")


def test_no_cross_schema_foreign_keys(db_session):
    rows = db_session.execute(text("""
        SELECT tc.table_schema, tc.table_name, ccu.table_schema AS ref_schema, ccu.table_name AS ref_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.constraint_schema = ccu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema != ccu.table_schema
    """)).fetchall()
    forbidden = [r for r in rows
                 if not _is_code_table_of_a_foundation(r.ref_schema, r.ref_table)]
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
