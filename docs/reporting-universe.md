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

The last column is how the fact counts the people a group covers. The small-cell threshold needs it: a group of fewer than five is merged away, and a fact that cannot count people cannot be grouped by a sensitive dimension at all.

The role column is the role the fact's **flat dataset dump** will need once the fence is built; see Roles below. Today every dump sits behind `require_admin_ui` like the rest of the back office.

| Fact | Name | Grain | Role | People | What it holds |
|---|---|---|---|---|---|
| `f_memberships` | Lidmaatschappen | één rij per gezin per lidmaatschapsjaar | `finance` | `SUM({view}.person_count)` | Lidmaatschappen per gezin per jaar, inclusief de gezinnen die dat jaar níét vernieuwden — anders is 'hoeveel vervallen er?' niet te tellen. |
| `f_registrations` | Inschrijvingen | één rij per inschrijfregel | `finance` | `COUNT(DISTINCT {view}.person_id)` | Inschrijvingen op activiteiten, één rij per gekozen product. Een inschrijving zonder producten telt mee met aantal 0. |
| `f_payments` | Betalingen | één rij per betaalrecord | `finance` | `COUNT(DISTINCT {view}.household_id)` | Vorderingen en terugbetalingen. Een terugbetaling draagt een negatief bedrag, dus elke som is meteen een nettobedrag. |
| `f_membership_persons` | Leden (personen) | één rij per persoon per lidmaatschapsjaar | `admin` | `COUNT({view}.person_id)` | Wie er lid is, op persoonsniveau — de korrel die vraag 8 nodig heeft. Een persoon in twee gezinnen telt één keer. |
| `f_form_submissions` | Formulierinzendingen | één rij per inzending | `admin` | — | Inzendingen op formulieren. Zonder naam of e-mailadres: een rapport telt inzendingen, het formulierscherm toont wat iemand schreef. |
| `f_operations` | Operaties | één rij per open werkbanktaak | `admin` | — | De werkvoorraad: wat er open staat in de werkbank. Een definitief mislukte e-mail en een te bevestigen terugbetaling zitten er als taaksoort in — niet als aparte rij ernaast. Antwoordt morgen anders, en dat is wat een werkvoorraad hoort te doen. |

## Dimensions

| Dimension | Name | Identifying column |
|---|---|---|
| `d_date` | Datum | `date_key` |
| `d_activity` | Activiteit | `activity_id` |
| `d_household` | Gezin | `household_id` |
| `d_person` | Persoon | `person_id` |
| `d_payment_method` | Betaalwijze | `code` |
| `d_payment_status` | Betaalstatus | `code` |
| `d_membership_status` | Lidmaatschapsstatus | `code` |
| `d_form` | Formulier | `form_id` |

## Join graph

Every join also matches on `tenant_id`, unconditionally — a dimension row can never be borrowed from another tenant.

| Fact | Dimension | On |
|---|---|---|
| `f_payments` | `d_date` | `date_key` = `date_key` |
| `f_payments` | `d_activity` | `activity_id` = `activity_id` |
| `f_payments` | `d_household` | `household_id` = `household_id` |
| `f_payments` | `d_payment_method` | `method_code` = `code` |
| `f_payments` | `d_payment_status` | `status_code` = `code` |
| `f_registrations` | `d_date` | `date_key` = `date_key` |
| `f_registrations` | `d_activity` | `activity_id` = `activity_id` |
| `f_registrations` | `d_person` | `person_id` = `person_id` |
| `f_registrations` | `d_payment_method` | `method_code` = `code` |
| `f_memberships` | `d_household` | `household_id` = `household_id` |
| `f_memberships` | `d_membership_status` | `status_code` = `code` |
| `f_membership_persons` | `d_person` | `person_id` = `person_id` |
| `f_membership_persons` | `d_household` | `household_id` = `household_id` |
| `f_form_submissions` | `d_form` | `form_id` = `form_id` |
| `f_form_submissions` | `d_date` | `date_key` = `date_key` |
| `f_operations` | `d_date` | `date_key` = `date_key` |

## Roles

Every object carries a role. In v2.3.0 these are **declared and not enforced**: reporting sits behind `require_admin_ui`, the same door as every other admin screen, and the engine applies no per-object fence. The declaration records what must hold once that switch is built — as its own change, with its own test. Half a fence suggests a protection that is not there.

