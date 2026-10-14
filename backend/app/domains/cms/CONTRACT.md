# cms — componentcontract (CR-17 fase 1, #1671)

## Purpose and process

**Doel.** Pagina's als gestructureerde documenten (blokken als JSON tegen
één schema), publiek leesbaar, admin schrijfbaar — met concept, publicatie
en geschiedenis per taal.

*Process (A2.4.3 — web content and forms).* One record, `CmsPage`: a page or a block of the site, with its own validator on title and slug.

## Publishes

### Facade (`api.py`)

- `CmsPage`, `CmsPageTranslation` (modellen als type), `render_cms_content`
  (placeholder-rendering) + de interne format-helpers.
- CR-17: `save_document`, `save_page_form`, `publish`, `take_page_offline`,
  `restore`, `versions`, `draft_differs`, `editable_document`,
  `published_document`, `published_html`, `published_text`, `placeholders`,
  `schema` (waaronder `schema_for`, `validate_document`), `get_translation`,
  `create_page`, `references`.
- De chatbot-context leest `published_text` (niet meer
  `render_cms_content`): de gepubliceerde versie, nooit het concept.

### Router

`router.py` — publieke reads (pagina's/blokken op slug) + admin-CRUD onder
`/api/v1`. The postal-code endpoint (`/api/v1/postal-codes`) moved to mdm and
is gone since CR-13 phase 4b (#1251): it had no caller, the screens read the
postal codes through `mdm.api.list_postal_codes`.

*Counted in the code on 13 October 2026, on master:* the facade exports 22 names (18 functions, 3 classes, 1 values); CR-17 adds the names listed above, not counted again here. Events it owns (`kernel/contracts/`): none; ports it offers: none.

Where the Dutch text above names a `router.py` with reads and admin CRUD under `/api/v1`: the module has no `router.py` and no JSON route (#1251); its screens ask the facade.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, forms, mdm, media, membership, payment; subscribes to `TenantCreated`; calls no port.

## Owns

### Data

Schema `cms`: `cms_pages` (migratie 083), `page_translations` en
`cms_page_history` (migratie 200, CR-17 fase 1). De vertaalrij draagt
`draft_json` en `published_json`; de site toont de gepubliceerde versie,
en een pagina die de migratie niet verliesvrij kon omzetten houdt haar
opgeslagen HTML tot de auteur publiceert. `chatbot_info.cms_page_id` is een
soft-ref (§8, FK gedropt; ORM via expliciete primaryjoin).

*Counted in the code on 13 October 2026, on this branch with CR-17:* schema `cms`, 3 tables (`cms_pages`, `page_translations`, `cms_page_history`), 1 of them with `tenant_id` (`cms_pages`); status columns: none; jobs: none.

## Screens

`/admin/paginas` (lijst) en `/admin/paginas/{id}` (recordscherm met de
TipTap-editor, snede 3) via `admin_ui.py`; de publieke pagina via
`ui.py`. De editor noemt haar set via `schema.schema_for("page")`.

`ui.py`: 7 routes — `/`, `/{slug}`, `/p/{slug}`, `/betaling/succes`, `/betaling/geannuleerd`, `/robots.txt`, `/sitemap.xml`; `admin_ui.py`: 11 routes under `/admin/paginas` (counted on this branch with CR-17, 13 October 2026; master's contract counted 8). Both are server-rendered.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

None: no row of part D of the architecture document names this module, and its `models.py` names no standard.

## Rules and gates

- **Rules whose home is this module** — `CmsPage`: `@validates` on `title` and `slug`; no `CheckConstraint` in `models.py`.
- **Gates in this module's own `tests/`** — none among its 20 test files (counted on this branch).

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E22** — web content (CR-17): pages as structured documents, the CMS carrying a company tenant's whole public site; in build, on v2.17.
- **E26** — the checkout in two steps (CR-31): the return page's retry; planned, on no release.
- **E38** — the close-out of CR-17's status line.
