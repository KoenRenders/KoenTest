# CR-33 appendix — the inventory of the data model, per module

Generated from the ORM metadata by `scripts/attribute-inventory.py`, measured on the build branch of CR-21 (webshop) on 15 October 2026; the schemas sales, product, stock and pricing are not on master yet and are marked. Re-generated on the handover commit of phase 1 (C1). The classification per row follows the rules K0–K10 below; every rule and every exception was decided by Koen on 15 October 2026 (the Q&A log of the change request, Q10 and Q12).

Business columns: **426**; technical columns by the metadata (primary key, foreign key to a table that is no code list, tenant_id, timestamps): 332, covered by one rule (never shown, to a model only as the token they already are).

**Reading:** the label is a proposal where the column name has a fixed word, empty where the build chooses it with the screen that shows the datum. The classification comes from a RULE (K0–K10), named per row. Levels: public (the public assistant may say it) · plain = **intern** (the back-office assistant only) · tokenised (the back-office assistant sees persoon-90) · never. Every row is decided (Koen, 15 October 2026).

| Classification (plain = intern) | Rows |
|---|---|
| plain | 287 |
| never | 70 |
| public | 63 |
| tokenised | 6 |

| Rule | Rows |
|---|---|
| K0 a code: the label is the code list's, the value is a code | 51 |
| K1 identifies a person, names who did it, or is a secret or an opaque payload | 53 |
| K10 one column, several data: per key; the membership amounts and dates are public, the rest never (Koen, 15 October 2026) | 1 |
| K10 one column, several data: the label comes from the code | 1 |
| K2 the name of a person: the token stands for it | 6 |
| K3 a mail to a person: its text names the person | 4 |
| K3 free text or an address beside a person's payment, mail or stock movement (Koen, 15 October 2026) | 4 |
| K3 free text written about or by a person | 2 |
| K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) | 6 |
| K4 public content (pages, media) | 30 |
| K5 what the public activity page already shows | 19 |
| K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) | 14 |
| K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) | 13 |
| K8 an amount, a date, a count, a flag or a code | 153 |
| K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) | 53 |
| K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) | 16 |


## activities — 55 business columns, 35 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| activities | name | VARCHAR(255) | required |  | Naam | public | K5 what the public activity page already shows |
| activities | slug | VARCHAR(255) |  |  | Webadres | public | K5 what the public activity page already shows |
| activities | location | VARCHAR(255) |  |  | Locatie | public | K5 what the public activity page already shows |
| activities | description | TEXT |  |  | Omschrijving | public | K5 what the public activity page already shows |
| activities | poster_url | TEXT |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| activities | is_cancelled | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activities | members_only | BOOLEAN | required |  | Alleen voor leden | public | K5 what the public activity page already shows |
| activities | board_notes | TEXT |  |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| activities | status | VARCHAR(20) | required | → activities.activity_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| activities | target_audience | VARCHAR(20) |  | → activities.target_audience_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| activities | copied_from_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_dates | start_date | DATE | required |  | Startdatum | public | K5 what the public activity page already shows |
| activity_dates | end_date | DATE |  |  | Einddatum | public | K5 what the public activity page already shows |
| activity_dates | start_time | TIME |  |  | Beginuur | public | K5 what the public activity page already shows |
| activity_dates | end_time | TIME |  |  | Einduur | public | K5 what the public activity page already shows |
| activity_organisers | person_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_organisers | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| activity_organisers | is_contact | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_organisers | email_override | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| activity_organisers | mobile_override | VARCHAR(50) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| activity_organisers | show_email | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_organisers | show_mobile | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_sub_registrations | name | VARCHAR(255) | required |  | Naam | tokenised | K2 the name of a person: the token stands for it |
| activity_sub_registrations | description | TEXT |  |  | Omschrijving | public | K5 what the public activity page already shows |
| activity_sub_registrations | external_register_url | VARCHAR(500) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| activity_sub_registrations | external_registrations_url | VARCHAR(500) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| activity_sub_registrations | info_url | VARCHAR(500) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| activity_sub_registrations | registration_type_code | VARCHAR(10) | required | → activities.registration_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| activity_sub_registrations | max_participants | INTEGER |  |  | Maximum aantal deelnemers | public | K5 what the public activity page already shows |
| activity_sub_registrations | registration_closes_on | DATE |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_sub_registrations | price | NUMERIC(10, 2) | required |  | Prijs | public | K5 what the public activity page already shows |
| activity_sub_registrations | member_price | NUMERIC(10, 2) |  |  | Ledenprijs | public | K5 what the public activity page already shows |
| activity_sub_registrations | is_free | BOOLEAN | required |  | Gratis | public | K5 what the public activity page already shows |
| activity_sub_registrations | team_name_required | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_sub_registrations | form_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_sub_registrations | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| activity_products | name | VARCHAR(255) | required |  | Naam | public | K5 what the public activity page already shows |
| activity_products | price | NUMERIC(10, 2) | required |  | Prijs | public | K5 what the public activity page already shows |
| activity_products | member_price | NUMERIC(10, 2) |  |  | Ledenprijs | public | K5 what the public activity page already shows |
| activity_products | is_free | BOOLEAN | required |  | Gratis | public | K5 what the public activity page already shows |
| activity_products | pay_on_site | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| activity_products | is_active | BOOLEAN | required |  | Actief | plain | K8 an amount, a date, a count, a flag or a code |
| activity_products | max_participants | INTEGER |  |  | Maximum aantal deelnemers | public | K5 what the public activity page already shows |
| activity_products | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| registrations | registered_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| registrations | registration_type | VARCHAR(10) | required | → activities.registration_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| registrations | contact_name | VARCHAR(200) | required |  | Naam | tokenised | K2 the name of a person: the token stands for it |
| registrations | contact_email | VARCHAR(255) | required |  | E-mail | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| registrations | phone | VARCHAR(50) |  |  | Telefoon | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| registrations | team_name | VARCHAR(200) |  |  | Ploegnaam | tokenised | K2 the name of a person: the token stands for it |
| registrations | payment_method | VARCHAR(20) |  |  | Betaalwijze | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| registrations | remarks | TEXT |  |  |  | never | K3 free text written about or by a person |
| registrations | form_submission_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| registrations | answer_token | VARCHAR(64) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| registration_items | quantity | INTEGER | required |  | Aantal | plain | K8 an amount, a date, a count, a flag or a code |

