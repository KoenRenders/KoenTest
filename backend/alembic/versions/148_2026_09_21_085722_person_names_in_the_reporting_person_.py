"""Namen in de personen-view, en een markering die zegt welke kolommen er een dragen (#1132)

Beslist door Koen op 21 september 2026: *"Ik vind dat in de views de naam en
voornaam etc wel moet staan, maar Raakje mag het niet naar Mistral sturen."*

`d_person` droeg bewust géén naam — bescherming door afwezigheid. Die vorm kostte
twee dingen. De terugvertaling van `persoon-90` moest zoeken in elke view die
toevallig een naam droeg (twee takken, en één erbij per nieuwe rol). En
`scrub_question` — die een naam die de beheerder TYPT vervangt door het token van
die entiteit — bouwde zijn namenlijst uit diezelfde beperkte bronnen.

**Eén premisse uit #1132 is gemeten en klopt niet, en dat hoort hier te staan.**
Het issue zegt dat de naadwachter iemand die nergens in de rapportering staat "ook
niet herkent". Dat geldt voor `scrub_question`, niet voor de wachter: die krijgt
zijn namen van `mdm.person_name_parts`, dat élke persoon van de afdeling leest
(`mdm/service.py:269`). De blokkerende bescherming dekte dus al iedereen.

Wat hier werkelijk verandert is dus niet de privacygrens maar de BRUIKBAARHEID:
typte je de naam van iemand die geen bestuurslid of organisator was, dan liet
`scrub_question` hem staan en blokkeerde de naadwachter de oproep — de naam lekte
niet, de vraag mislukte. Nu wordt diezelfde naam `persoon-90` en werkt de vraag.

## De markering, en waarom het een COMMENT is

Met namen in de views moet iets tegenhouden dat een universe-object ze als `PLAIN`
naar een taalmodel stuurt. Die poort moet weten welke kolommen een PERSOONSnaam
dragen, en dat is de eigenlijke ontwerpvraag van #1132.

**Een naamgevingsafspraak op `_name` is gemeten en afgewezen.** Van de twintig
objecten die vandaag uit een kolom met "name" of "label" in de naam lezen, zijn er
vijftien terecht `PLAIN`: `activity_name`, `form_name`, `product_name`,
`gender_label`, `payment_status.label`. Een activiteit heeft ook een naam. En
andersom draagt `payable_label` wél een persoonsnaam zónder "name" in de kolomnaam
— dat is precies het geval dat een achtervoegselregel mist, en een poort die dat
geval mist is groen terwijl er niets bewaakt wordt.

Het onderscheid zit dus niet IN de kolomnaam en moet verklaard worden. Dat gebeurt
hier, in dezelfde opdracht die de kolom maakt: een kolom die een persoonsnaam draagt
krijgt een COMMENT dat begint met `persoonsnaam`. De poort
(`test_universe_person_names.py`) leest die markeringen uit `pg_description` — uit de
databank zelf, niet uit een lijst die iemand bijhoudt. Verdwijnt de kolom, dan
verdwijnt haar markering mee; komt er een kolom bij, dan staat de markering in
dezelfde `CREATE OR REPLACE` als de kolom.

Het markeerwoord staat VOORAAN en de uitleg erachter, zodat dezelfde tekst leesbaar
is in psql en toetsbaar door de poort. Komt er ooit een omschrijving op élke kolom
(uitgesteld werk, bewust), dan past die achter het markeerwoord zonder deze poort te
raken.

## Wat dit niet doet

Het model krijgt niets extra te zien: het krijgt nog altijd tokens, nooit namen. De
grens verschuift van *"het staat er niet"* naar *"het staat er wel, en de poort
bewaakt waar het heen mag"*. En geen enkel bestaand rapport verandert: de kolommen
bestaan, maar een rapport toont alleen wat een universe-object declareert — er komt
hier geen object bij.
"""
from alembic import op


revision = '148_2026_09_21_085722'
down_revision = '147_2026_09_20_165122'
branch_labels = None
depends_on = None


