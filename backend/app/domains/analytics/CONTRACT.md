# analytics — componentcontract (fase 4c, #404)

**Doel.** Het read-model op het rapportageschema (§5.8): PII-vrije
business-events en de geaggregeerde rapporten daarop.

## Facade (`api.py`)

- `log_business_event(db, event_type, ...)` — schrijft een event; de service
  dwingt PII-vrijheid van de payload af.
- `BusinessEvent` (model als type).

## Schermen

`/admin/analyse` (htmx): omzet (netto, uit de betalingen zelf — bron van
waarheid #324), event-tellingen en een **server-gerenderde SVG**-weekgrafiek
(§23-patroon: geen chart-lib, geen JS-eiland).

## Data

Rapportageschema `analytics` (migratie 085): `business_events` — bewust geen
FK's (events overleven hun onderwerp), enkel niet-PII id's + payload.
