"""De ingeschrevene bereikt de rapportering — uit twee bronnen, als één kolom (#1135)

Koen vroeg Raakje op een activiteit *"Wie is ingeschreven?"* en kreeg *"Sorry, dat
lukt me even niet."* Het universum kón die vraag niet beantwoorden:
`f_registrations` draagt wel `person_id`, maar geen enkel object ontsluit de
ingeschrevene.

## Het getal dat de vorm bepaalt

Een inschrijving kan gebeuren zonder aanmelding; dan staat de naam als vrije tekst
op de inschrijving zelf. Gemeten op PROD, 132 inschrijvingen: **3** gekoppeld aan
een persoon, **129** alleen een contactnaam, 0 geen van beide.

Een kolom die alleen `person_id` volgt, beantwoordt de vraag dus in 2% van de
gevallen en ziet er volledig uit. Daarom voegt de VIEW de twee bronnen samen:
`registrant_name` is de naam van de gekoppelde persoon als die er is, en anders de
contactnaam.

## Waarom de herkomst ernaast staat

Zonder die kolom lijken twee soorten zekerheid op elkaar: een naam uit de
ledenadministratie en een naam die iemand zelf intypte. `registrant_source` zegt
welke van de twee het is.

**Ze beschrijft de herkomst van de NAAM, niet het bestaan van een koppeling**, en
dat verschil is met opzet. Een inschrijving kán een `person_id` dragen naar iemand
die intussen verwijderd of samengevoegd is; dan levert `d_person` geen rij, valt de
naam terug op de contactnaam, en zou 'Lid' een zekerheid suggereren die er niet is.

## De persoonsnaam komt uit `d_person` en wordt hier niet opnieuw samengesteld

`TRIM(CONCAT_WS(' ', first_name, last_name))` stond na #1132 al op drie plaatsen
(`d_person`, `d_board_member`, `d_activity_organiser`). Een vierde kopie is precies
hoe er op een dag één 'achternaam, voornaam' gaat schrijven. Deze view leest dus
`reporting.d_person.person_name`.

Dat brengt de uitsluitingen van die weergave mee — soft-deleted en samengevoegde
personen — en dat is hier de juiste kant op: van zo iemand hoort de naam niet in
een rapport te verschijnen, en de contactnaam vangt het geval op.

## DROP en niet CREATE OR REPLACE

De bestaande view is `SELECT x.*, <berekening> FROM (…) x`. Een kolom in de
binnenste SELECT landt binnen `x.*` en dus vóór `line_amount`; `CREATE OR REPLACE`
eist dat bestaande kolommen op hun plaats blijven staan en weigert dat.

De DROP staat er **zonder CASCADE**, en dat is een keuze: gemeten hangt er vandaag
geen enkele weergave aan `f_registrations`. Komt die er ooit, dan hoort deze
migratie luid te falen in plaats van haar stil mee te slepen.
"""
from alembic import op


revision = '149_2026_09_21_094703'
down_revision = '148_2026_09_21_085722'
branch_labels = None
depends_on = None


_BINNENSTE = """
    SELECT
        reg.tenant_id,
        reg.id                                  AS registration_id,
        ri.id                                   AS registration_line_id,
        reg.activity_id,
        reg.component_id,
        COALESCE(comp.name, 'Onbekend')         AS component_name,
        ri.product_id,
        COALESCE(prod.name, 'Geen product')     AS product_name,
        COALESCE(ri.quantity, 0)                AS quantity,
        reg.person_id,
        reg.registered_at,
        reg.registered_at::date                 AS date_key,
        reg.registration_type,
        COALESCE(reg.payment_method, 'online')  AS method_code,
        (reg.team_name IS NOT NULL AND reg.team_name <> '')         AS has_team,
        (reg.contact_email IS NOT NULL AND reg.contact_email <> '') AS has_contact,
        COALESCE(prod.is_free, TRUE)            AS is_free,
        COALESCE(prod.pay_on_site, FALSE)       AS pay_on_site,
        mem.is_member,
        CASE
            WHEN prod.id IS NULL THEN 0::numeric(12, 2)
            WHEN mem.is_member AND prod.member_price IS NOT NULL AND prod.member_price >= 0
                THEN prod.member_price
            ELSE prod.price
        END                                     AS unit_price{extra}
    FROM activities.registrations reg
    LEFT JOIN activities.registration_items ri
           ON ri.registration_id = reg.id AND ri.deleted_at IS NULL
    LEFT JOIN activities.activity_products prod
           ON prod.id = ri.product_id AND prod.deleted_at IS NULL
    LEFT JOIN activities.activity_sub_registrations comp
           ON comp.id = reg.component_id AND comp.deleted_at IS NULL{join}
    LEFT JOIN LATERAL (
        SELECT EXISTS (
            SELECT 1
            FROM mdm.member_persons mp
            JOIN membership.memberships mms
              ON mms.member_id = mp.member_id AND mms.deleted_at IS NULL
            WHERE mp.person_id = reg.person_id AND mp.deleted_at IS NULL
              AND mms.is_active
              AND mms.valid_from IS NOT NULL AND mms.valid_to IS NOT NULL
              AND mms.valid_from <= reg.registered_at::date
              AND reg.registered_at::date <= mms.valid_to
        ) AS is_member
    ) mem ON TRUE
    WHERE reg.deleted_at IS NULL
"""

