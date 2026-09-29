# Change Request 14 — Extra questions on a registration: a form attached to a component

**Project:** Web Portal "Raak Millegem"
**Status:** shaped with Koen on 29 September 2026 · **draft — Part A to be confirmed by Koen** · not assigned
**Applies to:** the activity registration flow (public modal, board form, JSON API), the `forms` domain, the registration detail and export in the admin.

> Part A is written from Koen's spoken brief of 29 September 2026. Where the
> brief left something open, the sentence says *to confirm* and the Q&A log
> carries the question. Part B is measured on `master` `6a96af01` the same day.

---

# Part A — The business

## A1. Reason to act

An activity sometimes needs more from a participant than a name, an e-mail,
a phone number and a choice of products. Who joins which group, which size,
an allergy, a lift needed, a licence number — questions that differ per
activity and per component. The activities module cannot ask them: a
registration collects the contact, the products and a free "remarks" box,
and nothing else. So today those questions are asked next to the
registration — by mail, on the day itself, or through a separate form that
the participant has to find and fill in a second time — and the treasurer
or the organiser matches the answers to the registrations by hand.

The moment is now because an activity is coming up that needs such
questions, and because the portal already has a form builder (the `forms`
module, with ten field types, sections and a submissions view) that asks
exactly this kind of question — only not *as part of* a registration. The
idea, in Koen's words: attach a form to a component of an activity, so that
registering flows into the questions **in one movement**, and the answers
belong to the registration.

The trigger is the **Sint activity** (Koen, 29 September): five questions
that today have no place in the registration — see A4.

## A2. As-is process

| Step | Who | Today | Pain |
|---|---|---|---|
| 1. The organiser sets up the activity and its components in the admin, with products and prices. | organiser | activities module | — |
| 2. A member registers on the site: contact, products, remarks, payment method; pays through Mollie or by transfer. | member | public modal | the modal has no place for the activity's own questions |
| 3. The extra questions are asked *elsewhere*: in the confirmation mail's reply, in a separate form, on the day. | organiser, member | mail, a form, paper | a second action for the member; answers arrive late or not at all |
| 4. The organiser matches answers to registrations. | organiser, treasurer | by hand | error-prone; the registration list and the answers are two lists |
| 5. The export of a component (one row per registration) has no answers. | organiser | .ods export | a third list |

Measured on `master` (29 Sep): a registration carries `remarks` as its only
free field; the component has no setting that points at a form; the form
builder has 25 admin screens and 7 public routes, and a submission cannot
be linked to anything today.

## A3. To-be process

| Step | Who | Afterwards |
|---|---|---|
| 1. The organiser builds the questions as a form in the form builder (as today for any form). | organiser | forms module |
| 2. The organiser attaches that form to the component: "Extra questions: <form>". | organiser | one setting on the component |
| 3. A member registers on **one page**, in this order: who (contact), what (the products — "two children for the Sint"), **then the component's questions** — with a choice: answer them now, or later through a link in the confirmation mail (Koen: "ik schreef ze eerst in, en een week voor de Sint vulde ik de rest in") — then the payment method; one submit; then Mollie or the transfer instructions, as today. | member | the public registration page |
| 4. The board registers a member on **the same page** as the member sees, in the admin shell, with the same choice: answer now, or the member answers later through the link in the mail. | board, member | the same registration page; the answer link |
| 4b. Whoever chose "later" — member or board — the member gets the link in the confirmation mail, answers when it suits, and the answers land on the registration. The organiser sees who still owes answers and can resend the link. | member, organiser | the answer link; the registration detail |
| 5. The answers are on the registration: in the admin detail, in the component's export (one column per question), in the confirmation mail *(to confirm)*. | organiser, treasurer | activities module |
| 6. A required question that is not answered refuses the registration with the same message on the entrances that ask it — the public screen and the JSON API. | — | — |

## A4. Supplied material

The questions of the Sint activity (Koen, 29 September 2026), and what
they teach about the shape:

| Question | Kind | Form builder field type | Note |
|---|---|---|---|
| Which time slots suit you? | several of a list | `checkbox` (multi) | a preference, not a booking: a person plans the visits afterwards (Koen, Q8) — so no capacity, no product |
| Inside or outside? | one of two | `radio` | — |
| Tell us about the children | free text | `textarea` | personal data about minors; seen by the organiser only |
| Allergies | free text | `textarea` | health data — asked because the activity needs it; no special handling in the system, the organiser decides to ask |
| Remarks | free text | `textarea` | replaces the registration's own *Opmerkingen* box on this screen: a component with a form hides the fixed box (Koen, Q9) |

Learnt: all five fit the ten field types, in one section, without
branching; none depends on a product; one form serves the activity (one
component). Nothing in the form builder has to change for this case.

