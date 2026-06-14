"""Maak alle timestamp-kolommen timezone-aware (TIMESTAMPTZ) (#121)

Best practice voor wereldwijde software: sla tijdstippen op als een ondubbelzinnig
UTC-instant (`timestamp with time zone`) i.p.v. een naïeve lokale tijd.

Conversie van bestaande data — de valkuil:
`ALTER COLUMN ... TYPE timestamptz` interpreteert bestaande naïeve waarden
volgens de *sessie-timezone*. Onze code schreef altijd UTC weg (datetime.utcnow /
datetime.now(timezone.utc)), dus we converteren expliciet met
`USING <col> AT TIME ZONE 'UTC'`: "deze naïeve waarde wás al UTC". Zonder die
USING-clausule zou een niet-UTC sessie-timezone het opgeslagen moment verschuiven.

Generiek en idempotent: we reflecteren elke kolom van type
`timestamp without time zone` in het public schema en converteren ze stuk voor
stuk. Na de conversie matchen ze niet meer, dus een rebuild doet niets.

Revision ID: 042
Revises: 041
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def _naive_timestamp_columns(conn):
    """(tabel, kolom) voor elke `timestamp without time zone`-kolom in public."""
    rows = conn.execute(sa.text(
        "SELECT table_name, column_name "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "  AND data_type = 'timestamp without time zone' "
        "ORDER BY table_name, column_name"
    )).fetchall()
    return [(r[0], r[1]) for r in rows]


def upgrade():
    conn = op.get_bind()
    for table, column in _naive_timestamp_columns(conn):
        op.execute(
            f'ALTER TABLE "{table}" '
            f'ALTER COLUMN "{column}" TYPE timestamptz '
            f'USING "{column}" AT TIME ZONE \'UTC\''
        )


def downgrade():
    """Terug naar naïeve UTC-tijd. We strippen de offset door de waarde in UTC
    te lezen (`AT TIME ZONE 'UTC'` op een timestamptz geeft een naïeve UTC-tijd)."""
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT table_name, column_name "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "  AND data_type = 'timestamp with time zone' "
        "ORDER BY table_name, column_name"
    )).fetchall()
    for table, column in [(r[0], r[1]) for r in rows]:
        op.execute(
            f'ALTER TABLE "{table}" '
            f'ALTER COLUMN "{column}" TYPE timestamp '
            f'USING "{column}" AT TIME ZONE \'UTC\''
        )