## designstudio — 49 business columns, 21 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| designs | activity_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | template_key | VARCHAR(40) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| designs | template_version | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | preset | VARCHAR(20) | required | → designstudio.preset_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| designs | duo_code | VARCHAR(60) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | status | VARCHAR(20) | required | → designstudio.design_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| designs | poster_title | VARCHAR(255) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| designs | tagline | VARCHAR(90) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| designs | subtitle | VARCHAR(120) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| designs | explanation_md | TEXT |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| designs | main_image_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | main_focus_x | NUMERIC(4, 3) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | main_focus_y | NUMERIC(4, 3) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | inset_image_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | inset_corner | VARCHAR(20) | required | → designstudio.inset_corner_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| designs | third_image_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | published_version_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| designs | created_by | VARCHAR(255) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| design_highlights | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| design_highlights | icon_code | VARCHAR(30) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_highlights | text | VARCHAR(90) | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| design_highlights | emphasis | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_logos | media_asset_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_logos | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| design_versions | number | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_versions | facts_fingerprint | VARCHAR(64) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| design_versions | sponsor_asset_ids | VARCHAR(120) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| design_versions | created_by | VARCHAR(255) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| image_generations | request_key | VARCHAR(64) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| image_generations | ai_call_log_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | seed | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | scene | TEXT | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| image_generations | style | VARCHAR(20) | required | → designstudio.drawing_style_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| image_generations | width | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | height | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | status | VARCHAR(20) | required | → designstudio.generation_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| image_generations | failure_reason | TEXT | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| image_generations | media_asset_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | reserved_cents | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | requested_by | VARCHAR(255) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| image_generations | requested_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| image_generations | finished_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_renditions | layout_code | VARCHAR(20) | required | → designstudio.layout_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| design_renditions | variant | VARCHAR(20) | required | → designstudio.render_variant_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| design_renditions | size_code | VARCHAR(20) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_renditions | media_asset_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_renditions | facts_fingerprint | VARCHAR(64) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| design_renditions | min_effective_dpi | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| design_renditions | rendered_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |

