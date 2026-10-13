# payment — componentcontract (fase 3, #401)

## Purpose and process

**Doel.** Betalingen: de Mollie-gateway (checkout, webhook) en het interne
PaymentRecord-grootboek (charges, refunds, handmatige bevestiging) als één
component.

*Process (A2.2 — an activity: registering and paying; A2.3 — a refund; the payment of a membership in A2.1).* Aggregate: `PaymentRecord`, which carries its own `check()`, with its history; `GatewayPayment` is the provider's side of one online payment.

## Publishes

### Facade (`api.py`) — de enige toegangsdeur voor andere componenten

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

### Events (kernel, §5.8 — trede 1)

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
- Subscribes to `SalesOrderChanged` (`app.kernel.contracts.sales`, CR-21 phase
  2): `handlers.reconcile_order_on_change` brings a webshop order's charges to
  the event's `total_due` (D4, R16); a cancelled order is a change to 0 (Q61).
  It never commits.

*Counted in the code on 13 October 2026:* the facade exports 56 names (42 functions, 10 classes, 4 values); events it owns (`kernel/contracts/`): `PaymentReceived`, `RefundDue`; ports it offers: none.

## Callers

The JSON routes of this component that exist for a named caller (R14, CR-13 phase
4b, #1251 — no other caller found in: the repository, the PROD application log of
10 September – 8 October 2026):

- `POST /api/v1/payment-gateway/webhooks/mollie` — Mollie, after a payment changes;
  `gateway_service` builds the URL and hands it to Mollie. The body is never
  trusted: the status is fetched again (`AGENTS.md`, the security invariant).
- `POST /api/v1/payment-gateway/webhooks/stub` — the stub provider's pretend
  checkout (#1274), for the browser test of the payment chain; the route exists
  only where the stub may.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, mdm, membership; subscribes to `MembershipDeleted`, `OrderChanged`; calls no port.

## Owns

### Jobs (kernel, §5.8)

- `payment.reconcile` (`handlers.py`, §19.2): wees-record-check op
  `payable_type/payable_id`. Een record zonder bestaande payable faalt luid
  (ERROR-log) én wordt een FINANCE-werkbank-taak (idempotent per record).
  Her-enqueuet zichzelf dagelijks; de applicatie-start borgt dat er precies
  één geplande run leeft.

### Data

Schema `payment` (migratie 079): `gateway_payments`, `payment_records`,
`payment_record_history`. `payable_type/payable_id` is een soft-ref (§6/§8) —
bewust geen FK naar registraties/lidmaatschappen; de reconciliatie-job is de
bewaker. Refunds verwijzen via `refund_of_id` naar hun charge (self-FK).

*Counted in the code on 13 October 2026:* schema `payment`, 11 tables (3 data, 8 code and label), 3 of them with `tenant_id`; status columns: `payment_records.status` (code list `payment_status`: pending, paid, failed, cancelled); `gateway_payments.status` and its copy on `payment_record_history` are plain columns: the provider's word (CR-12 §B4.10); jobs: none.

Where the Dutch text above names a job `payment.reconcile`: no `@job` of that name is registered in the code.

## Screens

`ui.py`: 15 routes under `/admin/betalingen`, and the payment tabs of an activity, a registration and a household (`/admin/activiteiten`, `/admin/inschrijvingen`, `/admin/leden`).

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| Belgian structured communication; ISO 20022 | OGM (mod 97); `RmtInf/Strd` | `payment.payment_records.structured_communication` | follows (`kernel/structured_communication.py`) |
| UBL 2.1 | `cac:PaymentMeans`, `cbc:PaymentID`, `cbc:Note` | `payment.payment_records` · `structured_communication`, `description` | follows (CR-31 B3a) |
| ISO 20022 | payment status (`ACSC`, `RJCT`, …) | `payment.gateway_payments.status` | deviates: the provider's own word, mapped in the adapter and never stored as our list (CR-12 §B4.10) |
| OpenDocument | Spreadsheet (ODS), cells typed | the payments export | follows (#200) |

## Rules and gates

- **Rules whose home is this module** — `PaymentRecord.check()` on the aggregate; 2 `CheckConstraint`s in `models.py`. The webhook never trusts its body: the status is fetched again (`AGENTS.md`, the security invariant).
- **Gates in this module's own `tests/`** — none among its 28 test files. The gates about it stand in `backend/tests/`: `test_payable_delete_gate.py`, `test_payment_choice_gate.py`.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E25** — the webshop (CR-21): the order as a payable, with its describer; in build, on v2.18.
- **E26** — the checkout in two steps (CR-31): a port, a pay route with its page, one column; planned, on no release.
- **E34** — parked on v2.19: #1884 (a received amount equal to the full amount settles the payment).
