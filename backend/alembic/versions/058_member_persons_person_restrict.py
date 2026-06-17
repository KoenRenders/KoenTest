"""FK RESTRICT op member_persons.person_id (#97)

Maakt het ondelete-gedrag van de persoon-koppeling **expliciet en benoemd**.
Tot nu erfde member_persons.person_id de impliciete default (NO ACTION) uit de
initiële schema-migratie (001) — die blokkeert een harde verwijdering óók al,
maar als ongekozen neveneffect. #97 vraagt een bewuste, gedocumenteerde keuze.

Bewuste keuze: **RESTRICT** (niet CASCADE). De app hard-delete nooit een persoon
sinds soft-delete (#166); de DB is hier de laatste vangnet tegen directe scripts.
member_persons heeft eigen soft-delete + history en mag niet stil mee verdwijnen
wanneer een persoon hard wordt verwijderd — een persoon kan dus niet verdwijnen
zolang er gezinskoppelingen aan hangen.

Idempotent: de bestaande FK (anonieme naam uit 001) wordt op referred_table +
kolom opgezocht en gedropt; daarna komt de benoemde RESTRICT-FK. Draait de
migratie toch twee keer, dan blijft de benoemde FK staan en gebeurt er niets.

Revision ID: 058
Revises: 057
"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

_NEW_FK = "fk_member_persons_person_restrict"


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)

    existing = insp.get_foreign_keys("member_persons")
    if any(fk.get("name") == _NEW_FK for fk in existing):
        return  # al toegepast

    for fk in existing:
        if fk.get("referred_table") == "persons" and "person_id" in fk.get("constrained_columns", []):
            if fk.get("name"):
                op.drop_constraint(fk["name"], "member_persons", type_="foreignkey")
            break

    op.create_foreign_key(
        _NEW_FK,
        "member_persons",
        "persons",
        ["person_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint(_NEW_FK, "member_persons", type_="foreignkey")
    op.create_foreign_key(
        None,
        "member_persons",
        "persons",
        ["person_id"],
        ["id"],
    )
