# cms — componentcontract (CR-17 fase 1, #1671)

**Doel.** Pagina's als gestructureerde documenten (blokken als JSON tegen
één schema), publiek leesbaar, admin schrijfbaar — met concept, publicatie
en geschiedenis per taal.

## Facade (`api.py`)

- `CmsPage`, `CmsPageTranslation` (modellen als type), `render_cms_content`
  (placeholder-rendering) + de interne format-helpers.
- CR-17: `save_document`, `save_page_form`, `publish`, `take_page_offline`,
  `restore`, `versions`, `draft_differs`, `editable_document`,
  `published_document`, `published_html`, `published_text`, `placeholders`,
  `schema` (waaronder `schema_for`, `validate_document`), `get_translation`,
  `create_page`, `references`.
- De chatbot-context leest `published_text` (niet meer
  `render_cms_content`): de gepubliceerde versie, nooit het concept.

## Router

`router.py` — publieke reads (pagina's/blokken op slug) + admin-CRUD onder
`/api/v1`. The postal-code endpoint (`/api/v1/postal-codes`) moved to mdm and
is gone since CR-13 phase 4b (#1251): it had no caller, the screens read the
postal codes through `mdm.api.list_postal_codes`.

## Data

Schema `cms`: `cms_pages` (migratie 083), `page_translations` en
`cms_page_history` (migratie 200, CR-17 fase 1). De vertaalrij draagt
`draft_json` en `published_json`; de site toont de gepubliceerde versie,
en een pagina die de migratie niet verliesvrij kon omzetten houdt haar
opgeslagen HTML tot de auteur publiceert. `chatbot_info.cms_page_id` is een
soft-ref (§8, FK gedropt; ORM via expliciete primaryjoin).

## Schermen

`/admin/paginas` (lijst) en `/admin/paginas/{id}` (recordscherm met de
TipTap-editor, snede 3) via `admin_ui.py`; de publieke pagina via
`router.py`. De editor noemt haar set via `schema.schema_for("page")`.
