"""contact types say which of them are social networks

The footer used to decide the other way round: everything it did not recognise
became a social icon (#1160). That put the association's mobile number in the
footer of every public page — with the raw number as `href`, so the browser
read it as a relative path to our own domain.

The list of "not an icon" lived in a UI module, next to the source instead of
in it, and it was already one code short. This column moves the decision to
the source: `contact_type_codes` says which of its codes is a social network,
so a fifth network stays one row (the openness #945 wanted) while an eighth
contact type stays out of the footer by default.

NULL means "not classified yet", deliberately: a migration that adds a contact
type without saying what it is makes `test_every_contact_type_is_classified`
fail, with the code in the message. A NOT NULL DEFAULT false would have decided
silently for whoever adds the next one — and silence is what this issue is
about. NULL renders as "not a network", so the footer is safe either way.
"""
from alembic import op
import sqlalchemy as sa


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '150_2026_09_21_224043'
down_revision = '149_2026_09_21_094703'
branch_labels = None
depends_on = None

# The seven codes that exist today, and what each of them is. The three networks
# are exactly the three that `SOCIALE_CODES` carried in `app/ui/__init__.py`;
# that literal disappears in the same commit, so this is a move and not a copy.
NETWORKS = ("FACEBOOK", "INSTAGRAM", "TIKTOK")
NOT_NETWORKS = ("EMAIL", "MOBILE", "PHONE", "WEBSITE")


def upgrade() -> None:
    bind = op.get_bind()
    kolommen = {r[0] for r in bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'mdm' AND table_name = 'contact_type_codes'"))}
    if "is_social_network" not in kolommen:
        op.add_column("contact_type_codes",
                      sa.Column("is_social_network", sa.Boolean(), nullable=True),
                      schema="mdm")
    op.execute("COMMENT ON COLUMN mdm.contact_type_codes.is_social_network IS "
               "'Does this contact type belong between the social icons in the "
               "public footer? NULL = not classified yet; the test suite fails "
               "on it (#1160).'")

    # Classify the rows that exist. `IN` and not a loop: the set is closed and
    # short, and a row that is somehow missing simply gets no update instead of
    # an error — this migration runs on four environments with the same seeds.
    bind.execute(sa.text(
        "UPDATE mdm.contact_type_codes SET is_social_network = true, "
        "updated_at = now() WHERE code IN :codes AND is_social_network IS DISTINCT FROM true")
        .bindparams(sa.bindparam("codes", NETWORKS, expanding=True)))
    bind.execute(sa.text(
        "UPDATE mdm.contact_type_codes SET is_social_network = false, "
        "updated_at = now() WHERE code IN :codes AND is_social_network IS DISTINCT FROM false")
        .bindparams(sa.bindparam("codes", NOT_NETWORKS, expanding=True)))

    # An unclassified row left behind would be invisible until the gate runs in
    # CI; say it here, where whoever runs the deploy sees it.
    rest = [r[0] for r in bind.execute(sa.text(
        "SELECT code FROM mdm.contact_type_codes WHERE is_social_network IS NULL "
        "ORDER BY code"))]
    if rest:
        print(f"150: contact types not classified as network or not: {', '.join(rest)}")


def downgrade() -> None:
    # Herstelt deze downgrade ook de DATA, of alleen het schema? Zeg het
    # hardop. Een halve omkering die zich als een hele voordoet is erger dan een
    # die eerlijk is over wat ze niet doet.
    #
    # Deze omkering is volledig: de classificatie bestaat alleen in deze kolom,
    # dus met de kolom verdwijnt precies wat de migratie toevoegde. De footer
    # valt dan terug op de literal in de UI-module, die in dezelfde commit weg
    # gaat — een downgrade zonder terugdraai van de code toont dus geen iconen.
    op.drop_column("contact_type_codes", "is_social_network", schema="mdm")
