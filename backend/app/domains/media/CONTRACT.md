# media — capaciteitscontract (fase 4c, #404)

**Doel.** Opslag en levering van media (sponsors, foto's, affiches,
reglementen) + tekst-extractie voor de ai-context.

## Facade (`api.py`)

- `MediaAsset` (model als type), `extract_document_text`,
  `update_media_extracted_text`, `EXTRACTABLE_KINDS`.

## Soorten (`kind`)

`sponsor`, `activity_photo`, `activity_poster`, `component_info`,
`newsletter_file`, en sinds #1005 voor CR-10: `design_image` (een beeld ín een
affiche, tot 4096 px) en `design_render` (de gerenderde affiche). Wat er via het
upload-eindpunt binnen mag, staat in `UPLOADABLE_KINDS`; `design_render` wordt
door de Design Studio zelf gemaakt en daar expliciet geweigerd.

**Elke geüploade afbeelding wordt heropend en opnieuw gecodeerd** — ook een
`design_image`. Dat is geen verkleining maar een beveiliging: EXIF en
kleurprofiel gaan eruit, het type komt uit de inhoud, en een bestand dat zich
als afbeelding voordoet komt er niet doorheen. Alleen de doelmaat verschilt per
soort (`MAX_FULL_BY_KIND` in `images.py`).

## Opslag-adapter

Vandaag: `LargeBinary` in Postgres (`data`/`thumbnail`) — mee in de ene
backup (§13.1). Een latere object-storage-adapter wisselt achter deze facade
zonder consumers te raken.

## Data

Schema `media` (migratie 085): `media_assets`. Koppelingen naar activiteiten
en ai-context zijn soft-refs (§8, gedropt in 081/084).
