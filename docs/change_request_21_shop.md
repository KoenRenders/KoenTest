# Change Request 21 — Webshop: products, stock and pricing

**Project:** Web Portal "Raak Millegem"
**Status:** being shaped since 6 October 2026 · Part A in progress · nothing is built; not on a release
**Tracking issue:** none yet — the one place where what is open stands; this document is the design, the issue is the status
**Applies to:** to be filled in once Part B is shaped
**Reading:** A <n> words · B <n> · C <n> — measured with the word count per part; A ≤ 1 500, B ≤ 2 500

---

# Part A — The business

## A1. Reason to act — the trigger

On 6 October 2026 Koen put forward the reason, in his words: *"we currently have no module to sell the T-shirts we have."* Raak has T-shirts in stock and no way to sell them through the portal.

The second half of the trigger is the platform: *"I also want a module we can later use in companies — T-shirts for Raak, selling other things, for other companies that will use the platform."* The shop is not a one-off for one batch of T-shirts; it is meant to serve any tenant of the platform, with its own products.

The platform half has no concrete case behind it yet (Koen, 6 October 2026): *"there is no concrete demand or process from companies that sell articles; it comes from the principle."* Raak's garments are the one real case; other tenants are the reason the shape must not be Raak-only.

## A2. As-is process — how it works today, and where it hurts

Raak has three kinds of garment in stock — T-shirts, sweaters and polos — each in several sizes. A sale today runs on conversation and e-mail; the portal plays no part in it.

```mermaid
flowchart LR
  subgraph Buyer
    b0((Needs a garment)) --> b1[Ask for a size]
    b2[Try the garment on] --> bq{Fits?}
    bq -- no --> b1
    b3[Transfer the amount]
  end
  subgraph Seller["Seller (a volunteer)"]
    s1[Bring sizes to try] --> s2[Hand over the garment] --> s3[Mail the price and account number]
  end
  subgraph Treasurer
    t1[Check the bank account] --> tq{Paid?}
    tq -- yes --> te((Sold and paid))
    tq -- no --> t2[Remind the buyer]
  end
  b1 -.-> s1
  s1 -.-> b2
  bq -- yes --> s2
  s3 -.-> b3
  s3 -. cc .-> t1
  t2 -.-> b3
  b3 -.-> t1
```

*What to see: three people and an e-mail carry the sale; nothing records what was sold or what is left on the shelf.*

| # | Step | Who | Tool | Pain — confirmed by Koen, 7 Oct 2026 |
|---|---|---|---|---|
| 1 | Ask for a garment in a size | Buyer | word of mouth, message | the buyer cannot see what is available, in which size, at what price |
| 2 | Bring sizes to try on | Seller | the stock, at home or in storage | depends on one person being available |
| 3 | Hand over the garment | Seller | — | the stock count is in nobody's system; what is left is known by looking |
| 4 | Mail the price and Raak's account number, treasurer in copy | Seller | e-mail | written by hand for every sale; the price is whatever the mail says |
| 5 | Transfer the amount | Buyer | own bank | free-text communication; the transfer has to be matched by eye |
| 6 | Check the bank account, remind if unpaid | Treasurer | bank, an Excel list | the open sales are kept by hand in an Excel list, apart from the bank and the mails |

Not measured: how many garments are sold per year, how many are in stock, and what a garment costs. Deliberately left out (Koen, 7 Oct 2026: "niet zo belangrijk, gaan we nu niet uitkristalliseren"); the case for the shop rests on the principle of A1, not on volume.

## A3. To-be process — how it should work afterwards

> [!NOTE]
> *How the work should go afterwards: the same drawing and table as A2, the*
> *same lanes in the same order, so the difference is what the eye finds.*
> *Still no components: "the portal renders the poster", not "WeasyPrint*
> *renders the poster". A step that disappears, moves lane or turns into a*
> *choice is the change — name it under the drawing in one line each.*
>
> *The words the user will read are decided here, not in Part C: the name*
> *of a button, a page title, a tile label, a menu item — one short list,*
> *"what it says on the screen", in the user's language and never the*
> *domain's pet word.*

```mermaid
flowchart LR
  subgraph Buyer
    b0((Needs a garment)) --> b1[Fill the basket] --> b2[Order and choose how to pay]
    b3[Try the garment on] --> bq{Fits?}
    b4[Transfer the amount]
  end
  subgraph Verkoop
    s1[Bring sizes to try]
    s2[Change the order]
    s3[Register the delivery]
    s4[Remind or cancel] --> se2((Cancelled))
  end
  subgraph Boekhouding
    t1[Check the account] --> tq{Money in?}
  end
  subgraph Portal
    p1[Reserve the articles] --> pq{How paid?}
    pq -- transfer --> p3[Open a task for Boekhouding]
    p2[Record the payment]
    p4[Lower the stock] --> pe((Delivered))
  end
  b2 -.-> p1
  pq -- online, paid --> p2
  pq -- online, failed or hanging --> s4
  p3 -.-> t1
  b4 -.-> t1
  tq -- yes --> p2
  tq -- not yet paid --> s4
  s4 -. reminder .-> b4
  p1 -.-> s1
  s1 -.-> b3
  bq -- no --> s2 --> p1
  bq -- yes --> s3 --> p4
```

*What to see: the portal now holds what the e-mail and the Excel list held — the order, the reservation, the price and the open payment — and the treasurer's chase becomes a task that reaches Verkoop only when Boekhouding says the money is not there.*

What changes against A2, one line each:

- **Asking for a size** becomes filling a basket in the Webshop: the buyer sees what exists, in which size, at what price (pain 1).
- **The mail with price and account number** disappears: the portal shows the amount and the structured communication, as for a registration (pain 4, pain 5).
- **The stock** is in the portal: reserved at the order, lowered at delivery (pain 3).
- **The Excel list** disappears: an unpaid transfer is a task on the workbench, first Boekhouding, then Verkoop (pain 6, R18).
- **Trying on and exchanging** stay by agreement, outside the portal; a change of size changes the order and the money follows it (R15, R16).
- **Bringing sizes** still depends on a volunteer (pain 2): the portal shows what is reserved, it does not deliver.

| # | Step | Who | Tool | What changed |
|---|---|---|---|---|
| 1 | Fill the basket, order, choose online or transfer | Buyer | Webshop | was: ask by word of mouth |
| 2 | Reserve the articles | Portal | — | new: what is reserved cannot be sold again (R13) |
| 3 | Pay online, or transfer with the structured communication | Buyer | Mollie, own bank | was: free-text transfer after a mail |
| 4 | Check the account and book the transfer | Boekhouding | workbench task, bank | was: the Excel list; the task is due in 14 days and turns red after (R18, Q38) |
| 5 | Remind the buyer or cancel the order | Verkoop | workbench task | new: only when Boekhouding says "not yet paid", or an online payment failed (R17, R18) |
| 6 | Bring sizes, try on, change the order | Verkoop, Buyer | Verkoop screen | the order and the money follow the change (R15, R16) |
| 7 | Register the delivery, per line | Verkoop | Verkoop screen | new: the stock goes down here (R21) |
| 8 | Book a receipt from the supplier, correct the stock | Voorraadbeheer | Voorraadbeheer screen | new (R36, R37) |

Step 8 has no place in the drawing: it is not part of a sale.

**What it says on the screen** (Koen, 6 October 2026):

