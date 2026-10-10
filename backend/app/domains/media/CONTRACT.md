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

## Ports this domain offers

A port is a synchronous command another domain may ask of media, with an answer
(`kernel/ports.py`, `docs/architecture.md` §3.2.1 step 2). The contracts stand in
`kernel/contracts/media.py`, the handlers in `handlers.py`. The bytes cross once:
the caller's door read the upload and its service hands a name, a type and the
bytes over. A handler flushes and never commits — the caller's transaction
commits. The limits are media's own (`MAX_UPLOAD_BYTES`, the content types per
kind); the kernel has none.

| Port | What media does | Outcome | Refuses with |
|---|---|---|---|
| `StoreFile` | stores one file of a kind, by the kind: an activity's poster and a component's info document take the place of the one their owner had and get their text read by a job that starts when the caller commits; a render and a newsletter's attachment are kept beside the others; a design image is re-encoded like every uploaded image | `AssetStored(asset_id, title, content_type)` | `MediaFout`, with the sentence for the screen: a content type the kind does not take, an empty file, a file over the limit, a file that is not what its type says, a poster or an info document without its owner; `LookupError` for a design image of an activity that does not exist |
| `RemoveAsset` | removes one asset by its id | `AssetsRemoved(1)` | `LookupError` for an id that is not there |
| `RemoveFileOf` | removes what an owner has of a kind (an activity's poster, a component's info document) | `AssetsRemoved(count)` — zero when there was nothing | `MediaFout` when no owner is named |
| `ReadTextAgain` | plans the reading of a stored document's text once more (the "Opnieuw lezen" button of the AI context) as the same job; only the extracted text is replaced | `ReadingPlanned(asset_id)` | `LookupError` for an asset that is not there or of a kind whose text is never read |

**Publishes** `DocumentTextExtracted(asset_id, title, text, extracted_at)`
(`kernel/contracts/media.py`, CR-13 phase 4d, #1251): the reading job read a
poster or an info document — also when it found no text. The chatbot keeps the
text in its own row; media writes no row of the AI context. Whether a document
was read already, the job asks the chatbot (`chatbot.api.has_extracted_text`).

Not a port: `activity_image_path`, the picture that stands for an activity in a
letter. It is a read through `api.py` and writes nothing.

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
