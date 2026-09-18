"""Home intro: the contact sentence names the button, not a form (F24, #996).

The seeded placeholder text said "Gebruik het contactformulier hieronder",
but the home page has no inline contact form — it has the "Contacteer ons"
button linking to /berichten. Found by the round-2 external review (#785).

Only the exact old sentence is replaced, in every tenant's home-intro that
still carries it: text an owner edited around it is preserved, and a fully
rewritten intro is left alone. The data step lives in a module function so
the test runs exactly the SQL a host runs.
"""
import sqlalchemy as sa
from alembic import op

revision = "132_2026_09_17_104125"
down_revision = "131_2026_09_17_073104"
branch_labels = None
depends_on = None

OUD = "<p>Heb je gewoon een vraag? Gebruik het contactformulier hieronder.</p>"
NIEUW = "<p>Heb je gewoon een vraag? Klik op “Contacteer ons”.</p>"


def vervang(bind) -> int:
    """Vervang de oude zin waar hij nog staat; geeft het aantal geraakte
    rijen terug zodat een aanroeper kan vaststellen dát er iets veranderde."""
    resultaat = bind.execute(sa.text(
        "UPDATE cms.cms_pages SET content = replace(content, :oud, :nieuw), "
        "updated_at = now() "
        "WHERE slug = 'home-intro' AND content LIKE :patroon"
    ).bindparams(oud=OUD, nieuw=NIEUW, patroon=f"%{OUD}%"))
    return resultaat.rowcount


def upgrade() -> None:
    vervang(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE cms.cms_pages SET content = replace(content, :nieuw, :oud) "
        "WHERE slug = 'home-intro' AND content LIKE :patroon"
    ).bindparams(oud=OUD, nieuw=NIEUW, patroon=f"%{NIEUW}%"))
