"""Geen cross-schema FK's (#396/#397, §8-handhaving 2): een FK die twee schema's
koppelt zou onafhankelijk deployen breken én de merge-redirect onmogelijk maken."""
from sqlalchemy import text


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
    assert rows == [], f"Cross-schema FK's gevonden: {rows}"
