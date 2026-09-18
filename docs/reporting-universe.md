<!--
GENERATED FILE — do not edit by hand.

Rendered from `backend/app/domains/reporting/universe.py` by
`python -m app.domains.reporting.docs`. `test_reporting_universe_gate.py` fails
when this file and the declaration disagree, so editing it here would only make
the build red.
-->

# The reporting universe

The semantic layer over the `reporting` star schema (CR-06 §4). A board member
picks **objects**; the engine resolves the joins, aggregates the measures, adds
the tenant filter, and writes the SQL. Nobody writes SQL, and no object exists
that is not in this document.

Object names are Dutch: they are what the objects pane shows. Object keys are
English and permanent — a saved report references keys, so a renamed key breaks
every report that used it.

## Facts

A report is about exactly one fact — its measures decide the grain. Measures from two facts in one selection are refused: they would multiply each other (CR-06 §2.6).

The last column is how the fact counts the people a group covers. It is a **declaration and nothing more** since 14 September 2026: the small-cell threshold that used to read it has been removed, so no query asks for this count today. It records which facts could answer "how many people are behind this group", which stays true whether or not a rule leans on it — the same honesty as the role column below.

The role column is the role the fact's **flat dataset dump** will need once the fence is built; see Roles below. Today every dump sits behind `require_admin_ui` like the rest of the back office.

| Fact | Name | Grain | Role | People | What it holds |
|---|---|---|---|---|---|
| `f_memberships` | Lidmaatschappen | één rij per gezin per lidmaatschapsjaar | `finance` | `SUM({view}.person_count)` | Lidmaatschappen per gezin per jaar, inclusief de gezinnen die dat jaar níét vernieuwden — anders is 'hoeveel vervallen er?' niet te tellen. |
| `f_registrations` | Inschrijvingen | één rij per inschrijfregel | `finance` | `COUNT(DISTINCT {view}.person_id)` | Inschrijvingen op activiteiten, één rij per gekozen product. Een inschrijving zonder producten telt mee met aantal 0. |
| `f_payments` | Betalingen | één rij per betaalrecord | `finance` | `COUNT(DISTINCT {view}.member_id)` | Vorderingen en terugbetalingen. Een terugbetaling draagt een negatief bedrag, dus elke som is meteen een nettobedrag. |
| `f_membership_persons` | Leden (personen) | één rij per persoon per lidmaatschapsjaar | `admin` | `COUNT({view}.person_id)` | Wie er lid is, op persoonsniveau — de korrel die vraag 8 nodig heeft. Een persoon in twee gezinnen telt één keer. |
| `f_members` | Gezinnen | één rij per gezin | `admin` | `COUNT(DISTINCT {view}.member_id)` | Elk gezin, ook een dat nooit lid was. Dat is het verschil met Lidmaatschappen, dat alleen gezinnen kent die ooit aansloten. |
| `f_forms` | Formulieren | één rij per formulier | `admin` | — | Elk formulier, ook een zonder inzendingen. Dat is het verschil met Inzendingen, dat alleen formulieren kent waarop iemand antwoordde. |
| `f_activities` | Activiteiten | één rij per activiteit | `admin` | — | Elke activiteit, ook een zonder inschrijvingen. Dat is het verschil met Inschrijvingen, dat alleen activiteiten kent waarop iemand inschreef. |
| `f_form_submissions` | Formulierinzendingen | één rij per inzending | `admin` | — | Inzendingen op formulieren. Zonder naam of e-mailadres: een rapport telt inzendingen, het formulierscherm toont wat iemand schreef. |
| `f_tasks` | Taken | één rij per werkbanktaak, open én afgehandeld | `admin` | — | De werkbank: elke taak, met haar status als dimensie. Een definitief mislukte e-mail en een te bevestigen terugbetaling zitten erin als taaksoort — niet als aparte rij ernaast. Filter op Open voor de werkvoorraad; laat het filter weg en je ziet of ze groeit of krimpt. |

## Dimensions

| Dimension | Name | Identifying column |
|---|---|---|
| `d_date` | Datum | `date_key` |
| `d_activity` | Activiteit | `activity_id` |
| `d_member` | Gezin | `member_id` |
| `d_person` | Persoon | `person_id` |
| `d_payment_method` | Betaalwijze | `code` |
| `d_payment_status` | Betaalstatus | `code` |
| `d_membership_status` | Lidmaatschapsstatus | `code` |
| `d_form` | Formulier | `form_id` |
| `d_board_member` | Verantwoordelijk bestuurslid | `board_member_id` |
| `d_address` | Adres | `address_id` |
| `d_registration_date` | Inschrijfdatum | `date_key` |
| `d_payment_created` | Aanmaakdatum | `date_key` |
| `d_membership_year` | Lidmaatschapsjaar | `date_key` |
| `d_member_created` | Aanmaakdatum gezin | `date_key` |
| `d_form_created` | Aanmaakdatum formulier | `date_key` |
| `d_submission_date` | Inzenddatum | `date_key` |
| `d_task_created` | Aanmaakdatum taak | `date_key` |
| `d_paid_date` | Betaaldatum | `date_key` |
| `d_done_date` | Afhandeldatum | `date_key` |
| `d_activity_start` | Startdatum | `date_key` |
| `d_activity_end` | Einddatum | `date_key` |

