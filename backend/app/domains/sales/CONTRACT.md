# sales — the webshop (CR-21, the webshop)

## Purpose and process

**Doel.** Verkoop: the webshop's order and its lines, the shop's settings and its
contact persons. The buyer's basket lives in his browser (localStorage); placing
an order recomputes every price, reserves the lines, starts the payment and
publishes `SalesOrderPlaced`, in one transaction.

*Process (A2 — the shop): browse → fill the basket → order and choose how to pay →
pay or transfer → receive the confirmation mail → deliver (Verkoop).* Aggregates:
`SalesOrder` (soft-deleted as a registration, Q61) with its `SalesOrderLine`s,
each line carrying the price fixed at the order (D3); `ShopSettings` and
`ShopContact`.

## Publishes

### Facade (`api.py`)

- `article_offer(db, product_id, member) -> dict | None` — one article's offered
  sizes with their prices, or None when it is not offered.
- `offered_products(db, member) -> list[dict]` — the articles on offer today.
- `basket_lines(db, *, member, items) -> list[dict]` — the basket's lines with
  the price recomputed here (C5).
- `place_order(db, *, …, items, member)` — the lines and their reservations.
- `submit_order(db, *, …, method, items) -> (checkout_url, order_id)` — the whole
  placing flow, committed once (C4.1).
- `total_of(order) -> Decimal` — the order's total (the derived value
  `order.total`).
- `get_order`, `orders_of_person`, `owned_order` — the reads of the order pages;
  `owned_order` admits the buyer and his household, another id is None (C5).
- `order_describer()` — the describer `app.main.py` registers for
  `PayableType.ORDER`.
- The ORM classes `SalesOrder`, `SalesOrderLine`, `ShopSettings`, `ShopContact`
  and the `ProductHasOrderLines` / `SalesError` exceptions, for other domains'
  services.

### Events (kernel)

- Publishes `SalesOrderPlaced` (`app.kernel.contracts.sales`) inside the placing
  transaction, so a rolled-back order queues no mail (#1743 A9).
- Publishes `SalesOrderChanged` on a change or a cancel (a cancel is a change to
  a total of 0, Q61) — with Verkoop's cancel, phase 2.

*Counted in the code on 13 October 2026:* events it owns (`kernel/contracts/`):
`SalesOrderPlaced`, `SalesOrderChanged`; ports it offers: none.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of `pricing`
(`price_for`), `product` (`get_product_in_tenant`, `get_variant`, `variants_of`,
`size_of`, `list_products`, `pre_order_window`, `ProductStatus`), `membership`
(`has_valid_membership`) and `mdm` (`PaymentMethod`, `MemberPerson`); subscribes
to `ProductDeleted`; calls the ports `ReserveStock` (of `stock`) and
`CreatePayment` (of `payment`), both through CR-13 phase 4c.

## Owns

### Data

Schema `sales`: `sales_orders`, `sales_order_lines` (`quantity > 0`, `unit_code`
'C62'), `shop_settings`, `shop_contacts`. `variant_id` and `person_id` are soft
references into `product` and `mdm` (no foreign key across schemas).

*Counted in the code on 13 October 2026:* schema `sales`, 4 tables (2 data, 2
settings); jobs: none; reference codes of its own: none.

## Screens

`ui.py`: `/webshop` (the list), `/webshop/{product_id}` (one article), the basket
and placing (`/webshop/bestellen`), `/webshop/bedankt` (the thank-you page),
`/mijn/aankopen` and `/mijn/aankopen/{order_id}`. The back-office screens of
Verkoop come with the commits that follow.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| UBL 2.1 / ISO 20022 | the order as a payable | `sales.sales_orders` as `PayableType.ORDER` | follows (the order pays through `payment`) |
| UN/ECE | the unit of a piece | `sales.sales_order_lines.unit_code` 'C62' | follows |

## Rules and gates

- **Rules whose home is this module** — the offer rule (`sales.service`: an
  article in sale with a price valid today for at least one size); the
  price-recomputed-at-placing rule (`place_order`, C5); `owned_order` (C5); the
  `CheckConstraint` `quantity > 0` on `sales_order_lines`.
- **Gates in this module's own `tests/`** — none. The gates about it stand in
  `backend/tests/`: `test_layer_gate.py`, `test_module_gate.py`,
  `test_payable_delete_gate.py`, `test_schema_boundaries.py`.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E25** — the webshop (CR-21): the order as a payable, the basket, Verkoop's
  screens; in build, on v2.18.
