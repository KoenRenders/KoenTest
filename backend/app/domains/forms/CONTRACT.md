# CONTRACT — forms

## Publiceert
- **Facade** (`api.py`):
  - `get_form_by_slug(db, slug) -> Form | None` — publiek raadpleegbaar formulier.
  - `submission_count(db, form_id) -> int`.
  - `submission_confirmation(db, submission_id) -> dict | None` — what the confirmation of
    a submission says (the form's title, the submitter's name, the form's own sentence, the
    link to change the answer); a read, for `mail`, which words the confirmation.
- **Events**: `SubmissionCreated` (kernel/contracts/forms.py) — gepubliceerd bij elke inzending (berichten/workflow is de
  eerste consument; event-ladder trede 1, synchroon/in-transactie).
  Since CR-13 phase 4d (#1251) it carries `confirm_to`: the address a confirmation goes to,
  or None. Forms decides (the form asks for one, is not anonymous, an address was given);
  `mail` subscribes and queues the mail. An ordinary form's submission publishes it too
  since then — until then only a message did, whatever the line above said.
  `SubmissionDeleted` (same contract file, #1377) — published by
  `delete_submission` in the delete's transaction; workflow closes the open task.
- **Constant**: `CONTACT_FORM_SLUG` — the slug of the seeded contact form, written
  once in `service.py` (#1377).

## Ports this domain offers

A port is a synchronous command another domain may ask of forms, with an answer
(`kernel/ports.py`, `docs/architecture.md` §3.2.1 step 2). The contracts stand in
`kernel/contracts/forms.py`, the handlers in `handlers.py`; a handler flushes and
never commits — the caller's transaction commits.

| Port | What forms does | Outcome | Refuses with |
|---|---|---|---|
| `SubmitAttached` | stores the answers another domain's record carries (a registration's answers to its component's questions, CR-14 §B4.2) as an attached submission, judged by the form's own rules; no mail, no event | `AttachedSubmission(submission_id)` | `VeldFout` (422, the question in `veld_id`): a required question without an answer, an option that is not the question's, a value outside its range |
| `UpdateAttached` | replaces the answers of an attached submission (the board corrects them, CR-14 §B4.7), by the same rules | `AttachedSubmission(submission_id)` | `VeldFout` as above; `LookupError` for a submission that does not exist or is not attached |
| `SubmitMessage` | stores a message for the board on the contact form — the one write path of a message (#398), for a caller without a visitor's form (the chatbot's tool); publishes `SubmissionCreated` | `MessageSubmitted(submission_id)`, None when there is no contact form | forms' own refusal of a missing name, address or message, unchanged |
| `CopyForm` | makes a new form with the same sections, questions and options and no submissions, the new year in its title and slug (a copied activity's component, #1397) | `FormCopied(form_id)` | `LookupError` for a form that does not exist |

The two service functions behind them are not in the facade any more: another
domain asks through the ports.

## Consumeert
- Facades: geen.

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
