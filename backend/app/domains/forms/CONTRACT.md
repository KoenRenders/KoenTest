# CONTRACT — forms

## Publiceert
- **Facade** (`api.py`):
  - `get_form_by_slug(db, slug) -> Form | None` — publiek raadpleegbaar formulier.
  - `submission_count(db, form_id) -> int`.
- **Events**: `SubmissionCreated` (kernel/contracts/forms.py) — gepubliceerd bij elke inzending (berichten/workflow is de
  eerste consument; event-ladder trede 1, synchroon/in-transactie).

## Consumeert
- Facades: geen.
- Legacy (krimpt): `analytics.service.log_business_event` — vervalt met de
  business_events-opruiming (blok O).

## Bezit
- **Schema**: `form` (forms, form_sections, form_fields, form_field_options,
  form_submissions, form_submission_answers) — geen cross-schema FK's.
- **Jobs**: geen (nog).

## Deprecaties
| Sinds | Wat | Vervangen door | Verwijderen bij |
|---|---|---|---|

## Schermen
- `/berichten` (publiek, htmx — ui.py): het geseede Contacteer-ons-formulier (#398).
- Nog React (`/admin/formulieren`, publieke render `/f/<slug>`); klappen om met
  de form-builder-herbouw (#405) resp. blok P-fundament.
