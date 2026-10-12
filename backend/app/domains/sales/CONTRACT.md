# sales — the webshop (CR-21, the webshop)

**Doel.** The orders, their lines and the shop's own settings (D6): a `SalesOrder`
is a payable of `payment` (D4), its lines carry the price fixed at the order (D3),
and the shop's intro and contact persons live here (F17). The screens come with the
commits that follow.

## Facade (`api.py`)

- The ORM classes `SalesOrder`, `SalesOrderLine`, `ShopSettings`, `ShopContact`,
  the `ProductHasOrderLines` / `SalesError` exceptions.
- `order_describer()` — the describer `app/main.py` registers for
  `PayableType.ORDER`.

## Data

Schema `sales` (a migration of phase 2): `sales_orders` (soft-deleted as a
registration, Q61), `sales_order_lines` (`quantity > 0`, `unit_code` 'C62'),
`shop_settings` (one intro per tenant), `shop_contacts`. `variant_id` and
`person_id` are soft references into `product` and `mdm`.

## Events

Subscribes to `ProductDeleted`: a size with order lines is refused with
`SizeDeleteRefused`, a whole article with `ProductHasOrderLines` (T19, Q75). No
event of its own in phase 2 — `SalesOrderPlaced` and `SalesOrderChanged` are
published by the placing and change commits that follow.

## Callers

No JSON route of this component exists; none is named here.