## Join graph

Every join also matches on `tenant_id`, unconditionally — a dimension row can never be borrowed from another tenant.

| Fact | Dimension | On |
|---|---|---|
| `f_payments` | `d_payment_created` | `date_key` = `date_key` |
| `f_payments` | `d_paid_date` | `paid_date` = `date_key` |
| `f_payments` | `d_activity` | `activity_id` = `activity_id` |
| `f_payments` | `d_member` | `member_id` = `member_id` |
| `f_payments` | `d_payment_method` | `method_code` = `code` |
| `f_payments` | `d_payment_status` | `status_code` = `code` |
| `f_registrations` | `d_registration_date` | `date_key` = `date_key` |
| `f_registrations` | `d_activity` | `activity_id` = `activity_id` |
| `f_registrations` | `d_person` | `person_id` = `person_id` |
| `f_registrations` | `d_payment_method` | `method_code` = `code` |
| `f_memberships` | `d_membership_year` | `date_key` = `date_key` |
| `f_memberships` | `d_member` | `member_id` = `member_id` |
| `f_memberships` | `d_membership_status` | `status_code` = `code` |
| `f_membership_persons` | `d_membership_year` | `date_key` = `date_key` |
| `f_membership_persons` | `d_person` | `person_id` = `person_id` |
| `f_membership_persons` | `d_member` | `member_id` = `member_id` |
| `f_form_submissions` | `d_form` | `form_id` = `form_id` |
| `f_forms` | `d_form_created` | `date_key` = `date_key` |
| `f_forms` | `d_form` | `form_id` = `form_id` |
| `f_form_submissions` | `d_submission_date` | `date_key` = `date_key` |
| `f_tasks` | `d_task_created` | `date_key` = `date_key` |
| `f_tasks` | `d_done_date` | `done_date` = `date_key` |
| `f_members` | `d_member_created` | `date_key` = `date_key` |
| `f_members` | `d_member` | `member_id` = `member_id` |
| `f_activities` | `d_activity` | `activity_id` = `activity_id` |
| `f_activities` | `d_activity_start` | `first_date` = `date_key` |
| `f_activities` | `d_activity_end` | `last_date` = `date_key` |
| `d_member` | `d_board_member` | `board_member_id` = `board_member_id` |
| `d_person` | `d_address` | `person_id` = `person_id` |
| `f_members` | `d_person` | `head_person_id` = `person_id` |

## Roles

Every object carries a role. In v2.3.0 these are **declared and not enforced**: reporting sits behind `require_admin_ui`, the same door as every other admin screen, and the engine applies no per-object fence. The declaration records what must hold once that switch is built — as its own change, with its own test. Half a fence suggests a protection that is not there.

| Universe role | Meaning | Objects |
|---|---|---|
| `admin` | the default: what an admin screen already shows | 84 |
| `finance` | money — every measure formatted as money, and the Betalingen class | 30 |
| `member_details` | person-level details; CR-06 §7.3 keeps these out of the universe, so nothing carries it yet | 9 |

## Objects

**sensitive** marks a dimension that cuts people into groups small enough to recognise somebody by. Like the people-count above it is **declared and not enforced**: the small-cell threshold that used to read it was removed on 14 September 2026. Inside the back office a report shows what it counted; what may not reach a language model is decided by `AI` below, and a count is not personal data. **not additive** is a declaration in the same sense: it records that a measure cannot be summed across groups that were rolled together — an average of averages is not an average — which stays true although nothing rolls groups together today.

**AI** is how far the object may travel towards a language model (CR-07 §5.1): `admin_plain` as it is, `admin_tokenised` only as a token like `gezin-23`, `none` never. The field has no default in the declaration — adding an object without deciding this is an import error, not an oversight that ships.

### Leden

