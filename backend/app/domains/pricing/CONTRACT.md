# pricing — prices over time (CR-21, the webshop)

**Doel.** The price of an article, over time and per audience: a `REGULAR` price
and a `MEMBER` price, each valid from a start date. A variant's price overrides
the product's (Q4). Managed on Prijsbeheer behind `price.manage` (CR-24).

## Facade (`api.py`)

- The ORM class `Price`, the `PriceType` code list and `PriceError`.
- `price_for(variant_id, on, member) -> Decimal | None` (F3): the member price
  for a member with a valid membership, else the regular price; the variant's
  price over the product's; the newest start date on or before `on`.

## Data

Schema `pricing` (a migration of phase 1): `prices` (`product_id` and
`variant_id` are soft references into `product`; `variant_id` NULL = the
product's price; `amount` CHECK ≥ 0; `currency` ISO 4217; `valid_from` date).
A price ends where the next one of the same type starts (C4.2); the key
`UNIQUE NULLS NOT DISTINCT (tenant_id, product_id, variant_id, price_type,
valid_from)` makes overlap impossible at rest.

## Events

Subscribes to `ProductDeleted` (`kernel/contracts/product.py`): drops the
product's prices in the delete's transaction (Q75).

## Callers

No JSON route of this component exists; none is named here.
