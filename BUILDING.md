# Bouwen & valideren — één ingang (#396, architectuurdoc §13.2)

Lokaal en CI draaien dezélfde stappen. Eén commando:

```bash
make ci        # = migrate-check + test + boundaries
```

| Stap | Commando | Wat het garandeert |
|---|---|---|
| **Migrate** | `make migrate-check` | de éne Alembic-keten heeft precies één head en draait van nul tot head op een wegwerp-DB |
| **Test** | `make test` | volledige pytest-suite (unit + contract + golden flows) tegen echte Postgres |
| **Grenzen** | in de suite | `tests/test_import_boundaries.py` — kernel↑, cross-domain enkel via facades, krimpende legacy-allowlist |
| **Types** | `make typecheck` | mypy over `app/` |

Vereisten: draaiende Postgres met een `raaktest`-database (de suite dropt en
herbouwt het schema — **nooit** naar een echte DB wijzen), `pip install -r
backend/requirements-dev.txt`.

De CI (`.github/workflows/backend-tests.yml`) draait dezelfde stappen plus de
frontend-jobs (zolang de hybride periode duurt) en de blokkerende e2e/audit-gates.
Groen = mergebaar; dit bestand is de definitie van "af" (§13.2).

Deploys: `deploy-hdev.sh` (master), `deploy-uat.sh`/`deploy-prod.sh <tag>` met
pre-migratie-backup + smoke-gate + auto-rollback (#395); restore-oefening via
`scripts/restore-test.sh`.