| Where | Word |
|---|---|
| The public page | Webshop |
| Role and screen: the product list | Productbeheer |
| Role and screen: prices | Prijsbeheer |
| Role and screen: orders, delivery, fitting, exchanges | Verkoop |
| Role and screen: stock | Voorraadbeheer |
| Delivery status of an order, for the buyer | **Klaar om af te halen** (nothing delivered yet) · **Deels afgeleverd** · **Afgeleverd** · **Geannuleerd** |
| Payment status of an order | Te betalen · Betaald · Terugbetaald — the payment domain's words, as on registrations |

## A4. Benefits — what the change earns

> [!NOTE]
> *The business side of the decision: what this change earns, in the*
> *measures the association counts in — hours of volunteer work saved per*
> *activity or per year, mistakes avoided, money collected sooner or not*
> *lost, members who would otherwise drop out, a process that becomes*
> *possible at all. One line per benefit, with the figure where it can be*
> *estimated and the reason where it cannot; a benefit that only the*
> *solution can name does not belong here. Set against the cost of B5, this*
> *is what says whether the change is worth doing, and when.*

## A5. Supplied material — and what it taught us

> [!NOTE]
> *What the business handed over to start from — brand guides, examples,*
> *photos, spreadsheets, briefs — with where it lives (described in words or*
> *by file name; never a local path, never in the repository when it holds*
> *personal data or brand assets). What was learnt from it goes here too, as*
> *measurements: "four example posters; none has a bleed". Do not forget the*
> *reporting need: must something be counted, listed, exported or printed*
> *afterwards, for whom, in which form? If so, it is a requirement in A6; if*
> *not, A6 says so in one row.*

## A6. Business requirements — what the board asks, with MoSCoW

> [!NOTE]
> *One table. Each requirement is a sentence a board member would say, with a*
> *MoSCoW class. Numbered, so Part B, Part C and the acceptance criteria can*
> *point at them.*

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | The webshop shows clearly what an article is. | Must | Koen, 6 Oct 2026 | description, pictures and documents, R3 |
| R2 | Products are master data: the product portfolio is managed in its own place, apart from any activity. | Must | Koen, 6 Oct 2026 | "very simple at this moment" |
| R3 | A product has a description, one or a few pictures — one, two, three, four — and one or more documents a buyer looking at the article can open, for example the size chart that came with the delivery of the clothing, so the buyer can choose a size from it. | Must | Koen, 6 Oct 2026 | documents added later the same day, first as R20 |
| R4 | Only the role Masterdata may manage the products (product master data); others may not. | Must | Koen, 6–7 Oct 2026 | the role of CR-24 (Q2 there); first written as "a role for product master data" |
| R5 | Any tenant of the platform can use the shop with its own products, not only Raak. | Must | Koen, 6 Oct 2026 (A1) | no company asks for it yet; a principle |
| R6 | One product can have different prices over time; at any moment it is clear what the price of an article is. | Must | Koen, 6 Oct 2026 | "maybe overdone now, but in time price setting will matter" |
| R7 | Stock is kept per location: which articles are in stock, and how many, at which place. | Must | Koen, 6 Oct 2026 | today one location: a volunteer's home serves as the warehouse of Raak Millegem |
| R8 | The value of the stock can be known. | Won't *(now)* | Koen, 6 Oct 2026 | stock valuation is for later; what is built now must not stand in its way |
| R9 | Warehouse management: where inside a location an article lies — which rack, which shelf — and barcodes on articles, with scanning. | Won't | Koen, 6 Oct 2026 | barcodes added as R10 the same day |
| R10 | *Merged into R9.* | — | Koen, 6 Oct 2026 | the number stays empty, so later references do not shift |
| R11 | Everyone can buy, members and non-members; a member pays the member price where the article has one — the same principle as registering for an activity. | Must | Koen, 6 Oct 2026 | |
| R12 | The portal arranges how the buyer gets the article — pick-up, bringing it, trying it on first. | Won't | Koen, 6 Oct 2026 | all three stay possible, by agreement between buyer and seller, outside the portal |
| R13 | An order reserves its articles the moment it is placed: what is reserved cannot be sold again. The stock itself only goes down when the article has left the warehouse — when it is delivered. A reservation is cancelled when the buyer withdraws, exchanges for another article, or the payment fails; the article is then free to sell again. | Must | Koen, 6 Oct 2026 | replaces "stock is taken at the order" of the same day (Q16) |
| R14 | The buyer pays online or by bank transfer, as with a registration for an activity. | Must | Koen, 6 Oct 2026 | |
| R15 | An order can be changed after trying on — a bigger size for a smaller one, a T-shirt instead of a sweater — and the stock follows the change. | Must | Koen, 6 Oct 2026 | same principle as changing a registration |
| R16 | The money follows a changed order as it does for a registration: an extra payment when it was paid and the new amount is higher, an updated amount when it was not paid yet, a refund when it was paid and the new amount is lower. | Must | Koen, 6 Oct 2026 | |
| R17 | An order whose online payment fails, or stays hanging (the buyer closed the browser), becomes a task on the workbench for Sales, because something has to happen with it. | Must | Koen, 6 Oct 2026 | replaces "cancelled by itself" of the same day (Q15); the reservation stays until someone acts (Q17) |
| R18 | An order paid by bank transfer becomes a workbench task at once, due within 14 days, and runs as a workflow of two steps: first **Boekhouding** ("is the money on the account?" — it books the transfer, and the task closes by itself), then **Verkoop** (remind the buyer or cancel the order) — the task moves to Verkoop only when Boekhouding answers "nog niet betaald", not by itself. Verkoop's task shows how recent the information is: when Boekhouding last checked the account. A task past its due date only turns red on the workbench; no mail goes out (Q38). | Must | Koen, 6 and 7 Oct 2026 | "de boekhouding moet wel op tijd de betaling afboeken, anders heeft sales geen juiste informatie"; Q15, Q36. Built on the steps of `WorkflowDefinition` (a role per step); a due date on a task is new to the workbench. Importing bank statements is a change request of its own, reserved and not planned (Q37) |
| R19 | The roles that carry the process: Masterdata (keeps the product list — product master data), Prijsbeheer (sets the price of an article), Verkoop (the webshop: orders, delivery, fitting moments, exchanges), Boekhouding (follows up payments — the existing role `FINANCE`) and Voorraadbeheer (enters stock and changes it by hand). One person may hold several. | Must | Koen, 6–7 Oct 2026 (Q11, Q33) | Productbeheer became part of Masterdata (CR-24); screen names follow CR-24 |
| R20 | *Merged into R3.* | — | Koen, 6 Oct 2026 | the number stays empty, so later references do not shift |
| R21 | Sales registers per order line that it is delivered; picked up or brought makes no difference. That is the moment the stock goes down. | Must | Koen, 6–7 Oct 2026 (Q30) | the goods issue (GI) of an ERP: in one transaction the line is delivered, the stock goes down and the reservation closes; a line is delivered whole — a partial delivery is a change that splits the line (R15) (Q30) |
| R22 | An unpaid order ends in one of three ways: the buyer still pays — for example through a new payment link — and the task closes by itself; the buyer cancels it (R23); or Sales cancels it from the task. | Must | Koen, 6 Oct 2026 | |
| R23 | A signed-in buyer (member or account) can cancel his own order in the webshop, on the same page Sales uses in the back office. | Must | Koen, 6 Oct 2026 | first Won't, taken in the same day: "if we use the same screen in public and in the back office, we may get it for free" (Q19); until delivery (Q20); the buyer gets back to his order through a link in the confirmation mail (Q21); a guest cannot — without an account nothing is changed afterwards (CR-22 Q10): he asks Sales |
| R24 | The buyer collects articles in a shopping basket and orders and pays two, three or more articles in one go. | Must | Koen, 6 Oct 2026 | the basket reserves nothing and needs no account; it lives in the buyer's browser (Q22, Q23) |
| R25 | The buyer may cancel until the order is delivered. A return after delivery is out of scope: it is handled by hand — Sales removes the order and books the refund. | Must | Koen, 6–7 Oct 2026 | "retour is out-of-scope, gaan we doen door bestelling te verwijderen en terugbetaling te boeken" — "manueel" (Q40) |
| R26 | *Moved to CR-22* (signing in to buy or register: member, account or guest). | — | Koen, 7 Oct 2026 | the number stays empty, so later references do not shift |
| R27 | *Moved to CR-22* (signing in to buy or register: member, account or guest). | — | Koen, 7 Oct 2026 | the number stays empty, so later references do not shift |
| R32 | *Moved to CR-22* (signing in to buy or register: member, account or guest). | — | Koen, 7 Oct 2026 | the number stays empty, so later references do not shift |
| R33 | The buyer signs in as a member or with an account, or orders as a guest, as CR-22 defines for activity registrations and the webshop alike. | Must | Koen, 7 Oct 2026 | CR-22 is built first, on the activities; the webshop uses the same mechanism |
| R34 | An order shows its statuses side by side, each from its own source: its payment status from payments, its delivery status from its lines (reserved, partly delivered, delivered, cancelled). Later, for companies, an invoicing status from invoices joins them, in parallel with payments. | Must | Koen, 7 Oct 2026 (Q29) | invoices: not now; the shape must take them |
| R35 | Invoices. | Won't *(now)* | Koen, 7 Oct 2026 (Q31) | later, in the existing payment domain, called finance; the webshop will ask it through its facade to invoice delivered lines and will only know the invoicing status |
| R36 | Voorraadbeheer can correct the stock of an article by hand, up or down, at a location — for example when a returned garment comes back after delivery (R25). | Must | Koen, 7 Oct 2026 (Q41) | a stock movement of its own kind, next to the goods issue of R21 |
| R37 | Voorraadbeheer books a delivery from the supplier as a receipt at a location — a stock movement apart from corrections, so it stays visible what came in and what was corrected. | Must | Koen, 7 Oct 2026 (Q42) | the goods receipt (GR) of an ERP, next to the goods issue of R21; keeps the way open for stock valuation (R8) |
| R28 | *Moved to CR-22* (signing in to buy or register: member, account or guest). | — | Koen, 7 Oct 2026 | the number stays empty, so later references do not shift |
| R29 | *Moved to CR-22* (signing in to buy or register: member, account or guest). | — | Koen, 7 Oct 2026 | the number stays empty, so later references do not shift |
| R30 | *Moved to CR-22* (signing in to buy or register: member, account or guest). | — | Koen, 7 Oct 2026 | the number stays empty, so later references do not shift |
| R31 | An account says whether it is a company or a natural person, and holds an address to deliver to. | Won't *(for now)* | Koen, 6 Oct 2026 | today an order is only ever for a person |

