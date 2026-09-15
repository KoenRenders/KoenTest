"""MDM (#945): identificaties, rekeningen en links zijn lijsten, geen kolommen.

Vervolg op #924. De organisatie droeg haar wereld-kenmerken als elf kolommen, en
op drie plaatsen stond één kolom waar de werkelijkheid een lijst is. Koen zag het
bij het nalezen: een tweede btw-nummer in een ander land, een tweede rekening,
een vijfde sociaal netwerk — elk van de drie kostte vandaag een migratie.

De vorm komt van **UBL 2.1 / EN 16931**, het Europese semantische factuurmodel
waarop PEPPOL BIS Billing 3.0 draait, en dus het vocabularium dat deze codebase
hoe dan ook binnenkomt. Drie antwoorden, letterlijk:

- ``cac:PartyIdentification`` en ``cac:PartyTaxScheme`` zijn herhaalbaar, en die
  laatste draagt een eigen registratieland → `mdm.organization_identifications`
  met (schema, waarde, land).
- ``cac:PayeeFinancialAccount`` is een eigen structuur met de IBAN als ``cbc:ID``
  en de BIC in de bankvertakking eronder → `mdm.bank_accounts`.
- ``cac:Contact`` en ``cbc:WebsiteURI`` → `mdm.contact_details`, de tabel die er
  al is, met een ``organization_id`` naast ``person_id``.

``legal_form`` blijft een kolom: ``cac:PartyLegalEntity/cbc:CompanyLegalForm`` is
per definitie enkelvoudig.

**De volgorde is kopiëren → tellen → droppen, en de telling is geen formaliteit.**
Niet droppen omdat de kopie gedraaid heeft, maar omdat ze aantoonbaar iets
opgeleverd heeft. Deze week meldde migratie 121 "0 pagina's ontdubbeld" en meldde
een zoek-en-vervang in `docs.py` succes zonder iets vervangen te hebben; beide
keren zei het gereedschap dat het klaar was. Een kolom droppen ná zo'n stille
nuloperatie is wél onherstelbaar. Postgres voert DDL transactioneel uit, dus een
telling die faalt rolt de hele migratie terug en de kolommen staan er nog.

Geen expand/contract over twee releases: de migraties draaien in `startup.sh` vóór
uvicorn en er is één versie van de code tegelijk.
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "124"
down_revision = "123"
branch_labels = None
depends_on = None


# De zes kolommen die een contactgegeven worden, met de code die ze krijgen.
CONTACT_KOLOMMEN = (
    ("email", "EMAIL"),
    ("phone", "PHONE"),
    ("website", "WEBSITE"),
    ("facebook_url", "FACEBOOK"),
    ("instagram_url", "INSTAGRAM"),
    ("tiktok_url", "TIKTOK"),
)

NIEUWE_CONTACTCODES = (
    ("WEBSITE", "Website", "Canonieke webstek"),
    ("FACEBOOK", "Facebook", "Facebook-pagina"),
    ("INSTAGRAM", "Instagram", "Instagram-profiel"),
    ("TIKTOK", "TikTok", "TikTok-profiel"),
)

# De twee identificatieschema's die we vandaag vullen. ISO 6523/ICD levert de
# vocabulaire; we nemen er alleen uit wat we gebruiken.
SCHEMAS = (
    ("KBO", "Ondernemingsnummer", "Belgisch ondernemingsnummer (KBO)"),
    ("VAT", "Btw-nummer", "Btw-identificatienummer"),
)

IDENTIFICATIE_KOLOMMEN = (("enterprise_number", "KBO"), ("vat_number", "VAT"))

OUDE_KOLOMMEN = (
    "enterprise_number", "vat_number", "email", "phone", "website",
    "payment_iban", "payment_beneficiary", "payment_bic",
    "facebook_url", "instagram_url", "tiktok_url",
)


def _nu():
    return datetime.now(timezone.utc)


def upgrade() -> None:
    bind = op.get_bind()
    nu = _nu()

    # ── De codelijst van de identificatieschema's ────────────────────────────
    # Gesplitst in identiteit + labels, zoals `organization_relation_types` en
    # niet zoals `contact_type_codes`: die laatste sleutelt op (code, taal) met
    # een uniciteit op de code alleen, en dat laat maar één taal toe (#929). Een
    # nieuwe tabel hoeft die fout niet te erven.
    op.create_table(
        "identification_schemes",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="mdm",
    )
    op.create_table(
        "identification_scheme_labels",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("language", sa.String(5), primary_key=True),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["code"], ["mdm.identification_schemes.code"],
                                name="fk_identification_scheme_labels_code"),
        schema="mdm",
    )
    for code, label, omschrijving in SCHEMAS:
        bind.execute(sa.text(
            "INSERT INTO mdm.identification_schemes (code, created_at) "
            "VALUES (:c, :t) ON CONFLICT (code) DO NOTHING"), {"c": code, "t": nu})
        bind.execute(sa.text(
            "INSERT INTO mdm.identification_scheme_labels "
            "(code, language, value, description, created_at, updated_at) "
            "VALUES (:c, 'nl', :v, :d, :t, :t) "
            "ON CONFLICT (code, language) DO NOTHING"),
            {"c": code, "v": label, "d": omschrijving, "t": nu})

    # ── De twee nieuwe tabellen ──────────────────────────────────────────────
    op.create_table(
        "bank_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False, index=True),
        sa.Column("iban", sa.String(40), nullable=False),
        sa.Column("bic", sa.String(20), nullable=True),
        sa.Column("beneficiary", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["mdm.organizations.id"],
                                name="fk_bank_accounts_organization"),
        schema="mdm",
    )
    op.create_table(
        "organization_identifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False, index=True),
        sa.Column("scheme", sa.String(20), nullable=False),
        sa.Column("value", sa.String(50), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["mdm.organizations.id"],
                                name="fk_organization_identifications_organization"),
        sa.ForeignKeyConstraint(["scheme"], ["mdm.identification_schemes.code"],
                                name="fk_organization_identifications_scheme"),
        schema="mdm",
    )

    # ── contact_details opent zich voor organisaties ─────────────────────────
    # Dezelfde XOR als bij `addresses` in #924: precies één eigenaar. `person_id`
    # geeft daarvoor zijn NOT NULL af.
    op.add_column("contact_details",
                  sa.Column("organization_id", sa.Integer(), nullable=True),
                  schema="mdm")
    op.create_foreign_key("fk_contact_details_organization", "contact_details",
                          "organizations", ["organization_id"], ["id"],
                          source_schema="mdm", referent_schema="mdm")
    op.alter_column("contact_details", "person_id", nullable=True, schema="mdm")
    op.create_check_constraint(
        "ck_contact_details_person_xor_organization", "contact_details",
        "(person_id IS NOT NULL AND organization_id IS NULL) OR "
        "(person_id IS NULL AND organization_id IS NOT NULL)",
        schema="mdm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_details_organization_id "
               "ON mdm.contact_details (organization_id)")
    # Eén rij per soort per organisatie: twee Facebook-links zijn een vergissing,
    # geen tweede geval. Partieel, zodat een verwijderde rij de plaats vrijgeeft.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS "
               "uq_contact_details_organization_type "
               "ON mdm.contact_details (organization_id, contact_type_code) "
               "WHERE organization_id IS NOT NULL AND deleted_at IS NULL")

    for code, label, omschrijving in NIEUWE_CONTACTCODES:
        bind.execute(sa.text(
            "INSERT INTO mdm.contact_type_codes "
            "(code, language, value, description, created_at, updated_at) "
            "VALUES (:c, 'nl', :v, :d, :t, :t) "
            "ON CONFLICT (code, language) DO NOTHING"),
            {"c": code, "v": label, "d": omschrijving, "t": nu})

    # ── Kopiëren ─────────────────────────────────────────────────────────────
    # Een rekening bestaat zodra er een IBAN is: zonder IBAN is er geen rekening,
    # ook niet als er een begunstigde ingevuld staat.
    bind.execute(sa.text(
        "INSERT INTO mdm.bank_accounts "
        "(organization_id, iban, bic, beneficiary, sort_order, created_at, updated_at) "
        "SELECT id, payment_iban, payment_bic, payment_beneficiary, 0, :t, :t "
        "FROM mdm.organizations "
        "WHERE COALESCE(payment_iban, '') <> '' AND deleted_at IS NULL"), {"t": nu})

    for kolom, schema in IDENTIFICATIE_KOLOMMEN:
        bind.execute(sa.text(
            "INSERT INTO mdm.organization_identifications "
            "(organization_id, scheme, value, country, sort_order, created_at, updated_at) "
            f"SELECT id, :s, {kolom}, 'BE', 0, :t, :t "
            "FROM mdm.organizations "
            f"WHERE COALESCE({kolom}, '') <> '' AND deleted_at IS NULL"),
            {"s": schema, "t": nu})

    # `tenant_id` krijgt de waarde van `organization_id` omdat de kolom NOT NULL
    # is en er geen betere bestaat — hij is hier NIET de scope. Zie de docstring
    # van `ContactDetail`; organisatierijen worden met `include_all_tenants=True`
    # gelezen en een RLS-policy op `tenant_id` zou ze stil mis-scopen.
    for kolom, code in CONTACT_KOLOMMEN:
        bind.execute(sa.text(
            "INSERT INTO mdm.contact_details "
            "(tenant_id, person_id, organization_id, contact_type_code, value, "
            " is_primary, created_at, updated_at) "
            f"SELECT id, NULL, id, :c, {kolom}, false, :t, :t "
            "FROM mdm.organizations "
            f"WHERE COALESCE({kolom}, '') <> '' AND deleted_at IS NULL"),
            {"c": code, "t": nu})

    # ── Tellen, en pas dan droppen ───────────────────────────────────────────
    _controleer(bind)

    for kolom in OUDE_KOLOMMEN:
        op.drop_column("organizations", kolom, schema="mdm")

    # De naam komt uit de organisatie; de instelling die hem overschreef bestond
    # vóór iemand erom vroeg. Koen op 14 september: "laten we gaan voor de naam
    # die we in organisatie hebben". Komt er ooit een merknaam, dan is dat een
    # kolom op de organisatie (`cbc:RegistrationName` naast de roepnaam).
    namen = bind.execute(sa.text(
        "SELECT COUNT(*) FROM kernel_tenant_settings WHERE key = 'display_name'")
    ).scalar()
    bind.execute(sa.text(
        "DELETE FROM kernel_tenant_settings WHERE key = 'display_name'"))
    print(f"  #945: {namen} display_name-instelling(en) verwijderd; de naam komt "
          "uit de organisatie.")


def _controleer(bind) -> None:
    """Elke kopie moet aantoonbaar iets opgeleverd hebben, per soort.

    Een verschil laat deze migratie falen, en dan rolt Postgres álles terug —
    inclusief de drops hieronder, die nog niet gebeurd zijn. Dat is de hele reden
    dat deze telling vóór de drops staat: daarna is ze een postmortem.
    """
    fouten: list[str] = []

    def vergelijk(wat: str, verwacht_sql: str, echt_sql: str,
                  params: dict | None = None) -> None:
        verwacht = bind.execute(sa.text(verwacht_sql), params or {}).scalar()
        echt = bind.execute(sa.text(echt_sql), params or {}).scalar()
        if verwacht != echt:
            fouten.append(f"{wat}: {verwacht} oude waarde(n), {echt} nieuwe rij(en)")
        else:
            print(f"  #945: {wat} — {echt} rij(en) overgezet.")

    vergelijk(
        "rekeningen",
        "SELECT COUNT(*) FROM mdm.organizations "
        "WHERE COALESCE(payment_iban, '') <> '' AND deleted_at IS NULL",
        "SELECT COUNT(*) FROM mdm.bank_accounts")

    for kolom, schema in IDENTIFICATIE_KOLOMMEN:
        vergelijk(
            f"identificaties {schema}",
            f"SELECT COUNT(*) FROM mdm.organizations "
            f"WHERE COALESCE({kolom}, '') <> '' AND deleted_at IS NULL",
            "SELECT COUNT(*) FROM mdm.organization_identifications "
            "WHERE scheme = :s", {"s": schema})

    for kolom, code in CONTACT_KOLOMMEN:
        vergelijk(
            f"contactgegevens {code}",
            f"SELECT COUNT(*) FROM mdm.organizations "
            f"WHERE COALESCE({kolom}, '') <> '' AND deleted_at IS NULL",
            "SELECT COUNT(*) FROM mdm.contact_details "
            "WHERE organization_id IS NOT NULL AND contact_type_code = :c",
            {"c": code})

    # De BIC reist mee met zijn rekening en heeft daarom geen eigen rij; hij moet
    # wel even goed bewaard zijn.
    vergelijk(
        "BIC's",
        "SELECT COUNT(*) FROM mdm.organizations "
        "WHERE COALESCE(payment_bic, '') <> '' AND COALESCE(payment_iban, '') <> '' "
        "  AND deleted_at IS NULL",
        "SELECT COUNT(*) FROM mdm.bank_accounts WHERE COALESCE(bic, '') <> ''")

    if fouten:
        raise RuntimeError(
            "#945: de kopie klopt niet, er wordt niets gedropt — "
            + "; ".join(fouten))


def downgrade() -> None:
    """De kolommen komen terug, **de data niet**.

    Dat is een halve omkering en ze zegt het zelf: de waarden staan na de upgrade
    in drie tabellen die deze downgrade weggooit. Wie echt terug wil, schrijft ze
    eerst terug — dat is een keuze en geen omkering. Een halve omkering die zich
    als een hele voordoet is erger dan een die eerlijk is over wat ze niet doet.
    """
    op.execute("DROP INDEX IF EXISTS mdm.uq_contact_details_organization_type")
    op.execute("DROP INDEX IF EXISTS mdm.ix_contact_details_organization_id")
    op.drop_constraint("ck_contact_details_person_xor_organization",
                       "contact_details", schema="mdm")
    op.execute("DELETE FROM mdm.contact_details WHERE organization_id IS NOT NULL")
    op.alter_column("contact_details", "person_id", nullable=False, schema="mdm")
    op.drop_constraint("fk_contact_details_organization", "contact_details",
                       schema="mdm")
    op.drop_column("contact_details", "organization_id", schema="mdm")
    op.execute("DELETE FROM mdm.contact_type_codes WHERE code IN "
               "('WEBSITE', 'FACEBOOK', 'INSTAGRAM', 'TIKTOK')")

    op.drop_table("organization_identifications", schema="mdm")
    op.drop_table("bank_accounts", schema="mdm")
    op.drop_table("identification_scheme_labels", schema="mdm")
    op.drop_table("identification_schemes", schema="mdm")

    breedtes = {"enterprise_number": 20, "vat_number": 20, "email": 255,
                "phone": 50, "website": 255, "payment_iban": 40,
                "payment_beneficiary": 255, "payment_bic": 20,
                "facebook_url": 255, "instagram_url": 255, "tiktok_url": 255}
    for kolom in OUDE_KOLOMMEN:
        op.add_column("organizations",
                      sa.Column(kolom, sa.String(breedtes[kolom]), nullable=True),
                      schema="mdm")