| Universe role | Meaning | Objects |
|---|---|---|
| `admin` | the default: what an admin screen already shows | 45 |
| `finance` | money — every measure formatted as money, and the Betalingen class | 26 |
| `member_details` | person-level details; CR-06 §7.3 keeps these out of the universe, so nothing carries it yet | 1 |

## Objects

**sensitive** marks a dimension that cuts people into groups small enough to recognise somebody by. Grouping on one turns on the small-cell threshold: every group of fewer than five people is merged into a single row. **not additive** marks a measure that may not be summed across those merged groups — an average of averages is not an average — so its cell stays empty there rather than showing a number that happens to be wrong.

### Leden

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `membership_households` | Aantal gezinnen | measure | count | `admin` | `SUM(f_memberships.is_member)` | Gezinnen met een lidmaatschap in dat jaar. |
| `membership_persons` | Aantal personen | measure | count | `admin` | `SUM(f_memberships.person_count)` | Personen in de gezinnen met een lidmaatschap in dat jaar. |
| `membership_new` | Nieuw | measure | count | `admin` | `SUM(f_memberships.is_new)` | Gezinnen die dat jaar lid werden en het jaar ervoor niet waren. |
| `membership_renewed` | Vernieuwd | measure | count | `admin` | `SUM(f_memberships.is_renewed)` | Gezinnen die dat jaar én het jaar ervoor lid waren. |
| `membership_lapsed` | Vervallen | measure | count | `admin` | `SUM(f_memberships.is_lapsed)` | Gezinnen die het jaar ervoor lid waren en dat jaar niet vernieuwden. |
| `membership_amount_charged` | Lidgeld gefactureerd | measure | money | `finance` | `SUM(f_memberships.amount_charged)` | Som van de vorderingen op het lidgeld, terugbetalingen afgetrokken. |
| `membership_amount_paid` | Lidgeld ontvangen | measure | money | `finance` | `SUM(f_memberships.amount_paid)` | Wat er effectief op het lidgeld ontvangen is. |
| `membership_open_amount` | Lidgeld openstaand | measure | money | `finance` | `SUM(f_memberships.open_amount)` | Gefactureerd min ontvangen. |
| `membership_status` | Lidmaatschapsstatus | dimension | label | `admin` | `d_membership_status.label` | Nieuw, vernieuwd of vervallen. |
| `household_municipality` | Gemeente | dimension | label | `admin` | `d_household.municipality` | Gemeente van het gezin, uit de postcodetabel. |
| `household_postal_code` | Postcode | dimension | label | `admin` | `d_household.postal_code` | Postcode van het gezin. |
| `household_size_group` | Gezinsgrootte | dimension | label | `admin` | `d_household.household_size_group` | Aantal personen in het gezin, in klassen. |
| `household_member_since` | Lid sinds | dimension | year | `admin` | `d_household.member_since_year` | Het eerste jaar waarvoor dit gezin een lidmaatschap heeft. |
| `household` | Gezin | dimension | count | `admin` | `d_household.household_id` | Het gezin zelf. Klik door naar het gezinsdossier. |
| `person_age_group` | Leeftijdsgroep | dimension | label | `admin` | `d_person.age_group` | Leeftijdsklasse van de inschrijver, berekend op vandaag. |
| `person_gender` | Geslacht | dimension | label | `admin` | `d_person.gender_label` | Geslacht van de inschrijver. |
| `person_relation_type` | Relatietype | dimension | label | `admin` | `d_person.relation_type_label` | Hoofdlid, partner of (meerderjarig) kind binnen het gezin. |
| `membership_person_count` | Aantal leden (personen) | measure | count | `admin` | `COUNT(f_membership_persons.person_id)` | Personen met een lidmaatschap in dat jaar. Eén rij per persoon per jaar, dus tellen is optellen. |

