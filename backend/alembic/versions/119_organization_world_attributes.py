"""MDM (#924): een organisatie is ook iets in de wereld, niet alleen een rol.

Koen: *"als ik platform negeer, zijn zowel de account als de units eigenlijk
organisaties. Dan zijn de tenants extensies van organisaties die het systeem
sturen."*

Raak vzw is een organisatie — een vzw, met een adres en een ondernemingsnummer —
die toevallig andere organisaties bezit. Raak Millegem is een organisatie — een
feitelijke vereniging — die toevallig een site heeft. Er zijn geen twee soorten
dingen; er is één ding met twee assen: **wat het is** (rechtsvorm, adres,
rekening) en **welke rol het speelt** (account, unit, platform). Alleen die tweede
bestond. Deze migratie voegt de eerste toe.

**Geen nieuwe entiteit**, en dus ook geen naamkeuze. Een tweede `Organization` in
hetzelfde schema was de duplicatie die dit issue juist opruimt.

**Het adres hangt aan de bestaande adrestabel** en krijgt geen tweede vorm. Daarvoor
moest `person_id` zijn NOT NULL afgeven en komt er een XOR-regel bij: precies één
van `person_id` en `organization_id` is gevuld. Bestaande query's zoeken op
`person_id = X` en zien de nieuwe rijen niet — dat is wat de wijziging contained
maakt. Voor het adres valt niets te migreren: het bestaat vandaag nergens als
gegeven, alleen als tekst in de footer.

**De betaalgegevens verhuizen en de oude rijen verdwijnen.** Niet "verhuisd én
blijven staan voor het geval dat": dan is er een tweede bron gebouwd in plaats van
er één weggenomen. Dit is de eerste van drie omschakelingen; de footer en de
contactgegevens volgen apart.

De rechtsvorm wordt gezet **op basis van `org_type`** en niet per naam geraden:
ACCOUNT is de vzw die de afdelingen bezit, UNIT is een afdeling en dus een
feitelijke vereniging. PLATFORM krijgt niets — het platform is geen vereniging, en
een verzonnen rechtsvorm daar is erger dan een lege kolom.
"""
import sqlalchemy as sa
from alembic import op

revision = "119"
down_revision = "118"
branch_labels = None
depends_on = None


# Het patroon van #779: de code in de databank, het label per taal op één plek.
LEGAL_FORMS = """
INSERT INTO mdm.legal_form_codes (code, language, value, description,
                                  created_at, updated_at)
VALUES
    ('VZW', 'nl', 'vzw', 'Vereniging zonder winstoogmerk', now(), now()),
    ('VZW', 'en', 'Non-profit association', 'Vereniging zonder winstoogmerk', now(), now()),
    ('FEITELIJKE_VERENIGING', 'nl', 'Feitelijke vereniging',
     'Vereniging zonder rechtspersoonlijkheid', now(), now()),
    ('FEITELIJKE_VERENIGING', 'en', 'Unincorporated association',
     'Vereniging zonder rechtspersoonlijkheid', now(), now()),
    ('BEDRIJF', 'nl', 'Bedrijf', 'Handelsvennootschap', now(), now()),
    ('BEDRIJF', 'en', 'Company', 'Handelsvennootschap', now(), now())
ON CONFLICT DO NOTHING
"""


