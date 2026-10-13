# workflow — componentcontract (fase 4b, #403)

## Purpose and process

**Doel.** Menselijke taken en workflows: definities (data-gedreven stappen),
instanties en taken; de werkbank is het ene scherm waarop álles landt (§20.5).

*Process.* None of its own: it carries the task a process hands to a person — the message to answer (A2.4.3), the refund to confirm (A2.3), the mail or job that failed for good. Its records are `WorkflowTask`, `WorkflowDefinition` and `WorkflowInstance`.

## Publishes

### Facade (`api.py`)

- **Taken** (het taakcontract — één DTO, `required_role`): `create_task`,
  `list_tasks`/`open_tasks`, `open_count`, `get_task`, `close_task`,
  `close_subject_tasks` (closes the open tasks of a subject that no longer
  exists and ends their workflow, #1377).
- **Workflows**: `start(db, definition_code, subject_type, subject_id,
  context)` → instantie + eerste taak; `complete_task` sluit de taak én zet de
  instantie verder ("een afwijzing is ook een beslissing" — het besluit blijft
  bewaard, de flow gaat hoe dan ook verder of eindigt); `advance`.

*Counted in the code on 13 October 2026:* the facade exports 47 names (26 functions, 8 classes, 13 values); events it owns (`kernel/contracts/`): none; ports it offers: none.

## Consumes

### Bronnen van de werkbank (v1)

1. **Berichten behartigen** — event-gedreven (`SubmissionCreated` start de
   geseede `bericht`-definitie). `SubmissionDeleted` closes the submission's open
   task with the reason "inzending verwijderd" (#1377). The contact form's slug
   comes from `forms.api.CONTACT_FORM_SLUG`, not from a copy here.
2. **Refund-bevestiging** — pending refunds (FINANCE), consolidatie van de
   bestaande wachtrij.
3. **Definitief gefaalde mails** — na de `mail.retry`-pogingen.
4. **Webhook-mismatch** — gateway `paid`, grootboek niet.
5. **Definitief gefaalde jobs** — `kernel_jobs.status = failed`.

Bron 2–5 via de idempotente uur-sweep (`workflow.sweep`, titel = sleutel).
Subscribes to `PaymentReceived` and `RefundDue` (CR-13 phase 2): both advance the
sweep (`vervroeg_sweep`, #705, #855) — never make or close a task themselves.
Zero-touch is het ontwerpdoel: een lege werkbank = gezond systeem.

*Counted in the code on 13 October 2026:* imports the facades of auth, forms, mail, payment; subscribes to `PaymentReceived`, `RefundDue`, `SubmissionCreated`, `SubmissionDeleted`, `TenantCreated`; calls no port.

## Owns

### Kill-switch

`WORKBENCH_ENABLED=false` (§20.5): geen sweep-taken en een
uitgeschakeld-banner; bestaande taken blijven onaangeroerd.

### Data

Schema `workflow` (migraties 072 + 082): `workflow_tasks`,
`workflow_definitions`, `workflow_instances`. Onderwerpen zijn soft-refs.

*Counted in the code on 13 October 2026:* schema `workflow`, 13 tables (3 data, 10 code and label), 3 of them with `tenant_id`; status columns: `workflow_tasks.status` (`task_status`: open, done), `workflow_instances.status` (`run_status`: running, done, failed); jobs: `workflow.sweep`.

## Screens

`ui.py`: 4 routes under `/admin/werkbank` — the list, a task's record (`/taken/{task_id}`) and its handling.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

None: no row of part D of the architecture document names this module, and its `models.py` names no standard.

## Rules and gates

- **Rules whose home is this module** — No `@validates` and no `check()` in `models.py`; no `CheckConstraint` there. Its rules stand in its service. Since #1931 the workbench's own rules have one home, `workbench.py`: the next step per kind, for whom a task is, and whether it is handled here.
- **Gates in this module's own `tests/`** — none among its 3 test files.

## Evolutions

### Bewust NIET (v1)

MDM-merge-kandidaten, e-mail-suggestielaag, SLA/prioriteiten, digests.

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E4** — tenant-aware background jobs: the hourly sweep scans every tenant and files its tasks under the default one; open.
- **E30** — workbench tasks for the member administration: open.
- **E34** — parked on v2.19: #1874 (a task offers no link to a screen its reader may not open).
- **E40** — a rule engine or a workflow engine for the workbench: rejected; task rules are queries in the owning domain.