# `dp.person_name` is leeg noch NULL als er een rij is (de weergave TRIMt al), dus
# `NULLIF` vangt de persoon zonder naam net zo goed op als de ontbrekende join.
_EXTRA = """,
        reg.contact_name,
        COALESCE(NULLIF(dp.person_name, ''),
                 NULLIF(TRIM(COALESCE(reg.contact_name, '')), ''),
                 '')                            AS registrant_name,
        CASE
            WHEN COALESCE(dp.person_name, '') <> '' THEN 'Lid'
            WHEN TRIM(COALESCE(reg.contact_name, '')) <> '' THEN 'Contactgegeven'
            ELSE 'Onbekend'
        END                                     AS registrant_source"""

_JOIN = """
    LEFT JOIN reporting.d_person dp
           ON dp.person_id = reg.person_id AND dp.tenant_id = reg.tenant_id"""

_BUITENSTE = """
CREATE OR REPLACE VIEW reporting.f_registrations AS
SELECT
    x.*,
    CASE WHEN x.is_free OR x.pay_on_site THEN 0::numeric(12, 2)
         ELSE (x.unit_price * x.quantity)::numeric(12, 2) END AS line_amount
FROM ({binnenste}) x
"""

F_REGISTRATIONS = _BUITENSTE.format(
    binnenste=_BINNENSTE.format(extra=_EXTRA, join=_JOIN))
F_REGISTRATIONS_ZONDER = _BUITENSTE.format(
    binnenste=_BINNENSTE.format(extra="", join=""))

assert "registrant_name" not in F_REGISTRATIONS_ZONDER, (
    "de downgrade-vorm draagt nog de nieuwe kolommen — dan draait ze de upgrade "
    "niet terug")

#: De tekst van migratie 096, letterlijk — een DROP neemt het commentaar mee en de
#: schema-poort eist dat elke weergave er een heeft.
COMMENTAAR_096 = (
    "Feit inschrijving, een rij per inschrijfregel. Een inschrijving zonder "
    "regels levert één rij met aantal 0. Soft-deleted inschrijvingen, regels "
    "en producten uitgesloten."
)

COMMENTAAR = (
    "COMMENT ON VIEW reporting.f_registrations IS "
    "'" + COMMENTAAR_096 + " Draagt sinds "
    "#1135 de ingeschrevene: `registrant_name` is de naam van de gekoppelde "
    "persoon als die er is en anders de contactnaam, en `registrant_source` zegt "
    "welke van de twee het werd. Naar een taalmodel gaat die naam nooit — de "
    "kolommen dragen de markering persoonsnaam en het object erboven is "
    "getokeniseerd op de INSCHRIJVING, zodat beide soorten één token krijgen.'"
)

#: Dezelfde markering als #1132: het eerste woord leest de poort, de rest is voor
#: wie de kolom in psql tegenkomt.
PERSOONSNAAM_KOLOMMEN = {
    ("f_registrations", "contact_name"): "de naam die de inschrijver zelf intypte",
    ("f_registrations", "registrant_name"): "de ingeschrevene, uit de persoon of uit de contactnaam",
}


def _markeer(tekst_of_none: str | None) -> None:
    for (view, kolom), reden in PERSOONSNAAM_KOLOMMEN.items():
        if tekst_of_none is None:
            op.execute(f"COMMENT ON COLUMN reporting.{view}.{kolom} IS NULL")
        else:
            tekst = f"persoonsnaam — {reden}".replace("'", "''")
            op.execute(f"COMMENT ON COLUMN reporting.{view}.{kolom} IS '{tekst}'")


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting.f_registrations")
    op.execute(F_REGISTRATIONS)
    op.execute(COMMENTAAR)
    _markeer("markeer")


def downgrade() -> None:
    """Herstelt het schema; er is geen data om te herstellen — de view leidt af.

    De markeringen verdwijnen met de kolommen. Het view-commentaar gaat terug naar
    de tekst van vóór dit issue.
    """
    op.execute("DROP VIEW IF EXISTS reporting.f_registrations")
    op.execute(F_REGISTRATIONS_ZONDER)
    op.execute("COMMENT ON VIEW reporting.f_registrations IS '"
               + COMMENTAAR_096 + "'")
