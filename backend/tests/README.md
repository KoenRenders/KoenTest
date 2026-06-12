# Backend-tests

Gerichte security- en regressietests rond de geldstromen (betalingen,
lidmaatschap-dedup, inschrijvingslimiet) en de audit-trail. De tests draaien
tegen een **echte PostgreSQL** (zoals productie) en bouwen het schema via de
volledige migratieketen (`alembic upgrade head`) — zo testen ze meteen ook de
migraties mee.

## Eenmalig: testdatabase

Wijs `TEST_DATABASE_URL` naar een lege Postgres-database die je mag wissen:

```bash
export TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/raaktest"
```

Met de Docker-stack kun je daarvoor de bestaande `db`-service gebruiken:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -c "CREATE DATABASE raaktest;"
```

## Draaien

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Standaard (zonder `TEST_DATABASE_URL`) wordt
`postgresql+psycopg2://postgres@localhost:5432/raaktest` verondersteld.

## Hoe de isolatie werkt

- Het schema wordt één keer per testsessie opgebouwd via `alembic upgrade head`.
- Elke test draait in een geneste transactie (SAVEPOINT) die achteraf wordt
  teruggedraaid, zodat de `db.commit()` in de endpoints de tests niet vervuilt.
- Mollie wordt gemockt (`mock_mollie`-fixture); er gaat geen netwerkverkeer uit.
- De in-memory rate-limiters worden per test gereset.