## form — 41 business columns, 25 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| forms | title | VARCHAR(200) | required |  | Titel | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| forms | slug | VARCHAR(200) |  |  | Webadres | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| forms | description | TEXT |  |  | Omschrijving | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| forms | share_token | VARCHAR(64) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| forms | status | VARCHAR(20) | required | → form.form_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| forms | requires_login | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| forms | max_submissions | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| forms | send_confirmation | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| forms | confirmation_message | TEXT |  |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| forms | allow_edit | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| forms | is_anonymous | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_sections | title | VARCHAR(300) |  |  | Titel | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_sections | description | TEXT |  |  | Omschrijving | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_sections | position | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_sections | next_is_end | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_submissions | submitted_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_submissions | submitter_name | VARCHAR(200) |  |  |  | tokenised | K2 the name of a person: the token stands for it |
| form_submissions | submitter_email | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| form_submissions | edit_token | VARCHAR(64) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| form_submissions | attached | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | field_type | VARCHAR(20) | required | → form.field_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| form_fields | label | VARCHAR(300) | required |  | Label | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_fields | help_text | TEXT |  |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| form_fields | required | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | position | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | min_value | NUMERIC(12, 2) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | max_value | NUMERIC(12, 2) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | min_length | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | max_length | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | regex_pattern | TEXT |  |  |  | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_fields | rating_max | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_fields | rating_low_label | VARCHAR(100) |  |  |  | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_fields | rating_high_label | VARCHAR(100) |  |  |  | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_field_options | label | VARCHAR(300) | required |  | Label | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_field_options | value | VARCHAR(300) |  |  | Waarde | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| form_field_options | position | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_field_options | is_other | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_field_options | skip_to_end | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_submission_answers | value_text | TEXT |  |  |  | never | K3 free text written about or by a person |
| form_submission_answers | value_number | NUMERIC(12, 2) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| form_submission_answers | value_rating | SMALLINT |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |

## newsletter — 35 business columns, 19 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| newsletters | subject | VARCHAR(500) | required |  | Onderwerp | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| newsletters | preview_text | VARCHAR(200) | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| newsletters | body_html | TEXT | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| newsletters | audience | VARCHAR(20) |  | → newsletter.audience_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| newsletters | status | VARCHAR(20) | required | → newsletter.letter_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| newsletters | created_by | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| newsletters | draft_activity_ids | JSON | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| newsletters | draft_meeting_ids | JSON | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| newsletters | reply_to_mode | VARCHAR(20) |  | → newsletter.reply_to_mode_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| newsletters | reply_to_address | VARCHAR(255) |  |  |  | never | K3 free text or an address beside a person's payment, mail or stock movement (Koen, 15 October 2026) |
| newsletters | link_base | VARCHAR(255) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| newsletters | sent_by | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| newsletters | send_started_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| newsletters | send_finished_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| newsletters | paused_until | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| subscribers | email | VARCHAR(255) | required |  | E-mail | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| subscribers | first_name | VARCHAR(100) |  |  | Voornaam | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| subscribers | status | VARCHAR(20) | required | → newsletter.subscriber_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| subscribers | source | VARCHAR(20) | required | → newsletter.subscriber_source_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| subscribers | consented_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| subscribers | confirmed_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| subscribers | unsubscribed_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| subscribers | imported_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| subscribers | confirm_sent_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| subscribers | confirm_token | VARCHAR(64) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| subscribers | unsubscribe_token | VARCHAR(64) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| subscribers | person_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| deliveries | email | VARCHAR(255) | required |  | E-mail | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| deliveries | kind | VARCHAR(20) | required | → newsletter.delivery_kind_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| deliveries | status | VARCHAR(20) | required | → newsletter.delivery_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| deliveries | sent_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| deliveries | error | TEXT |  |  |  | never | K3 free text or an address beside a person's payment, mail or stock movement (Koen, 15 October 2026) |
| drafting_messages | role | VARCHAR(20) | required | → newsletter.message_role_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| drafting_messages | text | TEXT | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| drafting_messages | proposal | JSON |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |

