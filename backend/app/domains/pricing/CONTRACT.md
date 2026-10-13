# pricing — prices over time (CR-21, the webshop)

## Purpose and process

**Doel.** The price of an article, over time and per audience: a `REGULAR` price
and a `MEMBER` price, each valid from a start date. A variant's price overrides
the product's (Q4). Managed on Prijsbeheer behind `price.manage` (CR-24).

*Process (A2 — the shop): an article is priced before it is in sale; the price in
force is the one whose start date is newest and at or before the day.* Aggregate:
`Price`.

## Publishes

### Facade (`api.py`)

- The ORM class `Price`, the `PriceType` code list and `PriceError`.
- `price_for(variant_id, on, member) -> Decimal | None` (F3): the member price
  for a member with a valid membership, else the regular price; the variant's
  price over the product's; the newest start date on or before `on`.

### Events (kernel)

None: pricing publishes no event of its own.

## Consumes

*Counted in the code on 13 October 2026:* subscribes to `ProductDeleted`
(`kernel/contracts/product.py`) and drops the product's prices in the delete's
transaction (Q75); imports no facade of another domain.

## Owns

### Data

Schema `pricing`: `prices` (`product_id` and `variant_id` are soft references
into `product`; `variant_id` NULL = the product's price; `amount` CHECK ≥ 0;
`currency` ISO 4217; `valid_from` date). A price ends where the next one of the
same type starts (C4.2); the key `UNIQUE NULLS NOT DISTINCT (tenant_id,
product_id, variant_id, price_type, valid_from)` makes overlap impossible at
rest.

*Counted in the code on 13 October 2026:* schema `pricing`, 3 tables; reference
codes of its own: `price_type_codes`; jobs: none.

## Screens

`admin_ui.py`: `/admin/prijzen/{product_id}`, behind `price.manage`.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| ISO 4217 | currency | `pricing.prices.currency` | follows |

## Rules and gates

- **Rules whose home is this module** — a price ends where the next of the same
  type starts (C4.2), held at rest by the unique key; `amount >= 0` by CHECK.
- **Gates in this module's own `tests/`** — the price-by-date and precedence
  (T4). The gates about it stand in `backend/tests/` (`test_module_gate.py`).

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E25** — the webshop (CR-21): the price in force, per audience; in build, on
  v2.18.
