# cms — componentcontract (fase 4c, #404)

## Purpose and process

**Doel.** CMS-pagina's en -blokken (markdown met placeholders), publiek
leesbaar, admin schrijfbaar.

*Process (A2.4.3 — web content and forms).* One record, `CmsPage`: a page or a block of the site, with its own validator on title and slug.

## Publishes

### Facade (`api.py`)

- `CmsPage` (model als type), `render_cms_content` (placeholder-rendering,
  óók gebruikt door de chatbot-context) + de interne format-helpers.

### Router

`router.py` — publieke reads (pagina's/blokken op slug) + admin-CRUD onder
`/api/v1`. The postal-code endpoint (`/api/v1/postal-codes`) moved to mdm and
is gone since CR-13 phase 4b (#1251): it had no caller, the screens read the
postal codes through `mdm.api.list_postal_codes`.

*Counted in the code on 13 October 2026:* the facade exports 22 names (18 functions, 3 classes, 1 values); events it owns (`kernel/contracts/`): none; ports it offers: none.

Where the Dutch text above names a `router.py` with reads and admin CRUD under `/api/v1`: the module has no `router.py` and no JSON route (#1251); its screens ask the facade.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, forms, mdm, media, membership, payment; subscribes to `TenantCreated`; calls no port.

## Owns

### Data

Schema `cms` (migratie 083): `cms_pages`. `chatbot_info.cms_page_id` is nu
een soft-ref (§8, FK gedropt; ORM via expliciete primaryjoin).

*Counted in the code on 13 October 2026:* schema `cms`, 1 tables (1 data, 0 code and label), 1 of them with `tenant_id`; status columns: none; jobs: none.

## Screens

De admin-CMS-schermen klappen om naar htmx bij de React-exit (#405), samen
met de publieke slug-pagina's (die vergen de frontend-catch-all); de
markdown/editor-afweging (§19.3-Tiptap-nota) hoort bij die omklap.

`ui.py`: 7 routes — `/`, `/{slug}`, `/p/{slug}`, `/betaling/succes`, `/betaling/geannuleerd`, `/robots.txt`, `/sitemap.xml`; `admin_ui.py`: 8 routes under `/admin/paginas`. Where the Dutch text above says the admin screens still have to turn to htmx, the code has done so: both are server-rendered.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

None: no row of part D of the architecture document names this module, and its `models.py` names no standard.

## Rules and gates

- **Rules whose home is this module** — `CmsPage`: `@validates` on `title` and `slug`; no `CheckConstraint` in `models.py`.
- **Gates in this module's own `tests/`** — none among its 13 test files.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E22** — web content (CR-17): pages as structured documents, the CMS carrying a company tenant's whole public site; in build, on v2.17.
- **E26** — the checkout in two steps (CR-31): the return page's retry; planned, on no release.
- **E38** — the close-out of CR-17's status line.
