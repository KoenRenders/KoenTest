"""Adres enkel op het hoofdlid (= gezinsadres) (#125)

Tot nu kreeg elk gezinslid een eigen adres (de import dupliceerde het gezinsadres
naar elke persoon). Voortaan hoort het adres enkel bij het hoofdlid; overige
gezinsleden hebben geen adres meer.

Veilig: gezinnen werden bij de import gegroepeerd op adres, dus alle adressen
binnen één gezin zijn identiek — verwijderen verliest geen unieke gegevens.

Stap 1 (vangnet): heeft een hoofdlid geen adres maar een ander gezinslid wel,
kopieer dat adres eerst naar het hoofdlid.
Stap 2: verwijder de adressen van alle niet-hoofdleden.

Revision ID: 044
Revises: 043
Create Date: 2026-06-14
"""
from alembic import op
from sqlalchemy import text

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Stap 1 — vangnet: hoofdleden zonder adres, terwijl een gezinslid er wél een heeft.
    missing = conn.execute(text(
        "SELECT m.id AS member_id, hp.person_id AS hoofdlid_person_id "
        "FROM members m "
        "JOIN member_persons hp ON hp.member_id = m.id AND hp.relation_type = 'HOOFDLID' "
        "WHERE NOT EXISTS (SELECT 1 FROM addresses a WHERE a.person_id = hp.person_id)"
    )).fetchall()
    for member_id, hoofdlid_pid in missing:
        src = conn.execute(text(
            "SELECT a.street, a.house_number, a.bus_number, a.postal_code_id "
            "FROM addresses a "
            "JOIN member_persons mp ON mp.person_id = a.person_id "
            "WHERE mp.member_id = :mid LIMIT 1"
        ), {"mid": member_id}).fetchone()
        if src:
            conn.execute(text(
                "INSERT INTO addresses (person_id, street, house_number, bus_number, "
                "postal_code_id, created_at, updated_at) "
                "VALUES (:pid, :street, :hn, :bus, :pcid, now(), now())"
            ), {"pid": hoofdlid_pid, "street": src[0], "hn": src[1], "bus": src[2], "pcid": src[3]})

    # Stap 2 — verwijder adressen van personen die nergens HOOFDLID zijn.
    conn.execute(text(
        "DELETE FROM addresses "
        "WHERE person_id NOT IN ("
        "  SELECT person_id FROM member_persons WHERE relation_type = 'HOOFDLID'"
        ")"
    ))


def downgrade():
    # Herstel de oude vorm: kopieer het hoofdlid-adres terug naar elk gezinslid
    # zonder adres.
    conn = op.get_bind()
    rows = conn.execute(text(
        "SELECT mp.person_id, a.street, a.house_number, a.bus_number, a.postal_code_id "
        "FROM member_persons mp "
        "JOIN member_persons hp ON hp.member_id = mp.member_id AND hp.relation_type = 'HOOFDLID' "
        "JOIN addresses a ON a.person_id = hp.person_id "
        "WHERE mp.relation_type <> 'HOOFDLID' "
        "  AND NOT EXISTS (SELECT 1 FROM addresses a2 WHERE a2.person_id = mp.person_id)"
    )).fetchall()
    for pid, street, hn, bus, pcid in rows:
        conn.execute(text(
            "INSERT INTO addresses (person_id, street, house_number, bus_number, "
            "postal_code_id, created_at, updated_at) "
            "VALUES (:pid, :street, :hn, :bus, :pcid, now(), now())"
        ), {"pid": pid, "street": street, "hn": hn, "bus": bus, "pcid": pcid})