# `CREATE OR REPLACE` en geen DROP: de twee kolommen komen er ACHTERAAN bij, en dat
# is precies wat Postgres bij een replace toelaat. Een drop zou CASCADE vragen en
# elke grant en afhankelijkheid meenemen voor niets.
#
# De naam wordt samengesteld met `TRIM(CONCAT_WS(...))` en niet met `||`: bij een
# ontbrekende voornaam levert `||` NULL voor de hele uitdrukking, en dan verdwijnt
# ook de achternaam. Dezelfde vorm als `d_activity_organiser` (#1077).
D_PERSON = """
CREATE OR REPLACE VIEW reporting.d_person AS
SELECT
    p.tenant_id,
    p.id                                        AS person_id,
    COALESCE(p.gender_code, 'X')                AS gender_code,
    COALESCE(gc.value, 'Onbekend')              AS gender_label,
    EXTRACT(YEAR FROM p.date_of_birth)::int     AS birth_year,
    CASE
        WHEN p.date_of_birth IS NULL THEN 'Onbekend'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 6 THEN '0-5'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 13 THEN '6-12'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 18 THEN '13-17'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 26 THEN '18-25'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 41 THEN '26-40'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 61 THEN '41-60'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 76 THEN '61-75'
        ELSE '76 of ouder'
    END                                         AS age_group,
    COALESCE(mp.relation_type, 'ONBEKEND')      AS relation_type_code,
    COALESCE(rt.value, mp.relation_type, 'Onbekend') AS relation_type_label,
    mp.member_id,
    p.first_name,
    p.last_name,
    TRIM(CONCAT_WS(' ', p.first_name, p.last_name)) AS person_name
FROM mdm.persons p
LEFT JOIN mdm.gender_codes gc
       ON gc.code = p.gender_code AND gc.language = 'nl'
LEFT JOIN LATERAL (
    SELECT mp2.member_id, mp2.relation_type
    FROM mdm.member_persons mp2
    WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
    ORDER BY (mp2.relation_type = 'HOOFDLID') DESC, mp2.id
    LIMIT 1
) mp ON TRUE
LEFT JOIN mdm.relation_type_codes rt
       ON rt.code = mp.relation_type AND rt.language = 'nl'
WHERE p.deleted_at IS NULL AND p.superseded_by_id IS NULL
"""

# Een DROP neemt het commentaar mee, en `CREATE OR REPLACE` laat het staan — maar
# de tekst klopt niet meer zodra de view namen draagt. De schema-poort toetst dát
# er een commentaar is, niet of het nog waar is; dat laatste is aan wie de view
# wijzigt.
VIEW_COMMENTAAR = (
    "COMMENT ON VIEW reporting.d_person IS "
    "'Persoon, een rij per persoon. Soft-deleted en samengevoegde personen "
    "uitgesloten. Leeftijdsgroep = de leeftijd vandaag. Draagt sinds CR-06 "
    "§7.3 persoonsgegevens waar de universe ze nodig heeft; de grens ligt bij de "
    "rol die het scherm bereikt. Draagt sinds #1132 ook voornaam, achternaam en "
    "de samengestelde naam: die maken de terugvertaling van een token één "
    "opzoeking en laten de naadwachter iedereen herkennen in plaats van alleen "
    "bestuursleden en organisatoren. Naar een taalmodel gaan ze nooit — de "
    "kolommen dragen de markering persoonsnaam en een poort weigert een object "
    "dat erop leest en PLAIN declareert.'"
)