## mdm — 33 business columns, 64 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| organizations | org_type | VARCHAR(10) | required | → mdm.organization_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| organizations | code | VARCHAR(50) | required |  | Code | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| organizations | name | VARCHAR(255) | required |  | Naam | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| organizations | site_name | VARCHAR(255) |  |  |  | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| organizations | is_active | BOOLEAN | required |  | Actief | plain | K8 an amount, a date, a count, a flag or a code |
| organizations | legal_form | VARCHAR(30) |  | → mdm.legal_form_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| organizations | kind | VARCHAR(20) |  | → mdm.tenant_kind_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| persons | last_name | VARCHAR(100) | required |  | Achternaam | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| persons | first_name | VARCHAR(100) | required |  | Voornaam | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| persons | date_of_birth | DATE |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| persons | gender_code | VARCHAR(10) |  | → mdm.gender_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| addresses | street | VARCHAR(255) | required |  | Straat | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| addresses | house_number | VARCHAR(10) | required |  | Huisnummer | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| addresses | bus_number | VARCHAR(10) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| addresses | postal_code_id | INTEGER | required | → mdm.postal_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| bank_accounts | iban | VARCHAR(40) | required |  | IBAN | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| bank_accounts | bic | VARCHAR(20) |  |  | BIC | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| bank_accounts | beneficiary | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| bank_accounts | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| contact_details | contact_type_code | VARCHAR(10) | required | → mdm.contact_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| contact_details | value | VARCHAR(255) | required |  | (label of the contact type: Mobiel, Telefoon, E-mail) | plain | K10 one column, several data: the label comes from the code |
| contact_details | is_primary | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| contact_details | confirmed_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| external_numbers | source | VARCHAR(50) | required | → mdm.external_source_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| external_numbers | external_id | VARCHAR(50) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| organization_identifications | scheme | VARCHAR(20) | required | → mdm.identification_scheme_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| organization_identifications | value | VARCHAR(50) | required |  | Waarde | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| organization_identifications | country | VARCHAR(2) |  |  | Land | plain | K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026) |
| organization_identifications | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| organization_persons | relation_type | VARCHAR(30) | required | → mdm.organization_relation_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| organization_persons | start_date | DATE |  |  | Startdatum | plain | K8 an amount, a date, a count, a flag or a code |
| organization_persons | end_date | DATE |  |  | Einddatum | plain | K8 an amount, a date, a count, a flag or a code |
| member_persons | relation_type | VARCHAR(10) | required | → mdm.relation_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |

## meetings — 30 business columns, 36 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| meetings | meeting_date | DATE | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meetings | start_time | TIME |  |  | Beginuur | plain | K8 an amount, a date, a count, a flag or a code |
| meetings | location | VARCHAR(255) |  |  | Locatie | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| meetings | status | VARCHAR(10) | required |  | Status | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| meetings | agenda_sent_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meetings | report_sent_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_extra_recipients | name | VARCHAR(255) |  |  | Naam | tokenised | K2 the name of a person: the token stands for it |
| meeting_extra_recipients | email | VARCHAR(255) | required |  | E-mail | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| meeting_files | purpose | VARCHAR(20) | required | → meetings.file_purpose_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| meeting_files | filename | VARCHAR(255) | required |  |  | never | K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) |
| meeting_files | content_type | VARCHAR(100) | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| meeting_files | byte_size | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_files | data | BLOB | required |  |  | never | K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) |
| meeting_files | on_agenda_mail | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_files | on_report_mail | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_files | sent_with_agenda_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_files | sent_with_report_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_sections | kind | VARCHAR(20) | required | → meetings.section_kind_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| meeting_sections | title | VARCHAR(255) |  |  | Titel | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| meeting_sections | position | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_attendances | person_id | INTEGER |  |  |  | never | K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) |
| meeting_attendances | status | VARCHAR(10) | required | → meetings.attendance_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| meeting_items | position | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_items | title | VARCHAR(255) |  |  | Titel | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| meeting_items | notes | TEXT |  |  | Opmerkingen | never | K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) |
| meeting_items | activity_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_items | activity_date_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| meeting_items | member_id | INTEGER |  |  |  | never | K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) |
| meeting_items | noted_steward_person_id | INTEGER |  |  |  | never | K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026) |
| meeting_items | sort_key | DATE |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |

