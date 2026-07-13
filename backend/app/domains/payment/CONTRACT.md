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

- Publiceert `PaymentSettled` (`app.kernel.contracts.payment`) bij elke
  bevestiging naar `paid` — exact één keer, want de gateway-update is
  idempotent (herhaalde webhook = no-op).

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