MoSCoW: **Must** (without it the change is worthless), **Should** (important,
but the change ships without it), **Could** (nice, if cheap), **Won't** (asked
and deliberately not done — recorded so it is not asked again).

## A7. Non-functional requirements — security, privacy, house style, tenants

> [!NOTE]
> *The requirements every change request is tested against, each answered*
> *explicitly at business level, "not applicable" included. How they are met*
> *belongs in Part C (C5):*

| Concern | This change |
|---|---|
| **Security** — who may do what; new inputs from outside; secrets | … |
| **Privacy** — personal data: what, where, who sees it, what leaves the system | … |
| **House style / UI norm** — `docs/design-system.md`; brand rules | … |
| **Multi-tenant** — what differs per unit, what is platform-wide | … |

## A8. Acceptance criteria — what the business signs off on HDEV

> [!NOTE]
> *Criteria the business signs off on, each testable by a person on HDEV*
> *without reading code, each pointing at a requirement and at the steps of*
> *the walkthrough (B2) that show it. These are the business's unit tests;*
> *the developer's tests live in Part C.*

| # | Criterion | Requirement | Walkthrough steps |
|---|---|---|---|
| AC1 | … | R1 | … |

---

# Part B — The solution, for whoever approves it

> [!NOTE]
> *Part B is read by the people who say "yes, build this": Koen, the*
> *analyst, the architect. It answers four questions — what is the solution,*
> *does it fit our process and our requirements, how does it hang together*
> *across the modules and what does it touch, what does it cost and in which*
> *steps does it arrive — and it ends with what is still theirs to decide.*
> *Reasoning in depth, mechanics and per-module detail go to Part C; Part B*
> *names the decision and the rejected alternative ("Rejected alternative: …"), in five lines at most.*

## B1. Solution outline — the solution and the decisions that shape it

> [!NOTE]
> *The solution in one paragraph; then the decisions that shape it, one*
> *bullet each of at most five lines: the decision, the rejected alternative that
> *lost, why (Europe First named where a tool or service is chosen). The*
> *full reasoning behind each decision is C4, which points back here. Then*
> *the **derived requirements** (F1, F2, …) in one table, traced to A6: the*
> *finer-grained requirements the solution answers — design work by the*
> *analyst, which is why they are not in Part A.*

## B2. Fit with the process and the requirements — for the business

> [!NOTE]
> *Three things. First, the **application usage drawing**: the to-be process*
> *of A3 once more — same lanes, same activities — with, in every activity*
> *box, a second line naming the screen or module that serves it, the box*
> *coloured per module (`classDef`, one legend line). Every step has a home*
> *or is marked "outside the portal"; a module no step uses is not part of*
> *this change. Two audiences (those who set up, those who use) means two*
> *drawings. Second, the **traceability matrix** — the one place where a*
> *requirement's thread is followed from left to right, so it is kept*
> *nowhere else: one row per requirement of A6 — R · how the solution meets*
> *it, in the words of the role that will see it · the derived requirements*
> *(F, B1) · the module that builds it (C2) · the test that proves it (C6) ·*
> *the acceptance criterion the business checks (A8). An empty cell is a*
> *finding: a requirement without a test, a test without a requirement. A*
> *Won't gets a row that says so. Third, the **walkthrough** — how the*
> *business tests this on HDEV: one numbered script per role of A3, in the*
> *order of the to-be process, happy path first and then the turns where it*
> *must refuse or fall back; each step names what to do and what to see —*
> *nothing else, it is a script. A8's last column names the steps that show*
> *each criterion; every criterion has at least one step. The closing*
> *comment of each issue points at the walkthrough instead of rewriting it.*

## B3. The whole across the modules — for the architect

> [!NOTE]
> *The **application structure drawing**: one subgraph per module touched,*
> *inside it a box per layer (screen · view-model · service · entity ·*
> *facade · migration · template) — a separate box for what is **new** and*
> *for what is **changed** in that layer, and one grey box for what is only*
> *used. Here the colour is the kind of change, not the module: green new,*
> *orange changed, grey unchanged. One legend line. Arrows between modules*
> *only through a facade (`api.py`), as the import gate enforces; external*
> *systems and data stores as their own boxes. Then the **data model at a*
> *glance**: a Mermaid `erDiagram` of the entities involved with their key*
> *columns and relationships, cardinality on the edges, soft references*
> *across schemas drawn as relationships too, and what is new or changed*
> *marked in the label. Under it, in at most two hundred words: who calls*
> *whom and through which facade, the direction of every new dependency,*
> *the transaction boundary, and the **impact on the existing*
> *architecture** — which existing modules, tables, screens and contracts*
> *are touched, and how the layer rules (`docs/code-style.md`, the import*
> *gate) hold. This is where a reviewer checks that the change does not*
> *bend the architecture; the per-module detail is C2.*