def upgrade() -> None:
    op.create_table(
        "legal_form_codes",
        sa.Column("code", sa.String(30), primary_key=True),
        sa.Column("language", sa.String(5), primary_key=True),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        # GEEN unieke sleutel op `code` alleen, en dat is met opzet. De sleutel is
        # (code, taal), dus zo'n uniciteit laat maar ÉÉN taal per code toe — en
        # daarmee verdwijnen de Engelse labels stilzwijgend bij het invoegen.
        #
        # Dat is precies wat er bij `relation_type_codes` gebeurd is (migratie
        # 017): dezelfde vorm, zes rijen ingevoegd met ON CONFLICT DO NOTHING,
        # drie ervan geland. Die tabel heeft vandaag alleen Nederlandse labels.
        # Losstaande bevinding, hier niet gerepareerd — maar wél de reden dat deze
        # tabel de vorm niet overneemt.
        schema="mdm",
    )
    op.execute(LEGAL_FORMS)

    # ── Wat de organisatie IS ────────────────────────────────────────────────
    for kolom, soort in (
        ("legal_form", sa.String(30)),
        ("enterprise_number", sa.String(20)),
        ("vat_number", sa.String(20)),
        ("email", sa.String(255)),
        ("phone", sa.String(50)),
        ("website", sa.String(255)),
        ("payment_iban", sa.String(40)),
        ("payment_beneficiary", sa.String(255)),
        ("facebook_url", sa.String(255)),
        ("instagram_url", sa.String(255)),
        ("tiktok_url", sa.String(255)),
    ):
        op.add_column("organizations", sa.Column(kolom, soort, nullable=True),
                      schema="mdm")
    # Geen FK naar de codelijst: die zou een uniciteit op `code` alleen vereisen,
    # en dat is precies de vorm die de tweede taal wegduwt. De geldige waarden
    # staan in `LegalForm` in de code en worden daar afgedwongen.

    op.execute("""
        UPDATE mdm.organizations SET legal_form =
            CASE org_type WHEN 'ACCOUNT' THEN 'VZW'
                          WHEN 'UNIT' THEN 'FEITELIJKE_VERENIGING' END
        WHERE org_type IN ('ACCOUNT', 'UNIT')
    """)

    # ── Het adres hangt aan een persoon OF aan een organisatie ───────────────
    op.add_column("addresses",
                  sa.Column("organization_id", sa.Integer(), nullable=True),
                  schema="mdm")
    op.create_foreign_key("fk_addresses_organization", "addresses",
                          "organizations", ["organization_id"], ["id"],
                          source_schema="mdm", referent_schema="mdm")
    op.alter_column("addresses", "person_id", nullable=True, schema="mdm")
    op.create_check_constraint(
        "ck_addresses_person_xor_organization", "addresses",
        "(person_id IS NOT NULL AND organization_id IS NULL) OR "
        "(person_id IS NULL AND organization_id IS NOT NULL)",
        schema="mdm")
    # Dezelfde partiële uniciteit als voor een persoon (migratie 053): één levend
    # adres per organisatie.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_addresses_organization_id "
               "ON mdm.addresses (organization_id) WHERE deleted_at IS NULL")

    # ── De betaalgegevens verhuizen, en de oude rijen gaan weg ───────────────
    bind = op.get_bind()
    for sleutel, kolom in (("payment_iban", "payment_iban"),
                           ("payment_beneficiary", "payment_beneficiary")):
        bind.execute(sa.text(
            f"UPDATE mdm.organizations o SET {kolom} = s.value "
            "FROM kernel_tenant_settings s "
            "WHERE s.tenant_id = o.id AND s.key = :k "
            "  AND COALESCE(s.value, '') <> ''"), {"k": sleutel})
    verplaatst = bind.execute(sa.text(
        "SELECT COUNT(*) FROM kernel_tenant_settings "
        "WHERE key IN ('payment_iban', 'payment_beneficiary')")).scalar()
    bind.execute(sa.text(
        "DELETE FROM kernel_tenant_settings "
        "WHERE key IN ('payment_iban', 'payment_beneficiary')"))
    print(f"  #924: {verplaatst} betaalinstelling(en) verhuisd naar de organisatie "
          "en uit kernel_tenant_settings verwijderd.")


def downgrade() -> None:
    op.drop_constraint("ck_addresses_person_xor_organization", "addresses",
                       schema="mdm")
    op.execute("DROP INDEX IF EXISTS mdm.uq_addresses_organization_id")
    op.drop_constraint("fk_addresses_organization", "addresses", schema="mdm")
    op.drop_column("addresses", "organization_id", schema="mdm")
    for kolom in ("legal_form", "enterprise_number", "vat_number", "email",
                  "phone", "website", "payment_iban", "payment_beneficiary",
                  "facebook_url", "instagram_url", "tiktok_url"):
        op.drop_column("organizations", kolom, schema="mdm")
    op.drop_table("legal_form_codes", schema="mdm")
