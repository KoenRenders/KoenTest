# payment — componentcontract (fase 3, #401)

**Doel.** Betalingen: de Mollie-gateway (checkout, webhook) en het interne
PaymentRecord-grootboek (charges, refunds, handmatige bevestiging) als één
component.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Gateway**: `create_payment` (Mollie-checkout), `refresh_payment_status`.
- **Grootboek**: `create_payment_record`, `confirm_manual_payment`,
  `create_refund` (FINANCE), `handle_gateway_update` (idempotent),
  `registration_balance`, `reconcile_registration_charges`, `net_paid`.
- **Dé lookup-helper (§19.3)**: `get_records_for(db, payable_type, payable_id)`
  — geen losse PaymentRecord-queries buiten het component.
- **Lidmaatschapsprijzen**: `membership_price_for_date`,
  `membership_valid_period`, `current_membership_counts`.
- **Modellen als type**: `PaymentRecord`, `GatewayPayment`,
  `PaymentRecordHistory`.

## Events (kernel, §5.8 — trede 1)

- Publishes `PaymentReceived` (`app.kernel.contracts.payment`, CR-13 phase 2)
  on every way money comes in — the provider's webhook, "bevestig betaald", the
  treasurer's status correction — with the booked amount and whether it covers
  the record (`fully_paid`, #720). A repeated webhook is a no-op and publishes
  nothing. It replaced `PaymentSettled`, which only the webhook published.
- Publishes `RefundDue` when a refund is created that has yet to be paid out.
- Subscribes to `OrderChanged` (`app.kernel.contracts.activities`, CR-13
  phase 1): `handlers.reconcile_registration_on_order_change` brings a
  registration's charges to the event's `total_due` (#185), in the publisher's
  transaction. It never commits.

## Jobs (kernel, §5.8)

- `payment.reconcile` (`handlers.py`, §19.2): wees-record-check op
  `payable_type/payable_id`. Een record zonder bestaande payable faalt luid
  (ERROR-log) én wordt een FINANCE-werkbank-taak (idempotent per record).
  Her-enqueuet zichzelf dagelijks; de applicatie-start borgt dat er precies
  één geplande run leeft.

## Data

Schema `payment` (migratie 079): `gateway_payments`, `payment_records`,
`payment_record_history`. `payable_type/payable_id` is een soft-ref (§6/§8) —
bewust geen FK naar registraties/lidmaatschappen; de reconciliatie-job is de
bewaker. Refunds verwijzen via `refund_of_id` naar hun charge (self-FK).

## Callers

The JSON routes of this component, each with the caller it exists for (R14, CR-13
phase 4b — measured 29 September 2026 in the repository and in the PROD
application log):

- `POST /api/v1/payment-gateway/webhooks/mollie` — Mollie, after a payment
  changes; the URL is built by `gateway_service` and handed to Mollie. The body
  is never trusted: the status is fetched again (`CLAUDE.md`, the security
  invariant).
- `POST /api/v1/payment-gateway/webhooks/stub` — the stub provider's pretend
  checkout (#1274), for the e2e payment chain; the route exists only where the
  stub may.