### Activiteiten

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `registration_count` | Aantal inschrijvingen | measure | count | `admin` | `COUNT(DISTINCT f_registrations.registration_id)` | Aantal inschrijvingen, ongeacht hoeveel producten erop staan. |
| `registration_quantity` | Aantal stuks | measure | count | `admin` | `SUM(f_registrations.quantity)` | Som van de aantallen op de inschrijfregels — de bezetting. |
| `registration_amount` | Inschrijfbedrag | measure | money | `finance` | `SUM(f_registrations.line_amount)` | Waarde van de inschrijfregels aan de prijs van dat moment. Gratis producten en 'ter plaatse te betalen' tellen niet mee. |
| `activity` | Activiteit | dimension | label | `admin` | `d_activity.activity_name` | Naam van de activiteit. Klik door naar het activiteitdossier. |
| `activity_year` | Jaar van de activiteit | dimension | year | `admin` | `d_activity.activity_year` | Het jaar van de eerste datum van de activiteit. Het model kent geen seizoen (CR-06 §12). |
| `activity_location` | Locatie | dimension | label | `admin` | `d_activity.location` | Waar de activiteit doorgaat. |
| `activity_cancelled` | Geannuleerd | dimension | label | `admin` | `CASE WHEN d_activity.is_cancelled THEN 'Ja' ELSE 'Nee' END` | Of de activiteit geannuleerd werd. |
| `activity_members_only` | Enkel voor leden | dimension | label | `admin` | `CASE WHEN d_activity.members_only THEN 'Ja' ELSE 'Nee' END` | Of enkel leden zich mochten inschrijven. |
| `component` | Onderdeel | dimension | label | `admin` | `f_registrations.component_name` | Het onderdeel van de activiteit waarop ingeschreven werd. |
| `product` | Product | dimension | label | `admin` | `f_registrations.product_name` | Het gekozen product. 'Geen product' bij een inschrijving zonder regels. |
| `registration_type` | Inschrijfvorm | dimension | label | `admin` | `f_registrations.registration_type` | Individueel of gezin. |
| `registration_has_team` | Ploegnaam ingevuld | dimension | label | `admin` | `CASE WHEN f_registrations.has_team THEN 'Ja' ELSE 'Nee' END` | Of er een ploegnaam ingevuld werd. |

### Betalingen

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `payment_amount` | Te betalen | measure | money | `finance` | `SUM(f_payments.amount)` | Som van de bedragen; terugbetalingen tellen negatief mee. |
| `payment_amount_paid` | Ontvangen | measure | money | `finance` | `SUM(f_payments.amount_paid)` | Wat er effectief ontvangen is. |
| `payment_open_amount` | Openstaand | measure | money | `finance` | `SUM(f_payments.open_amount)` | Te betalen min ontvangen. |
| `payment_refunded` | Terugbetaald | measure | money | `finance` | `SUM(CASE WHEN f_payments.record_type = 'refund' THEN -f_payments.amount ELSE 0 END)` | Terugbetaalde bedragen als positief getal. |
| `payment_count` | Aantal betalingen | measure | count | `finance` | `COUNT(DISTINCT f_payments.payment_id)` | Aantal betaalrecords, vorderingen en terugbetalingen samen. |
| `payment_days_to_paid` | Gemiddelde betaaltermijn | measure | days | `finance` | `AVG(f_payments.days_to_paid)` | Gemiddeld aantal dagen tussen aanmaak en betaling, over de betaalde records. |
| `payment_method` | Betaalwijze | dimension | label | `finance` | `d_payment_method.label` | Online, overschrijving of cash. |
| `payment_status` | Betaalstatus | dimension | label | `finance` | `d_payment_status.label` | In afwachting, betaald, mislukt of geannuleerd. |
| `payment_type` | Soort | dimension | label | `finance` | `f_payments.record_type_label` | Vordering of terugbetaling. |
| `payment_payable_type` | Waarvoor | dimension | label | `finance` | `f_payments.payable_type_label` | Lidgeld of activiteit. |
| `payment_age_bucket` | Ouderdom | dimension | label | `finance` | `f_payments.age_bucket` | Hoe lang een vordering al openstaat, in klassen. Betaalde records staan op 'Betaald'. |
| `payment_record` | Betaling | dimension | label | `finance` | `f_payments.payment_id` | Het betaalrecord zelf. Klik door naar de betalingenpagina. |

