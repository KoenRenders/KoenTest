# media — capaciteitscontract (fase 4c, #404)

**Doel.** Opslag en levering van media (sponsors, foto's, affiches,
reglementen) + tekst-extractie voor de ai-context.

## Facade (`api.py`)

- `MediaAsset` (model als type), `extract_document_text`,
  `update_media_extracted_text`, `EXTRACTABLE_KINDS`.
- The storage seam (#1473): `media_url` (a picture's address) and `asset_bytes`
  (its bytes) — the only way another module reaches either, enforced by
  `test_media_seam_gate.py`.
- The picker (#1472/#1473): `pick_options`, `offered_by_picker`,
  `PICKABLE_KINDS`, `KIND_BRANCHES` — what is shown and what may be stored come
  from one condition.

## Soorten (`kind`)

`sponsor`, `activity_photo`, `activity_poster`, `component_info`,
`newsletter_file`, en sinds #1005 voor CR-10: `design_image` (een beeld ín een
affiche) en `design_render` (de gerenderde affiche). Wat er via het
upload-eindpunt binnen mag, staat in `UPLOADABLE_KINDS`; `design_render` wordt
door de Design Studio zelf gemaakt en daar expliciet geweigerd.

**Elke geüploade afbeelding wordt heropend en opnieuw gecodeerd** — ook een
`design_image`. Dat is geen verkleining maar een beveiliging: EXIF en
kleurprofiel gaan eruit, het type komt uit de inhoud, en een bestand dat zich
als afbeelding voordoet komt er niet doorheen. Sinds #1473 is er één doelmaat voor
elke soort: 2 400 px aan de lange zijde (`MAX_FULL` in `images.py`), genoeg voor
een A3-affiche.

## Opslag-adapter

Vandaag: `LargeBinary` in Postgres (`data`/`thumbnail`) — mee in de ene
backup (§13.1). Een latere object-storage-adapter wisselt achter deze facade
zonder consumers te raken.

## Data

Schema `media` (migratie 085): `media_assets`. Koppelingen naar activiteiten
en ai-context zijn soft-refs (§8, gedropt in 081/084).

## Callers

The JSON routes of this component that exist for a named caller (R14, CR-13 phase
4b, #1251 — no other caller found in: the repository, the PROD application log of
10 September – 8 October 2026):

- `GET /api/v1/media/{asset_id}` — every page, mail and newsletter that shows or
  links a stored file: `media_url` builds the address (the activity poster, the
  component info file, a page's pictures, the newsletter's pictures and
  attachments, the logo).
- `GET /api/v1/media/{asset_id}/thumb` — the same, for the small rendering of an
  image or of the first page of a PDF.
