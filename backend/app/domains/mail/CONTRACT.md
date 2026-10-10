# mail — componentcontract (fase 1a, #399)

**Doel.** Alle uitgaande e-mail van het platform: opbouw, verzending (SMTP),
centrale logging (`mail.email_log`) en herverzending bij falen.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- `send_registration_confirmation(to_email, name, family, ...)`
- `send_activity_registration_confirmation(...)`
- `send_form_confirmation(...)`
- `purge_old_email_logs(db, retention_days=None) -> int`

Alle `send_*` accepteren een optionele FastAPI `BackgroundTasks`; mét wordt de
SMTP-call ná de response uitgevoerd, zónder synchroon.

## Router

`router.py` — admin-inzage in het e-maillog, gemount onder `/api/v1/admin`.

## Events (kernel, §5.8 — trede 1)

- Abonnee van `MailRequested` (`app.kernel.contracts.mail`): componenten
  zonder directe mail-afhankelijkheid publiceren dit event; het mail-component
  verstuurt en logt via het `_send`-chokepoint.
- Subscriber of `SubmissionCreated` (`app.kernel.contracts.forms`, CR-13 phase 4d): when
  forms names an address in `confirm_to`, mail words the confirmation of the submission
  (`form_confirmation_message`, from `forms.api.submission_confirmation`) and queues it in
  the publisher's transaction. Forms no longer calls `send_form_confirmation`.

## Jobs (kernel, §5.8)

- `mail.retry` (`handlers.py`): geplande herverzending wanneer SMTP faalt;
  backoff en max-pogingen komen uit de kernel-jobtabel. Succes zet de
  bestaande log-rij op `sent`.

## Data

Schema `mail`, tabel `email_log` (migratie 075; structuur uit 062). Bewust
geen FK's naar personen — losgekoppeld, `recipient` is het adres. Bewaartermijn
via `EMAIL_LOG_RETENTION_DAYS` (+ opschoning bij applicatiestart).

## Interne modules

`service.py` (opbouw + `_send`-choke point + logging) en `models.py` zijn
intern; buiten het component alleen via `api.py` (import-grens-test #396).
Uitzonderingen: `app.models.__init__` importeert `models` (Alembic-discovery)
en `app.main` mount `router` en importeert `handlers` (composer).