### Betaaldetail

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `payment_payable_label` | Waarvoor | detail | label | `member_details` | `f_payments.payable_label` | Voor wie en waarvoor deze betaling is — de inschrijver en de activiteit, of het hoofdlid en het lidmaatschapsjaar. |
| `payment_kind_label` | Soort | detail | label | `finance` | `f_payments.payable_type_label` | Lidgeld of activiteit. |
| `payment_type_label` | Type | detail | label | `finance` | `f_payments.record_type_label` | Vordering of terugbetaling. |
| `payment_method_label` | Betaalwijze | detail | label | `finance` | `d_payment_method.label` | Online, overschrijving of cash. |
| `payment_status_label` | Status | detail | label | `finance` | `d_payment_status.label` | In afwachting, betaald, mislukt of geannuleerd. |
| `payment_ogm` | Mededeling (OGM) | detail | label | `finance` | `f_payments.structured_communication` | De gestructureerde mededeling op een overschrijving. |
| `payment_due` | Te betalen | detail | money | `finance` | `f_payments.amount` | Het bedrag van deze ene regel. Een terugbetaling is negatief. |
| `payment_received` | Betaald | detail | money | `finance` | `f_payments.amount_paid` | Wat er op deze regel ontvangen is. |
| `payment_balance` | Saldo | detail | money | `finance` | `f_payments.open_amount` | Te betalen min betaald, op deze regel. |
| `payment_paid_on` | Betaald op | detail | date | `finance` | `f_payments.paid_date` | Wanneer de betaling binnenkwam. |
| `payment_note` | Notitie | detail | label | `finance` | `f_payments.note` | Wat de penningmeester erbij schreef. |

### Formulieren

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `submission_count` | Aantal inzendingen | measure | count | `admin` | `COUNT(DISTINCT f_form_submissions.submission_id)` | Aantal inzendingen op een formulier. |
| `submission_answers` | Aantal antwoorden | measure | count | `admin` | `SUM(f_form_submissions.answer_count)` | Som van de ingevulde antwoorden — hoeveel er werkelijk ingevuld is. |
| `form` | Formulier | dimension | label | `admin` | `d_form.form_name` | Naam van het formulier. Klik door naar de formulierbouwer. |
| `form_status` | Status van het formulier | dimension | label | `admin` | `d_form.form_status_label` | Concept, gepubliceerd of gesloten. |
| `form_anonymous` | Anoniem formulier | dimension | label | `admin` | `d_form.is_anonymous_label` | Of het formulier anoniem ingevuld wordt. |
| `submission_edited` | Achteraf gewijzigd | dimension | label | `admin` | `CASE WHEN f_form_submissions.was_edited THEN 'Ja' ELSE 'Nee' END` | Of de inzender zijn antwoord nadien nog aangepast heeft. |

### Operaties

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `operation_count` | Aantal open items | measure | count | `admin` | `COUNT(DISTINCT f_operations.item_id)` | Hoeveel er nog ligt te wachten. |
| `operation_age_days` | Gemiddelde ouderdom | measure | days | `admin` | `AVG(f_operations.age_days)` | Gemiddeld aantal dagen dat een open item al wacht. |
| `operation_kind` | Soort | dimension | label | `admin` | `f_operations.kind_label` | Wat voor taak het is: een terugbetaling bevestigen, een mislukte e-mail, een webhook die afwijkt, een mislukte achtergrondtaak. |
| `operation_detail` | Onderwerp | dimension | label | `admin` | `f_operations.detail` | Waar de taak over gaat: een betaalrecord, een e-mail, een achtergrondtaak. |
| `operation_role` | Voor welke rol | dimension | label | `admin` | `f_operations.required_role` | Wie de taak hoort op te pakken. |
| `operation_age_bucket` | Ouderdom | dimension | label | `admin` | `f_operations.age_bucket` | Hoe lang een item al open staat, in klassen. |

### Tijd

| Key | Name | Type | Format | Role | Source | Description |
|---|---|---|---|---|---|---|
| `date_year` | Jaar | dimension | year | `admin` | `d_date.year` | Kalenderjaar van de gebeurtenis (inschrijfdatum of aanmaakdatum van de betaling). |
| `date_quarter` | Kwartaal | dimension | count | `admin` | `d_date.quarter` | Kwartaal 1 tot 4 binnen het jaar. |
| `date_month` | Maand | dimension | label | `admin` | `d_date.year_month` | Jaar en maand als 2026-03, zodat maanden vanzelf chronologisch staan. |
| `date_month_label` | Maand voluit | detail | label | `admin` | `d_date.month_year_label` | Dezelfde maand als 'maart 2026'. Een detail: sorteren doe je op Maand. |
| `date_day` | Datum | dimension | date | `admin` | `d_date.date_key` | De dag zelf. |
| `membership_year` | Lidmaatschapsjaar | dimension | year | `admin` | `f_memberships.year` | Het jaar waarvoor het lidgeld geldt. Staat los van Jaar: een lidmaatschap heeft een lidmaatschapsjaar, geen datum. |
| `membership_person_year` | Jaar van het lidmaatschap | dimension | year | `admin` | `f_membership_persons.year` | Het jaar waarvoor deze persoon lid was. |