| Key | Name | Type | Format | Role | AI | Source | Description |
|---|---|---|---|---|---|---|---|
| `member_created_year` | Aanmaakdatum gezin › Jaar | dimension | year | `admin` | admin_plain | `d_member_created.year` | Wanneer het gezin in de administratie kwam. Opgerold tot jaar. |
| `member_created_quarter` | Aanmaakdatum gezin › Kwartaal | dimension | label | `admin` | admin_plain | `(d_member_created.year::text \|\| '-K' \|\| d_member_created.quarter::text)` | Wanneer het gezin in de administratie kwam. Opgerold tot kwartaal. |
| `member_created_month` | Aanmaakdatum gezin › Maand | dimension | label | `admin` | admin_plain | `d_member_created.year_month` | Wanneer het gezin in de administratie kwam. Opgerold tot maand. |
| `member_created_day` | Aanmaakdatum gezin › Datum | dimension | date | `admin` | admin_plain | `d_member_created.date_key` | Wanneer het gezin in de administratie kwam. Opgerold tot datum. |
| `membership_year` | Lidmaatschapsjaar | dimension | year | `admin` | admin_plain | `d_membership_year.year` | Het jaar waarover een lidmaatschap gaat. Eén object voor beide lidmaatschapsfeiten (#894) — en géén hiërarchie, want de dag eronder is 1 januari en dus verzonnen. Niet te verwarren met 'Lid sinds' (het eerste jaar) of met de aanmaakdatum van het gezin. |
| `membership_count` | Aantal gezinnen | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_memberships.member_id)` | Gezinnen in de telling, ongeacht of ze dat jaar lid waren. Dit is de maat waarmee je op Lidmaatschapsstatus groepeert: een vervallen gezin heeft dat jaar per definitie géén lidmaatschap, dus 'Aantal leden (hoofdlid)' staat daar terecht op nul en telt het niet (#871). |
| `membership_households` | Aantal leden (hoofdlid) | measure | count | `admin` | admin_plain | `SUM(f_memberships.is_member)` | Gezinnen met een lidmaatschap in dat jaar — één per gezin, wat Koen 'leden (hoofdlid)' noemt. Wil je weten hoeveel daarvan nieuw, vernieuwd of vervallen zijn, groepeer dan op Lidmaatschapsstatus; dat is een dimensie en geen aparte maat (#871). |
| `membership_persons` | Aantal leden (personen) | measure | count | `admin` | admin_plain | `SUM(f_memberships.person_count)` | Personen in de gezinnen met een lidmaatschap in dat jaar. |
| `membership_amount_charged` | Lidgeld gefactureerd | measure | money | `finance` | admin_plain | `SUM(f_memberships.amount_charged)` | Som van de vorderingen op het lidgeld, terugbetalingen afgetrokken. De standaardbetekenis van 'lidgeldomzet': gefactureerd, niet ontvangen. |
| `membership_amount_paid` | Lidgeld ontvangen | measure | money | `finance` | admin_plain | `SUM(f_memberships.amount_paid)` | Wat er effectief op het lidgeld ontvangen is. Lager dan 'Lidgeld gefactureerd' zolang er nog iets openstaat. |
| `membership_open_amount` | Lidgeld openstaand | measure | money | `finance` | admin_plain | `SUM(f_memberships.open_amount)` | Gefactureerd min ontvangen: het lidgeld dat nog binnen moet komen. |
| `membership_is_active` | Actief | dimension | label | `admin` | admin_plain | `CASE WHEN f_memberships.active_membership_count > 0 THEN 'Ja' ELSE 'Nee' END` | Of dit gezin dat jaar een actief lidmaatschap had. Een dimensie en geen maat: 'hoeveel actieve leden' is een telling mét een filter, en dan staat op het scherm welk filter (#871). |
| `membership_status` | Lidmaatschapsstatus | dimension | label | `admin` | admin_plain | `d_membership_status.label` | Of dit lidmaatschap nieuw, vernieuwd of vervallen is ten opzichte van het jaar ervoor. Dit is de dimensie die 'hoeveel nieuwe leden' beantwoordt. |
| `member_municipality` | Gemeente | dimension | label | `admin` | admin_plain | `d_member.municipality` | De gemeente van het gezin, uit de postcodetabel. Op gezinskorrel: elk gezin telt één keer, ook al wonen er vier mensen. Voor de telling per bewoner is er 'Gemeente (adres)'. |
| `member_postal_code` | Postcode | dimension | label | `admin` | admin_plain | `d_member.postal_code` | De postcode van het gezin, uit de postcodetabel. Op gezinskorrel: elk gezin telt één keer. Voor de postcode per bewoner is er 'Postcode (adres)'. |
| `member_size_group` | Gezinsgrootte | dimension | label | `admin` | admin_plain | `d_member.household_size_group` | Het aantal personen in het gezin, samengenomen in klassen. Vraag de waarden op als je erop wil filteren — de klassegrenzen staan in de data, niet hier. |
| `member_since` | Lid sinds | dimension | year | `admin` | admin_plain | `d_member.member_since_year` | Het eerste jaar waarvoor dit gezin een lidmaatschap heeft — sinds wanneer het lid is. Iets anders dan de aanmaakdatum van het gezin (wanneer het in de administratie kwam) en dan Lidmaatschapsjaar (het jaar waarover een lidmaatschap gaat). |
| `member` | Gezin | dimension | count | `admin` | admin_tokenised (`gezin-…`) | `d_member.member_id` | Het gezin zelf. Klik door naar het gezinsdossier. |
| `address_line` | Adres | dimension | label | `member_details` | admin_tokenised (`gezin-…`) | `COALESCE(d_address.address_line, 'Geen adres')` | Straat, huisnummer en bus op één lijn; 'Geen adres' als er geen is. Afgeleid in de weergave, niet bewaard — een samenvoeging die in de databank staat, drijft weg van de velden waaruit ze komt. Sorteert op straat, huisnummer numeriek en bus, dus niet op zichzelf. Voor 'hoeveel gezinnen per gemeente' neem je Gemeente, die al op gezinskorrel staat. |
| `address_municipality` | Gemeente (adres) | dimension | label | `admin` | admin_plain | `COALESCE(d_address.municipality, 'Geen adres')` | De gemeente van dit adres, op persoonskorrel. Verschilt van 'Gemeente', die het gezin volgt: daar telt een gezin één keer, hier elke bewoner met een adres. Wie geen adres heeft, valt onder 'Geen adres' en verdwijnt dus niet uit het rapport. |
| `address_postal_code` | Postcode (adres) | dimension | label | `admin` | admin_plain | `COALESCE(d_address.postal_code, 'Geen adres')` | De postcode van dit adres, op persoonskorrel; 'Geen adres' voor wie er geen heeft. |
| `address_street` | Straat | dimension | label | `member_details` | admin_plain | `COALESCE(d_address.street, 'Geen adres')` | De straatnaam van dit adres, zonder huisnummer. Op persoonskorrel, dus elke bewoner telt mee. |
| `address_house_number` | Huisnummer | dimension | label | `member_details` | admin_tokenised (`gezin-…`) | `COALESCE(d_address.house_number, '')` | Het huisnummer. Wordt natuurlijk gesorteerd — het is tekst, dus alfabetisch zou 10 vóór 9 komen en staat een straat door elkaar. |
| `address_bus` | Bus | dimension | label | `member_details` | admin_tokenised (`gezin-…`) | `d_address.bus_number` | Het busnummer, leeg als er geen is. |
| `member_head_name` | Hoofdlid | dimension | label | `member_details` | admin_tokenised (`gezin-…`) | `d_member.head_name` | De naam van het hoofdlid van dit gezin. Op gezinskorrel, dus één per rij. |
| `member_partner_name` | Partner | dimension | label | `member_details` | admin_tokenised (`gezin-…`) | `d_member.partner_name` | De naam van de partner, leeg als er geen is. Staan er twee partners in één gezin, dan toont dit er één — de korrel blijft één rij per gezin. |
| `member_valid_today` | Vandaag geldig lid | dimension | label | `admin` | admin_plain | `CASE WHEN f_members.is_valid_today THEN 'Ja' ELSE 'Nee' END` | Of dit gezin vandaag een geldig lidmaatschap heeft. Iets anders dan 'lid voor dit jaar': wie in oktober voor volgend jaar aansluit, is vandaag geldig en hoort bij volgend jaar. |
| `person_age_group` | Leeftijdsgroep | dimension | label | `admin` | admin_plain | `d_person.age_group` | Leeftijdsklasse, berekend op vandaag. Van de persoon in het feit: de inschrijver bij inschrijvingen, het hoofdlid bij een gezinsrapport. |
| `person_gender` | Geslacht | dimension | label | `admin` | admin_plain | `d_person.gender_label` | Het geslacht van de persoon in het feit: de inschrijver bij inschrijvingen, het hoofdlid bij een gezinsrapport. Niet ingevuld blijft een eigen waarde en verdwijnt niet uit het rapport. |
| `person_relation_type` | Relatietype | dimension | label | `admin` | admin_plain | `d_person.relation_type_label` | Hoofdlid, partner of (meerderjarig) kind binnen het gezin. |
| `membership_person_count` | Aantal lidmaatschappen (personen) | measure | count | `admin` | admin_plain | `COUNT(f_membership_persons.person_id)` | Personen met een lidmaatschap in dat jaar. Eén rij per persoon per jaar, dus tellen is optellen. |
| `board_member` | Verantwoordelijk bestuurslid | dimension | label | `member_details` | admin_tokenised (`persoon-…`) | `COALESCE(d_board_member.board_member_name, 'Niet toegewezen')` | Het bestuurslid dat dit gezin tot zijn verantwoordelijkheid neemt. Gezinnen zonder toewijzing staan onder 'Niet toegewezen' — dat is een van de nuttigste uitkomsten van dit rapport, geen gat. Draagt de huidige toewijzing, geen historie. |
| `member_total_count` | Aantal gezinnen in de administratie | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_members.member_id)` | Elk gezin in de administratie, of het ooit lid was of niet. Dat is de populatie van het feit Gezinnen; 'Aantal leden (hoofdlid)' telt op het feit Lidmaatschappen en kent alleen gezinnen die ooit aansloten. Het paneel toont bij elk rapport welke populatie je telt. |
| `member_ever_member` | Ooit lid geweest | dimension | label | `admin` | admin_plain | `CASE WHEN f_members.was_ever_member THEN 'Ja' ELSE 'Nee' END` | Of dit gezin ooit een lidmaatschap had. |
| `membership_active_count` | Aantal actieve lidmaatschappen | measure | count | `admin` | admin_plain | `SUM(f_memberships.active_membership_count)` | Lidmaatschappen die op actief staan. Telt lidmaatschappen en geen gezinnen — dat is wat de dashboardtegel telt. |
| `membership_person_valid_today` | Vandaag geldig | dimension | label | `admin` | admin_plain | `CASE WHEN f_membership_persons.is_valid_today THEN 'Ja' ELSE 'Nee' END` | Of het lidmaatschap van deze persoon vandaag geldig is. Iets anders dan 'lid voor dit jaar': wie in oktober voor volgend jaar aansluit, is vandaag geldig en hoort bij volgend jaar. |
| `membership_person_unique` | Aantal unieke personen | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_membership_persons.person_id)` | Personen, elk één keer geteld over alle jaren heen. Gebruik dit als je niet op jaar groepeert; anders telt 'Aantal leden (personen)'. |

### Activiteiten

| Key | Name | Type | Format | Role | AI | Source | Description |
|---|---|---|---|---|---|---|---|
| `registration_date_year` | Inschrijfdatum › Jaar | dimension | year | `admin` | admin_plain | `d_registration_date.year` | Wanneer er ingeschreven is. Opgerold tot jaar. |
| `registration_date_quarter` | Inschrijfdatum › Kwartaal | dimension | label | `admin` | admin_plain | `(d_registration_date.year::text \|\| '-K' \|\| d_registration_date.quarter::text)` | Wanneer er ingeschreven is. Opgerold tot kwartaal. |
| `registration_date_month` | Inschrijfdatum › Maand | dimension | label | `admin` | admin_plain | `d_registration_date.year_month` | Wanneer er ingeschreven is. Opgerold tot maand. |
| `registration_date_day` | Inschrijfdatum › Datum | dimension | date | `admin` | admin_plain | `d_registration_date.date_key` | Wanneer er ingeschreven is. Opgerold tot datum. |
| `start_date_year` | Startdatum › Jaar | dimension | year | `admin` | admin_plain | `d_activity_start.year` | De eerste dag van de activiteit. Opgerold tot jaar. |
| `start_date_quarter` | Startdatum › Kwartaal | dimension | label | `admin` | admin_plain | `(d_activity_start.year::text \|\| '-K' \|\| d_activity_start.quarter::text)` | De eerste dag van de activiteit. Opgerold tot kwartaal. |
| `start_date_month` | Startdatum › Maand | dimension | label | `admin` | admin_plain | `d_activity_start.year_month` | De eerste dag van de activiteit. Opgerold tot maand. |
| `start_date_day` | Startdatum › Datum | dimension | date | `admin` | admin_plain | `d_activity_start.date_key` | De eerste dag van de activiteit. Opgerold tot datum. |
| `end_date_year` | Einddatum › Jaar | dimension | year | `admin` | admin_plain | `d_activity_end.year` | De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot jaar. |
| `end_date_quarter` | Einddatum › Kwartaal | dimension | label | `admin` | admin_plain | `(d_activity_end.year::text \|\| '-K' \|\| d_activity_end.quarter::text)` | De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot kwartaal. |
| `end_date_month` | Einddatum › Maand | dimension | label | `admin` | admin_plain | `d_activity_end.year_month` | De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot maand. |
| `end_date_day` | Einddatum › Datum | dimension | date | `admin` | admin_plain | `d_activity_end.date_key` | De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot datum. |
| `registration_count` | Aantal inschrijvingen | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_registrations.registration_id)` | Aantal inschrijvingen, ongeacht hoeveel producten erop staan. Voor 'hoeveel mensen of plaatsen' neem je 'Aantal stuks': één inschrijving kan vier kaarten bevatten. |
| `registration_quantity` | Aantal stuks | measure | count | `admin` | admin_plain | `SUM(f_registrations.quantity)` | Som van de aantallen op de inschrijfregels — de bezetting, dus wat je neemt voor 'hoeveel deelnemers'. Een inschrijving met vier kaarten telt hier vier en bij 'Aantal inschrijvingen' één. |
| `registration_amount` | Inschrijfbedrag | measure | money | `finance` | admin_plain | `SUM(f_registrations.line_amount)` | Waarde van de inschrijfregels aan de prijs van dat moment — de omzet uit inschrijvingen, gefactureerd en niet ontvangen. Gratis producten en 'ter plaatse te betalen' tellen niet mee. Wat er werkelijk betaald is, staat bij Betalingen. |
| `activity` | Activiteit | dimension | label | `admin` | admin_plain | `d_activity.activity_name` | Naam van de activiteit. Klik door naar het activiteitdossier. |
| `activity_id` | Activiteitnummer | dimension | label | `admin` | admin_plain | `d_activity.activity_id` | Het technische nummer van de activiteit. Niet in het objectenpaneel: het bestaat om op één activiteit te kunnen filteren, want de naam is daar niet eenduidig genoeg voor — een activiteit die elk jaar terugkomt, heet elk jaar hetzelfde (#975). |
| `activity_year` | Jaar van de activiteit | dimension | year | `admin` | admin_plain | `d_activity.activity_year` | Het jaar van de eerste datum van de activiteit, als eigenschap van de activiteit zelf. Neem dit voor 'welke activiteiten in 2026'; wil je per maand of kwartaal groeperen, gebruik dan Startdatum. Het model kent geen seizoen (CR-06 §12). |
| `activity_location` | Locatie | dimension | label | `admin` | admin_plain | `d_activity.location` | Waar de activiteit doorgaat, zoals ingevuld bij de activiteit — vrije tekst, dus geen adres en niet genormaliseerd. |
| `activity_cancelled` | Geannuleerd | dimension | label | `admin` | admin_plain | `CASE WHEN d_activity.is_cancelled THEN 'Ja' ELSE 'Nee' END` | Of de activiteit geannuleerd werd. Geannuleerde activiteiten blijven in de cijfers staan, dus filter hierop als je ze niet wil meetellen. |
| `activity_members_only` | Enkel voor leden | dimension | label | `admin` | admin_plain | `CASE WHEN d_activity.members_only THEN 'Ja' ELSE 'Nee' END` | Of enkel leden zich mochten inschrijven op deze activiteit. |
| `activity_count` | Aantal activiteiten | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_activities.activity_id)` | Elke activiteit, ook zonder inschrijvingen. Verschilt van 'Aantal inschrijvingen', dat de inschrijvingen telt. |
| `activity_last_date` | Laatste datum | dimension | date | `admin` | admin_plain | `f_activities.last_date` | De laatste dag van de activiteit (einddatum, anders begindatum). Filter hierop vanaf vandaag voor de komende activiteiten. |
| `component` | Onderdeel | dimension | label | `admin` | admin_plain | `f_registrations.component_name` | Het onderdeel van de activiteit waarop ingeschreven werd — een activiteit kan er meerdere hebben, elk met een eigen prijs en capaciteit. |
| `product` | Product | dimension | label | `admin` | admin_plain | `f_registrations.product_name` | Het gekozen product. 'Geen product' bij een inschrijving zonder regels. |
| `registration_type` | Inschrijfvorm | dimension | label | `admin` | admin_plain | `f_registrations.registration_type` | Of er individueel of als gezin ingeschreven werd. |
| `registration_has_team` | Ploegnaam ingevuld | dimension | label | `admin` | admin_plain | `CASE WHEN f_registrations.has_team THEN 'Ja' ELSE 'Nee' END` | Of er een ploegnaam ingevuld werd. |

### Betalingen

| Key | Name | Type | Format | Role | AI | Source | Description |
|---|---|---|---|---|---|---|---|
| `payment_created_year` | Aanmaakdatum › Jaar | dimension | year | `finance` | admin_plain | `d_payment_created.year` | Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot jaar. |
| `payment_created_quarter` | Aanmaakdatum › Kwartaal | dimension | label | `finance` | admin_plain | `(d_payment_created.year::text \|\| '-K' \|\| d_payment_created.quarter::text)` | Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot kwartaal. |
| `payment_created_month` | Aanmaakdatum › Maand | dimension | label | `finance` | admin_plain | `d_payment_created.year_month` | Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot maand. |
| `payment_created_day` | Aanmaakdatum › Datum | dimension | date | `finance` | admin_plain | `d_payment_created.date_key` | Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot datum. |
| `paid_date_year` | Betaaldatum › Jaar | dimension | year | `finance` | admin_plain | `d_paid_date.year` | Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot jaar. |
| `paid_date_quarter` | Betaaldatum › Kwartaal | dimension | label | `finance` | admin_plain | `(d_paid_date.year::text \|\| '-K' \|\| d_paid_date.quarter::text)` | Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot kwartaal. |
| `paid_date_month` | Betaaldatum › Maand | dimension | label | `finance` | admin_plain | `d_paid_date.year_month` | Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot maand. |
| `paid_date_day` | Betaaldatum › Datum | dimension | date | `finance` | admin_plain | `d_paid_date.date_key` | Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot datum. |
| `payment_amount` | Te betalen | measure | money | `finance` | admin_plain | `SUM(f_payments.amount)` | Som van de bedragen; terugbetalingen tellen negatief mee. Dit is wat 'omzet', 'opbrengst' of 'inkomsten' betekent zolang de vraag het niet preciseert: wat gefactureerd is, niet wat binnenkwam. Voor dat laatste neem je 'Betaald'. |
| `payment_amount_paid` | Betaald | measure | money | `finance` | admin_plain | `SUM(f_payments.amount_paid)` | Wat er effectief ontvangen is. Niet hetzelfde als 'Te betalen': het verschil tussen die twee is wat openstaat. Vraagt iemand naar omzet zonder meer, dan bedoelt hij 'Te betalen'. |
| `payment_open_amount` | Openstaand | measure | money | `finance` | admin_plain | `SUM(f_payments.open_amount)` | Te betalen min betaald — het derde getal van de rij Te betalen · Betaald · Openstaand, en zichtbaar het verschil van de eerste twee. De enige openstaand-maat sinds #871: 'Openstaand volgens status' stond ernaast met een statusvoorwaarde in zijn naam, en die twee liepen uiteen zodra een betaling deels betaald was. Wil je dat tweede antwoord, neem dan 'Te betalen' met een filter op Betaalstatus — dan staat de voorwaarde op het scherm. |
| `payment_refunded` | Terugbetaald | measure | money | `finance` | admin_plain | `SUM(CASE WHEN f_payments.record_type = 'refund' THEN -f_payments.amount ELSE 0 END)` | Terugbetaalde bedragen als positief getal. |
| `payment_count` | Aantal betalingen | measure | count | `finance` | admin_plain | `COUNT(DISTINCT f_payments.payment_id)` | Aantal betaalrecords, vorderingen en terugbetalingen samen. Telt regels en geen gezinnen: één gezin kan er meerdere hebben. |
| `payment_days_to_paid` | Gemiddelde betaaltermijn | measure | days | `finance` | admin_plain | `AVG(f_payments.days_to_paid)` | Gemiddeld aantal dagen tussen aanmaak en betaling, over de betaalde records. |
| `payment_method` | Betaalwijze | dimension | label | `finance` | admin_plain | `d_payment_method.label` | Hoe er betaald werd of moet worden: online, overschrijving of cash. |
| `payment_status` | Status | dimension | label | `finance` | admin_plain | `d_payment_status.label` | Waar deze betaling staat: in afwachting, betaald, mislukt of geannuleerd. Een deels betaalde vordering staat nog in afwachting. |
| `payment_type` | Type | dimension | label | `finance` | admin_plain | `f_payments.record_type_label` | Of deze regel een vordering is of een terugbetaling. Terugbetalingen tellen negatief mee in 'Te betalen'. |
| `payment_payable_type` | Soort | dimension | label | `finance` | admin_plain | `f_payments.payable_type_label` | Waarvoor betaald wordt: lidgeld of een activiteit. Hiermee splits je de geldvragen in hun twee stromen. |
| `payment_age_bucket` | Ouderdom | dimension | label | `finance` | admin_plain | `f_payments.age_bucket` | Hoe lang een vordering al openstaat, in klassen. Betaalde records staan op 'Betaald'. |
| `payment_record` | Betaling | dimension | label | `finance` | admin_plain | `f_payments.payment_id` | Het betaalrecord zelf. Klik door naar de betalingenpagina. |
| `payment_payable_label` | Waarvoor | detail | label | `member_details` | none | `f_payments.payable_label` | Voor wie en waarvoor deze betaling is — de inschrijver en de activiteit, of het hoofdlid en het lidmaatschapsjaar. |
| `payment_ogm` | Mededeling (OGM) | detail | label | `finance` | none | `f_payments.structured_communication` | De gestructureerde mededeling op een overschrijving. |
| `payment_due` | Bedrag | detail | money | `finance` | admin_plain | `f_payments.amount` | Het bedrag van deze ene regel. Een terugbetaling is negatief. |
| `payment_received` | Betaald bedrag | detail | money | `finance` | admin_plain | `f_payments.amount_paid` | Wat er op deze regel ontvangen is. |
| `payment_balance` | Saldo | detail | money | `finance` | admin_plain | `f_payments.open_amount` | Te betalen min betaald, op deze regel. |
| `payment_paid_on` | Betaald op | detail | date | `finance` | admin_plain | `f_payments.paid_date` | De dag waarop deze ene betaling binnenkwam. Leeg zolang er niets ontvangen is. |
| `payment_note` | Notitie | detail | label | `finance` | none | `f_payments.note` | Wat de penningmeester erbij schreef. |

### Formulieren

| Key | Name | Type | Format | Role | AI | Source | Description |
|---|---|---|---|---|---|---|---|
| `form_created_year` | Aanmaakdatum formulier › Jaar | dimension | year | `admin` | admin_plain | `d_form_created.year` | Wanneer het formulier aangemaakt is. Opgerold tot jaar. |
| `form_created_quarter` | Aanmaakdatum formulier › Kwartaal | dimension | label | `admin` | admin_plain | `(d_form_created.year::text \|\| '-K' \|\| d_form_created.quarter::text)` | Wanneer het formulier aangemaakt is. Opgerold tot kwartaal. |
| `form_created_month` | Aanmaakdatum formulier › Maand | dimension | label | `admin` | admin_plain | `d_form_created.year_month` | Wanneer het formulier aangemaakt is. Opgerold tot maand. |
| `form_created_day` | Aanmaakdatum formulier › Datum | dimension | date | `admin` | admin_plain | `d_form_created.date_key` | Wanneer het formulier aangemaakt is. Opgerold tot datum. |
| `submission_date_year` | Inzenddatum › Jaar | dimension | year | `admin` | admin_plain | `d_submission_date.year` | Wanneer het formulier ingevuld is. Opgerold tot jaar. |
| `submission_date_quarter` | Inzenddatum › Kwartaal | dimension | label | `admin` | admin_plain | `(d_submission_date.year::text \|\| '-K' \|\| d_submission_date.quarter::text)` | Wanneer het formulier ingevuld is. Opgerold tot kwartaal. |
| `submission_date_month` | Inzenddatum › Maand | dimension | label | `admin` | admin_plain | `d_submission_date.year_month` | Wanneer het formulier ingevuld is. Opgerold tot maand. |
| `submission_date_day` | Inzenddatum › Datum | dimension | date | `admin` | admin_plain | `d_submission_date.date_key` | Wanneer het formulier ingevuld is. Opgerold tot datum. |
| `form_count` | Aantal formulieren | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_forms.form_id)` | Formulieren, ook die zonder één inzending. Dat is de reden dat deze telling van het formulierfeit komt en niet van de inzendingen: op het inzendingenfeit verdwijnt een leeg formulier stilzwijgend, en 'welk formulier staat open en krijgt niets binnen' is juist een vraag die een bestuurder stelt (#871, dezelfde val als #848). |
| `submission_count` | Aantal inzendingen | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_form_submissions.submission_id)` | Aantal inzendingen op een formulier. Telt de inzendingen, niet de personen — wie twee keer invult, telt twee keer. |
| `submission_answers` | Ingevulde velden | measure | count | `admin` | admin_plain | `SUM(f_form_submissions.answer_count)` | Som van de ingevulde antwoorden — hoeveel er werkelijk ingevuld is. |
| `form` | Formulier | dimension | label | `admin` | admin_plain | `d_form.form_name` | Naam van het formulier. Klik door naar de formulierbouwer. |
| `form_status` | Status van het formulier | dimension | label | `admin` | admin_plain | `d_form.form_status_label` | Waar het formulier staat: concept, gepubliceerd of gesloten. Enkel een gepubliceerd formulier kan inzendingen krijgen. |
| `form_anonymous` | Anoniem formulier | dimension | label | `admin` | admin_plain | `d_form.is_anonymous_label` | Of het formulier anoniem ingevuld wordt. Bij een anoniem formulier is er geen inzender bekend, dus koppelen aan een gezin kan daar niet. |
| `submission_edited` | Achteraf gewijzigd | dimension | label | `admin` | admin_plain | `CASE WHEN f_form_submissions.was_edited THEN 'Ja' ELSE 'Nee' END` | Of de inzender zijn antwoord nadien nog aangepast heeft. |

### Taken

| Key | Name | Type | Format | Role | AI | Source | Description |
|---|---|---|---|---|---|---|---|
| `task_created_year` | Aanmaakdatum taak › Jaar | dimension | year | `admin` | admin_plain | `d_task_created.year` | Wanneer de taak ontstond. Opgerold tot jaar. |
| `task_created_quarter` | Aanmaakdatum taak › Kwartaal | dimension | label | `admin` | admin_plain | `(d_task_created.year::text \|\| '-K' \|\| d_task_created.quarter::text)` | Wanneer de taak ontstond. Opgerold tot kwartaal. |
| `task_created_month` | Aanmaakdatum taak › Maand | dimension | label | `admin` | admin_plain | `d_task_created.year_month` | Wanneer de taak ontstond. Opgerold tot maand. |
| `task_created_day` | Aanmaakdatum taak › Datum | dimension | date | `admin` | admin_plain | `d_task_created.date_key` | Wanneer de taak ontstond. Opgerold tot datum. |
| `done_date_year` | Afhandeldatum › Jaar | dimension | year | `admin` | admin_plain | `d_done_date.year` | Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot jaar. |
| `done_date_quarter` | Afhandeldatum › Kwartaal | dimension | label | `admin` | admin_plain | `(d_done_date.year::text \|\| '-K' \|\| d_done_date.quarter::text)` | Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot kwartaal. |
| `done_date_month` | Afhandeldatum › Maand | dimension | label | `admin` | admin_plain | `d_done_date.year_month` | Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot maand. |
| `done_date_day` | Afhandeldatum › Datum | dimension | date | `admin` | admin_plain | `d_done_date.date_key` | Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot datum. |
| `task_count` | Aantal taken | measure | count | `admin` | admin_plain | `COUNT(DISTINCT f_tasks.item_id)` | Hoeveel taken er zijn. Filter op status Open voor de werkvoorraad. |
| `task_age_days` | Gemiddelde ouderdom | measure | days | `admin` | admin_plain | `AVG(f_tasks.age_days)` | Gemiddeld aantal dagen dat een openstaande taak al wacht. Afgehandelde taken tellen niet mee — die wachten niet meer. |
| `task_days_to_done` | Gemiddelde doorlooptijd | measure | days | `admin` | admin_plain | `AVG(f_tasks.days_to_done)` | Gemiddeld aantal dagen tussen aanmaken en afhandelen, over de afgehandelde taken. |
| `task_kind` | Soort | dimension | label | `admin` | admin_plain | `f_tasks.kind_label` | Wat voor taak het is: een terugbetaling bevestigen, een mislukte e-mail, een webhook die afwijkt, een mislukte achtergrondtaak. |
| `task_status` | Status | dimension | label | `admin` | admin_plain | `f_tasks.status_label` | Of de taak open staat of afgehandeld is. Filter hierop in plaats van te vertrouwen op wat het feit toevallig bevat. |
| `task_detail` | Onderwerp | dimension | label | `admin` | none | `f_tasks.detail` | Waar de taak over gaat: een betaalrecord, een e-mail, een achtergrondtaak. |
| `task_role` | Voor welke rol | dimension | label | `admin` | admin_plain | `f_tasks.required_role` | De rol die deze taak hoort op te pakken — wie ze toegewezen krijgt, niet wie ze afhandelde. |
| `task_age_bucket` | Ouderdom | dimension | label | `admin` | admin_plain | `f_tasks.age_bucket` | Hoe lang een taak al open staat, in klassen. Afgehandelde taken staan op 'Afgehandeld'. |
| `task_done_by` | Afgehandeld door | dimension | label | `member_details` | none | `f_tasks.done_by` | Het e-mailadres van wie de taak afsloot. Groepeerbaar: dat is de vraag 'hoeveel heeft ieder van ons afgewerkt'. |