## A5. Business requirements

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | An organiser can attach one form, built in the form builder, to a component of an activity. | Must | Koen, 29 Sep 2026 | "dat je aan een onderdeel binnen een activiteit koppelt" |
| R2 | A member answers the component's questions **while registering** — or chooses to answer them **later**, through a link in the confirmation mail; the registration itself never waits for the answers. | Must | Koen, 29 Sep 2026 | "in één beweging" and, the same day, the Sint story: registered first, answered a week before the visit |
| R3 | The answers belong to the registration: they are shown on the registration in the admin and included in the component's export. | Must | Koen, 29 Sep 2026 | "een inschrijving met extra vragen te voorzien" |
| R4 | Whoever answers — now on the page, later through the link, member or board — is held to the same rules: a required question refuses the answers with the same message everywhere. No channel is lenient. | Must | Koen, 29 Sep 2026; CR-13 R1 | "helemaal invullen, of leeg"; one entrance rule |
| R5 | The choice "now or later" is the same for the member and the board: the board may answer completely or leave it to the member, who gets the link. | Must | Koen, 29 Sep 2026 | "zowel de bestuurder als de publieke gebruiker kunnen kiezen" |
| R6 | The confirmation mail repeats the answers. | Should | Koen, 29 Sep 2026 | the member sees what was recorded |
| R7 | An organiser can correct an answer in the admin afterwards. | Should | Koen, 29 Sep 2026 | the form builder already supports editing a submission — see B4.7 for how |
| R8 | A form attached to a component stays fillable on its own public URL. | Should | Koen, 29 Sep 2026 | such a submission is not linked to a registration; the form's submissions view shows it without an "inschrijving #N" cell — harmless, because the link runs from the registration to the submission |
| R9 | Questions that depend on the products chosen ("size per ticket"). | Won't | analyst | a product-level question is a different shape; own change if ever needed |
| R10 | A component may swap its form once registrations carry answers. | Won't | Koen, 29 Sep 2026 | once a registration of the component has a submission, the form can be detached but not replaced — attaching a different one is refused |
| R11 | One registration screen for the member and the board, built from the board's page as the ideal — **and the public user loses nothing**: every function and every nicety the public registration has today is on the page. | Must | Koen, 29 Sep 2026 | "dat we niet ineens functionaliteit … niet meer beschikbaar stellen voor publieke gebruikers"; the parity list is B4.9 |

## A6. Non-functional requirements

| Concern | This change |
|---|---|
| **Reporting** | The component export carries the answers, one column per question. The reporting engine (CR-06) does not — answers are per activity, not a measure. |
| **Security** | Nothing new from outside: the questions arrive through the registration entrances that exist, under the same rate limit, honeypot and CSRF as today. The form's own validation (required, bounds, options) applies. |
| **Privacy** | Answers are personal data on the registration; they are seen by whoever sees the registration (organiser, treasurer, board), never on the public participant list, and they follow the registration's soft delete. An allergy is health data — the organiser decides per activity whether to ask it; the system does not treat it differently *(to confirm with Koen)*. |
| **House style / UI norm** | The questions render with the same field macros as the form builder's public form, inside the registration screen. **One way for both, and it is a page** (Koen, 29 Sep): the public registration becomes a page, with or without a form, and the same page serves the board in the admin shell. This revises the fixed UI decision "public registration is a modal" in `CLAUDE.md` — Koen's decision, text proposal in B4.1. "Wie doet er mee?" stays the compact inline line. |
| **Multi-tenant** | A form and a component belong to the same tenant; the picker offers only the tenant's own forms. Nothing platform-wide. |

## A7. Acceptance criteria

| # | Criterion | Requirement |
|---|---|---|
| AC1 | On HDEV, the organiser attaches an open form with three questions (a choice, a number, a text) to a component; the public registration for that component shows the three questions between the products and the remarks; a component without a form shows nothing new. | R1, R2 |
| AC2 | "Now" chosen and a required question left empty: refused with the question named — on the public page, on the board page, through the JSON API and on the answer-link page — and nothing is saved. "Later" chosen: the registration is saved without answers and the mail carries the link. | R2, R4 |
| AC3 | After a paid registration (stub provider) and a free one, the answers show on the registration detail in the admin and in the component's export, one column per question, in the form's order. | R3 |
| AC4 | The member (public) and the board each register with "later": the member gets a mail with a link; opening it shows the questions, answering them puts the answers on that registration in the admin detail and the export; opening the link again shows "al ingevuld". The detail shows "antwoorden gevraagd op <date>" until then and lets the organiser resend the link. | R2, R5 |
| AC5 | Attaching a closed form, a form of another tenant, or a form with more than one section is refused with a message that says why; so is replacing the form of a component that already has answered registrations. | R1, R10 |
| AC6 | Once the form has answers on a registration, the form builder refuses to change its fields (as it does today for any form with submissions). | R3 |
| AC7 | The organiser corrects an answer on the registration detail; the corrected value shows in the detail and the export; an empty required answer is refused there too. | R7 |
| AC8 | The confirmation mail of a registration with answers lists them, label and value, after the products. | R6 |
| AC9 | Every row of the parity list in B4.9 is walked on HDEV on a phone and on a desktop: each public function of today is found on the new page, and the two screenshots (modal before, page after) sit side by side in the PR. | R11 |

---

# Part B — The solution

## B1. Solution outline

The component gets one nullable reference to a form (`form_id`); the
registration gets one nullable reference to a form submission
(`form_submission_id`). The public and board registration screens render
the attached form's fields with the form builder's own field partial, in the
registration form, and post them with the registration. `create_registration`
— the single implementation behind all three entrances — hands the answers
to the `forms` facade inside the same transaction, gets a submission back,
links it, and only then starts the payment. The answers are read back
through `forms.api.submission_view` for the admin detail and the export.
No new domain, no new event, no JSON column.

Decisions that shape it, with the alternatives:

- **The questions are asked in the registration, not after it** (R2). An
  extra step after the registration and before the payment would mean a
  registration saved without answers, a page in between, and a Mollie
  redirect that is no longer the response of the registration submit — three
  seams where a member drops out. A step *after* payment loses the member to
  the Mollie return page. In the registration, one transaction covers the
  registration, the answers and the payment record, and the refusal of a
  required question happens where the member is.
- **A form from the form builder, not new columns on the registration.**
  The builder exists (10 field types, options, validation as columns, a
  submissions view, an export). New columns per activity would be CR-03's
  six form types over again — the thing v2.0 simplified away.
- **The link lives on the activities side** (`component.form_id`,
  `registration.form_submission_id`), not on the form. The placement rule of
  CR-04/CR-13: "this component asks these questions" and "this registration
  gave these answers" are facts about the component and the registration.
  The form stays what it is — reusable, unaware. The submission gets no
  `subject` column: one submission belongs to at most one registration, and
  the registration says which.
