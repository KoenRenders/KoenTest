# stock — a ledger of movements (CR-21, the webshop)

## Purpose and process

**Doel.** What is in stock, where, and why it changed: on hand is the sum of the
movements, a reservation is kept apart, available is on hand minus the open
reservations (D2). Managed on Voorraadbeheer behind `stock.manage` (CR-24).

*Process (A2 — the shop): a receipt books what came in, a correction amends it, a
reservation holds a line apart from the order to the delivery, and the delivery
issues it.* Aggregate: `StockMovement` (the ledger); `StockReservation` and
`StockLocation` are its parts.

## Publishes

### Facade (`api.py`)

- The ORM classes `StockLocation`, `StockMovement`, `StockReservation`, the
  `movement_reason` and `reservation_status` code lists, and `StockError` /
  `NotEnoughStock`.
- `on_hand`, `available`, `reserved`, `receive`, `correct` (phase 1) and
  `reserve`, `release`, `issue`, `waiting`, `open_reservation_lines` (phase 2).

### Events (kernel)

None: stock publishes no event of its own; a delete with movements is refused
through the `ProductDeleted` event it subscribes to.

### Ports (kernel, `kernel/contracts/stock.py`)

- Offers `ReserveStock(order_line_id, variant_id, quantity, allow_short)` — the
  reservation `sales` asks when an order is placed (CR-21 Q64), handled in
  `stock/handlers.py`. Refused with `NotEnoughStock`.
- Offers `ReleaseStock(order_line_id)` — free the reservation of a cancelled
  order line (F8); handled in `stock/handlers.py`.
- Offers `IssueStock(order_line_id, actor)` — deliver a line: a GOODS_ISSUE
  movement and the reservation DELIVERED (F6, R21); handled in
  `stock/handlers.py`. Refused with `NotEnoughStock` while the on hand does not
  cover the line; the caller refuses earlier for a line with no open reservation.

## Consumes

*Counted in the code on 13 October 2026:* subscribes to `ProductDeleted`
(`kernel/contracts/product.py`) and refuses a delete of an article or a size that
still has movements (Q75); imports no facade of another domain.

## Owns

### Data

Schema `stock`: `stock_locations` (one default per tenant, created on the first
write), `stock_movements` (signed quantity, never zero, a reason),
`stock_reservations` (quantity > 0, a status). `variant_id` and `order_line_id`
are soft references into `product` and `sales`.

*Counted in the code on 13 October 2026:* schema `stock`, 5 tables; reference
codes of its own: `movement_reason_codes`, `reservation_status_codes`; jobs:
none.

## Screens

`admin_ui.py`: `/admin/voorraad` (the levels per variant), the receipt, the
correction and one size's movements, behind `stock.manage`.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| — (a signed ledger, double entry) | every change a movement with a reason | `stock.stock_movements` | follows the ERP's ledger, kept simpler (D2) |

## Rules and gates

- **Rules whose home is this module** — "available never below zero" has no home
  at rest: the advisory lock per tenant, variant and location is its one home
  (C4.1); `quantity` signed and never zero, a reservation's quantity > 0.
- **Gates in this module's own `tests/`** — the ledger sum and the lock (T5, T6).
  The gates about it stand in `backend/tests/` (`test_module_gate.py`,
  `test_schema_boundaries.py`).

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E25** — the webshop (CR-21): the ledger, the reservation and the delivery; in
  build, on v2.18.
