# media — capaciteitscontract (fase 4c, #404)

**Doel.** Opslag en levering van media (sponsors, foto's, affiches,
reglementen) + tekst-extractie voor de ai-context.

## Facade (`api.py`)

- `MediaAsset` (model als type), `extract_document_text`,
  `update_media_extracted_text`, `EXTRACTABLE_KINDS`.

## Opslag-adapter

Vandaag: `LargeBinary` in Postgres (`data`/`thumbnail`) — mee in de ene
backup (§13.1). Een latere object-storage-adapter wisselt achter deze facade
zonder consumers te raken.

## Data

Schema `media` (migratie 085): `media_assets`. Koppelingen naar activiteiten
en ai-context zijn soft-refs (§8, gedropt in 081/084).
