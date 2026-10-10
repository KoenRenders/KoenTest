# Change Request 31 — The checkout in two steps: a registration stands with an open charge when the provider does not answer

**Project:** Web Portal "Raak Millegem"
**Status:** shaped on 9 October 2026 · **not planned on any release** (Koen, 9 October 2026: "ja, goed idee, maar niet in v2.16" and "Dit plannen we ooit") · build read by dev2 taken in, every point (9 October 2026, #1829); the screen concepts (C9) still to come · two questions open and parked for when the change request is planned: Q6 (Koen, 9 October 2026) and Q7
**Tracking issue:** #1829 — the one place where what is open stands; this document is the design, the issue is the status
**Applies to:** payment (a port, a pay route with its page, one column), activities and membership (the three doors that open a charge), cms (the return page's retry), the events gate of CR-13 (three declared calls leave it); mail and reporting are used, not changed
**Reading:** A 1 498 words · B 2 493 · C 4 902 — code fences excluded, table pipes counted, measured on 9 October 2026 after the build read; the budget is A ≤ 1 500, B ≤ 2 500

---

# Part A — The business

## A1. Reason to act — the trigger

A member who registers, renews a membership or signs up a family and pays online is sent to the provider's payment page. When the provider does not answer, the portal throws everything away: registration, answers, family. The screen says *"… Je inschrijving is niet bewaard — probeer ze later opnieuw"*, and the member starts over, if at all.

Not acceptable for a thing the member did right: the association wants the registration kept and the payment tried again, now or later. Koen, 9 October 2026, to the proposal: *"ja, goed idee, maar niet in v2.16."*

Two more reasons made it a change request and not a repair: the domain-boundary work (CR-13) found these three places the last where one part of the portal reaches an outside service on another's behalf, and the coming webshop (CR-21) needs the same two steps — order, then pay.

## A2. As-is process — how it works today, and where it hurts

```mermaid
flowchart LR
  subgraph Member
    m0((Wants to register)) --> m1[Fill in the form]
    m1 --> m2[Choose online payment]
    m5[Pay at the provider] --> m6((Registered and paid))
    m8((Nothing kept)) 
  end
  subgraph Portal
    p1[Save the registration] --> p2[Ask the provider for a payment page]
    p2 --> q{Provider answers?}
    q -- yes --> p3[Send the member to the payment page]
    q -- no --> p4[Throw everything away, show an error]
    p5[Record the payment] --> p6[Send the confirmation]
  end
  subgraph Provider
    v1[Payment page] -.-> p5
  end
  m2 --> p1
  p3 --> m5
  m5 -.-> v1
  p4 --> m8
  p6 -.-> m6
```

*What to see: saving and asking the provider are one step; a silent provider takes the saving with it.*

| # | Step | Who | Pain |
|---|---|---|---|
| 1 | Fill in the form, choose online payment | member | — |
| 2 | Save and ask the provider, in one movement | portal | a silent provider undoes the saving |
| 3 | An error (502 or 422) | portal → member | everything typed is gone: registration, answers, family and persons |
| 4 | Pay at the provider, come back | member | — |
| 5 | Record the payment, confirm by mail | portal | — |

Three places do this: registering for an activity (public and from the board), renewing a membership in *Mijn gezin*, and *Word lid*. How often the provider is silent is not measured; the backend log carries one line per occurrence (*"Betaling aanmaken mislukt"*), countable on PROD before the build.

## A3. To-be process — how it should work afterwards

```mermaid
flowchart LR
  subgraph Member
    m0((Wants to register)) --> m1[Fill in the form]
    m1 --> m2[Choose online payment]
    m5[Pay at the provider] --> m6((Registered and paid))
    m7[Try again, or come back later] --> m9((Registered, payment open))
  end
  subgraph Portal
    p1[Save the registration and the open charge] --> p2[Open the pay page]
    p2 --> p3[Ask the provider for a payment page]
    p3 --> q{Provider answers?}
    q -- yes --> p4[Send the member on to the provider]
    q -- no --> p5[Say so: registration kept, button to try again]
    p6[Record the payment] --> p7[Send the confirmation]
  end
  subgraph Provider
    v1[Payment page] -.-> p6
  end
  m2 --> p1
  p4 --> m5
  m5 -.-> v1
  p5 --> m7
  m7 --> p2
  p7 -.-> m6
```

*What to see: one step split in two; saving stands, asking the provider is its own repeatable step.*

| # | Step | Who | What changes |
|---|---|---|---|
| 1 | Fill in the form, choose online payment | member | — |
| 2 | Save the registration **and the open charge** | portal | the saving stands, whatever the provider does |
| 3 | The portal's pay page asks the provider and sends the member on | portal | new; normally invisible — the browser goes straight on |
| 4 | Silent provider: the pay page says the registration is kept, offers to try again | portal → member | replaces the error |
| 5 | Pay at the provider, come back | member | — |
| 6 | Record the payment, confirm by mail | portal | — |

The state "registered, not yet paid" exists today for a member who closes the provider's page; the board sees an open booking in *Betalingen*. A silent provider now leaves the same state instead of an error.

**What it says on the screen:**

| Where | Text |
|---|---|
| the pay page, title | *Betalen* |
| the pay page, when the provider does not answer | *De betaalpagina is even niet bereikbaar.* — *Je inschrijving is bewaard. Probeer het zo meteen opnieuw.* (for a membership: *Je lidmaatschap is geregistreerd.*) |
| its buttons | *Opnieuw proberen* (primary) · *Terug naar de startpagina* |
| the return page after a payment that did not go through | gets a working *Opnieuw proberen*, to the same pay page |
| *Mijn gezin*, a renewal whose payment is open | *Betaling hervatten* (as today), now always offered |
| *Mijn inschrijvingen*, an online registration whose payment is open | *Betaling hervatten* (new; the card's word) |
| the confirmation mail, online, signed in | *Nog niet betaald? Je kan de betaling hervatten onder Mijn inschrijvingen.* (renewal or sign-up: *… in Mijn gezin*); a guest: Q6 |

## A4. Benefits — what the change earns

- **No registration lost to a silent provider.** Today an occurrence costs a member a whole form and the association maybe a participant; afterwards a click.
- **No repair work for volunteers.** Today a member who gave up mails the board, who registers them by hand.
- **A payment that can always be resumed.** Today *Betaling hervatten* depends on the provider still knowing the old page; afterwards the portal asks for a fresh one.
- **The webshop (CR-21) gets its checkout step**, and CR-13's last three direct provider calls disappear.

## A5. Supplied material — and what it taught us

None from the board; the source is the code on master and CR-13 phase 4c/4d (#1251). Reporting need: none — the open charge is a booking like any other in *Betalingen* and the payment reports.

## A6. Business requirements — what the board asks, with MoSCoW

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | A registration, a renewal or a sign-up with online payment is saved even when the provider does not answer; the payment stays open. | Must | Koen, 9 Oct 2026 ("ja, goed idee") | today's state of an abandoned payment |
| R2 | The member is told the registration is kept and can retry the payment from the same screen. | Must | Koen, 9 Oct 2026 | replaces the error |
| R3 | Retrying never makes the member pay twice: one open provider payment per charge. | Must | shaping | |
| R4 | The board sees it as an abandoned payment today: an open booking, no new state or screen. | Must | shaping | |
| R5 | The return page's *Opnieuw proberen* and *Mijn gezin*'s *Betaling hervatten* lead to the same pay page. | Should | shaping | the first goes to the home page today |
| R6 | The confirmation mail of an online registration tells the member where on the site the payment can be resumed. | Should | Koen, 9 Oct 2026 ("laten verwijzen naar het scherm waar de betaling kan hernomen worden, waar het zichtbaar is in de site") | not a pay link of its own; the guest's mail: Q6 |
| R8 | *Mijn inschrijvingen* offers *Betaling hervatten* for an online registration whose payment is open, as the membership card does for a renewal. | Should | shaping, from Koen's answer on R6 | today only the card has it |
| R7 | A waiting page that keeps asking the provider in the background. | Won't | architecture CLI, 9 Oct 2026 | a new screen for every payment, for a rare failure |

## A7. Non-functional requirements — security, privacy, house style, tenants

| Concern | This change |
|---|---|
| **Security** — who may do what; new inputs from outside; secrets | a public page behind an unguessable link; one payment per charge while one is open; rate-limited like the webhook; no new secret |
| **Privacy** — personal data: what, where, who sees it, what leaves the system | the page shows what the charge is for and the amount — the provider's words today; nothing new leaves the system; the link is personal, like the confirmation mail |
| **House style / UI norm** — `docs/design-system.md`; brand rules | one public page in the site shell, from the kit (the return page's shape) |
| **Multi-tenant** — what differs per unit, what is platform-wide | each unit's own provider account, as today; a unit's pay link does not work on another's address |

## A8. Acceptance criteria — what the business signs off on HDEV

| # | Criterion | Requirement | Walkthrough steps |
|---|---|---|---|
| AC1 | Provider unreachable: registering online shows the pay page with *Je inschrijving is bewaard* and *Opnieuw proberen*; the board's list has the registration with an open booking. | R1, R2, R4 | W1–W4 |
| AC2 | Provider back: *Opnieuw proberen* opens the provider's page; paying marks the booking paid, the return page says *Betaling ontvangen*. | R2, R3 | W5–W7 |
| AC3 | The pay link opened twice while a payment is open: the same payment page; one booking, one provider payment. | R3 | W8 |
| AC4 | The same for *Word lid* and for a renewal in *Mijn gezin*; *Betaling hervatten* opens the pay page. | R1, R5 | W9–W11 |
| AC5 | Provider reachable from the start: nothing looks different — the form sends the member straight to the provider. | R1 | W12 |
| AC6 | Signed in, an online registration left unpaid shows *Betaling hervatten* under *Mijn inschrijvingen*, which opens the pay page; the confirmation mail names that screen. | R6, R8 | W13–W14 |

---

# Part B — The solution, for whoever approves it

## B1. Solution outline — the solution and the decisions that shape it

Opening a charge and asking the provider for a payment page become two steps in two requests. The first is a **port** of payment, `OpenCharge`, called by the door service inside its own transaction; payment writes the charge, reaches no network, and answers with the charge's id and its pay path. The door commits and redirects there. The second is **payment's own pay route**, `/betalen/<token>`: it asks the provider for a payment page unless one is open and sends the browser on; when the provider does not answer it renders the page with *Opnieuw proberen*, the charge untouched. Transfer and free charges take the same port and change nothing visible; webhook, ledger, status screens and mails stay as they are.

- **D1 — a port, not a direct call with a licence.** `OpenCharge → ChargeOpened(record_id, pay_path, structured_communication)` in `kernel/contracts/payment.py`, handled in payment (§3.2.1). Rejected: the direct call as a named network exception — the provider stays inside the door's transaction. C4.1.
- **D2 — the provider is reached by payment's own route, after the commit.** One place starts, resumes and fails a checkout. Rejected: each door reaching the provider after its commit — the retry written three times. C4.2.
- **D3 — one open provider payment per charge.** Re-fetched, then reused while open, otherwise a new one; a paid charge goes to the return page; a closed charge is Q7. Rejected: a new provider payment per visit — duplicates, a webhook finding the wrong one. C4.3.
- **D4 — an opaque token column, not the charge's id.** The id travels in board URLs, exports and logs; a capability should not. Rejected: the id as the link. C4.4.
- **D5 — the failure is the pay page itself, with a button.** Rejected: a job and a polling wait page (R7). C4.5.
- **D6 — the existing retry paths point at the pay route.** `checkout_url_for` returns the pay path, so a lapsed provider page is no dead end. C4.6.
- **D7 — the port carries the description; the charge stores it.** `payment_records.description`: the provider gets each door's words of today, and payment never branches on a payable type (`describers.py`); the return address comes from the describer. Rejected: deriving it in payment. C4.2.

| # | Derived requirement | From |
|---|---|---|
| F1 | A port `OpenCharge` with exactly one handler in payment; the handler writes the charge, flushes, commits nothing, reaches no network. | R1, CR-13 |
| F2 | Every charge has an opaque token, unique, set at creation, never shown in a board screen. | R2, R3 |
| F3 | `GET /betalen/<token>` serves an online charge above zero: 303 to the provider, 200 with message and button, or 303 to the return page when paid; 404 for any other token or charge. | R2, R3 |
| F4 | The route locks the charge while it asks the provider: two visits at once, one provider payment. | R3 |
| F5 | The three doors call the port from a service, commit, redirect to the pay path for an online charge; transfer and free as today. | R1, R4 |
| F6 | The return page's *Opnieuw proberen* (while the charge is open and the provider's payment lapsed), *Mijn gezin*'s *Betaling hervatten* and a new one under *Mijn inschrijvingen* all open the pay path. | R5, R8 |
| F9 | The confirmation mail of an unpaid online charge names the screen where it can be resumed — *Mijn inschrijvingen* or *Mijn gezin* (a renewal sends no mail today); a guest's mail: Q6. | R6 |
| F7 | The three entries leave the events gate's declared set with the doors (the gate is red on a stale entry); `create_payment_record` stays an export that writes, called by payment only. | CR-13 F7/AC7 |
| F8 | A way to make the provider fail: a wrong provider key for the unit (HDEV), a switch on the stub (e2e). | AC1 |

## B2. Fit with the process and the requirements — for the business

```mermaid
flowchart LR
  subgraph Member
    m1[Fill in the form<br/>activities · membership]:::a --> m2[Choose online payment<br/>activities · membership]:::a
    m5[Pay<br/>provider]:::x --> m6((Paid))
    m7[Try again<br/>payment pay page]:::p --> p2
  end
  subgraph Portal
    p1[Save registration and open charge<br/>activities · membership → payment port]:::a --> p2[Pay page asks the provider<br/>payment /betalen]:::p
    p2 --> q{Answers?}
    q -- yes --> p4[303 to the provider<br/>payment]:::p
    q -- no --> p5[Message and button<br/>payment pay page]:::p
    p6[Webhook records the payment<br/>payment]:::p --> p7[Confirmation mail<br/>mail]:::m
  end
  m2 --> p1
  p4 --> m5
  m5 -.-> p6
  p5 --> m7
  p7 -.-> m6
  classDef a fill:#dbeafe,stroke:#1e3a8a
  classDef p fill:#dcfce7,stroke:#166534
  classDef m fill:#fef9c3,stroke:#854d0e
  classDef x fill:#e5e7eb,stroke:#374151
```

*Blue: the doors (activities, membership). Green: payment. Yellow: mail. Grey: outside the portal.*

| R | How the solution meets it (in the role's words) | F | Module (C2) | Test (C6) | AC |
|---|---|---|---|---|---|
| R1 | "My registration is saved before the portal even talks to the provider." | F1, F5 | payment, activities, membership | T1, T2, T3 | AC1, AC4, AC5 |
| R2 | "If the payment page is down I see that, and a button to try again." | F3 | payment | T4, T5 | AC1, AC2 |
| R3 | "Clicking twice does not make me pay twice." | F2, F3, F4 | payment | T6, T7 | AC3 |
| R4 | "The treasurer sees an open booking, nothing new." | F5 | payment (unchanged screens) | T2 | AC1 |
| R5 | "Every 'try again' goes to the same page." | F6 | cms, membership | T8 | AC4 |
| R6 | "The mail tells me where on the site I can finish paying." | F9 | mail | T12 | AC6 |
| R8 | "My unpaid registration shows a button to pay, like my membership." | F6 | activities | T8 | AC6 |
| R7 | Won't: no waiting page | — | — | — | — |

**Walkthrough on HDEV.** *Visitor, activity with a paid product; the operator first sets a wrong provider key on `/admin/tenants` (F8):*

1. W1 Register for the activity, *Online betalen*, send. **See:** *Betalen* with *De betaalpagina is even niet bereikbaar. Je inschrijving is bewaard.* and *Opnieuw proberen*.
2. W2 Press *Opnieuw proberen*. **See:** the same page again (the provider is still unreachable).
3. W3 As board: *Inschrijvingen* of the activity. **See:** the registration, its booking *Open*.
4. W4 *Betalingen*. **See:** one open booking.
5. W5 The operator enters the right key again; *Opnieuw proberen*. **See:** the provider's payment page (test mode) with the amount.
6. W6 Pay. **See:** the return page; within moments *Betaling ontvangen*.
7. W7 As board: *Betalingen*. **See:** the booking *Betaald*.
8. W8 Open the pay link of W1 again. **See:** the return page, no second payment. A fresh online registration, its pay link opened twice: **see** the same provider page; the board one booking.

*Member of a household, `Mijn gezin`; wrong key first:*

9. W9 *Lidmaatschap vernieuwen*, online, send. **See:** the pay page with *Je lidmaatschap is geregistreerd.*
10. W10 Back to *Mijn gezin*. **See:** the card with *Betaling hervatten*, which opens the pay page.
11. W11 Key restored; *Word lid*, online. **See:** straight to the provider's page.
12. W12 Any online registration, provider reachable. **See:** straight to the provider, no pay page.
13. W13 Signed in, register online, close the provider's page unpaid; open *Mijn inschrijvingen*. **See:** *Betaling hervatten* on the registration; it opens the provider's page.
14. W14 The confirmation mail of W13 (the e-mail log). **See:** the sentence naming *Mijn inschrijvingen*.

## B3. The whole across the modules — for the architect

```mermaid
flowchart TB
  subgraph kernel
    k1[contracts/payment.py: OpenCharge, ChargeOpened]:::new
    k2[ports.py · events.py]:::used
  end
  subgraph payment
    s1[handlers.py: @handles OpenCharge]:::new
    s2[checkout.py: open_charge, start_checkout]:::new
    s3[ui.py: GET /betalen/token · betalen.html]:::new
    s4[models.py: PaymentRecord.pay_token · migration]:::chg
    s5[service.py: create_payment_record → open_charge; checkout_url_for → pay path]:::chg
    s6[gateway_service · providers · webhook · admin screens]:::used
  end
  subgraph activities
    a1[service.py: the charge after register]:::chg
    a2[router.py · ui.py · admin_ui.py: redirect to pay_path]:::chg
  end
  subgraph membership
    b1[signup_service · portal_service: call the port]:::chg
    b2[membership_card: OnlineDue → pay path]:::chg
  end
  subgraph cms
    c1[betaling_resultaat.html · ui.py: retry to pay path]:::chg
  end
  P[(payment schema)]:::used
  X[Provider]:::used
  a1 -- call(OpenCharge) --> k2
  b1 -- call(OpenCharge) --> k2
  k2 --> s1 --> s2
  s3 --> s2 --> s6 -.-> X
  b2 -- payment.api --> s5
  c1 -- payment.api --> s5
  s2 --> P
  classDef new fill:#dcfce7,stroke:#166534
  classDef chg fill:#ffedd5,stroke:#9a3412
  classDef used fill:#e5e7eb,stroke:#374151
```

*Green new, orange changed, grey used; arrows are port calls or facade imports.*

```mermaid
erDiagram
  PAYMENT_RECORD {
    string id PK
    string payable_type
    int payable_id
    numeric amount
    string method
    string status
    string gateway_payment_id FK "nullable"
    string structured_communication "nullable"
    string pay_token "NEW · unique · not null"
    string description "NEW · nullable"
  }
  GATEWAY_PAYMENT {
    string id PK
    string provider
    string provider_payment_id
    string status "the provider's word"
    string checkout_url
  }
  REGISTRATION {
    int id PK
  }
  MEMBERSHIP {
    int id PK
  }
  PAYMENT_RECORD }o--o| GATEWAY_PAYMENT : "the open or last provider payment"
  PAYMENT_RECORD }o..o| REGISTRATION : "payable_type = registration"
  PAYMENT_RECORD }o..o| MEMBERSHIP : "payable_type = membership"
```

Who calls whom: the activities service and the two membership services call `kernel.ports.call(OpenCharge(...), db)`; payment's handler writes `PaymentRecord`, flushes, returns `ChargeOpened`; the door commits, as today. The pay route (`payment/ui.py`) alone asks the provider: lock, re-fetch, `gateway_service.create_payment` when no payment is open, link, commit, redirect. No new dependency direction: activities and membership already depend on payment; payment takes the household of a membership from its describer (`PayableDescription.household_id`) for the return address — no new read. The provider is reached only in payment's own request. Impact: two additive columns on `payment.payment_records`; `create_payment_record`'s gateway branch moves to `start_checkout`; the three door blocks reading `GatewayPayment` go; the import and layer gates hold (a `ui.py` on `payment.api`; the port called from services — rule 6 moves the activities block out of `router.py`).

## B3a. Standards the model follows — and where it deviates, on purpose

Standards checked: UBL 2.1 / EN 16931 (`cac:PaymentMeans`, `cbc:PaymentID`), ISO 20022. No business concept is new: the charge and the provider payment exist.

| Concept in this change | Standard and element | Ours (table · column, name) | Follows / deviates — why |
|---|---|---|---|
| the charge | UBL `cac:PaymentMeans`, `cbc:PaymentID` | `payment.payment_records`, `structured_communication` | follows, unchanged |
| the link to pay | none: UBL carries a payment means, not a web capability | `payment.payment_records.pay_token` | no standard applies; a random identifier, no meaning encoded |
| the description | UBL `cbc:Note` on the payment means; the provider's `description` | `payment.payment_records.description` | follows: free text |
| the provider payment | ISO 20022 payment status (`ACSC`, `RJCT`, …) | `payment.gateway_payments.status`, the provider's word (CR-12 §B4.10) | deviates as before: the provider's vocabulary, mapped in the adapter |

## B4. Rules this change needs an exception from — decided once, here

| Rule (where) | What the design does instead | Mechanism | Temporary until … / the new rule | Decided |
|---|---|---|---|---|
| none — gates checked: *events, not calls* (a port call is no command call; three declared entries go), rule 6 *a port is called from a service, never from a door* (the activities block moves to the service), *no network in a handler* (T1 guards the provider call: the gate does not see it), *no commit behind another domain's api*, the layer gate (a `ui.py` on `payment.api`), the import gate (payment → membership, a read), `NETWORK_MODULES` (the provider's client stays in payment's adapter) | — | — | — | architecture CLI, 9 Oct 2026 |

## B5. Cost — investment and running cost, and what operations must know

**Investment:** one phase. payment (contract, handler, `checkout.py`, route and page, columns, tests): M, about 1.5 CLI-days; activities and membership (the doors, the card, *Mijn inschrijvingen*): S, 0.75; cms: S, 0.25; mail: S, 0.25; the stub's switch and the e2e: S, 0.5. About 3.25 CLI-days, plus the screen concepts (C9).

**Running cost:** none: no new service or dependency; the provider is called as often as today or less.

**Operations:** one additive migration (existing charges get a token). No env var. On HDEV, AC1 uses a wrong provider key on the unit's settings screen (W1, W5) — in the "Na de merge" block. Rollback: the previous tag; the columns are harmless to the old code.

## B6. Phasing — shippable phases, and what changes on the failure paths

| Phase | Delivers | Migration | Env vars | Data | Failure paths that change | Manual validation |
|---|---|---|---|---|---|---|
| 1 — two pull requests | (a) port, handler, columns, pay route and page, the three doors, the three entries out of the events gate, the stub switch, tests; (b) the retry paths on the pay path, the mail sentence | one, additive | none | tokens for existing charges | **provider unreachable at registration:** today an error (502; 422 at the sign-up and the renewal), nothing saved; afterwards saved, the pay page (R1, R2). **At the retry:** the same page, charge untouched. **Provider payment lapsed, charge still pending:** today a dead provider page behind *Betaling hervatten*; afterwards a fresh payment. **Charge closed by the webhook:** Q7. **Two visits at once:** one provider payment. **A paid charge's link:** the return page. Unchanged: webhook, abandoned payment, refused form | W1–W14 |

**Order:** not planned (Koen, 9 October 2026: "niet voor v2.16. Dit plannen we ooit"); when it is, before CR-21 phase 0. The declared calls name this change request until (a) merges.

## B7. Rule and gatekeeper — what this fixes for all future work

**The rule:** a charge is opened through payment's port in the caller's transaction and never reaches the provider; only payment's own pay route does, in its own request, after the commit. It goes into `docs/architecture.md` §3.2.1 (the second worked example of a port) and payment's `CONTRACT.md`.

**Reach and baseline:** three call sites today, none afterwards; the events gate holds them declared, pull request (a) removes them and the gate is **hard** for both domain pairs. T1 guards the handler's provider call (C7). No new gate.

## B8. Open decisions — what the approver still decides

| # | Question | Recommendation | What the answer changes |
|---|---|---|---|
| Q6 | **Parked by Koen on 9 October 2026 ("graag laten liggen, is voor later").** A guest (no account, so no screen to resume on) — what does the mail say about an unpaid online charge? | The return page's sentence: *Nog niet betaald? Je kan de betaling later voltooien via een bestuurslid.* — consistent with CR-22; the alternative is a pay link for guests only. | the mail's template branches on "has a person"; whether a guest can pay without the board. |
| Q7 | **Parked with Q6 until planned.** The webhook closes a charge whose provider payment lapsed (failed or cancelled on the record); what does the pay route do with such a closed charge? | Reopen it (pending again, a history row, a fresh provider payment) unless a newer open charge for the same payable exists; the alternative is to serve pending charges only. Reasons in C4.7. | whether `start_checkout` may change a charge's status; one history action. |

## B9. Decisions log — dated answers

| Date | Decision | By |
|---|---|---|
| 9 Oct 2026 | On the master CLI's question C7-B (CR-13 phase 4c): a port that writes the charge and a route of payment's own that starts the checkout; *Opnieuw proberen* instead of a 502. Rejected: a named network exception; a job with a wait page. A functional change, so its own change request. | architecture CLI |
| 9 Oct 2026 | "ja, goed idee, maar niet in v2.16. Maak je issue aan?" — the registration may stand with an open charge; a change request of its own; not on v2.16. Tracking issue #1829. | Koen, to the master CLI |
| 9 Oct 2026 | Shaped as CR-31; the three calls stay declared on the events gate until it removes them. | architecture CLI |
| 9 Oct 2026 | Build read by dev2 (#1829) taken in, every point (C8); one needs Koen and is parked with Q6: Q7. | architecture CLI |
| 9 Oct 2026 | Q1: no pay link of its own in the mail; it refers to the screen where the payment can be resumed — "Ik zou laten verwijzen naar het scherm waar de betaling kan hernomen worden, waar het zichtbaar is in de site." R6, R8, F9; the guest's mail Q6. | Koen, via the master CLI |
| 9 Oct 2026 | Q2: "En neen, niet voor v2.16. Dit plannen we ooit." — not planned. | Koen, via the master CLI |

---

# Part C — The build, for the master CLI and the dev CLIs

## C1. Verified premises — measured before the handover

Measured on master @ `b8abc0bd` on 9 October 2026 (the merge of #1824); to be re-measured on master just before the handover.

| Concept or claim | Kind | Readers or measurement (file:line) | Verdict | Consequence |
|---|---|---|---|---|
| `create_payment_record` writes the record, flushes and does not commit; for `ONLINE` it calls `gateway_service.create_payment` first | relies on | `domains/payment/service.py:68–140` | holds | the handler is this function without the gateway branch |
| three callers outside payment, each rolling back with a 502 when the provider fails | relies on | `activities/router.py:473–510`, `membership/portal_service.py:150–184`, `membership/signup_service.py:143–160` | holds; `signup_service` only takes `ValueError` back and reads the checkout URL after its commit | all three become port calls; the 502 branches go |
| a fourth caller inside payment: the reconciliation opens a transfer charge for an outstanding amount | relies on | `domains/payment/service.py:822` | holds | `create_payment_record` stays payment's internal service (renamed or not: the build's call); the port is the door for other domains |
| `activities/router.py::create_registration` is a *door* to the rules gate (`_is_door`: `router.py`), and a port may not be called from a door (rule 6) | relies on | `tests/test_rules_gate.py:1135`, `:1623` | holds | the payment block moves into `activities/service.py` (C2) |
| `PaymentRecord.id` is a uuid4 string; `gateway_payment_id` is nullable | relies on | `domains/payment/models.py:232`, `:253` | holds | an online charge without a provider payment is representable today; D4 adds a token beside the id |
| `PaymentStatus` has four codes: pending, paid, failed, cancelled | relies on | `domains/payment/models.py:58` | holds | no new status: "no provider payment yet" is `pending` with `gateway_payment_id` null — but the webhook closes the charge itself on a lapse (`handle_gateway_update`, `service.py:166–175`, writes failed or cancelled), after which `open_renewal_payment` and the sign-up's guard no longer see it: Q7 |
| `GatewayPayment.status` holds **our** code: the adapter maps before it answers (`our_status(...).value`, `providers/mollie.py:118,132`) and `gateway_service` stores that value or the literal `needs_review` (`:77,115,119`); the model's comment ("Mollie's vocabulary") says otherwise | relies on | corrected by the build read (dev2, 9 Oct): the first version of this row read it as the provider's word | D3 reads it as `PaymentStatus(gp.status)` with a branch for a value that is no member (`needs_review`: not open), as `payment/service.py:577–580` does; `expired` arrives as `failed` (`mollie.py:47`) |
| readers of `gateway_payment_id` outside payment | changes | the three door blocks above; `workflow/handlers.py:142` (inner join, the webhook-mismatch task) | the three go with the port; the join skips a charge without a provider payment — stays right | — |
| the board's payments list reads `GatewayPayment.checkout_url` | changes | `payment/service.py:1365` | stays right: the provider's URL, for the board | — |
| the rules gate's declared set holds the three calls; `_ratchet` is red on an entry that no longer occurs | relies on | `tests/rules_baseline.py:56–68` (six entries on 9 Oct, three of them these), `test_rules_gate.py:2536–2551` | holds | the three leave in pull request (a), F7 |
| `checkout_url_for(db, record)` returns the provider's URL or None | changes | `payment/service.py:1583`; its readers `membership/membership_card.py:83`, `payment/api.py:40` | must change: returns the pay path (D6) | the card's *Betaling hervatten* is always offered for an open online charge |
| `open_renewal_payment` counts a membership charge not paid/cancelled/failed as running | relies on | `membership/service.py:367` | holds | an open online charge without a provider payment blocks a second renewal and shows the card — right |
| the return page `/betaling/succes` reads the ledger, polls while not settled; `/betaling/geannuleerd` renders *Opnieuw proberen* with `href="/"` | changes | `cms/ui.py:105–133`, `cms/templates/betaling_resultaat.html:41` | must change (F6): the button goes to the pay path; **finding:** nothing links to `/betaling/geannuleerd` — the provider always returns to the success address | F6 adds the button to the success page's lapsed state; the cancelled route is a Non-goal, reported |
| the `redirect_url` the provider returns to differs per door: public `/betaling/succes?registration=<id>`, board `/admin/inschrijvingen/{id}`, membership `/betaling/succes?member=<household id>` | changes | `activities/router.py:389`, `activities/api.py:354`, `portal_service.py:145`, `signup_service.py:137` | must change: the pay route derives it (C4.2) | the describer gives the household (`PayableDescription.household_id`, `membership/payables.py:78`) and the registration's id — no new read; the board passes `?terug=`, checked by `app.ui.veilige_terug` (`app/ui/__init__.py:262`) (C5) |
| the provider's description per door: *Inschrijving <activity> – <contact>*, *Raak Millegem lidmaatschap <year> – <name>* | changes | `activities/router.py:468`, `portal_service.py:140–142` (the signed-in person, last name first, `valid_to.year`), `signup_service.py:131–134` (the main member, today's year); the describers word it differently again (`membership/payables.py:59,72`, `activities/payables.py:86–87`), and `payment` may not branch on a payable type to describe it (`describers.py:10–14`) | the port carries the door's words and the charge stores them (D7): the text on the member's bank statement does not change | one nullable column more |
| the board's registration with online payment redirects the board to the provider's page | relies on | `activities/admin_ui.py:1643` | holds | the board is redirected to the pay path with `?terug=/admin/inschrijvingen/<id>`; same behaviour |
| the stub provider has no failure switch; the e2e chain waits for the stub's checkout URL after submit | changes | `payment/providers/stub.py`, `tests_e2e/activities/test_online_payment_chain.py:39` | the wait holds through the 303 of the pay route (not run: C8); a switch is added (F8), and a helper that lapses a payment beside `pay()` (T6) | T10 |
| `test_nothing_is_committed_before_the_payment_step` expects the 502 to take the answers back | changes | `tests/integration/test_registration_questions.py:198–231` | must change: the premise ("a payment that cannot start") no longer exists at the door; a zero amount never reaches the port either — the door opens a charge only above zero (`router.py:458`) | rewritten as T3: the port handler made to raise rolls everything back; a silent provider never reaches the door |
| other tests naming `create_payment_record` or the 502 | changes | `payment/tests/test_payment_history_rows.py`, `test_payment_stub_1274.py`, `test_webhook_url_1279.py`; `tests/integration/test_codes_phase1.py`, `test_kritische_flows_coverage.py`, `test_membership_payment_return.py`, `test_structured_communication.py`, `test_transfer_wording_1775.py`; `tests/test_record_form_gate.py` | the payment-internal ones stay right (the function stays, exported and writing — the rules gate's parametrised test names it, `test_rules_gate.py:2771`); the webhook-URL test moves to `start_checkout`; the build read named the others that pin the provider's URL or the call at the door: `tests/integration/test_registration_form_1284.py`, `test_membership_renewal.py`, `test_gezinsportaal_lopende_vernieuwing.py`, `test_household_add_and_email_1641.py`, `test_publieke_site.py`, `test_deelnemerslijst_na_inschrijving.py`; `test_kritische_flows_coverage.py::test_families_betaalfout_rolt_alles_terug` expects 422 and a full rollback | C6 |
| `_renewal_running.html:20–22` explains a missing checkout URL | changes | the card's template | the branch becomes dead: an open online charge always has a pay path — it goes | C2 membership |
| the confirmation mails read `payment_record_id` from the event and build the transfer block; the registration mail already carries a line with the history URL for a registration made while signed in | relies on | `mail/handlers.py:131–245` (`_transfer_of`, `history_url`), `mail/service.py:755` | holds | F9 adds its sentence to that line; the family welcome mail gets one naming *Mijn gezin* |
| *Mijn inschrijvingen* shows the transfer block for an unpaid registration and nothing for an unpaid online one | changes | `activities/my_registrations.py:68–74`, `templates/_my_registration.html:33`; the card's online block `membership/membership_card.py:83`, `_renewal_running.html:18` | must change (R8): the online block as the card has it | C2 activities, T8 |
| reporting: no view reads a column this change adds | relies on | migrations 096, 100, 102, 106, 116 read `payment_records` columns; none is `pay_token` | holds | reporting — none (C2) |
| PostgreSQL 16 has `gen_random_uuid()` in core | relies on | the stack's image (`docker-compose.*.yml`, Postgres 16) | to confirm in the build read | the migration's default for existing rows |
| which provider HDEV runs | relies on | the server's env (`PAYMENT_PROVIDER`), not in the repository | **to measure by the master CLI** | the walkthrough's F8 path: a wrong key (Mollie test mode) or the stub's switch |
| the three entries on the events gate name `create_payment_record` from the three callers | relies on | `tests/test_rules_gate.py`, the declared set after CR-13 phase 4d | holds on 9 Oct (dev1's count) | pull request (b) removes them |

## C2. Per module: what must happen

### kernel

**Code:** `kernel/contracts/payment.py` gains the port `OpenCharge(payable_type: str, payable_id: int, amount: Decimal, method: str, source: str, actor: Optional[str])` and its outcome `ChargeOpened(record_id: str, pay_path: str, structured_communication: Optional[str])` — plain values only, as the ports gate demands. No code list is new: `payable_type` and `method` are the codes of `PayableType` and `PaymentMethod`, converted at the handler as `create_payment_record` converts them today. **Tests:** T1.

### payment

**Screens:** one new public page, `betalen.html`, in the site shell: the result-page shape of the return page (`ui.public_form_page(result=True)`, `ui.flow_card`), with the heading *Betalen*, the message of A3 per payable type, the amount, and two buttons (`ui.btn_primary` *Opnieuw proberen* to the same path, `ui.btn_secondary` *Terug naar de startpagina*). Judged at 390 px (C9). The happy path renders nothing: a 303.

**Code:** `payment/handlers.py`: `@handles(OpenCharge)` — converts, calls `open_charge` (the body of today's `create_payment_record` without the gateway branch: the record, the structured communication for a transfer, the history row), returns `ChargeOpened`. `payment/checkout.py` (new): `open_charge(...)`, `pay_path_for(record) -> str` (`/betalen/<pay_token>`), `start_checkout(db, record) -> str | None`: refuses anything but an online charge above zero (the route's 404); `SELECT … FOR UPDATE` on the record; paid → None; a linked provider payment is re-fetched first (`refresh_payment_status`, then `handle_gateway_update`, inside the lock — the webhook is left out on localhost and may lag elsewhere) and reused when `PaymentStatus(gp.status) is PENDING` and a checkout URL stands (a value that is no member, such as `needs_review`, is not open); otherwise a new one through `gateway_service.create_payment(...)` with the charge's stored description and the describer's return address, linked with a history row `checkout_started` (the link is a column of the history row), the old one left unlinked (its webhook finds no record: a no-op); a charge the re-fetch or the webhook closed: Q7; commit. The return address: a registration → `/betaling/succes?registration=<payable id>`, a membership → `/betaling/succes?member=<household_id>` from `PayableDescription` — payment asks the describer, it does not branch. `payment/ui.py`: `GET /betalen/{token}` (no login; a limiter in `app/limiter.py` like the webhook's `mollie_webhook_limiter`): 404 for an unknown token, a record of another tenant (the tenant filter is automatic, `kernel/tenancy.py`) or a charge that is not an online charge above zero; 303 to the return address for a paid record; otherwise `start_checkout`; a `ValueError` or network error from the provider → 200 with the page (the record untouched, the session rolled back); a URL → 303. An optional `?terug=<path>`, checked by `app.ui.veilige_terug`, overrides the return address for the board (C5). `service.py`: `create_payment_record` keeps its name for payment's own callers, stays an export of `payment.api` that writes, and loses the gateway branch (or delegates to `open_charge`; the build's call); `checkout_url_for` returns `pay_path_for(record)` for an online charge not paid, None otherwise. `payment/api.py` exports `pay_path_for`. The named owner of every writer to `payment.payment_records`: payment, as today.

**Database:** `payment.payment_records.pay_token VARCHAR(36) NOT NULL UNIQUE`, default `gen_random_uuid()::text` on the server for the backfill and `uuid4` in the ORM; `payment.payment_records.description VARCHAR(200) NULL` (D7); one migration from `alembic revision`, additive. No copy action has this entity.

**Templates and mail:** `betalen.html`; `messages.pot` gets the four sentences of A3. Mail: unchanged unless Q1.

**Tests:** T1, T4–T7, T9.

### activities

**Screens:** none change. **Code:** the payment block of `router.py::create_registration` (lines 456–510 today) moves into `activities/service.py` as the step after `register`: compute the total, call `OpenCharge` for a paid method, publish `RegistrationConfirmed` with the record id as today, return the record and the pay path; the router keeps the HTTP mapping and sets `result["checkout_url"]` to the pay path, so `registration_form.py` and the two doors (`ui.py:282`, `admin_ui.py:1643`) redirect as they do; the board's door appends `?terug=/admin/inschrijvingen/<id>`. `api.py:354`'s `return_path` parameter goes with the block. *Mijn inschrijvingen* (R8): `my_registrations.py` adds the online block beside the transfer block — amount and `checkout_url_for` as `membership_card.py::_running_renewal` does — and `_my_registration.html` renders *Betaling hervatten* as `_renewal_running.html` does (`ui.btn_primary`, `href`); one block shape for both screens. **Database:** none. **Tests:** T2, T3, T8, the rewritten `test_nothing_is_committed_before_the_payment_step`.

### membership

**Screens:** none change; the card's *Betaling hervatten* keeps its label. **Code:** `signup_service.py::register_family` and `portal_service.py::renew_membership` call the port instead of `create_payment_record`, drop their `GatewayPayment` queries and 502 branches, and return `pay_path` as `checkout_url`; `membership_card.py::_running_renewal` builds `OnlineDue` with `checkout_url_for` as today, which now returns the pay path. No new read: the describer carries the household. `_renewal_running.html` loses its branch for a missing checkout URL (dead once every open online charge has a pay path). **Tests:** T2 (membership variant), T8.

### cms

**Screens:** the return page in its lapsed state (`bevestigd == false` and the provider's word is expired, failed or cancelled) shows *Opnieuw proberen* to the pay path; the pending state keeps polling as today. **Code:** `cms/ui.py::_payment_confirmed` also returns the pay path through `payment.api` when the charge is open and online. **Tests:** T8.

### mail

**Templates and mail:** the activity confirmation (`activity_confirmation_message`) gets one sentence when the charge is online and not paid: for a registration with a person, *Nog niet betaald? Je kan de betaling hervatten onder Mijn inschrijvingen.* beside the history URL it already carries (CR-22 R6); for a guest, the sentence of Q6. The family welcome mail (`family_welcome_message`) gets *… in Mijn gezin.* No pay link in a mail (Koen, 9 October 2026). The handlers read the record already; the words are A3's. **Tests:** T12.

### reporting

None: no view reads the new column; no column changes meaning (`gateway_payment_id` null for an online charge not yet started is a state the views already carry for a transfer charge).

## C3. Cross-cutting impact — the checklist of what gets forgotten

| Row | Answer |
|---|---|
| reporting views and saved reports | no: nothing read changes (C2) |
| existing tests, e2e golden flows, 390 px screenshots | yes: one test rewritten (T3), the webhook-URL test moves, the e2e chain holds through a 303, one new e2e for the failure page (T10), one new screenshot `betalen` at 390 px |
| fixed UI decisions and `AGENTS.md` | the hard redirect to the provider stays a hard redirect (`HX-Redirect`), now to the pay path which 303s on; no fixed decision changes |
| design-system documentation | no: kit macros only |
| code lists | no new code; `PaymentStatus` unchanged |
| events, ports and handlers — which gate sees every new call across domains, and what it says | the port call: the ports gate (contract plain, one handler at home, called from a service — the activities block moves to the service or rule 6 says "a router or a screen calls its own domain's service"); the handler: *no commit in a handler*; *no network in a handler* does not see a provider object's method, so T1 guards it; the events gate: three declared entries gone, the rest hard |
| mail templates | no (Q1: yes, one line) |
| migration: additive or contract | additive, with a backfill in the same migration |
| tenant settings | none new; the provider key per unit is read as today |
| env vars | none on UAT/PROD; the stub's switch is a route, not a variable |
| JSON routes and API callers | none: the pay route is a UI route; the JSON registration route is gone since CR-13 phase 4b (`activities/router.py:36–38`); the public and the board's door answer the pay path as `checkout_url` |
| external services | the provider is called from one place, idempotently; the webhook unchanged |
| copy actions | none: no entity with a copy action gains a field |
| visitors and tenants, walked | anonymous: registers, lands on the pay page or the provider; guest/account/member: the same, plus *Mijn inschrijvingen* shows the open booking as today; member with a shared address: the renewal's pay page per household, as the card is; board user without a person: registers on behalf, is sent to the pay path with `?terug=`; signed in at another tenant: a pay link of tenant A on tenant B's address is 404; operator: sets the provider key (W1); a tenant without members: registrations only, same path; the platform tenant: no activities, no path |
| order inside a transaction | the port writes inside the door's transaction and starts nothing that leaves; the provider is reached after the commit, in the pay route's own request — by construction (D2) |

## C4. Detailed decisions — one subsection each, with the reasons

### C4.1 A port (D1)

The architecture's rule (§3.2.1): an event for a fact, a port where the caller needs the answer, a read for a question. The door needs the charge's id (the confirmation event carries it) and where to send the browser — an answer. An event would make the door blind to both. The direct call with a licence ("this one may reach the network") keeps a provider call inside a transaction that holds a registration, its answers and a family — exactly the coupling CR-13 B4.1 names: a 10 s timeout holding rows, a failure that must roll back three domains. A port with a handler that reaches no network removes the coupling instead of excusing it, and it is the shape CR-21 needs for an order.

### C4.2 Payment's own route reaches the provider (D2)

Three doors reach the provider today, each with its own 502 branch, its own description and its own return address — three copies of one thing, which `AGENTS.md`'s duplication rule calls the bug. One route knows how a checkout starts, how it resumes and what to say when it fails; the doors only know the path. It runs in a request of its own, after the door's commit, so the registration is never at the provider's mercy. The return address is derived from the payable's describer, because the route runs later and stores no URL: a registration returns to the public success page with its id; a membership to the household's; the board's registration passes `?terug=` (C5). The description is not derived: the three doors word it differently today, and payment may not branch on a payable type to describe it (`describers.py`), so the port carries the door's words and the charge stores them (D7) — what the member reads on the bank statement does not change.

### C4.3 One open provider payment per charge (D3)

Mollie's payments lapse (expire, fail, get cancelled) and cannot be paid afterwards; an open one can. The stored status is our code, written by the webhook or a refresh — never the provider's word (C1) — and the webhook is left out on localhost and may lag, so the route re-fetches before it reuses: `refresh_payment_status`, then `handle_gateway_update`, inside the lock. Then: reuse while pending with a URL, replace when lapsed, never two open ones. The re-fetch may close the charge itself, as the webhook does: what the route does then is Q7, and until it is answered the build has no rule to follow for that case. The route locks the record (`FOR UPDATE`) for the few seconds it asks the provider, which serialises two visits at once; the lock is one row of one member. The old `GatewayPayment` row stays unlinked: its webhook finds no record and `handle_gateway_update` does nothing, as for any unknown id today; the workflow's mismatch task joins through `gateway_payment_id` and so never flags it. Rejected: a new provider payment per visit (duplicates, and a member who pays the older one after a newer was made — a webhook for an unlinked payment that *was* paid: money without a record).

### C4.4 A token, not the id (D4)

`PaymentRecord.id` is a uuid4 and as unguessable as any token. What it is not is private: it stands in board URLs (`/admin/betalingen/<id>`), in exports and in log lines. A link that starts a payment is a capability and should be a value that appears nowhere else, so that a leaked export is not a list of pay links. The cost is one column and one migration with a backfill, so that the charges open today are resumable through the route too.

### C4.5 The failure is the page (D5)

A silent provider is rare and short. A job that keeps asking and a page that polls would add a screen and a state to every online payment to cover it; the member would wait on a page that cannot say how long. The page with the button says what happened in one sentence and lets the member decide — now or later — and it reuses the return page's shape. The board sees an open booking either way.

### C4.6 The existing retry paths join (D6)

The return page's *Opnieuw proberen* goes to the home page today (C1, a finding), and *Betaling hervatten* opens the provider's old page, which has lapsed after Mollie's expiry window. Both become the pay path: one more consumer of the route and no code of their own. The cancelled route `/betaling/geannuleerd` is unreachable today and stays out (Non-goals).

### C4.7 A charge the webhook closed (Q7, parked)

`handle_gateway_update` writes the provider's lapse onto the record itself — `failed` or `cancelled` (`payment/service.py:166–175`) — and from then on `open_renewal_payment` (`membership/service.py:386–388`) and the sign-up's guard (`signup_service.py:101–103`) no longer see a running payment: the card loses *Betaling hervatten* and a renewal opens a second charge. The pay route meets such a charge through an old link, or through its own re-fetch (C4.3). Two answers. **Reopen:** set the charge back to `pending` with a history row (`checkout_reopened`), ask a fresh provider payment, and refuse only when a newer open charge for the same payable exists (then the page says so and points at the screen of F6). A member who presses *Opnieuw proberen* after a failed payment expects to pay, and a registration has no other road to an online payment: this is the recommendation. **Serve pending only:** a closed charge gets the message to contact the board — today's outcome with a sentence instead of a dead link; nothing in the ledger moves without the webhook or the treasurer. The choice is Koen's, when the change request is planned; the build has no rule for this case until then.

## C5. Privacy and security — the mechanics behind A7

The token is 122 bits of randomness (uuid4), unique, never shown in a board screen, and selects exactly one record of the request's tenant (the route filters on both; another tenant's token is 404, not 403, so it tells nothing). The route is rate-limited per address like the provider's webhook (`app.limiter`), so a scan cannot make the portal call the provider in a loop; and it calls the provider at most once per charge while a payment is open (D3). The page shows the amount and the description — the same words the provider shows — and no other personal data. `?terug=` goes through `app.ui.veilige_terug` (a local path, or the fallback): no open redirect. The provider receives what it receives today (amount, description, metadata with the payable, the return and webhook addresses). Log lines carry record ids, never names. Nothing new is stored about the member.

## C6. Tests — what the build must prove

**What the build must prove:**

| # | Test | Red when |
|---|---|---|
| T1 | `OpenCharge` writes the record and the history row, flushes, does not commit, and the provider is never called (the provider's `create_payment` monkeypatched to raise) — for online, transfer (with structured communication) and cash; T1 is the only guard of this: the *no network in a handler* gate sees libraries and functions, not a provider object's method | a network call or a commit in the handler |
| T2 | Each of the three doors, with the provider raising: 303/`HX-Redirect` to `/betalen/<token>`, the registration (or family and membership) committed, one pending charge without a provider payment, the confirmation event published with the record id | a 502, a rollback, a missing charge |
| T3 | (rewrites `test_nothing_is_committed_before_the_payment_step` and `test_families_betaalfout_rolt_alles_terug`) the port handler made to raise takes the registration with its answers, or the family, back; the count of commits before the port is 0 | an early commit |
| T4 | the pay route, provider reachable: creates one `GatewayPayment`, links it, 303 to its checkout URL; the description is the charge's stored one, the return address the describer's (C1) | a wrong word, a missing link |
| T5 | the pay route, provider raising: 200, the page with *Je inschrijving is bewaard* and the button to the same path; the record unchanged, no `GatewayPayment` | a 5xx, a changed record |
| T6 | the pay route twice for an open payment: one `GatewayPayment`, the same URL, the stub's status read before the reuse; after the stub's new helper lapses it: a second `GatewayPayment`, the first unlinked, the record's `gateway_payment_id` on the new one with a history row | a second payment while open, or no new one when lapsed |
| T7 | the pay route for a paid charge: 303 to the return address; an unknown token: 404; a token of another tenant on this host: 404; a transfer charge, a cash charge and a refund: 404 (F3); `?terug=//evil` ignored | — |
| T8 | `checkout_url_for` returns the pay path for an open online charge; the card's `OnlineDue` carries it; *Mijn inschrijvingen* renders *Betaling hervatten* to it for an unpaid online registration and nothing for a transfer; the return page in a lapsed state renders *Opnieuw proberen* to it | — |
| T9 | the migration gives every existing charge a distinct token (a seeded table before the upgrade, counted after) | a null or a duplicate |
| T10 | e2e with the stub: the chain as today (the wait for the stub's checkout URL holds through the 303); and the failure page: stub switched down → register online → the page with the button; switched up → the button → the stub's checkout → pay → webhook → *Betaling ontvangen* | — |
| T11 | the events gate: the three entries removed from the declared set, the gate red when one of the old calls is put back (the proof, additive, in the docstring) | — |
| T12 | the confirmation mail of an online registration made while signed in carries the *Mijn inschrijvingen* sentence; a guest's carries the Q6 sentence; the family welcome mail names *Mijn gezin*; a transfer or paid charge gets none of them | a mail with a pay link, or a sentence for the wrong case |

**Impact on the test landscape:** `test_registration_questions.py::test_nothing_is_committed_before_the_payment_step` and `test_kritische_flows_coverage.py::test_families_betaalfout_rolt_alles_terug` are rewritten (T3); `test_webhook_url_1279.py` asserts on `start_checkout`'s call to the provider instead of `create_payment_record`'s; the tests that pin the provider's URL or the call at the door follow the pay path — `test_registration_form_1284.py`, `test_membership_renewal.py`, `test_gezinsportaal_lopende_vernieuwing.py`, `test_household_add_and_email_1641.py`, `test_membership_payment_return.py`, `test_publieke_site.py`, `test_deelnemerslijst_na_inschrijving.py` (C1); the e2e chain is unchanged in its steps; one new screenshot set (`betalen`, 390 px). The webhook, the ledger, the transfer path and the admin screens are untouched.

## C7. The gate — what refuses a deviation from now on

The three existing gates of CR-13 hold the rule; this change adds none. *Events, not calls* (`test_events_not_calls`): a call from another domain into `payment.api.create_payment_record` is red once the three declared entries are gone — proven in T11 by putting one back. *No network in a handler* would **not** see `provider.create_payment(...)` inside `@handles(OpenCharge)`: it follows functions and library imports, and `httpx` sits in `providers/mollie.py`, not in `gateway_service` — so T1 is the guard, written down as the weaker guarantee it is. *A port is called from a service, never from a door* (rule 6): `kernel.ports` imported in `activities/router.py` is red — which is what moves the payment block into the service. Where a grep is not a gate: that the pay route stays the only place that creates a provider payment is held by `NETWORK_MODULES` at module level (`gateway_service`, `providers`) and by review; a second caller of `gateway_service.create_payment` inside payment would not be caught mechanically, and is written down here as the weaker guarantee it is.

## C8. Prototype findings — what was measured before the build

Nothing was run. The names of the tests that mention the concept were read (C1): one guards the old behaviour at the door (`test_nothing_is_committed_before_the_payment_step`) and is rewritten; the e2e chain's wait for the stub's checkout URL survives a 303 by construction, to be confirmed in the build. Two findings for the master CLI from the reading: `/betaling/geannuleerd` is unreachable (nothing links to it), and the return page's *Opnieuw proberen* goes to `/`. The build read (dev2, 9 October, #1829, laid against master `5c6802d2`) found four points that blocked the build as written — the stored provider status is our code, a lapse closes the charge itself, the entries leave in pull request (a), the route had no limit to online charges — and eleven more; all are in the document, one as Q7 for Koen when the change request is planned.

## C9. Screens before the build — the concepts the approver saw

Three concepts to render at 390 px and show Koen before the handover, kept in the CR-31 folder of the project material outside the repository: (1) the pay page in its failure state for a registration (heading, message, amount, two buttons); (2) the return page's lapsed state with *Opnieuw proberen*; (3) *Mijn inschrijvingen* with an unpaid online registration and its *Betaling hervatten*. Not yet shown; the status line says so.

## C10. Close-out at the release

Not written: the change is not built.

---

## Q&A log — asked once, answered here

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 9 Oct 2026 | Does the confirmation mail carry the pay link? (architecture CLI, through the master CLI) | Koen asked "wat is de betaalpagina?" and answered: "Ik zou laten verwijzen naar het scherm waar de betaling kan hernomen worden, waar het zichtbaar is in de site." — the mail names the screen, no link of its own (R6, F9, B9). That screen does not exist yet for a registration: R8 adds it. For a guest, who has no screen: Q6. |
| Q2 | 9 Oct 2026 | Which release? (architecture CLI, through the master CLI) | "En neen, niet voor v2.16. Dit plannen we ooit." — not planned (B9). |
| Q6 | 9 Oct 2026 | What does a guest's confirmation mail say about an unpaid online charge? (architecture CLI) | **Open — B8.** Parked by Koen the same day: "graag laten liggen, is voor later" — asked again only when the change request is planned. |
| Q7 | 9 Oct 2026 | What does the pay route do with a charge the webhook closed (failed, cancelled)? (dev2, build read 2) | **Open — B8**, parked with Q6 until the change request is planned. |
| Q8 | 9 Oct 2026 | Does the route re-fetch the provider before it reuses a payment? (dev2, build read 8) | Yes, inside the lock, through the existing refresh (C4.3): the stored status is written by the webhook, which is left out on localhost and may lag. |
| Q9 | 9 Oct 2026 | Why does the port carry the description instead of payment deriving it? (dev2, build read 6) | Three wordings at the doors today, and the describer rule forbids a branch on the payable type in payment (D7). |
| Q3 | 9 Oct 2026 | Why not the record's uuid id as the link, without a migration? (shaping) | It is an identifier that appears in board URLs, exports and logs; a capability should appear nowhere else (C4.4). |
| Q4 | 9 Oct 2026 | Why no job and waiting page for the silent provider? (master CLI, CR-13 C7-B) | A screen and a state for every payment to cover a rare, short failure; the page with the button says it in one sentence (C4.5). |
| Q5 | 9 Oct 2026 | Where does the pay route get the return address and the description from, since the port does not carry them? (shaping) | The return address from the describer; the description travels with the port and is stored on the charge (D7) — the build read found three wordings at the doors and the describer rule (C4.2, C5). |

## Non-goals — deliberately outside this change

- A waiting page or a job that keeps asking the provider (R7).
- A pay link of its own in a mail (Koen, 9 October 2026: the mail refers to the screen on the site).
- The mails that wait for their answer (the meeting mail, the newsletter sign-up's confirmation): a change request about mail's own queue, not yet shaped (CR-13 phase 4d).
- The unreachable `/betaling/geannuleerd` route: reported, not touched.
- The webshop's basket and order (CR-21): it uses this port and this route.
- A second payment provider; any change to the webhook's security model.

## Relationship to existing work — issues and change requests

- #1829 — tracking issue of this change request.
- #1251 — CR-13 phase 4: the three calls declared on the events gate until this change; the C7-B answer of 9 October 2026 that shaped it.
- CR-13 (`docs/change_request_13_oo_foundation.md`) B4.1, B4.9, Q46: "the payment record stays a door call — it reaches Mollie and the route needs the checkout URL"; this change ends that reason.
- #1743 — CR-21, the webshop: builds on the port and the route.
- #618 (resume a broken-off payment), #1589 and #1590 (the return page reads the ledger), #1274 (the stub provider and the e2e chain), CR-14 test 4 (one transaction at the door).
