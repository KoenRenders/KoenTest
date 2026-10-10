# stock — a ledger of movements (CR-21, the webshop)

**Doel.** What is in stock, where, and why it changed: on hand is the sum of the
movements, a reservation is kept apart, available is on hand minus the open
reservations (D2). Managed on Voorraadbeheer behind `stock.manage` (CR-24).

## Facade (`api.py`)

- The ORM classes `StockLocation`, `StockMovement`, `StockReservation`, the
  `movement_reason` and `reservation_status` code lists, and `StockError` /
  `NotEnoughStock`.
- `on_hand`, `available`, `receive`, `correct` (phase 1). `reserve`, `release`,
  `issue` come with phase 2.

## Data

Schema `stock` (a migration of phase 1): `stock_locations` (one default per
tenant, created on the first write), `stock_movements` (signed quantity, never
zero, a reason), `stock_reservations` (quantity > 0, a status). `variant_id` and
`order_line_id` are soft references into `product` and `sales`.

## The lock (C4.1)

Every writer of the ledger takes the same transaction-scoped advisory lock per
tenant, variant and location; "available never below zero" has no home at rest,
so the lock is its one home. `reserve` computes available and refuses with
`NotEnoughStock` when it is short.

## Callers

No JSON route of this component exists; none is named here.