- **`forms` writes its own rows.** `activities` never constructs a
  `FormSubmission` (CR-13 *no foreign writes*); it calls a `forms.api`
  command inside the request, exactly as it calls
  `payment.api.create_payment_record` today. That is a door call, not an
  event: the answers are part of the request (CR-13 B4.1, the payment-record
  decision of 29 September).

### B1.1 Functional analysis

| # | Derived requirement | From |
|---|---|---|
| F1 | A component has at most one form; a form may be attached to several components (the same questions for every component of one activity). | R1 |
| F2 | Only an *open* form of the same tenant with **one section** can be attached; sections and branching (#336) do not fit a registration screen — refused at attach time with the reason. | R1, AC5 |
| F3 | The attached form's fields render on the registration page after the products and before the payment method (B4.1), behind the choice "nu invullen / later via de link" (B4.8), with the builder's field partial; the `info` field type renders as text, `rating` as today. **The registration's own *Opmerkingen* box is hidden when the component has a form** (Koen, Q9) — the form asks for remarks if it wants them; `remarks` stays empty on such a registration. | R2 |
| F4 | The answers are validated by the `forms` rules (`build_answers`: required, min/max, options) before the registration is created; a refusal names the question and re-renders the screen with the answers kept. | R4 |
| F5 | The submission's `submitter_name`/`submitter_email` are the registration's contact; the form's own confirmation mail is **not sent** for an attached submission (the registration mail carries the answers, R6). | R3, R6 |
| F6 | The JSON API's `RegistrationCreate` accepts `answers: {field_id: value}`; answers present = "now" (validated, same message); `answers` absent = "later" (token and link). | R2, R4 |
| F7 | Both pages render the questions behind the same explicit choice — now (complete, same validation) or later by link (B4.8). With "later" the registration gets an `answer_token`; the confirmation mail (or a separate mail when no confirmation goes out) carries the link `/inschrijving/{answer_token}/vragen`; that page renders the form's fields, and its post creates the submission through `forms.api.submit_attached` and links it — once: a used token shows "al ingevuld". The detail shows the open request and a "link opnieuw sturen" action. | R5 |
| F8 | The admin detail shows the answers as label/value rows; the export adds one column per field after *Opmerkingen*, in field order; a checkbox field joins its options with ", ". | R3 |
| F9 | The attached form's public URL keeps working as for any form; a submission made there has no registration and is shown as such in the form's submissions view. | R8 |
| F10 | Soft-deleting a registration leaves the submission in place (history); the submissions view of the form shows it as "on registration #N". | R3 |
| F11 | The form builder's existing rule — no field change once submissions exist (#665) — protects attached forms unchanged. | AC6 |
| F12 | The registration detail edits the answers through the same field partial and `forms.api.update_attached(db, submission, answers)`, which re-validates with `build_answers` and replaces the answer rows; a history row on the registration records "answers edited" with the old and new values. | R7 |
| F13 | Replacing a component's form is refused when any registration of the component has a submission; detaching is allowed (the submissions stay). | R10 |

## B2. Architecture

### B2.1 Components

| Component | new / used / changed | Role |
|---|---|---|
| `activities/models.py` — `ActivitySubRegistration.form_id`, `Registration.form_submission_id` | **changed** | the two links |
| `activities/router.py::create_registration` | **changed** | validates and stores the answers through `forms.api` inside the transaction, before the payment record; on the board channel with a form: sets `answer_token` instead |
| `activities/ui.py` — `/inschrijving/{answer_token}/vragen` (GET, POST) | **new** | the answer-later page: the form's fields, then `submit_attached` + link, once |
| `activities/models.py` — `Registration.answer_token` | **changed** | the link's secret (32+ random url-safe bytes, unique, nullable; the `edit_token` pattern of `forms`) |
| `activities/registration_form.py` | **changed** | parses the answer fields from the posted form (public and board) into `RegistrationCreate.answers` |
| `activities/templates/_inschrijf_velden.html` | **changed** | includes the form's fields, after the products, when the component has one |
| `activities/templates/_inschrijf_form.html` (modal) → `inschrijven.html` (page) | **changed** | the public registration becomes a page in the site shell; the board page keeps `admin_inschrijving_nieuw.html` in the admin shell, same content block (B4.1) |
| `activities/admin_ui.py` — component settings | **changed** | the form picker ("Extra vragen"), with F2's and F13's refusals |
| `activities/templates/_inschrijving_detail.html`, `export.py` | **changed** | show and export the answers |
| `forms/api.py` | **changed** | new commands `submit_attached(db, form, answers, submitter)` and `update_attached(db, submission, answers)` — both validate with `build_answers`; the first creates the submission without mail, the second replaces its answers; new read `attachable_forms(db)` |
| `forms/templates/_formulier_veld.html`, `screenfields.py` | used | the field rendering, unchanged |
| `mail` — registration confirmation | **changed** | lists the answers after the products (R6); on a board registration with an open answer request it carries the link instead (R5) |
| JSON API `POST /api/v1/activities/{id}/register` | **changed** | `answers` in the schema |

### B2.2 Application usage

```mermaid
flowchart LR
  subgraph business["A3 — process"]
    S1["1. build the questions"]
    S2["2. attach to the component"]
    S3["3. member registers, answers, pays"]
    S4["4. board registers a member"]
    S5["5. organiser reads the answers"]
  end
  subgraph app["application"]
    FB["form builder<br/>/admin/formulieren"]
    CS["component settings<br/>/admin/activiteiten/…/onderdelen"]
    PR["public registration<br/>/activiteiten/{id}/inschrijven/{cid}"]
    BR["board registration<br/>/admin/activiteiten/{id}/inschrijvingen/nieuw"]
    CR["create_registration → forms.api.submit_attached → payment.api.create_payment_record"]
    AD["registration detail + export"]
  end
  S1 --> FB
  S2 --> CS
  S3 --> PR --> CR
  S4 --> BR --> CR
  S5 --> AD
```

### B2.3 Application structure

```mermaid
flowchart TB
  subgraph activities
    UI["ui.py · admin_ui.py"]
    RF["registration_form.py"]
    SVC["router.py::create_registration<br/>service.register"]
    M["Registration (+form_submission_id)<br/>ActivitySubRegistration (+form_id)"]
    EX["export.py"]
  end
  subgraph forms
    FAPI["api.py<br/>submit_attached · submission_view · attachable_forms"]
    FS["service.py build_answers"]
    FM["Form · FormField · FormSubmission · FormSubmissionAnswer"]
    FV["_formulier_veld.html"]
  end
  subgraph payment
    PAPI["api.py create_payment_record"]
  end
  UI --> RF --> SVC
  UI -. renders .-> FV
  SVC --> FAPI --> FS --> FM
  SVC --> PAPI
  SVC --> M
  EX --> FAPI
  M -. FK .-> FM
```

`activities` reaches `forms` only through `forms.api` (import gate); the
template include of `_formulier_veld.html` is a *read* of a template, which
the layer gate allows as it allows the macros.

### B2.4 Impact on the existing architecture

- **Cross-schema FKs** `activities.activity_sub_registrations.form_id →
  form.forms.id` and `activities.registrations.form_submission_id →
  form.form_submissions.id`, both nullable — the pattern
  `registrations.person_id → mdm.persons` already uses. `ON DELETE`:
  `SET NULL` for `form_id` (a deleted form detaches; the component keeps
  working); `RESTRICT` for `form_submission_id` (an answered submission is
  not deleted under a registration — #94 phase 4 decides per FK, this one is
  decided here).
- **CR-13 rules respected:** no foreign write (forms creates its rows);
  the door service commits once (the answers, the registration and the
  payment record in one transaction, `create_registration`'s existing
  commit); no rule in a router (the "required answers" rule is `forms`'
  `build_answers`; the one cross-object rule — a linked submission belongs to the
  component's form — is `Registration.check()`, on flush; "a component with
  a form needs answers" is *not* an invariant of the row, because the board
  registers without them (R5): it is the public and API entrances' rule,
  enforced where the answers are posted); no new JSON route
  (the existing `POST /register` grows a field).
- **CR-12:** no new code list. The field types are `forms`' list.
- **Templates:** `StrictUndefined` — the registration view-model promises
  `form_fields` (possibly empty) on every render.

## B3. Cost and operations

None new: no service, no env var, no job. One migration (two nullable
columns with FKs; additive under #1255). Kill switch: detaching the form
from the component restores today's screen — no flag needed.

## B4. Detailed decisions

### B4.1 One registration page, for the member and for the board

**Decided by Koen, 29 September 2026: a page, not a modal — one way, with or
without a form.** Until now the public registration was a narrow modal
(`max-w-md`, a fixed UI decision of v2.0) and the board had its own page in
the admin (`admin_inschrijving_nieuw.html`, #1284), both including the same
field partial `_inschrijf_velden.html`. From this CR on there is **one
registration page, built from the board's page as the ideal** (Koen, 29
September): the public route `GET /activiteiten/{id}/inschrijven/{cid}`
renders it in the site shell, the board route renders the same content in
the admin shell; the differences between the two channels stay the ones
`registration_form.py` already lists (backoffice products, the actor, the
return path) plus the questions being optional for the board (B4.8).

Why a page and not the modal, honestly weighed (Q3): a dialog is for a
short task, and contact + products + five questions + payment method is a
page's worth; on a desktop a long modal scrolls in a small box and hides a
refused question; on iOS a fixed modal with a keyboard misbehaves on long
input; a page has a URL to share ("schrijf hier in") and a back button; and
it is the shape the forms module and the coming longer flows already have.
What it costs: every registration changes, also without a form; the
participant list "Wie doet er mee?" no longer refreshes in place (#1159)
but on return to the activity; the e2e golden flow and the 390 px
screenshots are redone. On a phone — 80 % of visits — nothing changes: the
modal was already a full-width sheet.

**The order on the page** (Koen, 29 Sep — "the flow is: register two
children, then answer"): 1. who — contact; 2. what — the products; 3. the
component's questions; 4. the payment method; then submit → Mollie or the
transfer instructions. The questions come *after* the choice and *before*
the payment, never before the registration itself: "before the payment
step" in R2 means before the redirect to Mollie, because after Mollie the
member is gone from the site.

**Text proposal for the fixed UI decision in `CLAUDE.md`** (Koen decides
the wording, the master CLI edits): *"Registration is a page — one page for
the member (site shell) and the board (admin shell), same fields, same
order: contact, products, the component's questions if any, payment method.
Not a modal (revised 29 September 2026, CR-14). 'Wie doet er mee?' is a
compact inline line (`text-xs`, N ingeschreven — naam · naam)."*

### B4.2 One transaction, in this order

Inside `create_registration`, between `service.register` (flush) and the
payment record:

1. `forms.api.submit_attached(db, form, answers, submitter=(contact_name,
   contact_email))` — `build_answers` refuses a missing required answer or
   an out-of-range value with `FormError` (alias of the forms exception,
   CR-13 B4.4), which the screen shows next to the question; on success the
   submission is flushed, not committed.
2. `registration.form_submission_id = submission.id`; `Registration.check()`
   on flush confirms: a linked submission's `form_id` is the component's
   `form_id`. (Not "component with a form ⇒ submission": the board form
   registers without answers, R5.) The board channel skips step 1.
3. `payment.api.create_payment_record` — as today; a Mollie failure rolls
   back the registration **and the submission** (one transaction; today's
   502 path).
4. `db.commit()`, mail.

The answers are validated *before* the registration's own "full" and
"already registered" checks? No — after `service.register` has passed them,
so a member is not asked to fix an answer on a component that is full. Order
of refusals on one submit: contact → products → component rules → answers.

### B4.3 Rendering and posting the fields

Field names in the registration post: `q_<field_id>` (the form builder's
own public form posts `field_<id>`; the prefix differs on purpose so a
registration field and a question can never collide — `phone` is a field
type *and* a registration column). `registration_form.py` collects every
`q_*` into `RegistrationCreate.answers: dict[int, str | list[str]]`
(checkbox = list). The board form posts the same names. The JSON API takes
`answers` as `{"<field_id>": value}`; unknown ids are refused (a question
that is not on this form).

### B4.4 Reading the answers

`forms.api.submission_view(db, submission_id)` exists (label/value rows for
the workflow task detail) and is reused for the admin detail. The export
asks `forms.api.form_definition` for the field order and `submission_view`
per registration; one column per field, header = field label. A component
whose form changed after the first answers cannot happen (F11).

### B4.5 Attaching and detaching

The component settings get a select "Extra vragen" over
`forms.api.attachable_forms(db)`: open, same tenant, one section, not
anonymous. Detaching is allowed at any time; existing registrations keep
their submissions. **Replacing** the form of a component that already has a
registration with a submission is refused (Koen, 29 Sep, R10): the answers
of one component then all belong to one form, and the export has one set of
columns. To change the questions after answers exist, the organiser detaches
and attaches a new form on a *new* component, or lives with #665's rule.

### B4.7 Correcting an answer afterwards (R7)

How the form builder edits today: a standalone form with `allow_edit` mails
the submitter an edit link (`edit_token`); the public route re-renders the
fields with the answers, and `update_submission` runs `build_answers` again
and replaces the answer rows (a checkbox answer is several rows, deleted and
recreated). No history is kept on a submission.

For an attached submission the organiser edits on the **registration
detail**, not through an edit link: the detail renders the form's fields
with the current answers (the same partial as the registration screen), the
save posts to `/admin/inschrijvingen/{id}/antwoorden`, which calls
`forms.api.update_attached` — same validation, same replacement — inside the
registration's own transaction, and writes a `RegistrationHistory` row
"answers edited" carrying old and new values as label/value text (the
registration already keeps history for remarks and lines; answers join it).
The member does not get an edit link for an attached submission (Non-goals).

Changing the **form itself** after answers exist is a different question and
is already answered by the form builder: refused (#665), because
`apply_definition` deletes fields and the answers cascade with them.

### B4.8 Answers later, by link (R5)

A board registration for a component with a form does not ask the questions
(the board rarely knows the answers); the member answers afterwards through
a link. The mechanics follow the form builder's own edit link
(`edit_token`), on the registration side:

- `create_registration`, either channel, "later" chosen (or the API without
  `answers`): no submission; `registration.answer_token` = a fresh url-safe
  secret; the confirmation mail — sent on both channels today — carries
  `/inschrijving/{answer_token}/vragen`.
- The page renders the component's form fields with the registration's
  contact shown read-only ("Inschrijving van <name> voor <activity>"); the
  post runs `submit_attached`, links the submission, clears the token, one
  transaction, `check()` on flush. A second visit: "al ingevuld", with the
  answers shown, no edit (the organiser edits, B4.7).
- The detail shows "antwoorden gevraagd op <registered_at>" while the token
  is open, with "link opnieuw sturen" (same token, new mail). The token has
  no expiry: the activity's date is the natural end, and a stale link shows
  the registration's current state.
- A registration whose component got a form *after* it was made has no
  submission and no token — the organiser sends the link from the detail for
  those too ("link sturen" when there is no submission), which covers "we
  attached the form after the first registrations".
- The token is the only secret; it is not the registration id, and the
  page does not accept an id. The rate limiter of the registration routes
  covers the post.

**The mail — proposal, open (Q11).** A board registration already sends the
same confirmation mail as a member's own registration, to the member's
address, with the payment information. Keep that: **one mail**, with one
variable block after the products and the payment information — the
answers as label/value when a submission exists; "nog even de vragen" with
the link when the token is open; nothing when the component has no form.
Subject stays "Inschrijving bevestigd".

**Now or later — one choice, on both pages** (Koen, 29 September: first
"the board fills it in completely or not at all", then "I would do the same
on the public side: my children were registered first so the Sint's round
could be planned, and I filled in the rest a week before"). Above the
questions, on the member's page and on the board's alike, one explicit
choice: *"Vragen: ○ nu invullen ○ later, via de link in de bevestigingsmail"*.
"Nu": the form's fields appear (Alpine toggle) and the post is validated by
`build_answers`, required fields included, refused the same way for
everyone. "Later": no answers are posted, the registration gets the token
and the confirmation mail carries the link. Completely or not at all — no
half-filled form, no lenient channel. An explicit choice rather than "all
blank means later", because a form may consist of optional fields only, and
an empty post would then be ambiguous. **Default:** "nu" on the member's
page (the questions are why the form is there), "later" on the board's (the
board rarely knows the answers) — a default, not a rule; the fields and the
validation are identical. *(Koen to confirm the two defaults, Q16.)* The
thank-you page after a "later" registration repeats the link, so a member
who changes their mind answers at once. "Link opnieuw sturen" on the detail
sends the same mail with the subject "Herinnering: de vragen voor
<activity>" and without the payment block once that is settled.

### B4.9 Parity: what the public keeps (R11)

Measured on `master` (29 Sep): the public modal (`_inschrijf_form.html` in
the card overlay of `_activiteiten_cards.html`) and the board page
(`admin_inschrijving_nieuw.html`) already share the field block
`_inschrijf_velden.html`, the context builder and the processing (#1284), so
the fields, the counters, the live total and the payment choice are one
already. What differs is the frame around them. Every row below is a
function the public has **today**; the last column says where it lives on
the one page. The build walks this list (AC9); a row that cannot be kept
goes back to Koen before the build, not after.

| # | The public has today | Where | On the one page |
|---|---|---|---|
| P1 | The form names the activity and its date above the fields (#996 F22) | modal header | the page header: activity · date · component, the board page's `page_header` |
| P2 | Name, e-mail, mobile prefilled for a signed-in member (#476) | `_prefill` | unchanged — the field block reads `person` from the session on the public channel |
| P3 | Member price for the signed-in person, never for a typed address (security note in `registration_form.py`) | context builder | unchanged — the public channel has no `prijzen_url`; the board's keeps it |
| P4 | Product rows with − / + counters (#1171), only publicly bookable products (#1191) | `_inschrijf_prijsblok.html` | unchanged |
| P5 | The total recomputed server-side on every change (§19.3, #607) | `/…/totaal`, `_inschrijf_totaal.html` | unchanged |
| P6 | Payment choice with its one-line consequence under each option (#996 F21); hidden when nothing is payable (#607) | field block | unchanged |
| P7 | A refusal re-renders the form with the values kept and the banner on top | `ui.error_banner`, `values` | unchanged; on a page the banner is at the top of the form and the refused question is scrolled into view (a page can do that, a modal could not) |
| P8 | After a free or transfer registration: the thank-you banner "je krijgt een bevestiging per e-mail" (#606) | `_inschrijf_klaar.html` | a thank-you **page** with the same text and a link back to the activity's component |
| P9 | After an online registration: "je wordt doorgestuurd" and the hard redirect to Mollie (`HX-Redirect`) | `_inschrijf_klaar.html`, ui.py | unchanged: the redirect is the response of the submit |
| P10 | "Wie doet er mee?" on the card refreshes in place after a free registration (#1159) | `hx-swap-oob` | on return to the activity (P8's link lands on the component's card with the list open and fresh); the in-place swap goes — that is the one visible difference, named here |
| P11 | The button on the card is the only way in; Volzet, closed, past date and an external URL hide it (#451, #974) | `_activiteiten_cards.html` | unchanged: the card decides; the button becomes a link to the page; the page itself refuses a closed or full component with the same messages as the service does today |
| P12 | Close with ×, Escape or a click outside; the sheet scrolls within 90 vh (#601) | the overlay | the browser's back button and the "‹ Terug" link; a page scrolls |
| P13 | Rate limit on the public submit (`registration_limiter`) | ui.py | unchanged |
| P14 | A component switch: **the board has it** (buttons for the activity's components), the public does not | board page | the public page gets it too when the activity has more than one component — the one thing the public *gains* from the board's page |
| P15 | Compact, phone-first: the modal was a full-width sheet at 390 px | overlay `max-w-md` | the page's form column keeps `max-w-xl` on desktop (the board page's width) and full width on a phone |

What the board page has that the public page must **not** get: the CSRF
hidden field is the admin's (the public form has its own guard), the
back-office-only products with their badge (P4), the price refresh on the
typed address (P3), the "‹ Inschrijvingen" link into the admin. Those are the `Channel`
differences `registration_form.py` already carries; this CR adds nothing to
that list — the questions and their now-or-later choice are on both pages.

**How the fields render in the two shells — no exceptions.** One partial,
`_inschrijf_velden.html`, includes the form's fields through `forms`' own
`_formulier_veld.html` with their `required` attributes as the builder set
them; the public page includes the partial in `site_base.html`, the board
page includes the same partial in `admin_base.html`. The shell differs, the
block does not. Server side one function validates the answers, called on
both channels whenever answers are posted; since 29 September the choice is
on both pages, so the channels differ in nothing about the questions at
all — only in the default of the choice.

### B4.6 What the form builder shows

The form's submissions view (`/admin/formulieren/{id}/inzendingen`) lists
the attached submissions like any other, with one extra cell "inschrijving
#N" linking to the registration. The form's results view (counts per
option) works unchanged — that is a free win: "how many chose vegetarian".

## B5. Data model

### B5.1 Entity-relationship diagram

```mermaid
erDiagram
  ACTIVITY ||--o{ COMPONENT : has
  COMPONENT }o--o| FORM : "asks (form_id, nullable)"
  COMPONENT ||--o{ REGISTRATION : receives
  REGISTRATION ||--o| FORM_SUBMISSION : "answered (form_submission_id, nullable, unique)"
  FORM ||--o{ FORM_FIELD : defines
  FORM ||--o{ FORM_SUBMISSION : collects
  FORM_SUBMISSION ||--o{ FORM_SUBMISSION_ANSWER : holds
  FORM_FIELD ||--o{ FORM_SUBMISSION_ANSWER : "answered by"
```

### B5.2 Tables

| Table | Change | Validation |
|---|---|---|
| `activities.activity_sub_registrations` | `form_id INTEGER NULL REFERENCES form.forms(id) ON DELETE SET NULL` | attach rule in the service (open, tenant, one section); nothing at rest beyond the FK |
| `activities.registrations` | `form_submission_id INTEGER NULL REFERENCES form.form_submissions(id) ON DELETE RESTRICT`, `UNIQUE` (partial, `WHERE deleted_at IS NULL`, the B4.2 pattern of CR-13); `answer_token VARCHAR(64) NULL UNIQUE` | `Registration.check()`: a linked submission belongs to the component's form; `CHECK (form_submission_id IS NULL OR answer_token IS NULL)` — answered and still open cannot both be true |
| `form.*` | unchanged | the forms rules as today |

Migration: one, `alembic revision -m "component form, registration submission and answer token"`,
additive (`ADDITIVE = True`); no data step. Check the CHECK constraints on
both tables before writing it (the `CLAUDE.md` lesson): none on these columns.

## B6. Privacy and security — the mechanics

Answers are stored in `form.form_submission_answers`, seen through the
admin only (`require_admin_ui` on the detail and export), never rendered on
the public participant list or in the "Wie doet er mee?" line. They ride
the registration's audit history? No — the submission has no history table
today, and an answer edited by the organiser (R7, Could) would need one;
that is why R7 is Could. Nothing leaves the system except in the
confirmation mail (R6, Could) to the registrant's own address. The export
already carries personal data and stays behind the same login.

## B7. Phasing

One phase; it is one feature. Ships after CR-13 phase 1 is on `master`
(the `Registration` aggregate with `check()`, `Money`, the one
`create_registration`), so the "component with a form needs a submission"
rule has its home from day one.

| Phase | Delivers | Depends on | Migration | Env vars | Failure paths that change (R13-style) | Manual validation |
|---|---|---|---|---|---|---|
| 1 | the two links and the token, the picker with its refusals (F2, F13), the fields in the public screen and the API, the board form unchanged plus the answer link and page (B4.8), the admin detail and export | CR-13 phase 1 on `master` | one, additive | none | a registration refused on a question is not saved (new refusal); a Mollie failure now also rolls back the submission; a "later" registration, public or board, sends the confirmation with the answer link where today it sends the plain confirmation | AC1–AC6 on HDEV |
| 1b | R6 mail with the answers, R7 edit on the registration detail with history | 1 | none | none | an empty required answer is refused on edit (new refusal) | AC7, AC8 on HDEV |

## B8. Tests

Each able to go red:

1. **Three entrances, one rule.** Public page, board page and JSON API each
   post "now" with a required question left empty → refused with the
   question's label in the message; the registrations table is unchanged
   (count before = after). Each posts "later" → saved, `form_submission_id`
   NULL, `answer_token` set, one mail with the link.
1b. **The link, once.** GET the page with the token → the fields; POST valid
   answers → submission linked, token cleared; POST again or GET again →
   "al ingevuld", no second submission; a wrong token → 404, nothing
   revealed.
2. **One transaction.** Stub provider set to fail → after the 502 there is
   no registration *and no submission* for that component.
3. **The link is right.** After a registration, `registration.form_submission`
   is the submission whose `form_id` is the component's form, and its
   submitter matches the contact.
4. **Attach rules by violation.** Attaching a closed form, another tenant's
   form, a two-section form → each refused with its own message; an open
   one-section form → attached.
5. **Export columns.** A form with three fields → the export sheet has three
   extra columns after *Opmerkingen*, headers = labels, in field order; a
   checkbox answer joined with ", ".
6. **Detached object.** `Registration.check()` on an in-memory registration
   whose submission belongs to another form → refused; the component's form
   → passes; no submission → passes (the board case); no session (CR-13
   test 5).
7. **Replace refused, detach allowed.** A component with one answered
   registration: attaching another form → refused with the message; detaching
   → allowed, the submission still there (F13).
9. **Edit re-validates and records.** Editing an answer to empty on a
   required field → refused; to a valid value → the answer rows replaced, one
   `RegistrationHistory` row with old and new (F12).
8. **Screen at 390 px** (CR-13's merge-gate eye): the questions render in
   order, each label once, nothing clipped — measured from the DOM.
10. **Parity, mechanically where it can be.** For P2–P7, P9, P11 and P13 the
   existing tests of #1284 and #1159's neighbours must pass on the page
   unchanged (same field names, same routes, same totals); P8 and P10 get a
   new e2e step (register free → thank-you page → back on the component with
   the list showing the new name); P1, P12, P14, P15 are the eye, on the two
   screenshots of AC9.

## B9. Rule and gatekeeper

1. **The rule.** *Anything the portal asks a member beyond the fixed fields
   of a registration is a form of the form builder, linked from the
   registration — never a new column on the registration, never a JSON
   column.* Home: `docs/code-style.md` (one line under "where a rule
   belongs") and this CR.
2. **Reach and baseline.** `activities.registrations` and its schema
   objects. Baseline today: 0 ad-hoc question columns (`remarks` and
   `team_name` are fixed fields of every registration, not questions) and 0
   JSON columns on the table.
3. **The gate.** Hard, small: a pytest in `backend/tests/` asserts that
   `Registration.__table__` has no JSON column and that its column set equals
   a frozen list in the test — adding a column means editing the list in the
   same commit, which is the review moment the rule needs. Proven by
   violation: add `t_shirt_size = Column(String)` → red with "a question is
   a form field (CR-14 B9)". The cross-domain mechanics are already gated by
   CR-13 (*no foreign writes*, *one transaction*, the import gate).

## B10. Prototype findings

None yet. To measure before build: how `_formulier_veld.html` renders inside
`_inschrijf_velden.html` on the registration page at 390 px for each of the
ten field types (one screenshot per type), and whether `build_answers` can run on a flushed but
uncommitted form submission (it reads the form definition, so it should).

## B11. Decisions log

| Date | Decision | By |
|---|---|---|
| 29 Sep 2026 | A registration can carry extra questions; they are a form attached to a component and answered in one movement while registering. | Koen (spoken brief; Part A to confirm) |
| 29 Sep 2026 | The Sint time slots are a preference (checkbox), not a booking with capacity — a person plans afterwards. A component with a form hides the registration's fixed remarks box. | Koen |
| 29 Sep 2026 | Questions in the registration screen, before the payment. The board form asks none; the member gets a link to answer afterwards. A component cannot replace its form once answers exist. The confirmation mail lists the answers; the organiser can correct an answer on the registration detail. The form's own public URL stays usable. One presentation, with or without a form: **a page**, the same page for the member and the board; the order is contact, products, questions, payment method. | Koen |
| 29 Sep 2026 | One screen for member and board, the board's page as the ideal; the public loses nothing — parity list B4.9, walked on HDEV (AC9). | Koen |
| 29 Sep 2026 | The board fills the questions in completely or not at all — one explicit choice, no board-only leniency in validation; "not at all" sends the member the link. **Extended the same day to the member:** the public page has the same choice, now or later via the link. | Koen |

## Q&A log

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 29 Sep 2026 | Which activity triggers this, and what are its questions? (Claude) | Koen, 29 Sep: the Sint activity — a multi-select of time slots, inside/outside, a story about the children, allergies, remarks. A1, A4. |
| Q8 | 29 Sep 2026 | Do the Sint time slots have a capacity (so many visits per slot)? (Claude) | Koen, 29 Sep: no — a person plans the visits afterwards. A checkbox question it is. |
| Q9 | 29 Sep 2026 | The form's "remarks" and the registration's own *Opmerkingen* box: keep both on one screen? (Claude) | Koen, 29 Sep: the proposal — a component with a form hides the registration's box; the form's remarks are the one place. F3. |
| Q2 | 29 Sep 2026 | Are the questions asked in the registration screen (before payment), or on a page after it? (Claude) | Koen, 29 Sep: in the registration, before the payment. B1. |
| Q11 | 29 Sep 2026 | Is the board registration's mail the same as the member's, given the form is not filled yet — unless the board fills it? (Koen) | One mail with one variable block (answers, or the link, or nothing); the resend is the same mail with a reminder subject. B4.8. Koen, 29 Sep, on the board's part: **completely or not at all** — no board-only leniency; the CR makes it one explicit choice on the board page (default: the member answers by link), same validation when the board fills it in. |
| Q15 | 29 Sep 2026 | Give the public user the same choice as the board — answer now or later through the link? (Koen, from his own Sint years: registered first, answered a week before) | Yes: one choice on both pages, "nu invullen / later via de link"; the API says it by sending `answers` or not; the thank-you page repeats the link. R2, R4, R5, F3, F6, F7, B4.8, B8 test 1. No channel difference about the questions remains. |
| Q16 | 29 Sep 2026 | The default of the choice: "nu" for the member, "later" for the board? (Claude) | *proposed* — a default, not a rule; *open* |
| Q14 | 29 Sep 2026 | One screen for back office and public, built from the internal form as the ideal — but check that the public loses no function or nicety. (Koen) | Measured: both already share the field block, context and processing (#1284); the frame differs. B4.9 lists the fifteen things the public has today and where each lives on the page; one visible difference (P10, the in-place participant refresh becomes a refresh on return) and one gain (P14, the component switch). R11, AC9, test 10. |
| Q13 | 29 Sep 2026 | How do the questions render in the admin shell and the public shell, without exceptions for the board? (Koen) | One partial (`_inschrijf_velden.html` → `forms`' `_formulier_veld.html`, `required` as the builder set it) included in two shells; one validation function on both channels; the board's only extra input is the choice. B4.8. |
| Q10 | 29 Sep 2026 | "Why not define and store them with the existing form engine?" (Koen) | That is the proposal, exactly: defined in the form builder, stored in `form.form_submissions` / `form_submission_answers`, validated by `build_answers`, read back by `submission_view`. What is *new* is only the two links (component → form, registration → submission) and the rendering of the form's fields inside the registration screen, so the answers ride the registration's transaction and its payment. B1. |
| Q3 | 29 Sep 2026 | A component with a form: still the narrow modal, or a full page? (Claude) | Koen, 29 Sep: one way for both — first leaning modal, then, after the honest pros and cons (a dialog is for a short task), **a page**, and the same page for the board. B4.1; the fixed UI decision in `CLAUDE.md` to be revised by Koen. |
| Q12 | 29 Sep 2026 | Why would the questions come at the start, before choosing and paying? (Koen) | They do not: the order is contact → products → questions → payment method → Mollie. "Before the payment step" means before the redirect to Mollie. Made explicit in A3 step 3, F3 and B4.1. |
| Q4 | 29 Sep 2026 | Must the board answer the questions on the board form? (Claude) | Koen, 29 Sep: no — "dan sturen we een link dat ze het formulier nog moeten invullen". R5 Must: an answer link by mail, the answers land on the registration; B4.8, F7, AC4, B4.2. |
| Q5 | 29 Sep 2026 | May a component swap its form once registrations have answers? (Claude) | Koen, 29 Sep: no. R10, F13, B4.5. |
| Q6 | 29 Sep 2026 | Repeat the answers in the confirmation mail (R6)? Let the organiser correct an answer (R7)? (Claude) | Koen, 29 Sep: yes to both (Should), with the question "how does it work when the form may be changed afterwards?" — answered in B4.7: an *answer* is edited on the registration detail, re-validated, with a history row; the *form* cannot change once it has answers (#665). |
| Q7 | 29 Sep 2026 | Does the attached form's own public URL stay usable? (Claude) | Koen, 29 Sep: yes. R8 Should; such a submission has no registration and the form's submissions view shows it so. F9. |

## Non-goals

- Questions per product or per ticket (R9) — a different shape.
- Sections and branching inside a registration (#336) — a one-section form only; a longer questionnaire stays a standalone form.
- Answers in the reporting engine (CR-06) — the export covers it.
- A new field type (date, file upload) — the form builder's list is what it is; a new type is a forms change.
- Editing answers by the member after registering — the form builder's edit link exists for standalone forms; not wired to a registration here (the organiser edits, R7).

## Relationship to existing work

- **CR-03 (form types):** the six registration form types this idea replaces in spirit — v2.0 removed them; this CR is the attachable form instead of fixed types.
- **CR-13:** the placement rule, *no foreign writes*, the one transaction in `create_registration`, `Registration.check()` — this CR builds on phase 1.
- **CR-12:** no new code list.
- **#1192 / #1284:** the one `create_registration` and the board form that this CR extends.
- **#336, #337, #665:** sections, "Andere…", and the no-change-after-submissions rule in the form builder.
- **#94 phase 4:** `ON DELETE` per FK — the two FKs here are decided in B2.4.