## ai — 26 business columns, 7 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| chatbot_info | media_asset_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| chatbot_info | cms_page_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| chatbot_info | title | VARCHAR(255) |  |  | Titel | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| chatbot_info | extracted_text | TEXT |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| chatbot_info | text_override | TEXT |  |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| chatbot_info | text_addition | TEXT |  |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| chatbot_info | extracted_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| chatbot_info | is_active | BOOLEAN | required |  | Actief | plain | K8 an amount, a date, a count, a flag or a code |
| chatbot_info | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| ai_call_log | surface | VARCHAR(32) | required | → ai.ai_surface_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| ai_call_log | capability | VARCHAR(32) | required | → ai.ai_capability_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| ai_call_log | actor | VARCHAR(255) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| ai_call_log | model | VARCHAR(64) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| ai_call_log | payload | TEXT | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| ai_call_log | tokens_prompt | INTEGER |  |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| ai_call_log | tokens_completion | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| ai_call_log | blocked_reason | TEXT | required |  |  | plain | K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03) |
| ai_call_log | provider | VARCHAR(32) |  | → ai.ai_provider_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| ai_call_log | endpoint | VARCHAR(128) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| ai_call_log | provider_request_id | VARCHAR(128) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| ai_call_log | status | VARCHAR(16) | required | → ai.ai_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| ai_call_log | duration_ms | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| ai_call_log | cost_credits | NUMERIC(12, 4) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| ai_call_log | cost_amount | NUMERIC(12, 6) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| ai_call_log | cost_currency | CHAR(3) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| ai_call_log | output_megapixels | NUMERIC(6, 2) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |

## payment — 18 business columns, 12 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| gateway_payments | provider | VARCHAR(20) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| gateway_payments | provider_payment_id | VARCHAR(100) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| gateway_payments | amount | NUMERIC(10, 2) | required |  | Bedrag | plain | K8 an amount, a date, a count, a flag or a code |
| gateway_payments | currency | VARCHAR(3) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| gateway_payments | status | VARCHAR(20) | required |  | Status | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| gateway_payments | checkout_url | VARCHAR(500) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| gateway_payments | description | VARCHAR(200) |  |  | Omschrijving | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| gateway_payments | payment_metadata | JSON |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| payment_records | payable_type | VARCHAR(50) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| payment_records | payable_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| payment_records | amount | NUMERIC(10, 2) | required |  | Bedrag | plain | K8 an amount, a date, a count, a flag or a code |
| payment_records | method | VARCHAR(20) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| payment_records | status | VARCHAR(20) | required |  | Status | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| payment_records | type | VARCHAR(10) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| payment_records | amount_paid | NUMERIC(10, 2) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| payment_records | note | VARCHAR(200) |  |  | Opmerking | never | K3 free text or an address beside a person's payment, mail or stock movement (Koen, 15 October 2026) |
| payment_records | structured_communication | VARCHAR(20) |  |  | Gestructureerde mededeling | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| payment_records | paid_at | DATETIME |  |  | Betaald op | plain | K8 an amount, a date, a count, a flag or a code |

## media — 17 business columns, 12 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| tags | name | VARCHAR(80) | required |  | Naam | public | K4 public content (pages, media) |
| media_assets | kind | VARCHAR(20) | required | → media.media_kind_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| media_assets | activity_id | INTEGER |  |  |  | public | K4 public content (pages, media) |
| media_assets | component_id | INTEGER |  |  |  | public | K4 public content (pages, media) |
| media_assets | data | BLOB | required |  |  | public | K4 public content (pages, media) |
| media_assets | content_type | VARCHAR(50) | required |  |  | public | K4 public content (pages, media) |
| media_assets | thumbnail | BLOB |  |  |  | public | K4 public content (pages, media) |
| media_assets | thumb_content_type | VARCHAR(50) |  |  |  | public | K4 public content (pages, media) |
| media_assets | byte_size | INTEGER |  |  |  | public | K4 public content (pages, media) |
| media_assets | width | INTEGER |  |  |  | public | K4 public content (pages, media) |
| media_assets | height | INTEGER |  |  |  | public | K4 public content (pages, media) |
| media_assets | title | VARCHAR(255) |  |  | Titel | public | K4 public content (pages, media) |
| media_assets | link_url | VARCHAR(500) |  |  |  | public | K4 public content (pages, media) |
| media_assets | sort_order | INTEGER | required |  | Volgorde | public | K4 public content (pages, media) |
| media_assets | is_active | BOOLEAN | required |  | Actief | public | K4 public content (pages, media) |
| media_assets | show_in_footer | BOOLEAN | required |  |  | public | K4 public content (pages, media) |
| media_thumbs_up | visitor_token | VARCHAR(64) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |

