# product — the catalogue (CR-21, the webshop)

**Doel.** The product portfolio, apart from any activity (R2): an article with
its name and description, its sizes as variants, and its pictures and documents
as links into the media library. Master data, managed on Productbeheer behind
`product.masterdata` (CR-24).

## Facade (`api.py`)

- The ORM classes `Product`, `ProductVariant`, `ProductAttachment`, the
  `ProductStatus` code list and `ProductError`.
- `get_product`, `list_products(active_only)`, `get_variant`, `variants_of`,
  `is_on_sale(product_id)`, `pre_order_window(product, on)`.

## Life cycle (`status`)

`CONCEPT` → `ON_SALE` → `DISCONTINUED`, and `DISCONTINUED` → `ON_SALE`; never
back to `CONCEPT` (Q74). Checked on the aggregate (`Product.check()`), held at
rest by the foreign key to `product.product_status_codes`. One state for the
whole article, none per size.

## Data

Schema `product` (a migration of phase 1): `products`, `product_variants`
(`sku` unique per tenant), `product_attachments` (`media_asset_id` is a soft
reference across schemas). `pricing` and `stock` read the catalogue through this
facade.

## Events

Publishes `ProductDeleted(product_id, variant_ids)` (`kernel/contracts/product.py`),
inside the transaction of the delete, so `pricing` drops the prices in the same
transaction (Q75).

## Callers

No JSON route of this component exists; none is named here.
