# cms — componentcontract (fase 4c, #404)

**Doel.** CMS-pagina's en -blokken (markdown met placeholders), publiek
leesbaar, admin schrijfbaar.

## Facade (`api.py`)

- `CmsPage` (model als type), `render_cms_content` (placeholder-rendering,
  óók gebruikt door de chatbot-context) + de interne format-helpers.

## Router

`router.py` — publieke reads (pagina's/blokken op slug) + admin-CRUD onder
`/api/v1`. The postal-code endpoint (`/api/v1/postal-codes`) moved to mdm and
is gone since CR-13 phase 4b (#1251): it had no caller, the screens read the
postal codes through `mdm.api.list_postal_codes`.

## Data

Schema `cms` (migratie 083): `cms_pages`. `chatbot_info.cms_page_id` is nu
een soft-ref (§8, FK gedropt; ORM via expliciete primaryjoin).

## Schermen

De admin-CMS-schermen klappen om naar htmx bij de React-exit (#405), samen
met de publieke slug-pagina's (die vergen de frontend-catch-all); de
markdown/editor-afweging (§19.3-Tiptap-nota) hoort bij die omklap.
