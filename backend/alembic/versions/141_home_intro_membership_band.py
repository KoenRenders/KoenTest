"""Home intro becomes the membership-band text (golf 11, #913).

The homepage now shows the membership fee and validity in an intro band at the
top, sourced from the payment helpers — so the seeded default intro, which
spelled out the tariff story in prose (027/028, contact sentence rewritten by
132), duplicates what the band computes. Koen supplied the replacement text
(19 September 2026).

Safety, same contract as 028 and 132: only the exact untouched default is
replaced — an intro a board has rewritten is left alone. The data step reports
how many rows it touched, so "zero touched" never silently passes for success
(see test_golf11_home.py).

Revision ID: 141_2026_09_19_210502
Revises: 140_2026_09_19_190000
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

revision = "141_2026_09_19_210502"
down_revision = "140_2026_09_19_190000"
branch_labels = None
depends_on = None

# The untouched default after 028 (placeholders), 095 (which stripped the
# literal euro signs — the placeholders carry their own since #579) and 132
# (contact sentence). Verified against a scratch database built by the full
# chain, not reconstructed from the seed sources.
OUD = (
    "<p>Heb je zin om lid te worden? Het lidmaatschap bedraagt {{membership_price_full}} "
    "voor een gezin. Van {{half_price_start}} tot {{half_price_end}} betaal je "
    "slechts {{membership_price_half}}. Vanaf {{next_year_from}} ben je meteen ook "
    "lid voor het volgende jaar.</p>"
    "<p>Heb je gewoon een vraag? Klik op “Contacteer ons”.</p>"
)
NIEUW = (
    "<p>Een heel gezin hoort erbij. Word lid en doe een jaar mee. "
    "Samen meer beleven, daar staan we voor. #SamenBeleefJeMeer</p>"
)


def vervang(bind) -> int:
    """Replace the exact untouched default; return the number of rows touched."""
    result = bind.execute(sa.text(
        "UPDATE cms.cms_pages SET content = :nieuw, updated_at = now() "
        "WHERE slug = 'home-intro' AND content = :oud"
    ).bindparams(oud=OUD, nieuw=NIEUW))
    return result.rowcount or 0


def upgrade():
    print(f"141: home-intro vervangen op {vervang(op.get_bind())} rij(en)")


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE cms.cms_pages SET content = :oud, updated_at = now() "
        "WHERE slug = 'home-intro' AND content = :nieuw"
    ).bindparams(oud=OUD, nieuw=NIEUW))
