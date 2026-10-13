# product — the catalogue (CR-21, the webshop)

## Purpose and process

**Doel.** The product portfolio, apart from any activity (R2): an article with
its name and description, its sizes as variants, and its pictures and documents
as links into the media library. Master data, managed on Productbeheer behind
`product.masterdata` (CR-24).

*Process (A2 — the shop): an article is created, set in sale, priced and, at the
end, Afgevoerd.* Aggregate: `Product`, which carries its own `check()` (the life
cycle); `ProductVariant` and `ProductAttachment` are its parts.

## Publishes

### Facade (`api.py`)

- The ORM classes `Product`, `ProductVariant`, `ProductAttachment`, the
  `ProductStatus` code list and `ProductError`.
- `get_product`, `get_product_in_tenant` (the tenant-filtered read, J4),
  `list_products(active_only)`, `get_variant`, `variants_of`, `is_on_sale`,
  `pre_order_window(product, on)`, and the writes `create_product`, `set_status`,
  `add_variant`, `delete_product`.

### Events (kernel)

- Publishes `ProductDeleted(product_id, variant_ids)` (`kernel/contracts/product.py`)
  inside the delete's transaction, so `pricing` drops the prices and `stock` (and,
  later, `sales`) refuse a delete that still has movements or order lines (Q75).

*Counted in the code on 13 October 2026:* events it owns: `ProductDeleted`;
ports it offers: none.

## Consumes

*Counted in the code on 13 October 2026:* imports the facade of `media` and calls
its ports `StoreFile` and `RemoveFileOf` for the pictures and documents; imports
nothing else of another domain.

## Owns

### Data

Schema `product`: `products`, `product_variants` (`sku` unique per tenant),
`product_attachments` (`media_asset_id` is a soft reference across schemas).

*Counted in the code on 13 October 2026:* schema `product`, 6 tables; reference
codes of its own: `product_status_codes`; jobs: none.

## Screens

`admin_ui.py`: `/admin/producten` (the list) and `/admin/producten/{id}` (the
record), behind `product.masterdata`.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| UBL 2.1 | `cac:Item` with repeatable `cbc:Description`/property | `product.product_variants.properties` (JSON list of name/value) | follows |

## Rules and gates

- **Rules whose home is this module** — the life cycle `CONCEPT → ON_SALE →
  DISCONTINUED` (never back to `CONCEPT`) on `Product.check()` (Q74); `sku` unique
  per tenant.
- **Gates in this module's own `tests/`** — the status walk, the sku uniqueness.
  The gates about it stand in `backend/tests/` (`test_module_gate.py`,
  `test_schema_boundaries.py`).

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E25** — the webshop (CR-21): the catalogue, its prices and its stock; in
  build, on v2.18.