## B3a. Standards the model follows — and where it deviates, on purpose

*Seeded on 7 October 2026, before B3 is written: the names here are the ones B3 and Part C will use.*

Standards checked: UBL 2.1 (`Catalogue`, `Order`, `DespatchAdvice`, `InventoryReport`) and EN 16931 / PEPPOL BIS Billing 3.0 for the later invoice; UN/CEFACT code lists UNCL 5387 (price type) and UN/ECE Rec. 20 (unit of measure); ISO 4217 for currency; GS1 GTIN and GLN for article and location identifiers; ISO 20022 and the Belgian structured communication for payment references; schema.org `Product` / `Offer` for the public page. For a reservation no standard applies: it is an ERP concept (a sales order's committed quantity), modelled after common practice.

| Concept in this change | Standard and element | Ours (table · column, name) | Follows / deviates — why |
|---|---|---|---|
| Product | UBL `cac:Item` (`cbc:Name`, `cbc:Description`); schema.org `Product` | `product` · `name`, `description` | follows |
| Variant (size) | UBL `cac:Item/cac:AdditionalItemProperty` (`cbc:Name` "Maat", `cbc:Value` "M"); schema.org `ProductGroup` + `variesBy` | `product_variant` · `product_id`, and its properties as rows (name, value) | follows: a property is repeatable, so a second axis (colour) is a row, not a column |
| Article identification | UBL `cac:SellersItemIdentification`; GS1 GTIN in `cac:StandardItemIdentification` | `product_variant` · `sku`; GTIN: not now | follows for the seller's code; GTIN left out "not now" — a separate identification row can take it, never a second column |
| Pictures and documents | UBL `cac:AdditionalDocumentReference` (`cbc:DocumentTypeCode`, `cac:Attachment`); schema.org `image` | `product_attachment` · `product_id`, `kind` (picture, document), `media_asset_id`, `sort_order`, `title` | follows: repeatable, typed, pointing at the media library (CR-15) |
| Price | UBL `cac:Price` (`cbc:PriceAmount` with `currencyID`, `cbc:BaseQuantity`, `cac:ValidityPeriod`) | `pricing.price` · `product_id`, `variant_id` (null = the product's), `amount`, `currency` (EUR), `valid_from`, `valid_to` | follows: validity as a period, a variant's price overrides the product's (Q4) |
| Member price | UBL `cbc:PriceType` / `cbc:PriceTypeCode` (UNCL 5387) | `pricing.price` · `price_type` code list: `REGULAR`, `MEMBER` | follows: a second price is a row with a type, not a column `member_price` |
| Currency | ISO 4217 | `currency` CHAR(3) | follows |
| Order and its lines | UBL `Order` · `cac:OrderLine/cac:LineItem` (`cbc:Quantity` with `unitCode`, `cac:Price`, `cac:Item`) | `sales_order`, `sales_order_line` · `variant_id`, `quantity`, `unit_code` ("C62"), `unit_price` | follows; the line keeps its price at sale, as EN 16931 needs it on the invoice (BT-146) |
| Buyer | UBL `cac:BuyerCustomerParty` (a `cac:Person`; later a party with a contact person) | `sales_order.person_id` (the person who ordered, CR-22 account or member) or the guest's name, e-mail, mobile on the order | follows for a person; deviates for a guest: contact fields on the order without a party — "not now", as for registrations; the household is no buyer but a point of view (Q34) |
| Reservation | — (ERP: committed quantity of a sales order) | `stock_reservation` · `order_line_id`, `variant_id`, `location_id`, `quantity`, `status` (open, delivered, cancelled) | no standard; kept apart from movements (Q16) |
| Delivery | UBL `DespatchAdvice` · `cac:DespatchLine` (`cbc:DeliveredQuantity`) | `sales_order_line.delivered_at` + a stock movement | follows the meaning per line (Q25); no despatch document "not now" |
| Stock movement | UBL `InventoryReport` (a count); GS1 EPCIS (events) | `stock_movement` · `variant_id`, `location_id`, `quantity` (signed), `reason`, `occurred_at`, `order_line_id` | follows EPCIS's event shape: one row per what happened; a count is a correction row |
| Location | UBL `cac:Location`; GS1 GLN | `stock_location` · `name`; GLN: not now | follows; no bins (R9) |
| Payment reference | Belgian structured communication; ISO 20022 `RmtInf/Strd` | the existing `payment_records.structured_communication` | follows, as payments already do |
| Invoice (later) | EN 16931 / PEPPOL BIS 3.0 | — | not now; the order line carries what an invoice line needs (quantity, unit, unit price, item) |

## B4. Rules this change needs an exception from — decided once, here

> [!NOTE]
> *Every existing rule, gate or fixed decision the design breaks or bends:*
> *the rule by name and place (`CLAUDE.md`, `docs/code-style.md`,*
> *`docs/architecture.md` §…, a gate in `backend/tests/`), what the design*
> *does instead, the mechanism (a named baseline entry, a widened gate, a*
> *replaced fixed UI decision), and whether the exception is temporary (with*
> *what ends it) or the new rule. One table; "none" is an answer, with the*
> *gates that were checked to say so. The approver decides each row at the*
> *handover — once. CR-14 needed an exception from the cross-domain call rule*
> *and nobody had written it down: the gate found it, the master CLI asked*
> *six times, and the third case became a change request of its own.*

| Rule (where) | What the design does instead | Mechanism | Temporary until … / the new rule | Decided |
|---|---|---|---|---|
| … | … | … | … | <who>, <date> |

## B5. Cost — investment and running cost, and what operations must know

> [!NOTE]
> *Three parts, each with a figure or "none". **Investment:** one table,*
> *module × phase, with the effort to build in CLI-days or person-days (S /*
> *M / L until the team has a track record), a total per module and per*
> *phase; then analysis, review, validation on HDEV and the release steps;*
> *then one-off purchases (a licence, a product, a device). **Running*
> *cost:** what it costs per month or per year once live — usage rights and*
> *paid services (per use and per month, measured where a prototype exists),*
> *storage and backups, hosting, and the maintenance it adds (a job to watch,*
> *a certificate to renew, a dependency to keep current). **Operations:***
> *settings, env vars, limits, kill switch, backups — what the person running*
> *the stack must know. Set beside the benefits of A4: the two together are*
> *the input for the release decision.*

## B6. Phasing — shippable phases, and what changes on the failure paths

> [!NOTE]
> *Shippable phases, each with what it delivers and its dependencies, one*
> *row per phase: issue · migration · env vars · data · failure paths that*
> *change · manual validation. The "Na de merge" block per phase names what*
> *CI cannot see. The column **failure paths that change** exists because a*
> *change that reorganises behaviour — where a rule lives, who commits, what*
> *a handler does — rarely changes what the system does on the happy path,*
> *and almost always changes what it does when something fails: what rolls*
> *back, what is refused, what is left half done. Name those per phase, so*
> *"no functional change" is a claim about the happy path with the failure*
> *paths listed beside it. "None" is an answer. Dependencies on other change*
> *requests are named per phase, so the approver can order them.*

## B7. Rule and gatekeeper — what this fixes for all future work

> [!NOTE]
> *An architectural change request fixes a way of doing things, not just one*
> *instance of it. Here, for the approver: **the rule** in one sentence a*
> *reviewer can apply, in the form the decision takes from now on, and where*
> *it ends up (`CLAUDE.md`, `docs/code-style.md`, the architecture document,*
> *the design system); **the reach and the baseline** — where it applies and*
> *how many places violate it today, measured on the branch, and to what*
> *this change brings that number; and in one line whether the gate is a*
> *ratchet or hard. The gate itself — what it looks at, its message, the*
> *violation it was proven with — is C7. "No gate" is an answer, with the*
> *reason and what catches it instead, written down as the weaker guarantee*
> *it is.*

## B8. Open decisions — what the approver still decides

> [!NOTE]
> *The questions that are still open, each with the author's recommendation*
> *and the difference the answer makes; numbered Q-entries, the same numbers*
> *as the Q&A log, so an answer moves the row from here to the log. This is*
> *the last thing the approver reads before saying yes; an empty section*
> *means the change request is ready to assign.*

| # | Question | Recommendation | What the answer changes |
|---|---|---|---|
| Q39 | Reminding the buyer of an unpaid transfer: a button on Verkoop's task that mails the payment link, or a mail that goes out by itself after some days? **Parked by Koen on 7 October 2026.** | A button on the task: Verkoop already decides per order (Q36), and a mail by itself would also go to a buyer whose transfer Boekhouding has not booked yet. | A button is one action on the task; a mail by itself needs a schedule, a text per tenant and a rule for when it stops. Until decided, Verkoop reminds the buyer outside the portal. |

## B9. Decisions log — dated answers

> [!NOTE]
> *Dated decisions of the business and of the architecture, one row each,*
> *with who decided. A decision taken during the build is added here with*
> *the date and marked "built as"; the text it contradicts gets an as-built*
> *note pointing here (C10).*

| Date | Decision | By |
|---|---|---|
| 6 Oct 2026 | A size is a variant of a product; stock is kept per variant (Q1). | Koen |
| 6 Oct 2026 | The price hangs at the product; a variant may override it. One price is entered, only the exception is set per variant; prices over time (R6) work the same for both (Q4). | Koen |
| 6 Oct 2026 | Price gets its own domain, `pricing`, small from the start: a price per article with the date from which it applies; no discounts or price lists per customer group yet (Q2). | Koen |
| 6 Oct 2026 | Everyone may buy; members pay the member price where there is one, by the same rule as an activity registration (Q5). This refines Q2: `pricing` holds two kinds of price from the start, the regular price and the member price, both with their date; still no other customer groups. | Koen |
| 6 Oct 2026 | Stock is taken at the order, not at the payment; a cancelled order gives it back — "for now" (Q7). | Koen |
| 6 Oct 2026 | Five roles: product master, pricing, sales, stock management — four new — and the existing finance role for following up payments (Q11). | Koen |
| 6 Oct 2026 | ADMIN may view everything of the webshop, only the four roles may change it — the pattern of the financial separation (#83). OPERATOR may do everything, as today (Q12). | Koen |
| 6 Oct 2026 | The task for an unpaid order goes to Sales; Finance confirms a payment as today (Q13). | Koen |
| 6 Oct 2026 | Screen names: Productbeheer, Prijsbeheer, Verkoop, Voorraadbeheer; the public page is the "Webshop" (Q14). | Koen |
| 6 Oct 2026 | Stock is kept as movements — receipt, order, cancellation, exchange, correction, each with date and reason — and the stock of a variant at a location is their sum (Q3). | Koen |
| 6 Oct 2026 | An order reserves stock; the stock goes down only at delivery, registered by Sales without distinguishing pick-up from bringing. A reservation can be cancelled (buyer withdraws, exchange, failed payment). **Replaces** the decision "stock is taken at the order" (Q7) of the same day (Q16). | Koen |
| 6 Oct 2026 | An unpaid order becomes a task for Sales at once, due within 14 days, closing by itself when the payment comes in — for a bank transfer, and also for a failed or hanging online payment, because something has to happen with it (Q15). | Koen |
| 6 Oct 2026 | The reservation of an unpaid order stays until someone acts — nothing expires it by itself, also not after a failed or hanging online payment (Q17). | Koen |
| 6 Oct 2026 | The buyer may cancel his own order in the webshop; the order page is one page, public and in the back office, as the registration is since CR-14. **Replaces** the part of Q18 that left it out (Q19). | Koen |
| 6 Oct 2026 | The buyer may cancel until delivery; after that it is a return through Sales; a paid order is refunded through the recalculation of R16 (Q20). | Koen |
| 6 Oct 2026 | The buyer reaches his order through a link in the confirmation mail, valid until delivery, without an account (Q21). | Koen |
| 6 Oct 2026 | Stock is reserved when the buyer presses "Bestellen", not when an article goes into the basket (Q22). | Koen |
| 6 Oct 2026 | The basket lives in the buyer's browser, without an account (Q23). | Koen |
| 6 Oct 2026 | Cancelling applies to the whole order; taking one line out is a change (R15) (Q24). | Koen |
| 6 Oct 2026 | Sales registers "delivered" per order line, not per order (Q25). | Koen |
| 6 Oct 2026 | The link in the confirmation mail is a sign-in link that brings the buyer to his order: link and account are one way in (Q26). | Koen |
| 6 Oct 2026 | An account with an e-mail address already on a person creates no second person; a sign-in link goes to that address (Q27). | Koen |
| 7 Oct 2026 | Signing in is lifted out into its own change request, CR-22, built first on the activity registrations so registration and webshop share one mechanism: a household member (an e-mail address may be shared inside one household), an account (e-mail address unique outside a household, otherwise "this account already exists"), or a guest (name, e-mail address and mobile on the order, regular price). R26–R30 and R32 move there (Q28). | Koen |
| 7 Oct 2026 | Two statuses side by side, none stored on the order: payment from the payment domain (`payable_type` ORDER), delivery derived from the lines; only a cancellation is stored, with date and who. Invoices for companies come later, in parallel with payments, as a third status from their own domain (Q29). | Koen |
| 7 Oct 2026 | "Afgeleverd" is the goods issue of an ERP (SAP Post Goods Issue): line delivered, stock movement out, reservation closed, in one transaction; no separate delivery document, no picking. A line is delivered whole; to deliver part of it, Sales splits the line by a change (Q30). | Koen |
| 7 Oct 2026 | Invoices, later and out of scope now, belong to the payment domain (called finance): receivables, payments and open items in one place, as `docs/architecture.md` table 5 foresees; sales asks finance to invoice delivered lines; no own invoice domain, no rename (Q31). | Koen |
| 7 Oct 2026 | The buyer reads "Klaar om af te halen" while nothing of the order is delivered; then Deels afgeleverd, Afgeleverd, or Geannuleerd (Q32). | Koen |
| 7 Oct 2026 | **Party model for CR-21:** the buyer is the **person** who orders, exactly as a registration is made by a person (`registrations.person_id`); a guest has no person, only the contact fields on the order. The household is a point of view, not the buyer: the member price comes through the person's household membership, and a household sees the orders of all its persons (as CR-22 R8 for registrations). An organisation as buyer — a person ordering on its behalf — comes later (R31). **Not final:** a person changes company, a household splits (divorce, custody); whether an order then stays with the person, the organisation or the parent who has the children is an open architectural question for later (Q34). | Koen |
| 7 Oct 2026 | Orders follow registrations exactly: no household recorded on the order; the party concept (person, household, organisation; what happens on a divorce or a change of company) is worked out as a whole later, for registrations and orders alike (Q35). | Koen |
| 7 Oct 2026 | Productbeheer is part of the role Masterdata (CR-24, Q2), which holds `product.masterdata`; Penningmeester is called Boekhouding. **Replaces** the five roles of Q11 in part (Q33). | Koen |
| 7 Oct 2026 | The expiry of a transfer payment is a workflow of two steps, Boekhouding and then Verkoop, the task moving to Verkoop only when Boekhouding answers "not yet paid", and Verkoop's task shows how recent the information is (when Boekhouding last checked the account). **Replaces** in part Q15: the task for a transfer starts with Boekhouding, not Verkoop; a failed or hanging online payment (R17) stays a task for Verkoop (Q36). | Koen |
| 7 Oct 2026 | Reading bank statements automatically (CODA, ISO 20022 camt.053) is a change request of its own, CR-27, reserved now and left lying for a while; CR-21 relies on Boekhouding booking transfers by hand (Q37). | Koen |
| 7 Oct 2026 | A task past its due date only turns red on the workbench; nobody gets a mail about it (Q38). | Koen |
| 7 Oct 2026 | Cancelling until delivery is a Must; a return after delivery is out of scope and handled by hand: Sales removes the order and books the refund (Q40). | Koen |

---

# Part C — The build, for the master CLI and the dev CLIs

> [!NOTE]
> *Part C is read by whoever plans and builds. It is as long as it needs to*
> *be and it carries no decision Part B does not carry: a dev CLI that finds*
> *a decision missing here brings it to the master CLI, who brings it to the*
> *approver and records it in B9 — never a choice made in the code alone.*

## C1. Verified premises — measured before the handover

*Measured on master `f731a836`, 7 October 2026, before Part B is written — the step "who reads a concept this change alters" asked for after CR-22. Re-measured on the handover commit before assignment.*

**Readers of the concepts this change alters**

| Concept | What changes | Readers today (file:line) | Verdict |
|---|---|---|---|
| `PayableType` (`payment/models.py:78`, code list `payment/codes.py:60-73`) | a third value, ORDER | ~40 reader sites in ~22 files, every one an if/elif on two values. **Silently wrong for an order (~14):** `payment/service.py:265` `family_payables` and `:306`; `:951` `matches_filter` (no "Bestellingen" context); `:1385` `enriched_records` (no name, description, link); `payment/exports.py:40-71` (raw "order #id") and `:144` (exported as "Activiteit"); `payment/ui.py:296-321, 1089-1115` (no context link) and `:729-740` (no filter entry); `_betalingen_lijst.html:40,86` ("inschrijving" wording); `audit/changes.py:225-234` (empty subject); `reporting/universe.py:2409-2420` ("two streams"); view `reporting.f_payments` (`alembic/106:226-290`: CASE gives Activiteit/Lidgeld, joins registration/membership only). **Refused (1):** `kernel/modules.py:193` PAYMENT `depends_on (ACTIVITIES, MEMBERSHIP)` — a shop-only tenant cannot switch payments on. **Handled generically:** `create_payment_record`, `group_cards`, `status_router`, workflow refund title, event fields. | every "silently wrong" site must learn ORDER in this change (C2 payment, reporting); the dependency must accept the shop (C2 kernel) |
| `PaymentReceived` / `RefundDue` (`kernel/contracts/payment.py`) | an order must react when it is paid | 2 subscribers: `membership/handlers.py:16-28` (ignores non-membership), `workflow/handlers.py:40-50` (type-agnostic). Nothing subscribes for registrations. | an order needs its own subscriber for "paid" (closing the workbench task of R18) |
| `reconcile_charges` (`payment/service.py:769`) | a third caller (R16) | `payment/handlers.py:24` (`OrderChanged` → registrations), `membership/household_service.py:169`; `reconcile_registration_charges` exported, no non-test caller | reusable as planned |
| `OrderChanged` (`kernel/contracts/activities.py:11`) | name collision | its "order" means a registration's items (`payment/handlers.py:16-21`, `activities/service.py:1821-1838`) | the webshop's event needs another name (e.g. `SalesOrderChanged`); naming in B3a |
| member price: `has_valid_membership` (`membership/service.py:25`), `_unit_price` (`activities/totals.py:35`) | the shop prices by the same rule (Q5) | ~13 readers of the rule, ~9 of the totals (`totals.py:109-190`, `registration_form.py:92-101`, `activities/service.py:1843-1867`, `auth/router.py:157,167`, mail, payment, export, kernel/rules). **Three different "is member":** `membership.has_valid_membership` (dues), `mdm/service.py:274` `is_member` (in a household), `ui/__init__.py:954` and `auth/router.py:135` `is_member = person is not None` (read by `_member_nudge.html`, `_site_account.html`, `cms/home.html`) — the last one is what CR-22 had to split | the shop reads `has_valid_membership` only; the price column `member_price` stays on activity products (Non-goal), the shop's member price lives in `pricing` |
| `Role` (`auth/models.py:11`) | four new roles — superseded: the roles now come from CR-24 | ~30 role literals in 12 files; access sets `auth/session.py:116-120`; `landing_for` `auth/service.py:83`; nav `ui/__init__.py:858-900`; workflow defaults | CR-21 uses the roles of CR-24 and does not add codes of its own; built after CR-24 or with today's `require_admin_ui` as CR-22 did (B4) |
| `ModuleCode` and `mdm.tenant_modules` CHECK (`kernel/modules.py:31-52`, `alembic/187:58-59`) | a module for the shop | 1 enum, 1 CHECK, `DEFAULTS` `modules.py:287-294`, ~12 readers (tenant editor, nav, reporting, cms, auth landing) | a migration widens the CHECK; `DEFAULTS` decides whether VERENIGING and BEDRIJF get the shop |
| routes `/webshop`, products outside activities | new | none exist; the old `webshop_products`, `orders`, `order_items` were dropped by `006_remove_webshop.py`; "Product" already names `ActivityProduct` and a reporting object (`universe.py:2197`) and an audit entity (`audit/changes.py:531`) | the shop's names must not collide: B3a names `product` in its own schema; the reporting object needs a distinct label |

**Tests that guard the old behaviour (likely red, read before building)**
- `tests/test_payable_delete_gate.py:235` `test_de_payable_types_in_de_code_zijn_de_twee_die_de_gate_kent` — asserts the payable types are exactly two; with `PAYABLE_DOMEINEN` (line 80) and three more tests of that file.
- `tests/test_module_gate.py` (4), `mdm/tests/test_tenant_modules.py` (DEFAULTS, the CHECK, routes off → 404).
- `mdm/tests/test_codes_phase2.py` (the exact role set), `tests/test_role_set_gate.py` — if roles are added.
- Member price: `tests/integration/test_membership_pricing.py`, `test_kritische_flows_coverage.py`, `test_registration_form_1284.py`, `test_reporting_facts.py`, `test_db_constraints.py`.
- Payments by type: `tests/integration/test_betalingen_domeinregels.py`, `payment/tests/test_terugbetaling_kaarten.py`, `test_penningmeester_door_het_scherm.py`, `tests/integration/test_werkbank_betaalkaart.py`.

**Visitors and tenants walked (C3 list)** — to be completed with Part B: guest (orders without account: R33 via CR-22), account, member (member price), board user without a person (no shop buying), signed in at another tenant (accounts per tenant: no shop access across tenants), operator; tenant with members (Raak), company (no member price, no "of ben je lid"), platform (no shop).

## C2. Per module: what must happen

> [!NOTE]
> *One subsection per module touched, in build order, each with the same*
> *five headings: **screens** (which, what changes, at which width it is*
> *judged), **code** (view-model · service · entity · facade — the functions*
> *by name, and **the named owner of every writer** to a shared table),*
> ***database** (schema, table, each column with its type, nullability and*
> *constraints, the `ON DELETE` of every FK, the migration and whether it is*
> *additive — and, for every column added to an entity that has a **copy**
> *action, whether the copy takes it along or not, and why: the gate of*
> *#1464 refuses an unclassified column, so the design decides it here and*
> *the gate only confirms it; `target_audience` was added to the activity*
> *and `copy_activity` silently left it out, #1463), **templates and mail**,*
> ***tests** (which of C6). No effort*
> *here: the effort per module and phase is the table of B5. Which*
> *requirements a module serves is read from the matrix of B2, not repeated*
> *here. A module that is only used, not changed, gets one line. **Reporting*
> *is always one of the modules**, touched or not: the engine reads the*
> *tables through SQL views in the `reporting` schema and through its object*
> *universe, so for every column this change adds, renames, retypes,*
> *retires or gives a new meaning, its subsection says which views and*
> *objects read it (measured, not recalled) and in which phase the view*
> *follows. "Reporting — none: no view reads these columns" is a subsection*
> *too.*

## C3. Cross-cutting impact — the checklist of what gets forgotten

> [!NOTE]
> *One table, every row answered, "no" included, one sentence each:*
> *reporting views and saved reports (C2) · existing tests, e2e golden flows*
> *and 390 px screenshots (C6) · fixed UI decisions and `CLAUDE.md` ·*
> *design-system documentation · code lists · events, ports and handlers —*
> *and **which gate sees every new call across domains, and what it will*
> *say** · mail templates · migration: additive or contract (#1255) · tenant*
> *settings · env vars · JSON routes and API callers · external services*
> *(Mollie, mail) · **copy actions**: does this change add a field to an*
> *entity that has a copy action, and is the field copied or not, and why*
> *(C2). A "yes" points at the section that handles it. The next*
> *thing that gets missed becomes the next row.*

## C4. Detailed decisions — one subsection each, with the reasons

> [!NOTE]
> *The design decisions of B1 in full, one subsection each, with their*
> *reasons, the alternatives weighed and the measurements that decided*
> *them. B1 names the decision; this is where a builder reads why.*

## C5. Privacy and security — the mechanics behind A7

> [!NOTE]
> *How A7's privacy and security answers are implemented: what leaves the*
> *system to whom, what is sanitised, what is logged, which route answers*
> *what to whom.*

## C6. Tests — what the build must prove

> [!NOTE]
> *Two levels. **What the build must prove:** the new tests, each able to go*
> *red, guards proven by violation — numbered, so C2 can point at them per*
> *module. **Impact on the test landscape:** which existing suites, e2e*
> *golden flows and screenshot sets change or must be redone because of this*
> *change, per module, with the reason — a screen that moves, a route that*
> *changes, a fixture that no longer matches. A change that breaks no*
> *existing test says so, and why that is plausible. A test and a section of*
> *this document that contradict each other are a finding: CR-14's B5 said a*
> *spent link answers 404 while its test 3 expected "al ingevuld".*

## C7. The gate — what refuses a deviation from now on

> [!NOTE]
> *The gate behind B7's rule: which test fails when a new development breaks*
> *the rule, what it looks at, what its message says, and the violation it*
> *was proven with (C6). A rule is fixed only when its gate runs in CI on*
> *every push — a pytest in `backend/tests/` that `backend-tests.yml` runs,*
> *not a script someone remembers, not a review checklist. Two shapes, chosen*
> *by the baseline: a **ratchet** when the count is not yet zero (a frozen*
> *list of today's violations that may only shrink — the #780 pattern;*
> *nothing new may join it, an entry that disappears from the code must leave*
> *the list); a **hard gate** when the count is zero after this change.*
> *Gates come last, not first: a gate with a growing exemption list is a*
> *dead rule, and a gate written too early freezes the wrong understanding.*
> *Where the rule cannot be checked mechanically, say so and hand it to the*
> *judgment layer (the `design-conformiteit-bewaker` agent, the merge gate)*
> *instead of pretending a grep is a gate. The gate is also what makes the*
> *rule cheap to follow: for a new case it spells out the steps and fails on*
> *the one that was forgotten, with the name of the missing piece.*

## C8. Prototype findings — what was measured before the build

> [!NOTE]
> *What was learnt from prototypes and spikes before the build:*
> *measurements, refusals, things that did not work, the sizes and times*
> *that decided a choice in B1.*

## C9. Screens before the build — the concepts the approver saw

> [!NOTE]
> *For every screen this change adds or changes: a rendered concept at*
> *390 px (and at desktop width where it differs), with invented data, kept*
> *in the project folder outside the repository and looked at by the*
> *approver before the handover; here the list of those concepts, what each*
> *shows, and the date the approver saw it. A change request that changes a*
> *screen is not assigned without this row. Two of CR-14's four follow-ups*
> *at the HDEV validation were visible on a drawing: a question block that*
> *looked different from the form, a button named after the domain.*

## C10. Close-out at the release

> [!NOTE]
> *Filled in by the architecture CLI when the release that built this change*
> *runs on PROD (`CLAUDE.md`, release step 14): the status line set to "built*
> *in vX.Y.Z, on PROD since …"; every as-built deviation in B9, with an*
> *as-built note in the text it contradicts; the tracking issue closed by the*
> *master CLI with a comment naming the release; what was left for a later*
> *change request, by issue number. Until this section is written, the*
> *document describes the design, not what runs.*

---

## Q&A log — asked once, answered here

> [!NOTE]
> *Every question asked during shaping, review and build, dated, with who*
> *asked and the answer — so nothing is asked twice. Open questions stand in*
> *B8 with their recommendation; when answered they move here. An external*
> *review (Mistral, ChatGPT) is one entry with what was taken in and what*
> *was not, with the reason.*

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 6 Oct 2026 | Is a size a product of its own, or a variant of one product? (Claude) | A variant; stock is kept per variant. (Koen) |
| Q2 | 6 Oct 2026 | Does price get its own domain, or is it a column on the product? (Koen raised it, Claude asked) | Its own domain: `pricing`. (Koen) |
| Q3 | 6 Oct 2026 | Is stock kept as one number per variant and location, or as movements whose sum is the stock? (Claude) | Movements. (Koen) |
| Q4 | 6 Oct 2026 | Does the price hang at the product or at the variant? (Claude) | At the product, and a variant may override it. (Koen) |
| Q5 | 6 Oct 2026 | Who may buy — members only or everyone — and is there a member price? (Claude) | Both: everyone may buy, and there is a member price, the same principle as registrations for activities. (Koen) |
| Q6 | 6 Oct 2026 | How does the buyer get the article — pick-up or brought — and can it still be tried on first? (Claude) | Pick-up or brought, and trying on stays possible; automating any of it is out of scope. (Koen) |
| Q7 | 6 Oct 2026 | Is stock taken when the order is placed, or only when it is paid? (Claude) | For now at the order; if the order is cancelled, the stock comes free again. (Koen) |
| Q8 | 6 Oct 2026 | How does the buyer pay — Mollie, bank transfer, or both? (Claude) | Both, as with registrations. (Koen) |
| Q9 | 6 Oct 2026 | What happens with an exchange or a return after trying on? (Claude) | The same principle as activities: the order is changed (bigger size in, smaller size back, or a T-shirt instead of a sweater), and the financial impact is computed as for activities — extra payment if already paid, updated payment if not yet paid, refund if already paid and the new amount is lower. (Koen) |
| Q10 | 6 Oct 2026 | Who cancels an unpaid order — automatically when an online payment fails or expires, by hand for a bank transfer, from a list of open orders? (Claude) | Automatically for the online payment; for a transfer, a task on the workbench for a new role "sales". (Koen) |
| Q11 | 6 Oct 2026 | One role or several for products, prices, orders and stock? (Claude) | Five: product master, pricing, sales, finance (existing) and stock management. (Koen) |
| Q12 | 6 Oct 2026 | Does ADMIN see everything of the webshop, and may OPERATOR do everything? (Claude) | Yes: ADMIN may view everything and only the four roles may change; OPERATOR may do everything, as today. (Koen) |
| Q13 | 6 Oct 2026 | The task for an unpaid order: to Sales, with Finance confirming payments as today? (Claude) | Yes. (Koen) |
| Q14 | 6 Oct 2026 | Screen names of the roles, and "E-loket" or "Webshop"? (Claude) | Productbeheer, Prijsbeheer, Verkoop, Voorraadbeheer; "Webshop". (Koen) |
| Q15 | 6 Oct 2026 | When does the task for an unpaid transfer appear: at once with a due date, or after 14 days? (Claude) | At once, due within 14 days, closing by itself when paid — and also a task for a failed or hanging online payment, because then something has to happen. (Koen) |
| Q16 | 6 Oct 2026 | When does the stock go down — at the order, at the payment, or at the hand-over? (Claude, asked before Q7) | Koen came back on Q7: an order only reserves; the stock goes down when Sales registers the delivery, picked up or brought alike. (Koen) |
| Q17 | 6 Oct 2026 | Does the reservation of an unpaid order stay until Sales decides, or does it expire by itself? (Claude) | It stays until the user does something. (Koen) |
| Q18 | 6 Oct 2026 | Who ends an unpaid order: the buyer by paying, the buyer by withdrawing in the webshop, or Sales by cancelling? (Claude) | Paying and Sales cancelling; the buyer withdrawing in the webshop is not provided for now. (Koen) |
| Q19 | 6 Oct 2026 | (Koen came back on Q18) Should the buyer be able to cancel his own order after all? | Yes, modelled at once: with the same screen in public and in the back office it may come for free. (Koen) |
| Q20 | 6 Oct 2026 | Until when may the buyer cancel? (Claude) | Until the order is delivered; afterwards a return through Sales, refund through the recalculation of an exchange. (Koen) |
| Q21 | 6 Oct 2026 | How does the buyer get back to his order — a link in the confirmation mail, or by signing in? (Claude) | A link in the confirmation mail. (Koen) |
| Q22 | 6 Oct 2026 | Is stock reserved when an article goes into the basket, or at "Bestellen"? (Claude) | At "Bestellen". (Koen) |
| Q23 | 6 Oct 2026 | Where does the basket live? (Claude) | In the browser, without an account. (Koen) |
| Q24 | 6 Oct 2026 | Is cancelling per line or for the whole order? (Claude) | The whole order; one line out is a change. (Koen) |
| Q25 | 6 Oct 2026 | Is "delivered" registered per line or per order? (Claude) | Per line. (Koen) |
| Q26 | 6 Oct 2026 | Does the link in the confirmation mail stay now there is an account? (Claude) | Yes, as a link that signs in and brings the buyer to his order. (Koen) |
| Q27 | 6 Oct 2026 | An account with an e-mail address that already belongs to a person: a second person, or a sign-in link? (Claude) | A sign-in link to that address; no second person. (Koen) |
| Q28 | 7 Oct 2026 | Lift signing in out of CR-21 into its own change request, built on activities first? Three ways (member, account, guest) and name + e-mail + mobile for a guest? (Claude, after Koen's proposal) | Yes to all. (Koen) |
| Q29 | 7 Oct 2026 | Two statuses side by side — payment from the payment domain, delivery derived from the lines? (Claude) | Yes; and know that invoices towards companies come later, in parallel with payments. (Koen) |
| Q30 | 7 Oct 2026 | Is "Afgeleverd" a goods issue as in an ERP, and can part of a line be delivered? (Koen, Claude) | Yes, a goods issue; a line is delivered whole, a partial delivery splits the line through a change. (Koen) |
| Q31 | 7 Oct 2026 | Do invoices later go into the payment domain (finance), with the webshop asking it to invoice delivered lines? (Koen raised it, Claude) | Fully agreed — but for later; out of scope now. (Koen) |
| Q32 | 7 Oct 2026 | Delivery status for the buyer before anything is delivered: "Gereserveerd" or "Klaar om af te halen"? (Claude) | Klaar om af te halen. (Koen) |
| Q33 | 7 Oct 2026 | (Koen, in CR-24) Is product management product master data — one role Masterdata for persons, organisations and products? | One role is fine. (Koen) |
| Q34 | 7 Oct 2026 | Who buys: the household or the person? (Claude proposed the household; Koen asked who registers today) | The person, as with registrations; good for CR-21, not final: when a person changes company, the orders should stay with the company; after a divorce, perhaps with the parent who has the children. To think through later. (Koen) |
| Q35 | 7 Oct 2026 | Record on the order the household it was placed in, so a later rule (divorce, company change) has the fact? (Claude) | Not now: do exactly what registrations do; the party concept is to be worked out as a whole first, for registrations and orders together. (Koen) |
| Q36 | 7 Oct 2026 | Sales can only decide on an unpaid transfer if Boekhouding has booked the incoming payments in time. A workflow of two steps — Boekhouding confirms first, Verkoop decides after — with the freshness of the information on Verkoop's task? (Koen raised it, Claude proposed) | Agreed ("akkoord"), and confirmed in these words: an unpaid order goes to Boekhouding first ("is the money on the account?"); only when Boekhouding says "not yet paid" does it go to Verkoop ("remind or cancel"); Verkoop's task shows when Boekhouding last checked the account. ("prima", Koen) |
| Q37 | 7 Oct 2026 | Reserve a change request of its own for importing bank statements (CODA or camt.053), as with CR-26? (Claude) | Fine, but it will stay lying for a while. (Koen) |
| Q38 | 7 Oct 2026 | When the 14 days are over: does the task only turn red on the workbench, or does Verkoop also get a mail? (Claude) | Only red on the workbench. (Koen) |
| Q40 | 7 Oct 2026 | R25: should cancelling until delivery be a Should, and how is a return after delivery handled? (Claude) | Must; a return is out of scope — done by removing the order and booking the refund, by hand ("manueel"). (Koen) |
| Q41 | 7 Oct 2026 | A returned garment: does Voorraadbeheer raise the stock again by hand, with a correction — so the webshop needs one? (Claude) | Yes. (Koen) |
| Q42 | 7 Oct 2026 | How does new stock come in: with the correction of R36, or as a receipt of its own? (Claude proposed a receipt) | A receipt of its own. (Koen) |
| Q43 | 7 Oct 2026 | MoSCoW: all proposed Musts confirmed, R23 (the buyer cancels himself) too? (Claude) | "Kies maar, we gaan het toch bouwen" — the screen exists, so it is no extra work: Must. The other Musts stand as proposed. (Koen) |

## Non-goals — deliberately outside this change

> [!NOTE]
> *What is deliberately outside this change.*

- **Returns after delivery** (R25, Q40). Handled by hand: Sales removes the order and books the refund; the portal has no return flow.

## Relationship to existing work — issues and change requests

> [!NOTE]
> *Issues and CRs this builds on or hands off to; the tracking issue first.*