## cms — 16 business columns, 6 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| cms_pages | title | VARCHAR(255) | required |  | Titel | public | K4 public content (pages, media) |
| cms_pages | slug | VARCHAR(255) | required |  | Webadres | public | K4 public content (pages, media) |
| cms_pages | content | TEXT |  |  | Inhoud | public | K4 public content (pages, media) |
| cms_pages | is_published | BOOLEAN | required |  |  | public | K4 public content (pages, media) |
| cms_pages | show_in_nav | BOOLEAN | required |  |  | public | K4 public content (pages, media) |
| cms_pages | is_home | BOOLEAN | required |  |  | public | K4 public content (pages, media) |
| cms_pages | show_in_footer | BOOLEAN | required |  |  | public | K4 public content (pages, media) |
| cms_pages | sort_order | INTEGER | required |  | Volgorde | public | K4 public content (pages, media) |
| cms_pages | opening | VARCHAR(16) | required |  |  | public | K4 public content (pages, media) |
| cms_pages | hero | JSONB |  |  |  | public | K4 public content (pages, media) |
| page_translations | title | VARCHAR(200) | required |  | Titel | public | K4 public content (pages, media) |
| page_translations | menu_label | VARCHAR(80) |  |  |  | public | K4 public content (pages, media) |
| page_translations | draft_json | JSONB |  |  |  | public | K4 public content (pages, media) |
| page_translations | published_json | JSONB |  |  |  | public | K4 public content (pages, media) |
| page_translations | published_at | DATETIME |  |  | Gepubliceerd op | public | K4 public content (pages, media) |
| page_translations | published_by | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |

## workflow — 16 business columns, 11 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| workflow_definitions | name | VARCHAR(200) | required |  | Naam | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| workflow_definitions | steps | JSON | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| workflow_instances | subject_type | VARCHAR(50) | required | → workflow.subject_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| workflow_instances | subject_id | VARCHAR(36) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| workflow_instances | current_step | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| workflow_instances | status | VARCHAR(10) | required | → workflow.run_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| workflow_instances | done_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| workflow_tasks | kind | VARCHAR(100) | required | → workflow.task_kind_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| workflow_tasks | title | VARCHAR(300) | required |  | Titel | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| workflow_tasks | subject_type | VARCHAR(50) | required | → workflow.subject_type_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| workflow_tasks | subject_id | VARCHAR(36) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| workflow_tasks | status | VARCHAR(10) | required | → workflow.task_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| workflow_tasks | required_role | VARCHAR(20) | required | → auth.role_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| workflow_tasks | decision | TEXT |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| workflow_tasks | done_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| workflow_tasks | done_by | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |

## reporting — 14 business columns, 7 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| saved_reports | name | VARCHAR(120) | required |  | Naam | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| saved_reports | description | VARCHAR(500) |  |  | Omschrijving | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| saved_reports | owner_email | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| saved_reports | selection | JSON | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| saved_reports | is_shared | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| saved_reports | builtin_key | VARCHAR(60) |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| saved_reports | last_run_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| export_log | exported_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| export_log | actor | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| export_log | kind | VARCHAR(20) | required | → reporting.export_kind_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| export_log | saved_report_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| export_log | subject | VARCHAR(200) | required |  | Onderwerp | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| export_log | filters | JSON |  |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| export_log | row_count | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |

## sales — **CR-21, in build, not on master** — 14 business columns, 19 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| sales_orders | person_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| sales_orders | guest_name | VARCHAR(200) |  |  |  | tokenised | K2 the name of a person: the token stands for it |
| sales_orders | guest_email | VARCHAR(200) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| sales_orders | guest_mobile | VARCHAR(200) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| sales_orders | payment_method | VARCHAR(20) |  |  | Betaalwijze | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| sales_orders | placed_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| shop_contacts | person_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| shop_contacts | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| shop_settings | intro | TEXT |  |  |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| sales_order_lines | variant_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| sales_order_lines | quantity | INTEGER | required |  | Aantal | plain | K8 an amount, a date, a count, a flag or a code |
| sales_order_lines | unit_code | VARCHAR(8) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| sales_order_lines | unit_price | NUMERIC(10, 2) | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| sales_order_lines | delivered_at | DATETIME |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |

## stock — **CR-21, in build, not on master** — 13 business columns, 14 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| stock_locations | name | VARCHAR(255) | required |  | Naam | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| stock_locations | is_default | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| stock_movements | variant_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| stock_movements | quantity | INTEGER | required |  | Aantal | plain | K8 an amount, a date, a count, a flag or a code |
| stock_movements | reason | VARCHAR(20) | required | → stock.movement_reason_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| stock_movements | occurred_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| stock_movements | order_line_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| stock_movements | note | TEXT |  |  | Opmerking | never | K3 free text or an address beside a person's payment, mail or stock movement (Koen, 15 October 2026) |
| stock_movements | actor | VARCHAR(255) |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| stock_reservations | order_line_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| stock_reservations | variant_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| stock_reservations | quantity | INTEGER | required |  | Aantal | plain | K8 an amount, a date, a count, a flag or a code |
| stock_reservations | status | VARCHAR(20) | required | → stock.reservation_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |

