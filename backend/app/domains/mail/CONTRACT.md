# mail — componentcontract (fase 1a, #399)

## Purpose and process

**Doel.** Alle uitgaande e-mail van het platform: opbouw, verzending (SMTP),
centrale logging (`mail.email_log`) en herverzending bij falen.

*Process.* None of its own: every process of A2 that tells someone something (the confirmation of a registration, a renewal, a submission; the sign-in code; the meeting mail; the newsletter) sends through this module. One record: `EmailLog`.

## Publishes

### Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- `send_registration_confirmation(to_email, name, family, ...)`
- `send_activity_registration_confirmation(...)`
- `send_form_confirmation(...)`
- `purge_old_email_logs(db, retention_days=None) -> int`

Alle `send_*` accepteren een optionele FastAPI `BackgroundTasks`; mét wordt de
SMTP-call ná de response uitgevoerd, zónder synchroon.

*Counted in the code on 13 October 2026:* the facade exports 19 names (9 functions, 5 classes, 5 values); events it owns (`kernel/contracts/`): `MailRequested` (the contract is mail's; other domains publish it, mail subscribes); ports it offers: none.

Where the Dutch text above names `send_registration_confirmation` and `send_activity_registration_confirmation`: the facade no longer exports them; those mails follow the events `FamilyRegistered` and `RegistrationConfirmed` (see *Consumes*).

## Consumes

### Events (kernel, §5.8 — trede 1)

- Abonnee van `MailRequested` (`app.kernel.contracts.mail`): componenten
  zonder directe mail-afhankelijkheid publiceren dit event; het mail-component
  verstuurt en logt via het `_send`-chokepoint.
- Subscriber of `MembershipRenewalPlaced` (`app.kernel.contracts.membership`, #1903): mail
  words the confirmation of a membership renewal (`membership_renewal_message`, with
  payment's transfer block for a transfer) and queues it in the publisher's transaction.
- Subscriber of `SubmissionCreated` (`app.kernel.contracts.forms`, CR-13 phase 4d): when
  forms names an address in `confirm_to`, mail words the confirmation of the submission
  (`form_confirmation_message`, from `forms.api.submission_confirmation`) and queues it in
  the publisher's transaction. Forms no longer calls `send_form_confirmation`.

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, forms, membership, payment; subscribes to `AnswerLinkSent`, `CodeMailRequested`, `FamilyRegistered`, `MailRequested`, `MembershipRenewalPlaced`, `RegistrationConfirmed`, `SubmissionCreated`; calls no port.

## Owns

### Jobs (kernel, §5.8)

- `mail.retry` (`handlers.py`): geplande herverzending wanneer SMTP faalt;
  backoff en max-pogingen komen uit de kernel-jobtabel. Succes zet de
  bestaande log-rij op `sent`.

### Data

Schema `mail`, tabel `email_log` (migratie 075; structuur uit 062). Bewust
geen FK's naar personen — losgekoppeld, `recipient` is het adres. Bewaartermijn
via `EMAIL_LOG_RETENTION_DAYS` (+ opschoning bij applicatiestart).

### Interne modules

`service.py` (opbouw + `_send`-choke point + logging) en `models.py` zijn
intern; buiten het component alleen via `api.py` (import-grens-test #396).
Uitzonderingen: `app.models.__init__` importeert `models` (Alembic-discovery)
en `app.main` mount `router` en importeert `handlers` (composer).

*Counted in the code on 13 October 2026:* schema `mail`, 5 tables (1 data, 4 code and label), 1 of them with `tenant_id`; status columns: `email_log.status` (code list `mail_status`: sent, failed, skipped, logged); jobs: `mail.retry`.

## Screens

### Router

`router.py` — admin-inzage in het e-maillog, gemount onder `/api/v1/admin`.

`ui.py`: 4 routes under `/admin/e-maillog` (and `/admin/emails`). The Dutch text above names a `router.py` mounted under `/api/v1/admin`; no JSON route of mail exists since #1251.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

None: no row of part D of the architecture document names this module, and its `models.py` names no standard.

## Rules and gates

- **Rules whose home is this module** — No `@validates` and no `check()` in `models.py`; no `CheckConstraint` there. Its rules stand in its service. `_send` is the one point every mail leaves through.
- **Gates in this module's own `tests/`** — none among its 8 test files.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E4** — tenant-aware background jobs: the retry job sends with the environment's settings, not the tenant's (#1792, open).
- **E25** — the webshop (CR-21): the order mail; in build, on v2.18.
- **E36** — a provider seam for mail like the mock pattern of chat, OCR, speech and the payment provider; open.
- **E34** — parked on v2.19: #1924 (the environment label in the subject of every mail from a test environment).
