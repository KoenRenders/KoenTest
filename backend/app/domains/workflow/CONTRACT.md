# CONTRACT — workflow (embryo, #398)

## Publiceert
- **Facade** (`api.py`): `create_task`, `open_tasks(db, roles)`, `open_count`,
  `get_task`, `close_task(db, id, done_by, decision)` — taken sluiten door
  toestand; een afwijzing is ook een beslissing (besluit wordt bewaard).

## Consumeert
- **Events**: `SubmissionCreated` (forms) → behartigen-taak voor `berichten`.
- Facades: `forms.api.submission_view` (gast-weergave in het taakdetail).

## Bezit
- **Schema**: `workflow` (workflow_tasks). Soft-refs naar onderwerpen
  (`subject_type`/`subject_id`), geen cross-schema FK's.

## Deprecaties
| Sinds | Wat | Vervangen door | Verwijderen bij |
|---|---|---|---|

## Schermen
- `/admin/werkbank` (htmx, sessie-auth + CSRF): open taken, rol-gefilterd,
  polling 30s; behartigen + afgehandeld-met-besluit.

## Groei (fase 4b, #403)
Definities/instanties, de overige vier exceptie-bronnen, kill-switch per flow.
