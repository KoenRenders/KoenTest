# meetings — componentcontract (CR-09, #258)

**Doel.** De maandelijkse bestuursvergadering: agenda en verslag als één
document in het portaal, de bestuursmail met PDF en bijlagen, en de bron
waaruit de nieuwsbriefketen (CR-05) straks put.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Lezen**: `list_meetings`, `get_meeting`, `previous_meeting`, `sections_of`,
  `items_of`, `document_of` (de vergadering zoals ze op het scherm én in de PDF
  staat — één structuur, geen tweede opbouw), `member_standing`.
- **Schrijven**: `create_meeting` (genereert de agenda), `generate_agenda`,
  `add_item`, `update_item`, `delete_item`, `add_section`, `set_attendance`,
  `add_file`, `delete_file`, `add_extra_recipient`, `remove_extra_recipient`,
  `send_meeting_mail`, `reopen`.
- **PDF**: `render`, `filename_for`, `long_date`, `short_date`.
- **Modellen als type**: `Meeting`, `MeetingSection`, `MeetingItem`,
  `MeetingAttendance`, `MeetingFile`, `MeetingExtraRecipient`.

## Wat dit component van anderen gebruikt (alleen via hun facade)

| Component | Waarvoor |
|---|---|
| `activities.api` | `activities_active_between`, `activities_from` (de twee activiteitensecties), `registration_counts` (het aantal op de regel) |
| `mdm.api` | `organization_circle` (de vergaderkring), `new_members_between`, `add_to_circle`, `end_circle_relation` |
| `membership.api` | `members_with_membership_for_year`, `renewal_open`, `renewal_years` (de ledenkop) |
| `mail.api` | `send_with_attachments` (één mail, iedereen in To) |

## Wat andere componenten hier halen

Vandaag: niets. De nieuwsbriefketen (CR-05) wordt de eerste afnemer en leest
verslagen via `document_of`; wélke punten meegaan, kiest de nieuwsbriefmaker in
het compose-scherm. Dat is meteen de privacypoort: ongekozen verslaginhoud
bereikt nooit een LLM.

## Invarianten

- **Eén document, twee statussen.** `agenda` → `report` gebeurt impliciet
  (aanwezigheid aanvinken of een notitie typen ís notuleren); `sent` is het enige
  harde moment en `reopen` draait het terug. Elke verzending bewaart haar eigen
  PDF, dus de geschiedenis verliest nooit een versie die vertrokken is.
- **Punten verwijzen, ze kopiëren niet.** Naam, datum, locatie en het
  inschrijvingsaantal komen vers uit het activiteitendomein; `sort_key` bestaat
  alleen om in SQL te kunnen sorteren.
- **Geen cross-schema FK's, op één benoemde uitzondering na.**
  `activity_id`, `member_id` en `noted_steward_person_id` zijn soft-refs: een FK
  over schema's heen koppelt twee deploys aan elkaar
  (`test_schema_boundaries`). Een verwijzing die niet meer oplost, toont als
  vrij punt. The exception is `meeting_status_labels.language` →
  `mdm.language_codes.code` (CR-12 §B2.4): a code table of a foundation domain
  may be the target, because `mdm` depends on no business domain, and without
  that key any spelling of a language code could sit in a label row.
- **The status is a code list.** `meetings.meeting_status_codes` + `_labels`,
  with `MeetingStatus` as its enum and a foreign key from `meetings.status`
  (CR-12 phase 0, the pilot list). The three Dutch words live in the label
  table, not in a dictionary inside a screen; the badge fetches them with the
  `code_label` filter. A fourth status is a row plus a member — not a migration
  on a `CHECK` constraint, because that one was removed in the same change.
- **Bestanden zijn geen media-assets.** Media serveert publiek; deze bestanden
  gaan door een route achter de beheersessie. Een bijlage van een verstuurde
  vergadering kan niet verwijderd worden, afgeleid uit de verzendmomenten van de
  vergadering zelf.
- **Geen AI.** De agenda wordt deterministisch samengesteld. Drafting hoort bij
  CR-05.

## Migraties

- `122_meetings_module.py` — het schema `meetings` (zes tabellen) plus, in `mdm`,
  de generieke persoon-organisatierelatie met `BOARD_MEETING` als eerste code.