#: De kolommen in `reporting` die een PERSOONSnaam dragen, elk met de reden. Het
#: eerste woord is het markeerwoord dat de poort leest; de rest is voor wie het in
#: psql tegenkomt. Hier staan ook de vier kolommen die al bestonden: de markering
#: beschrijft de DATA, en die was er al vóór #1132 — een markering die alleen de
#: nieuwe kolommen kent, zou een poort opleveren die de oudste lekken niet ziet.
PERSOONSNAAM_KOLOMMEN = {
    ("d_person", "first_name"): "de voornaam zoals ze in de administratie staat",
    ("d_person", "last_name"): "de achternaam zoals ze in de administratie staat",
    ("d_person", "person_name"): "voornaam en achternaam samen, voor de terugvertaling van een token",
    ("d_member", "head_name"): "de naam van het hoofdlid van dit gezin",
    ("d_member", "partner_name"): "de naam van de partner in dit gezin",
    ("d_board_member", "board_member_name"): "de naam van het bestuurslid",
    ("d_activity_organiser", "organiser_name"): "de naam van de organisator",
    ("f_payments", "payable_label"): "bevat de naam van de inschrijver of het hoofdlid",
}


#: De view zoals migratie 106 hem achterliet, letterlijk — het ijkpunt van de
#: downgrade. Uitgeschreven en niet afgeleid uit `D_PERSON` met een string-vervanging:
#: zo'n vervanging vindt op een dag niets meer en levert dan stil dezelfde view op
#: als de upgrade, wat een downgrade is die zegt dat ze iets deed.
D_PERSON_ZONDER_NAAM = D_PERSON.replace(
    "    mp.member_id,\n"
    "    p.first_name,\n"
    "    p.last_name,\n"
    "    TRIM(CONCAT_WS(' ', p.first_name, p.last_name)) AS person_name\n",
    "    mp.member_id\n",
)
assert "first_name" not in D_PERSON_ZONDER_NAAM.split("FROM mdm.persons")[0], (
    "de downgrade-vorm draagt nog naamkolommen — de vervanging hierboven raakte "
    "niets, en dan draait de downgrade de upgrade niet terug")

#: Het commentaar van vóór #1132, voor diezelfde downgrade.
VIEW_COMMENTAAR_ZONDER_NAAM = (
    "COMMENT ON VIEW reporting.d_person IS "
    "'Persoon, een rij per persoon. Soft-deleted en samengevoegde personen "
    "uitgesloten. Leeftijdsgroep = de leeftijd vandaag. Draagt sinds CR-06 "
    "§7.3 (10 september 2026) persoonsgegevens waar de universe ze nodig "
    "heeft; de grens ligt bij de rol die het scherm bereikt.'"
)


def _markeer() -> None:
    for (view, kolom), reden in PERSOONSNAAM_KOLOMMEN.items():
        tekst = f"persoonsnaam — {reden}".replace("'", "''")
        op.execute(f"COMMENT ON COLUMN reporting.{view}.{kolom} IS '{tekst}'")


def _wis_markeringen() -> None:
    for view, kolom in PERSOONSNAAM_KOLOMMEN:
        # Alleen de kolommen die na de downgrade nog bestaan; de drie op `d_person`
        # verdwijnen met de view zelf.
        if view != "d_person":
            op.execute(f"COMMENT ON COLUMN reporting.{view}.{kolom} IS NULL")


def upgrade() -> None:
    op.execute(D_PERSON)
    op.execute(VIEW_COMMENTAAR)
    _markeer()


def downgrade() -> None:
    """Herstelt het SCHEMA, en er ís hier geen data om te herstellen.

    De view is afgeleid: hij bewaart niets, dus hem terugzetten naar de vorm zonder
    namen is een volledige omkering. De markeringen op de andere views gaan mee weg
    — ze beschrijven de data nog wel, maar de poort die ze leest hoort bij deze
    migratie.

    De kolommen verdwijnen NIET met een `CREATE OR REPLACE`: Postgres weigert een
    replace die kolommen weglaat. Vandaar een echte DROP. `CASCADE` is hier veilig
    en gemeten: geen enkele weergave in `reporting` selecteert uit `d_person` —
    `d_address` hangt eraan via een join die in de universe gedeclareerd staat, niet
    in SQL.
    """
    _wis_markeringen()
    op.execute("DROP VIEW IF EXISTS reporting.d_person CASCADE")
    op.execute(D_PERSON_ZONDER_NAAM)
    op.execute(VIEW_COMMENTAAR_ZONDER_NAAM)
