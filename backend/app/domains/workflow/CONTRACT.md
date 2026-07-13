# workflow — componentcontract (fase 4b, #403)

**Doel.** Menselijke taken en workflows: definities (data-gedreven stappen),
instanties en taken; de werkbank is het ene scherm waarop álles landt (§20.5).

## Facade (`api.py`)

- **Taken** (het taakcontract — één DTO, `required_role`): `create_task`,
  `list_tasks`/`open_tasks`, `open_count`, `get_task`, `close_task`.
- **Workflows**: `start(db, definition_code, subject_type, subject_id,
  context)` → instantie + eerste taak; `complete_task` sluit de taak én zet de
  instantie verder ("een afwijzing is ook een beslissing" — het besluit blijft
  bewaard, de flow gaat hoe dan ook verder of eindigt); `advance`.

## Bronnen van de werkbank (v1)

1. **Berichten behartigen** — event-gedreven (`SubmissionCreated` start de
   geseede `bericht`-definitie).
2. **Refund-bevestiging** — pending refunds (FINANCE), consolidatie van de
   bestaande wachtrij.
3. **Definitief gefaalde mails** — na de `mail.retry`-pogingen.
4. **Webhook-mismatch** — gateway `paid`, grootboek niet.
5. **Definitief gefaalde jobs** — `kernel_jobs.status = failed`.

Bron 2–5 via de idempotente uur-sweep (`workflow.sweep`, titel = sleutel).
Zero-touch is het ontwerpdoel: een lege werkbank = gezond systeem.

## Kill-switch

`WORKBENCH_ENABLED=false` (§20.5): geen sweep-taken en een
uitgeschakeld-banner; bestaande taken blijven onaangeroerd.

## Bewust NIET (v1)

MDM-merge-kandidaten, e-mail-suggestielaag, SLA/prioriteiten, digests.

## Data

Schema `workflow` (migraties 072 + 082): `workflow_tasks`,
`workflow_definitions`, `workflow_instances`. Onderwerpen zijn soft-refs.