## product — **CR-21, in build, not on master** — 12 business columns, 14 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| products | name | VARCHAR(255) | required |  | Naam | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| products | description | TEXT |  |  | Omschrijving | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| products | status | VARCHAR(20) | required | → product.product_status_codes | Status | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| products | pre_order | BOOLEAN | required |  |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| products | pre_order_until | DATE |  |  |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| product_attachments | media_asset_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| product_attachments | title | VARCHAR(255) |  |  | Titel | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| product_attachments | description | VARCHAR(255) |  |  | Omschrijving | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| product_attachments | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |
| product_variants | sku | VARCHAR(64) |  |  |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| product_variants | properties | JSON | required |  |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| product_variants | sort_order | INTEGER | required |  | Volgorde | plain | K8 an amount, a date, a count, a flag or a code |

## auth — 11 business columns, 12 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| users | email | VARCHAR(255) | required |  | E-mail | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| users | is_active | BOOLEAN | required |  | Actief | plain | K8 an amount, a date, a count, a flag or a code |
| login_tokens | email | VARCHAR(255) |  |  | E-mail | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| login_tokens | token | VARCHAR(128) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| login_tokens | otp_code | VARCHAR(64) |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| login_tokens | expires_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| login_tokens | used | BOOLEAN | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| login_tokens | attempts | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| login_tokens | purpose | VARCHAR(20) | required | → auth.login_purpose_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| login_tokens | payload | JSON |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| user_roles | role_code | VARCHAR(20) | required | → auth.role_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |

## public — 10 business columns, 5 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| kernel_tenant_settings | key | VARCHAR(100) | required |  |  | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| kernel_tenant_settings | value | TEXT |  |  | Waarde | never | K10 one column, several data: per key; the membership amounts and dates are public, the rest never (Koen, 15 October 2026) |
| kernel_tenant_settings | value_encrypted | TEXT |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| kernel_jobs | name | VARCHAR(100) | required |  | Naam | plain | K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03) |
| kernel_jobs | payload | JSON | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| kernel_jobs | status | VARCHAR(10) | required | → kernel_job_status_codes | (label of the code list) | plain | K0 a code: the label is the code list's, the value is a code |
| kernel_jobs | run_at | DATETIME | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| kernel_jobs | attempts | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| kernel_jobs | max_attempts | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| kernel_jobs | last_error | TEXT |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |

## mail — 6 business columns, 3 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| email_log | recipient | VARCHAR(255) | required |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |
| email_log | subject | VARCHAR(500) | required |  | Onderwerp | never | K3 a mail to a person: its text names the person |
| email_log | email_type | VARCHAR(40) | required | → mail.email_type_codes |  | never | K3 a mail to a person: its text names the person |
| email_log | body | TEXT |  |  | Tekst | never | K3 a mail to a person: its text names the person |
| email_log | status | VARCHAR(20) | required | → mail.mail_status_codes | Status | never | K3 a mail to a person: its text names the person |
| email_log | error_message | TEXT |  |  |  | never | K1 identifies a person, names who did it, or is a secret or an opaque payload |

## pricing — **CR-21, in build, not on master** — 6 business columns, 4 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| prices | product_id | INTEGER | required |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| prices | variant_id | INTEGER |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
| prices | price_type | VARCHAR(20) | required | → pricing.price_type_codes |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| prices | amount | NUMERIC(10, 2) | required |  | Bedrag | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| prices | currency | VARCHAR(3) | required |  |  | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |
| prices | valid_from | DATE | required |  | Geldig van | public | K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026) |

## membership — 4 business columns, 6 technical

| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |
|---|---|---|---|---|---|---|---|
| memberships | year | INTEGER | required |  | Jaar | plain | K8 an amount, a date, a count, a flag or a code |
| memberships | is_active | BOOLEAN | required |  | Actief | plain | K8 an amount, a date, a count, a flag or a code |
| memberships | valid_from | DATE |  |  | Geldig van | plain | K8 an amount, a date, a count, a flag or a code |
| memberships | valid_to | DATE |  |  |  | plain | K8 an amount, a date, a count, a flag or a code |
