# Change Request 12 — Codes, enums and labels

> Supersedes the text of #779 (codes en enums), which is shortened to a pointer
> here. First change request written against the template with **B9 Rule and
> gatekeeper** (25 September 2026): it fixes a way of doing things for every
> module that exists and every module that follows.

**Project:** Web Portal "Raak Millegem"
**Status:** shaped with Koen on 25 September 2026 · Part B development-ready pending Koen's correction of Part A and Q6/Q7 · not assigned to a release
**Applies to:** every column that carries a fixed vocabulary (status, type,
kind, method, role, …) in every domain schema; the code tables in `mdm`; the
label dictionaries in the UI layer; `app/kernel`.

---

# Part A — The business

> Draft from Koen's words of 25 September 2026, transcribed from speech. **To be
> corrected by Koen** — the analyst did not add requirements, only ordered what
> was said.

## A1. Reason to act

Two things come together. First, the platform is about to get new modules — a
mini CRM and a sales module for Koen's own company in formation, and a public
website that has to win customers rather than inform members. Before those are
built, the foundations they will stand on have to be right, so that they are
built the right way from day one instead of being reworked later. Second, the
codebase is fully English while the customers are Dutch-speaking, and soon
more than one language will be needed. Today a status is three things in
three wrong places: a loose string in the code, a comment next to the
column, and half a dozen little dictionaries that translate it — not always
the same way.

In Koen's words: *"Als ik het goed begrepen heb, gebruiken we in de code
enumeraties — dat is de best mogelijke manier om in de code bepaalde zaken af
te dwingen. En voor elke enumeratie moet er ook een code bestaan die in eerste
instantie in het Nederlands vertaald kan worden. De codebase is volledig
Engels, de enumeraties zijn Engels, maar de klanten zijn Nederlandstalig. Elke
code heeft een Engelse waarde en een Nederlandse waarde. En dan trekken we dat
door over alle schema's."*

And on why this is a change request and not an issue: *"Belangrijk om altijd
mee te denken of we een gatekeeper kunnen opzetten die de afspraak vastlegt,
zodat ze voor toekomstige ontwikkelingen automatisch gehandhaafd wordt. In
deze change request trekken we het door in alle modules, de hele codebase, en
vanaf dan is er een gatekeeper: komt er een nieuwe module, dan worden de
stappen 1, 2, 3, 4, 5, 6 automatisch afgedwongen."*

## A2. As-is process

There is no process — that is the finding. When a developer adds a status
today, they pick a word, write it in a comment next to the column, compare
against it as a string wherever the code branches, and add a Dutch text to
whichever screen shows it. Nothing checks that the word in the database, the
word in the code and the word on the screen are the same. Measured on 25
September 2026 (the full inventory is in B9.2):

- about 35 lists with a fixed vocabulary, kept in four different ways;
- 40 label dictionaries in Python and 25 templates that branch on a literal;
- `pending` shown as "In afwachting" in the list and "Openstaand" on the
  badge, sixteen lines apart (#779);
- the same payment-method list spelled `ONLINE` in one domain and `online` in
  another;
- three code tables that exist since the first migration and are used by
  nothing.

## A3. To-be process

A status is three things, each in one place: the **code** in a code table in
the database, the **enum** in the code where the code branches on it, and the
**label** per language in a label table. Whoever needs a label asks for it in
one place. A new language is a row, not a deploy. A developer who adds a list
or a value and forgets one of the three is told so by the build, with the name
of the missing piece.

Managing the lists and their translations through a screen is **not** part of
this change (Koen, 25 September 2026: *"nu maar geen scherm voorzien om
codelijsten te beheren, dat kan later"*). Until then, codes and labels are
added by migration.

## A4. Supplied material

None beyond the codebase itself and issue #779, which held the earlier design
(9 September 2026). Its measurements were redone on the branch — see B9.2.

## A5. Business requirements

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | Every fixed vocabulary in the system exists as a list of codes in the database, and the database refuses a value that is not in the list. | Must | Koen, 25 Sep 2026 | the check is in the data, not only in the code |
| R2 | Every code has a readable label per language; Dutch first, English second; a further language is rows added, not a change to the structure. | Must | Koen, 25 Sep 2026 | "elke code heeft een Engelse waarde en een Nederlandse waarde" |
| R3 | Where the application's behaviour depends on a value, the code uses an enumeration, so the tooling catches a wrong or misspelled value before it runs. | Must | Koen, 25 Sep 2026 | "de best mogelijke manier om in de code zaken af te dwingen" |
| R4 | The three — code list, enumeration, labels — can never drift apart; a build that misses one fails and names it. | Must | Koen, 25 Sep 2026 | the gatekeeper |
| R5 | The rule applies to the whole codebase, every module, existing and future. | Must | Koen, 25 Sep 2026 | "doortrekken in alle modules" |
| R6 | A list that belongs to one domain lives in that domain; a list that is master data, or is used by more than one domain, lives in master data — except security vocabulary (roles), which stays with security. | Must | Koen, 25 Sep 2026 | "als het niet single-domein is: masterdata"; roles: "zit dit niet in een security-domein waar we later Keycloak, SAML kunnen aan koppelen?" |
| R7 | A screen to manage code lists and translations without a deploy. | Won't | Koen, 25 Sep 2026 | "dat kan later" — the structure allows it; see Non-goals |
| R8 | Stored values do not change meaning or spelling; history and exports read as before. | Must | #779 | one exception proposed in B4.6 |

## A6. Non-functional requirements

| Concern | This change |
|---|---|
| **Reporting** — what must be countable afterwards, by whom | The report dimensions of CR-06 (payment method, status, membership status) take code and label from the code tables; the same words appear in reports as on screens. Countable per release: the B9.2 numbers, which may only fall. |
| **Security** — who may do what; new inputs from outside; secrets | No new inputs: codes and labels enter by migration only. Roles are one of the lists and stay in `auth` — security vocabulary is not master data; their *meaning* (which role may do what) stays in `auth` and `docs/rollen-en-rechten.md`, untouched. |
| **Privacy** — personal data | None. Code lists hold no personal data. |
| **House style / UI norm** | `docs/design-system.md` §2.5 already says "labels come from one place per code list, never from a dict in a screen (#779)"; this change makes it true. Badge tones stay a UI decision (B4.5). |
| **Multi-tenant** — what differs per unit, what is platform-wide | Code lists and labels are **platform-wide**; the *language* a tenant sees is the tenant's language setting (`language`, default `nl_BE`), which already exists. A tenant does not get its own codes. |

## A7. Acceptance criteria

| # | Criterion | Requirement |
|---|---|---|
| AC1 | On HDEV, inserting a payment record with status `payed` through the database is refused by the database. | R1 |
| AC2 | Switching a tenant's language setting to `en` shows English labels for every status, type and method badge, list and export; switching back shows Dutch. No screen shows a raw code. | R2 |
| AC3 | The payment screens, the exports and the report dimensions show the same word for the same status (no "In afwachting" versus "Openstaand" for one code). | R2, R4 |
| AC4 | A developer who adds an enum member without a code row, or a code row without a label, gets a red build that names the missing member, row or language. | R4 |
| AC5 | The release issue shows the B9.2 counts, and every one of them is lower than or equal to the previous release. | R5 |
| AC6 | Every payment record, registration and history row on HDEV reads with the same value as before the migration (checked by a before/after count per value). | R8 |

---

# Part B — The solution

## B1. Solution outline

One shape for every list, in three places with one job each: a **code
table** (`<schema>.<list>_codes`) that says which values exist and is the
target of a foreign key from every column that stores the value; a **label
table** (`<schema>.<list>_labels`) keyed on `(code, language)` that carries
the human text; and, only where Python branches on the value, a plain
**`Enum`** whose members are checked against the active codes by a test. One
function in the kernel returns the label for a code in the active language,
and one Jinja filter exposes it; the label dictionaries disappear. Placement
follows Koen's rule (R6): one domain → that domain's schema; master data or
more than one domain → `mdm`. Gates enforce the shape as **ratchets** while the
inventory is being migrated and become **hard gates** once each count is zero.

Decisions that shape it, with the alternatives that lost:

- **Code table + FK, not a Postgres `ENUM` type.** A native enum makes every
  new value an `ALTER TYPE` and cannot carry labels. Lost on both counts.
- **Two tables per list, not one.** The tables of migration 001 keep code and
  language in one row with `UNIQUE(code)`, so exactly one language fits. The
  split is what R2 needs. The #924 lists (`organization_relation_types`,
  `identification_schemes`) already have this shape; it is generalised, not
  invented.
- **Plain `Enum`, not `str, Enum`.** With a `str` subclass, `status == "paid"`
  stays a valid comparison for mypy and there is no gate; with a plain `Enum`,
  `strict_equality` flags every comparison against a loose string. The two
  existing `str, Enum` classes (`LegalForm`, `RegistrationState`) convert when
  their domain is migrated.
- **Labels in the database, not in the gettext catalogue.** `app/i18n.py`
  (`_()`) stays for *sentences* — screen copy, messages. A label of a code is
  *data about a code*: it belongs next to the code, is queryable (reports,
  CR-06), and a new language is a row for a translator, not a `.po` file for a
  developer. The boundary: **codes → label table; everything else → `_()`**.
- **Placement by Koen's rule, with one named exception to §8.** See B4.1.
- **No management screen now** (R7). The tables are designed so that one can
  be added without changing them.

Europe First: no new tool, library or service. Everything is SQLAlchemy,
Alembic, mypy and pytest, already in use.

### B1.1 Functional analysis

| # | Derived requirement | Traces to |
|---|---|---|
| F1 | One kernel module defines the shape (`CodeList`) and the label function; domains declare their lists against it. | R4, R5 |
| F2 | Every list has a code table with `code`, `sort_order`, `is_active`; retiring a value is `is_active = false`, never a delete, so history rows keep their FK target. | R1, R8 |
| F3 | Every list has a label table `(code, language, value, description)`; `nl` is mandatory for every active code, `en` is seeded for every list in this change. | R2 |
| F4 | Every mapped column that stores a list value carries a FK to the code table. History (`*_history`) tables are exempt: append-only snapshots must survive a retired code. | R1, R8 |
| F5 | A list on which Python branches has a plain `Enum`; a test asserts members == active codes after `alembic upgrade head`. | R3, R4 |
| F6 | A single `label(list, code)` function, cached per process, using the request's `current_locale`; a Jinja filter of the same name. | R2, R4 |
| F7 | Templates never compare a code to a literal; the view-model exposes what the template needs (label, tone, a boolean). | R4 |
| F8 | Language keys in the label table are language codes (`nl`, `en`), not locales (`nl_BE`); the lookup takes the language part of the active locale. | R2 |
| F9 | Ratchet gates for each count in B9.2, hard gates once zero. | R4, R5 |
| F10 | mypy `strict_equality` and `disallow_untyped_defs` per migrated domain, via `[[tool.mypy.overrides]]`. | R3 |

## B2. Architecture

### B2.1 Components

| Component | new / used / changed | Role in this change |
|---|---|---|
| `app/kernel/codes.py` | **new** | `CodeList` declaration, `label()` function, cache, Jinja filter, the mypy-friendly `EnumColumn` type decorator |
| `app/kernel/tenant_config.py` (`language`) | used | source of the active language; already feeds `current_locale` |
| `app/i18n.py` | used, unchanged | keeps `_()` for copy; the label filter is registered next to it |
| `mdm` (`models.py`, migrations) | **changed** | its three single-language code tables split into codes + labels; `legal_form` gets its FK; receives the cross-domain lists (payment method, languages) |
| `auth` (`models.py`, migrations) | **changed** | `role_codes` moves in from `public`, split into codes + labels; FKs from `user_roles` and `workflow`; the role enum |
| `payment` | **changed** | first domain migrated: three lists, three enums, 37 comparisons, exports and badges through `label()` |
| `newsletter`, `meetings`, `designstudio` | **changed** | module constants become code tables + enums |
| `workflow`, `forms`, `mail`, `media`, `chatbot`, `activities`, `auth`, `reporting` | **changed** | bare string columns get their list, FK and (where branching) enum |
| `public.payment_status_codes`, `public.role_codes`, `public.registration_type_codes` | **removed** | orphans since migration 001; rows move to their domain, tables dropped |
| `backend/tests/test_codes_gate.py` | **new** | the gates of B9.3 |
| `docs/code-style.md` | **changed** | the rule, one paragraph, pointing here |

### B2.2 Application usage

*ArchiMate application-usage view: the to-be steps of A3 on the left, what
serves them on the right.*

```mermaid
flowchart LR
  subgraph Business["A3 — to-be steps"]
    S1["A value is stored"]
    S2["The code decides on a value"]
    S3["A person reads the value"]
    S4["A developer adds a value or a list"]
    S5["A language is added"]
  end
  subgraph Application
    T1["code table + FK<br/>(<schema>.<list>_codes)"]
    T2["Enum in the owning domain"]
    T3["label() in the kernel<br/>+ label table"]
    T4["gates (test_codes_gate.py)<br/>+ mypy strict_equality"]
    T5["a migration with label rows"]
  end
  S1 --> T1
  S2 --> T2
  S3 --> T3
  S4 --> T4
  S5 --> T5
```

### B2.3 Application structure

*ArchiMate application-structure view: what is built where and what talks to
what.*

```mermaid
flowchart TB
  subgraph kernel["app/kernel"]
    K["codes.py<br/>CodeList · label() · EnumColumn · Jinja filter"]
    I["i18n.py<br/>current_locale · _()"]
  end
  subgraph mdm["mdm (master data)"]
    M1["gender · contact_type · relation_type · legal_form<br/>(split into codes + labels)"]
    M2["payment_method · language<br/>(cross-domain lists, new here)"]
  end
  subgraph auth["auth (security)"]
    A1["role<br/>codes + labels + Enum"]
  end
  subgraph payment["payment"]
    P1["payment_status · payment_type<br/>codes + labels"]
    P2["PaymentStatus · PaymentType · PaymentMethod<br/>Enum"]
    P3["payment_records<br/>FK status, type, method"]
  end
  subgraph other["newsletter · meetings · designstudio · workflow · forms · mail · media · chatbot · activities · auth"]
    O["own lists in own schema<br/>same shape"]
  end
  subgraph ui["UI layer (ui.py / admin_ui.py / templates)"]
    U["view-models: label · tone · booleans<br/>templates: {{ code | label('list') }}"]
  end
  G["tests: test_codes_gate.py<br/>Enum = codes · FK coverage · label coverage · ratchets"]

  K --> I
  P1 --> K
  P2 --> K
  P3 -->|FK| P1
  P3 -->|FK, cross-schema by exception| M2
  O --> K
  M1 --> K
  M2 --> K
  A1 --> K
  U --> K
  G -.checks.-> P1
  G -.checks.-> P2
  G -.checks.-> O
  G -.checks.-> U
```

### B2.4 Impact on the existing architecture

- **§8 "no cross-schema FKs"** gets one named exception: a FK from any schema
  **to a code table of a foundation domain** — `mdm`, and `auth` for roles.
  Neither depends on a business domain (`auth` depends on `mdm` only), so no
  cycle can arise; every domain already imports `mdm.api`. Without the exception a list
  in `mdm` would lose its database check, which is the point of R1. Recorded
  in the architecture document §8 when this change is built (B4.1).
- **Import gate** (`tests/test_import_boundaries.py`): domains import
  `app.kernel.codes` (kernel is shared by design) and reach `mdm` enums only
  through `mdm.api`. No domain imports another domain's enum directly.
- **Layer gate** (`test_layer_gate.py`): `ui.py`/`admin_ui.py` do not touch
  `db` — the label cache is loaded in the kernel from a session the kernel
  owns at startup and on demand, not from a UI module.
- **Template-variables gate**: the view-model promises `label`/`tone`
  attributes where templates used to branch on the code.
- **CR-04 placement rule**: "the value is one of a closed list" is a one-field
  rule → the FK is the constraint layer, the enum the meaning layer; nothing
  moves to routers.
- **CR-06 reporting**: dimension labels read the label tables through the
  same function; the CR-06 line "labels come from the code tables (#779)"
  becomes real.

## B3. Cost and operations

- **Settings / env vars:** none new. The tenant `language` setting already
  exists.
- **Migrations:** one per domain phase (B7); each moves rows, adds FKs, drops
  the `public` orphans. Idempotent, as every migration here.
- **Backups:** unchanged; the migrations add small tables.
- **Limits / kill switch:** none needed — the label cache is a few hundred
  rows per process.
- **Cache refresh:** labels change only by migration, so a process-level
  cache loaded on first use is safe; the container restarts on deploy. A
  future management screen must invalidate it (B4.4).
- **External cost:** none.

## B4. Detailed decisions

### B4.1 Placement of a list (Koen, 25 September 2026)

*One domain → that domain's schema. Master data, or used by two or more
domains → `mdm`.* The definition of master data is "cross-domain", so doubt
resolves towards `mdm`. Moving a list later is a migration that copies rows
and re-points a FK; stored values do not change, so a wrong guess is cheap.

Consequence: the one allowed cross-schema FK is *towards an `mdm` code table*
(B2.4). Applied to today's inventory:

| List | Used by | Goes to |
|---|---|---|
| payment method | `activities.payment_method`, `payment.method` | `mdm` |
| role | `auth.role_code`, `workflow.required_role`, tenant config | `auth` — security vocabulary, not master data (see below) |
| language (the `language` key of every label table) | every label table | `mdm` (a two-row list, `nl`, `en`) |
| gender, contact type, relation type, legal form, identification scheme, organisation relation type | `mdm` | `mdm` (already) |
| everything else (payment status/type, newsletter, meetings, design studio, workflow, forms, mail, media, chatbot, activities registration type) | one domain | that domain |

**Refinement (Koen, 25 September 2026): master data describes the world;**
security vocabulary is not master data. Roles — and later permissions,
identity providers, the mapping of an external group to an internal role —
belong to `auth`, the domain that Keycloak or a SAML directory will attach
to. `auth` therefore counts as a second foundation domain: it depends on
`mdm` only, and other domains may FK to its code tables. `public.role_codes`
moves to `auth.role_codes` + `auth.role_labels`, with FKs from
`auth.user_roles.role_code` and `workflow.required_role`; the role enum lives
in `auth` and is exported through `auth.api`.

The MDM domain itself — what else belongs to master data and how it is
governed — is being thought through separately, with an external MDM adviser. This change
does not pre-empt it: it applies the rule to the lists that exist today.

### B4.2 The shape of a list

Per list, two tables and, where the code branches, one enum. Columns are the
same everywhere; the kernel `CodeList` declaration ties them together.

| Table | Columns | Key |
|---|---|---|
| `<schema>.<list>_codes` | `code` · `sort_order` · `is_active` · `created_at` | `code` |
| `<schema>.<list>_labels` | `code` (FK) · `language` (FK → `mdm.language_codes`) · `value` · `description` · `created_at` · `updated_at` | `(code, language)` |

`is_active` retires a value without deleting it: history rows and old
records keep a valid FK target, the enum stops carrying it, and the label
stays readable. `sort_order` is what select lists and report dimensions
order by — the last place where a Python list decided the order.

### B4.3 When an enum, when only a table

The question that decides: **does Python branch on this value?**

- **No** (gender, contact type, relation type, language): code table + FK
  only. A row can be added by migration — later by a screen — without code.
- **Yes** (payment status, charge/refund, payment method, newsletter and
  meeting states, roles): code table + FK **and** a plain `Enum` in the domain
  that owns the table, exported through its `api.py`. A new value needs code
  anyway, so the enum costs nothing extra; the gate keeps it equal to the
  active codes.

The enum stores its `.value` in the column through a `TypeDecorator`
(`EnumColumn`) — never the member name (`PAID`) and never `str(member)`
(`PaymentStatus.PAID`). Test 3 in B8 reads the column raw to prove it.

### B4.4 One label function

`label(list, code)` in `app/kernel/codes.py`: looks up `(code, language)` in
the label table for `list`, with `language` = the language part of
`current_locale` (`nl_BE` → `nl`), falling back to `nl`, and — as a last
resort so a screen never renders blank under `StrictUndefined` — the code
itself, logged once. Cached per process on first use; `reset_label_cache()`
exists for tests and for the future screen.

The same function is a Jinja filter: `{{ record.status | label("payment_status") }}`.
Where two words used to exist for one code ("Betaald" on the badge,
"Vereffend" as the *balance* state — #669), the second word is a **different
concept with its own name** (a derived state on the view-model), not a
second label for the same code. Decided case by case in the migration of
that domain and recorded in the `CodeList` docstring.

### B4.5 Tones and other UI attributes stay in the UI

A badge tone (`green`/`yellow`/`red`) is not a translation; it is a UI
decision that changes with the design system, not with the language. It
stays in Python, **one total mapping per enum next to the enum's UI
consumer**, and the gate checks it is total (every member has a tone). The
code table does not get a `tone` column: that would put a design-system word
into master data, where a translator has no business changing it.

### B4.6 Payment method: one data fix (Koen, 25 September 2026)

`activities.payment_method` stores `ONLINE`/`TRANSFER`/`CASH`;
`payment.method` stores `online`/`transfer`/`cash`. One list, two spellings —
the duplication `CLAUDE.md` names as the bug. R8 says stored values do not
change; here the proposal is the **one exception**: an `UPDATE` that lowers
the case on `activities.payment_method` (and its history table, which is a
snapshot of the same value), with a before/after count per value in the
migration output. The alternative — two code tables for one list — keeps the
bug and gives it a FK. Koen chose the data fix (B11).

### B4.7 Templates show, view-models decide

25 templates branch on a literal (`.status == "paid"`). With a plain enum
those comparisons would silently become `False` — the most dangerous failure
mode of this change, because nothing errors. Therefore the rule from the
design system §8.3 is applied to codes: **a template never compares a
code**. The view-model exposes `status_label`, `status_tone`, `is_paid`
(whatever the template needs). This is a ratchet gate (B9.3) with the 25 as
baseline.

### B4.8 mypy strict, per domain

`[[tool.mypy.overrides]]` per migrated domain with `disallow_untyped_defs`,
`strict_equality`, `warn_return_any`. Not `--strict` globally: that needs an
exemption list, and an exemption list is where a rule dies (#760). The 133
untyped `db` parameters (#779 count; recounted per domain when migrated) are
typed as part of each domain's phase.

### B4.9 The kernel API (what phase 0 builds)

`app/kernel/codes.py`, small enough to read in one sitting. Names are the
contract; the dev CLI chooses the internals.

| Piece | Contract |
|---|---|
| `CodeList` | One declaration per list, in the owning domain's `codes.py` and exported through its `api.py`. Fields: `name` (the list's short name, e.g. `payment_status`), `codes` (the ORM class of the code table), `labels` (the ORM class of the label table), `enum` (the `Enum` class or `None`), `derived` (`True` for a list with no storing column, B5.3 note 4). A registry in the kernel collects every declaration at import time; the gates iterate over the registry. |
| `EnumColumn(enum_cls)` | A `TypeDecorator` over `String` that writes `member.value` and reads the member back. Never the member name, never `str(member)`. Raises on an unknown value **on read** only if the code is inactive *and* not in the table; a retired-but-present code reads back as a plain string so history screens still render. |
| `label(list_name, code, language=None)` | The one label function. `language` defaults to the language part of `current_locale` (`nl_BE` → `nl`); falls back to `nl`; as a last resort returns the code itself and logs once per (list, code). Accepts an `Enum` member or a string. |
| `labels(list_name, language=None)` | The ordered `(code, label)` pairs of the active codes, by `sort_order` — for select lists and report dimensions. |
| `reset_label_cache()` | Clears the process cache; used by tests and by the future screen. |
| Jinja filter `label` | Registered next to `install_jinja_i18n`: `{{ record.status \| label("payment_status") }}`. The *only* way a template turns a code into text. |
| `tone(list_name, code)` | Reads the total tone mapping the owning domain registers with its `CodeList` (B4.5); Jinja filter `tone`. |

The ratchet baselines live in `backend/tests/codes_baseline.py` as frozen
Python sets, one per gate, each entry a `schema.table.column`, a `file:line`
or a `file:name` — the same form as the #780 baseline, so the two gates read
alike. An entry may only be removed.

### B4.10 What is not a code list (Koen, 25 September 2026)

- **An external party's vocabulary.** Mollie's statuses (`open`, `authorized`,
  `expired`, `canceled`, …) on `gateway_payments.status` are Mollie's list:
  Mollie can add a value without our migration, and a FK would make the
  webhook fail on an unknown status at exactly the wrong moment. Therefore
  **no code table, no FK, no label**, but a plain `Enum` in the adapter
  (`providers/mollie.py`) for the statuses the adapter knows, an explicit
  branch for "unknown" (log, leave the record `pending`, never raise), and
  `MOLLIE_STATUS_MAP` typed from that enum to our `PaymentStatus`. The rule
  in B9.1 carries this as its second sentence. `gateway_payments.provider`
  (`mollie`, later `stripe`) is **our** list — which providers we support,
  and the code branches on it — and follows the pattern.
- **Design and brand data with a payload.** The design studio's icons
  (code → SVG path), colour duos (code → two brand colours), paper sizes and
  template keys are brand assets that change with the brand guide, not
  vocabularies a translator maintains. They stay in `brand.py`/`icons.py`.
  The icon picker's Dutch caption is the one label-shaped thing among them;
  it moves to the label table only if the design studio ever ships in
  English (parked, CR-11).
- **Numbers that are not codes.** The 1–5 rating scale of forms
  (`RATING_LABELS`) is a Likert scale, not a vocabulary; it is copy and goes
  through `_()`.
- **Provenance columns** on history and audit tables (`operation`, `action`,
  `source`) are free-form and append-only. `operation` alone
  (`insert`/`update`/`delete`) is a closed list and gets a code+label table
  **without** a FK (history exemption, F4).

## B5. Data model

### B5.1 Entity-relationship diagram

```mermaid
erDiagram
  LANGUAGE_CODES {
    string code PK "nl, en"
    int sort_order
    bool is_active
  }
  PAYMENT_STATUS_CODES {
    string code PK "pending, paid, failed, cancelled"
    int sort_order
    bool is_active
  }
  PAYMENT_STATUS_LABELS {
    string code PK, FK
    string language PK, FK
    string value "Betaald / Paid"
    string description
  }
  PAYMENT_METHOD_CODES {
    string code PK "online, transfer, cash (mdm)"
    int sort_order
    bool is_active
  }
  PAYMENT_METHOD_LABELS {
    string code PK, FK
    string language PK, FK
    string value
  }
  PAYMENT_RECORDS {
    int id PK
    string status FK
    string type FK
    string method FK "cross-schema, to mdm"
  }
  PAYMENT_RECORD_HISTORY {
    int id PK
    string status "no FK - snapshot"
  }
  PAYMENT_STATUS_CODES ||--o{ PAYMENT_STATUS_LABELS : "has label per language"
  LANGUAGE_CODES ||--o{ PAYMENT_STATUS_LABELS : "language"
  PAYMENT_METHOD_CODES ||--o{ PAYMENT_METHOD_LABELS : "has label per language"
  PAYMENT_STATUS_CODES ||--o{ PAYMENT_RECORDS : "status"
  PAYMENT_METHOD_CODES ||--o{ PAYMENT_RECORDS : "method"
  PAYMENT_RECORDS ||--o{ PAYMENT_RECORD_HISTORY : "snapshots"
```

The same pair (`_codes`, `_labels`) repeats for every list in B4.1; the
diagram shows payment because it is phase 1.

### B5.2 Tables

- **New, in `mdm`:** `language_codes` (+ labels), `payment_method_codes` (+
  labels).
- **New, in `auth`:** `role_codes` (+ labels; rows moved from
  `public.role_codes`), FKs from `auth.user_roles.role_code` and
  `workflow.required_role`.
- **Split, in `mdm`:** `gender_codes`, `contact_type_codes`,
  `relation_type_codes`, `legal_form_codes` — each becomes `_codes` +
  `_labels`; `contact_type_codes.is_social_network` (#1160) stays on the code
  table (it is data about the code, not a label). `organizations.legal_form`
  gets its FK.
- **New, in `payment`:** `payment_status_codes` (+ labels; rows moved from
  `public`), `payment_type_codes` (+ labels). FKs on
  `payment_records.status/type/method`. `gateway_payments.status` stays out
  (Mollie's words, B4.10); `.provider` is ours and gets its list.
- **New, per domain, in later phases:** newsletter (subscriber status,
  source, audience, letter status, reply-to, delivery kind/status, role),
  meetings (status, attendance, file kind, section kind), design studio
  (status, layout, variant, generation status, preset, corner, style, duo,
  icon, size), workflow (definition status, run status, kind), forms
  (status, field type), mail (status, type), media (kind), chatbot
  (surface, capability, status), activities (registration type — rows moved
  from `public.registration_type_codes`), reporting (kind).
- **Dropped:** the three `public` orphans, after their rows moved.
- **Untouched:** every `*_history` table (append-only; a value test instead
  of a FK), `operation`/`action`/`source` audit columns (free-form provenance,
  not a closed list).

Validation layers: form → Pydantic schemas keep their `Literal[...]` or take
the enum; meaning → the enum in the service; integrity at rest → the FK.

### B5.3 Catalogue — every list, ready to build

Measured on the branch on 25 September 2026. **Codes are the stored values
today and do not change** (R8; B4.6 is the one exception). Dutch labels are
the ones the screens show today; where two existed, the select-list word
won (#779). **English labels are proposed by the analyst** — Koen corrects
them here, not in a migration. `Enum` names are English, plain `Enum`;
members are the codes upper-cased.

Legend — *FK from:* the storing columns that get the foreign key. *Removes:*
the label dictionaries and constants that disappear. Phase numbers refer to
B7.

#### Phase 0 — kernel

| List | Schema.table | Codes → nl / en | Enum | FK from | Removes |
|---|---|---|---|---|---|
| language | `mdm.language_codes` | `nl` → Nederlands / Dutch · `en` → Engels / English | — | the `language` column of every `_labels` table | — |

#### Phase 1 — payment

| List | Schema.table | Codes → nl / en | Enum | FK from | Removes |
|---|---|---|---|---|---|
| payment status | `payment.payment_status_codes` | `pending` → In afwachting / Pending · `paid` → Betaald / Paid · `failed` → Mislukt / Failed · `cancelled` → Geannuleerd / Cancelled | `PaymentStatus` | `payment.payment_records.status` | `payment/exports.py:_STATUS`, `activities/export.py:_RECORD_STATUS_LABELS`, `reporting/assistant.py:_STATUS_LABEL`, the badge dicts in `payment/admin_ui.py` ("Openstaand"/"Vereffend" → derived balance state, B4.4) |
| payment type | `payment.payment_type_codes` | `charge` → Vordering / Charge · `refund` → Terugbetaling / Refund | `PaymentType` | `payment.payment_records.type` | `payment/exports.py:_TYPE`, `activities/export.py:_RECORD_TYPE_LABELS` |
| payable type | `payment.payable_type_codes` | `registration` → Inschrijving / Registration · `membership` → Lidmaatschap / Membership | `PayableType` | `payment.payment_records.payable_type` | 25 literal comparisons |
| payment provider | `payment.payment_provider_codes` | `mollie` → Mollie / Mollie | `PaymentProvider` | `payment.gateway_payments.provider` | `_get_provider` string branch |
| payment method | `mdm.payment_method_codes` | `online` → Online / Online · `transfer` → Overschrijving / Bank transfer · `cash` → Cash / Cash | `PaymentMethod` (in `mdm`, via `mdm.api`) | `payment.payment_records.method`, `activities.registrations.payment_method` (after B4.6) | `payment/exports.py:_METHOD`, `activities/export.py:_METHOD_LABELS` and `_RECORD_METHOD_LABELS` |

Note 1 — `public.payment_status_codes` is **dropped, not moved**: its rows
are `PENDING`/`PAID`/`FAILED` in upper case, which is not what the column
stores; nothing reads them.

#### Phase 2 — mdm split and auth

| List | Schema.table | Codes → nl / en | Enum | FK from | Removes |
|---|---|---|---|---|---|
| gender | `mdm.gender_codes` (split) | `M` → Man / Male · `F` → Vrouw / Female · `X` → X / X · `U` → Onbekend / Unknown · `O` → Onzijdig / Neutral **(retired, note 2)** | — | `mdm.persons.gender_code` (exists) | — |
| contact type | `mdm.contact_type_codes` (split; `is_social_network` stays on the code table) | `EMAIL` → E-mail / E-mail · `MOBILE` → Mobiel / Mobile · `PHONE` → Telefoon / Phone · `WEBSITE` → Website / Website · `FACEBOOK` → Facebook / Facebook · `INSTAGRAM` → Instagram / Instagram · `TIKTOK` → TikTok / TikTok | `ContactType` (code branches on `EMAIL`/`MOBILE`, note 3) | `mdm.contact_details.contact_type_code` (exists) | 10 literal comparisons |
| relation type | `mdm.relation_type_codes` (split) | `HOOFDLID` → Hoofdlid / Primary member · `PARTNER` → Partner / Partner · `KIND` → (meerderjarig) kind / Adult child | `RelationType` | `mdm.member_persons.relation_type` (exists) | `ui/__init__.py:_RELATIE_LABELS`, 2 template comparisons |
| legal form | `mdm.legal_form_codes` (split) | `VZW` → vzw / Non-profit association · `FEITELIJKE_VERENIGING` → Feitelijke vereniging / Unincorporated association · `BEDRIJF` → Bedrijf / Company | `LegalForm` (from `str, Enum` to plain) | `mdm.organizations.legal_form` (**new**) | — |
| organisation type | `mdm.organization_type_codes` | `ACCOUNT` → Rechtspersoon / Legal entity · `UNIT` → Afdeling / Unit · `PLATFORM` → Platform / Platform | `OrganizationType` | `mdm.organizations.org_type` (**new**) | `ui/organisaties_ui.py:SOORT_LABELS`, 2 template comparisons |
| organisation relation type | `mdm.organization_relation_types` + `_labels` (already the shape) | `BOARD_MEETING` → Bestuursvergadering / Board meeting | — | exists | registers in the `CodeList` registry only |
| identification scheme | `mdm.identification_schemes` + `_labels` (already the shape) | `KBO` → Ondernemingsnummer / Enterprise number · `VAT` → Btw-nummer / VAT number | — | exists | `en` rows added |
| role | `auth.role_codes` + `auth.role_labels` (moved from `public`) | `ADMIN` → Beheerder / Administrator · `FINANCE` → Penningmeester / Treasurer · `OPERATOR` → Platformbeheerder / Platform operator · `ACCOUNT_ADMIN` → Accountbeheerder / Account administrator · `MEMBER`, `USER` **(retired, note 4)** | `Role` (in `auth`, via `auth.api`) | `auth.user_roles.role_code` (**new**), `workflow.workflow_tasks.required_role` (**new**) | the `notin_(["USER", "MEMBER"])` filter in `auth/users.py`; the `HOOFDLID`/`PARTNER`/`KIND` rows that migrations 004/017 wrongly seeded into `role_codes` are dropped (they are relation types) |

Note 2 — gender: migration 001 seeded `O` (nl only), 004 added `X` (en only)
and `U`. Proposal: `X` active with an `nl` label, `O` retired
(`is_active = false`, label kept). **Koen decides** (Q6).

Note 3 — `CLAUDE.md` says `contact_type_code = "mobile"`; the stored codes
are upper case (`MOBILE`). The code compares against both spellings today
(13× `"mobile"`, 9× `"MOBILE"`). The enum ends that: one spelling, the
stored one. `CLAUDE.md` is corrected in the same phase.

Note 4 — `MEMBER` and `USER` exist since migration 001 and are excluded from
every screen (`auth/users.py:216`); no user carries them. Retired, not
deleted.

#### Phase 3 — the constants domains

| List | Schema.table | Codes → nl / en | Enum | FK from | Removes |
|---|---|---|---|---|---|
| subscriber status | `newsletter.subscriber_status_codes` | `pending` → Wacht op bevestiging / Awaiting confirmation · `confirmed` → Bevestigd / Confirmed · `unsubscribed` → Uitgeschreven / Unsubscribed | `SubscriberStatus` | `newsletter.subscribers.status` | `SUBSCRIBER_*` constants, `SUBSCRIBER_LABELS` |
| subscriber source | `newsletter.subscriber_source_codes` | `public_form` → Formulier / Form · `import` → Import / Import · `admin` → Beheer / Admin | `SubscriberSource` | `newsletter.subscribers.source` | `SOURCE_*`, `SOURCE_LABELS` |
| audience | `newsletter.audience_codes` | `members` → Leden / Members · `non_members` → Niet-leden / Non-members · `both` → Allebei / Both | `Audience` | `newsletter.newsletters.audience` | `AUDIENCE_*`, `AUDIENCE_LABELS` |
| letter status | `newsletter.letter_status_codes` | `draft` → Concept / Draft · `sending` → Wordt verstuurd / Sending · `sent` → Verstuurd / Sent | `LetterStatus` | `newsletter.newsletters.status` | `LETTER_*`, `LETTER_STATUS_LABELS` |
| reply-to mode | `newsletter.reply_to_mode_codes` | `association` → Vereniging / Association · `sender` → Afzender / Sender | `ReplyToMode` | `newsletter.newsletters.reply_to` | `REPLY_TO_*` |
| delivery kind | `newsletter.delivery_kind_codes` | `member` → Lid / Member · `subscriber` → Abonnee / Subscriber | `DeliveryKind` | `newsletter.deliveries.kind` | `DELIVERY_MEMBER/SUBSCRIBER` |
| delivery status | `newsletter.delivery_status_codes` | `queued` → In de wachtrij / Queued · `sent` → Verstuurd / Sent · `failed` → Mislukt / Failed · `skipped` → Overgeslagen / Skipped | `DeliveryStatus` | `newsletter.deliveries.status` | `DELIVERY_QUEUED/…`, `DELIVERY_LABELS` |
| message role | `newsletter.message_role_codes` | `author` → Auteur / Author · `raakje` → Raakje / Raakje | `MessageRole` | `newsletter.drafting_messages.role` | `MESSAGE_*` |
| meeting status | `meetings.meeting_status_codes` | `agenda` → Agenda / Agenda · `report` → Verslag (bezig) / Report (in progress) · `sent` → Verslag verstuurd / Report sent | `MeetingStatus` | `meetings.meetings.status` | `STATUS_*`, `STATUS_LABELS`, `STATUS_TONES` → tone mapping |
| section kind | `meetings.section_kind_codes` | `EVALUATION` → Evaluatie voorbije activiteiten / Evaluation of past activities · `UPCOMING` → Volgende activiteiten / Upcoming activities · `MEMBERS` → Leden / Members · `IDEAS` → Programma-ideeën / Programme ideas · `MISC` → Varia / Miscellaneous · `CUSTOM` → Eigen rubriek / Custom section | `SectionKind` | `meetings.meeting_sections.kind` | `SECTION_*`, `SECTION_LABELS`, 6 template comparisons |
| attendance | `meetings.attendance_codes` | `present` → Aanwezig / Present · `excused` → Verontschuldigd / Excused | `Attendance` | `meetings.meeting_attendances.status` | `ATTENDANCE_*` |
| file purpose | `meetings.file_purpose_codes` | `attachment` → Bijlage / Attachment · `sent_pdf` → Verstuurd verslag (pdf) / Sent report (PDF) | `FilePurpose` | `meetings.meeting_files.kind` | `FILE_*` |
| design status | `designstudio.design_status_codes` | `draft` → Ontwerp / Draft · `final` → Definitief / Final | `DesignStatus` | `designstudio.designs.status` | `STATUS_DRAFT/FINAL`, `STATUS_LABELS` |
| layout | `designstudio.layout_codes` | `print_a` → Print (A3/A4) / Print (A3/A4) · `feed_portrait` → Instagram (4:5) / Instagram (4:5) | `Layout` | `designstudio.design_renditions.layout_code` | `LAYOUT_*`, `LAYOUT_LABELS`, `FILE_LAYOUT_LABELS` |
| render variant | `designstudio.render_variant_codes` | `pdf` → PDF / PDF · `png` → PNG / PNG · `jpeg` → JPEG / JPEG · `svg` → SVG / SVG · `svg_edited` → Bewerkte SVG / Edited SVG | `RenderVariant` | `designstudio.design_renditions.variant` | `VARIANT_*` |
| generation status | `designstudio.generation_status_codes` | `requested` → Bezig… / In progress · `fetched` → Klaar / Ready · `picked` → Gekozen / Chosen · `discarded` → Niet gekozen / Not chosen · `refused` → Geweigerd (moderatie) / Refused (moderation) · `failed` → Mislukt / Failed | `GenerationStatus` | `designstudio.image_generations.status` | `GEN_*`, `GENERATION_LABELS` |
| preset | `designstudio.preset_codes` | `eenvoudig`, `beeld`, `tekst` → the three long captions of `PRESET_LABELS` / English equivalents | `Preset` | `designstudio.designs.preset` | `PRESETS`, `PRESET_LABELS` |
| inset corner | `designstudio.inset_corner_codes` | `top_left` → Linksboven / Top left · `top_right` → Rechtsboven / Top right · `bottom_left` → Linksonder / Bottom left · `bottom_right` → Rechtsonder / Bottom right | `InsetCorner` | `designstudio.designs.inset_corner` | `INSET_CORNERS`, `CORNER_LABELS` |
| drawing style | `designstudio.drawing_style_codes` | `lijn` → Lijntekening (zwart-wit) / Line drawing (black and white) · `lijnkleur` → Lijntekening met kleuraccenten / Line drawing with colour accents · `kleur` → Kleurtekening (vlakke kleuren) / Colour drawing (flat colours) | `DrawingStyle` | `designstudio.image_generations.style` | `STYLE_LABELS` |

#### Phase 4 — the remaining domains

| List | Schema.table | Codes → nl / en | Enum | FK from | Removes |
|---|---|---|---|---|---|
| task status | `workflow.task_status_codes` | `open` → Open / Open · `done` → Afgehandeld / Done | `TaskStatus` | `workflow.workflow_tasks.status` | 9 literal comparisons, 8 template comparisons |
| run status | `workflow.run_status_codes` | `running` → Bezig / Running · `done` → Afgerond / Done · `failed` → Mislukt / Failed | `RunStatus` | `workflow.workflow_instances.status` | — |
| task kind | `workflow.task_kind_codes` | `payment.webhook_mismatch` → Betaling: webhook wijkt af / Payment: webhook mismatch · `payment.refund_bevestigen` → Betaling: terugbetaling bevestigen / Payment: confirm refund · `mail.definitief_gefaald` → E-mail: definitief mislukt / E-mail: permanently failed · `kernel.job_gefaald` → Achtergrondtaak mislukt / Background job failed | `TaskKind` | `workflow.workflow_tasks.kind` | `workflow/ui.py:KIND_LABELS`, `CAT_LABELS` (the category is the part before the dot — a derived attribute, not a second list) |
| form status | `forms.form_status_codes` | `draft` → Concept / Draft · `open` → Open / Open · `closed` → Gesloten / Closed | `FormStatus` | `forms.forms.status` | `FORM_STATUSES`, `STATUS_TONES` → tone mapping, 3 template comparisons |
| field type | `forms.field_type_codes` | `text` → Tekst / Text · `textarea` → Tekstvak / Text area · `number` → Getal / Number · `email` → E-mail / E-mail · `select` → Keuzelijst / Dropdown · `radio` → Keuzerondjes / Radio buttons · `checkbox` → Selectievakje / Checkbox · `rating` → Beoordeling / Rating · `info` → Infotekst / Info text · `phone` → Telefoon / Phone | `FieldType` | `forms.form_fields.field_type` (replaces the CHECK of migration 062) | `FIELD_TYPES` |
| mail status | `mail.mail_status_codes` | `sent` → Verstuurd / Sent · `failed` → Mislukt / Failed · `skipped` → Overgeslagen / Skipped | `MailStatus` | `mail.email_log.status` | `mail/ui.py:_STATUS_LABELS` |
| e-mail type | `mail.email_type_codes` | `membership_confirmation` → Lidmaatschap / Membership · `activity_confirmation` → Activiteit / Activity · `idea_ack` → Idee (bevestiging) / Idea (acknowledgement) · `idea_board` → Idee (bestuur) / Idea (board) · `magic_link` → Inloglink / Login link · `member_contact_notice` → Contactbericht / Contact notice · `form_confirmation` → Formulier (bevestiging) / Form (confirmation) · `meeting` → Vergadering / Meeting · `newsletter_confirmation` → Nieuwsbrief (bevestiging) / Newsletter (confirmation) · `other` → Overig / Other | `EmailType` | `mail.email_log.email_type` | `EMAIL_TYPES`, `mail/ui.py:_TYPE_LABELS` |
| asset kind | `media.asset_kind_codes` | `sponsor` → Sponsor / Sponsor · `activity_photo` → Activiteitsfoto / Activity photo · `activity_poster` → Affiche / Poster · `component_info` → Onderdeel-info / Component info · `newsletter_file` → Nieuwsbriefbestand / Newsletter file · `design_image` → Ontwerpbeeld / Design image · `design_render` → Ontwerprender / Design render | `AssetKind` | `media.media_assets.kind` | `STANDAARD_KIND`, `DESIGN_*_KIND`, 9 literal comparisons |
| AI surface | `chatbot.ai_surface_codes` | `public` → Publiek / Public · `admin` → Beheer / Admin · `designstudio` → Ontwerpstudio / Design studio | `AiSurface` | `chatbot.ai_call_log.surface` | `SURFACE_*`, `SURFACE_LABELS` |
| AI capability | `chatbot.ai_capability_codes` | `reporting` → Rapporten / Reports · `newsletter_drafting` → Nieuwsbrief / Newsletter · `ocr` → Documenten lezen / Document reading · `dictation` → Dicteren / Dictation · `translate` → Vertalen / Translation · `image` → Beeld / Image | `AiCapability` | `chatbot.ai_call_log.capability` | `CAPABILITY` constants, `CAPABILITY_LABELS` |
| AI status | `chatbot.ai_status_codes` | `ok` → Gelukt / Succeeded · `blocked` → Tegengehouden / Blocked · `error` → Mislukt / Failed · `moderated` → Geweigerd door de provider / Refused by the provider | `AiStatus` | `chatbot.ai_call_log.status` | `STATUS_LABELS` |
| AI provider | `chatbot.ai_provider_codes` | the providers in use at build time (`mistral`, `bfl`, …) → their names | `AiProvider` | `chatbot.ai_call_log.provider` | `PROVIDER` constants |
| registration type | `activities.registration_type_codes` (moved from `public`) | `INDIVIDUAL` → Individueel / Individual · `FAMILY` → Gezin / Family | — (default only; no branch) | `activities.registrations.registration_type`, `activities.activity_sub_registrations.registration_type_code` (both **new**, §8 no longer blocks: same schema) | the router-side validation comment |
| registration state | `activities.registration_state_codes` (**derived**, note 5) | `open` → Open / Open · `closed` → Afgesloten / Closed · `past` → Voorbij / Past · `cancelled` → Geannuleerd / Cancelled | `RegistrationState` (from `str, Enum` to plain) | none | `activities/service.py:STATUS_LABELS` |
| export kind | `reporting.export_kind_codes` | `report` → Rapport / Report · `dataset` → Dataset / Dataset | `ExportKind` | `reporting.export_log.kind` | — |
| history operation | `audit.operation_codes` (no FK, B4.10) | `insert` → Toegevoegd / Added · `update` → Gewijzigd / Changed · `delete` → Verwijderd / Deleted | `Operation` | none (history exemption) | `audit/changes.py:_OPERATION_LABELS` |

Note 5 — a **derived** state (computed, never stored) is still a list with
labels: it gets a code+label table with no storing column, so its label
comes from `label()` like every other. The enum is the only consumer.

**Count:** 47 lists (1 + 5 + 8 + 19 + 14). The "~35" of B9.2 was the
inventory by column; the catalogue is by list and includes the derived and
the already-shaped ones.

## B6. Privacy and security — the mechanics

Nothing leaves the system. No personal data. Role codes move table but not
meaning: `require_admin_ui`/`require_finance_ui` keep deciding; the role gate
tests (`test_role_model_gates.py`) must stay green through the move, and a
test asserts the set of role codes is unchanged before and after.

## B7. Phasing

Each phase is a release-sized issue, shippable and revertible on its own.

| Phase | Delivers | Depends on |
|---|---|---|
| **0 — kernel + gates as ratchets** | `app/kernel/codes.py`, `mdm.language_codes`, `test_codes_gate.py` with the B9.2 baselines frozen, `docs/code-style.md` paragraph, §8 exception recorded | — |
| **1 — payment** | status/type in `payment`, method in `mdm`, three enums, FKs, 37 comparisons, exports/badges via `label()`, `public.payment_status_codes` dropped, mypy strict on `payment` | 0 |
| **2 — mdm split + roles** | the four `mdm` lists split into codes+labels, `legal_form` FK, `role_codes` to `auth` with FKs from `user_roles` and `workflow`, `_RELATIE_LABELS` and `SOORT_LABELS` gone | 0 |
| **3 — constants domains** | newsletter, meetings, design studio: constants → tables + enums, 20 label dicts gone | 0 |
| **4 — remaining domains** | workflow, forms, mail, media, chatbot, activities, reporting, `org_type`; `public.registration_type_codes` dropped | 0 |
| **5 — close** | every ratchet at zero → hard gate; mypy strict on every migrated domain | 1–4 |

The order after phase 1 is Koen's call; phases 2–4 are independent of each
other.

### B7.1 Per phase: issue and "Na de merge"

Each phase becomes one issue when Koen assigns it to a release (the master
CLI creates it; nothing is created before that). Suggested titles and the
handoff block CI cannot carry:

| Phase | Issue title | Migration | Env vars | Data | Manual validation |
|---|---|---|---|---|---|
| 0 | CR-12 fase 0 — kernel `codes.py`, `mdm.language_codes`, gates als ratchet | one: `language_codes` + labels | none | none | none — gates only |
| 1 | CR-12 fase 1 — betaaldomein: status, type, payable, provider; betaalwijze naar `mdm` | one: five lists, FKs, B4.6 update, drop `public.payment_status_codes` | none | **B4.6**: `activities.registrations.payment_method` and its history lower-cased; count per value before/after in the migration log | AC2, AC3 on the payment screens and both exports; a Mollie test payment on HDEV still lands as `paid` |
| 2 | CR-12 fase 2 — `mdm`-lijsten gesplitst, `legal_form` en `org_type` met FK, rollen naar `auth` | one: splits, moves, new FKs, drop `public.role_codes` | none | gender `O` retired (Q6); `MEMBER`/`USER` retired; wrong role rows dropped | log in as each of the four roles on HDEV; `docs/rollen-en-rechten.md` unchanged |
| 3 | CR-12 fase 3 — nieuwsbrief, vergaderingen, ontwerpstudio: constanten worden codetabellen | one per domain (three) | none | none | one newsletter send, one meeting agenda→report, one design render on HDEV |
| 4 | CR-12 fase 4 — workflow, formulieren, mail, media, chatbot, activiteiten, rapporten | one per domain | none | none | the workflow inbox, a form submission, the AI log screen |
| 5 | CR-12 fase 5 — ratchets dicht, mypy strikt per domein | none | none | none | CI only |

Every phase's issue closes with the B9.2 table re-measured, so the ratchet
lists shrink visibly.

## B8. Tests

Each able to go red; guards proven by violation, the violation noted in the
docstring.

1. **Enum = active codes**, both directions. Add a member without a row: red,
   names the member. Add a row without a member: red, names the code.
2. **The FK holds.** Raw `INSERT` of `status = 'payed'` fails on the
   constraint.
3. **Round trip.** A row written with `PaymentStatus.PAID` reads back raw as
   `paid` — not `PAID`, not `PaymentStatus.PAID`. A pre-migration row reads
   as the member.
4. **One label per code per language.** For every active code, `label()` in
   `nl` and `en` returns exactly one non-empty text; the label table has no
   active code without an `nl` row.
5. **Same words as before.** Snapshot of the label dictionaries at phase 0;
   each domain's phase asserts `label()` returns the same Dutch text the
   dictionary did, except where B4.4 deliberately split a concept (listed in
   the test).
6. **Templates render text.** Every template that shows a code renders the
   label, never `PaymentStatus.PAID` or a bare code — rendered through the
   real view-model, the `StrictUndefined` environment.
7. **Values before/after.** For every migrated column, count per value before
   and after the migration is identical (with B4.6 as the one declared
   exception).
8. **mypy in both directions.** Put one comparison back to a literal in
   `payment/service.py`: `comparison-overlap`. Back: green.
9. **Roles unchanged.** Set of role codes and `test_role_model_gates.py`
   identical across phase 2.
10. The gates of B9.3, each proven by one violation.

## B9. Rule and gatekeeper

### B9.1 The rule

> **A fixed vocabulary is a code table in the schema of the domain that owns
> it — in `mdm` when it is master data or used by more than one domain,
> in `auth` when it is security vocabulary — with
> a foreign key from every column that stores it, a label table per language,
> and a plain `Enum` in the owning domain wherever Python branches on the
> value. Labels come from `label()` and nowhere else; templates never compare
> a code. An external party's vocabulary gets an `Enum` in its adapter and a
> mapping to ours — never a code table: it is not our list.**

Lives in `docs/code-style.md` (one paragraph, pointing here) and in the
architecture document §8 (the `mdm` FK exception). `CLAUDE.md` points to
`docs/code-style.md` and does not repeat it.

### B9.2 Reach and baseline

Reach: the whole backend, every domain, existing and future. Measured on
the branch on 25 September 2026 (the counting commands are in
`test_codes_gate.py`, so the numbers re-appear per release):

| | 25 Sep 2026 | after this CR |
|---|---|---|
| lists with a fixed vocabulary | 47 (B5.3) | 47, all in the same shape |
| … kept as code table + FK, split codes/labels (#924 shape) | 2 | all |
| … kept as code table + FK, one language per code | 4 | 0 |
| … kept as orphan table in `public`, no FK | 3 | 0 |
| … kept as module constants | 14 (newsletter 6, meetings 3, designstudio 5) | 0 |
| … kept as a bare string + comment | ~12 | 0 |
| vocabulary columns without a FK to a code table | 43, rough count (excl. history and audit) | 0 |
| code tables that can carry two languages | 2 | all |
| domain enums | 2 (`str, Enum`) | one per branching list, plain `Enum` |
| label dictionaries in Python | 40 | 0 |
| templates comparing a code to a literal | 25 | 0 |
| loose-string comparisons on vocabulary columns (`.py`) | 92 (payment 37) | 0 |
| domains under mypy `strict_equality` | 0 | all migrated |
| languages seeded | `nl` 34 rows, `en` 17 rows | `nl` and `en` for every active code |

### B9.3 The gate

`backend/tests/test_codes_gate.py`, one test per row above that can be
counted mechanically. Shape per test: **ratchet** while the count is above
zero (a frozen list of today's offenders, checked in; a new offender is red
with its `file:line` or `schema.table.column`; an offender that disappears
from the code must be removed from the list or the test is red — the #780
pattern), **hard gate** once the list is empty (phase 5 deletes the list and
the exemption logic together).

What each gate looks at:

| Gate | Looks at | Message on violation |
|---|---|---|
| FK coverage | every mapped `String` column whose name is in the vocabulary set (`status`, `type`, `kind`, `method`, `role*`, `*_code`, `*_type`, …) on a non-history table without a FK to a `_codes` table | "`payment.payment_records.method` stores a vocabulary but has no FK to a code table — declare a `CodeList` or add it to the ratchet with a reason" |
| Label coverage | every `_codes` table has a `_labels` table; every active code has an `nl` row | "`mdm.gender_codes`: code `X` has no `nl` label" |
| Enum = codes | every `CodeList` with an enum: members == active codes | "`PaymentStatus.REFUNDED` has no row in `payment.payment_status_codes`" |
| Tone total | every enum with a tone mapping: every member has a tone | "`PaymentStatus.FAILED` has no badge tone" |
| No label dicts | `grep` for `LABELS = {` and `_LABEL = {` in `app/` | "`newsletter/admin_ui.py:50` defines labels in Python — use `label()`" |
| No template comparisons | `== "…"` / `!= "…"` on a vocabulary attribute in `templates/` | "`admin_betalingen.html:42` compares `record.status` to a literal — expose it on the view-model" |
| Loose-string comparisons | mypy `strict_equality` per domain (not a pytest) | `comparison-overlap` |

For a new module the gate spells out the steps: a new list needs (1) a
`_codes` table, (2) a `_labels` table with `nl` and `en` rows, (3) a FK from
each storing column, (4) a `CodeList` declaration, (5) an `Enum` if the code
branches, (6) `label()` on every screen and export — and fails on the one
that was forgotten, naming it. That is Koen's "1, 2, 3, 4, 5, 6 automatically".

What cannot be checked mechanically and goes to review: whether a list
really is single-domain (B4.1), and whether two words for one code are one
concept or two (B4.4).

## B10. Prototype findings

None yet. #779 notes an OGM value-object spike with zero DB fixtures as the
testability model; the enum/`TypeDecorator` round trip (B8 test 3) is the
one thing worth a spike before phase 1, because `sa.Enum` stores the member
*name* by default and that mistake would corrupt data silently.

## B11. Decisions log

| Date | Decision | Who |
|---|---|---|
| 25 Sep 2026 | Codes and enums become a change request (CR-12); #779 is shortened to a pointer. | Koen |
| 25 Sep 2026 | The CR template gets **B9 Rule and gatekeeper**; every architectural CR names its rule, baseline and gate. | Koen |
| 25 Sep 2026 | Placement: one domain → that domain; master data or two+ domains → `mdm`. MDM itself is thought through separately, with an external MDM adviser. | Koen |
| 25 Sep 2026 | No management screen for code lists now; later. | Koen |
| 25 Sep 2026 | Labels of codes live in label tables, not in the gettext catalogue; `_()` stays for sentences. The boundary: the name of a code → label table; a sentence on a screen → `_()`. Reasons: a label is data about a code, reports need it in SQL, a new language is rows, not a deploy. | Koen |
| 25 Sep 2026 | One allowed cross-schema FK: towards a code table of a foundation domain — `mdm`, and `auth` for roles (B2.4). Neither depends on a business domain, so no cycle; without the FK a shared list loses its database check. | Koen |
| 25 Sep 2026 | Payment method: one-time lower-casing of `activities.registrations.payment_method` and its history rows, with a count per value before and after; both columns then FK to `mdm.payment_method_codes`. The one exception to R8. | Koen |
| 25 Sep 2026 | Roles stay in `auth`. Master data describes the world (→ `mdm`); security vocabulary — roles, later permissions, identity providers, group-to-role mapping — belongs to `auth`, the domain Keycloak/SAML will attach to. The cross-schema FK exception covers both foundation domains, `mdm` and `auth`. | Koen |
| 25 Sep 2026 | Languages in this CR: `nl` and `en` only. The shape takes any language; `fr` is rows later. | Koen |
| 25 Sep 2026 | Mollie's statuses are not a code list: `Enum` in the adapter, explicit "unknown" branch, mapping to `PaymentStatus`; no table, no FK. `gateway_payments.provider` is ours and follows the pattern (B4.10). | Koen |
| 25 Sep 2026 | Badge tones stay in Python, one total mapping per enum, not a column on the code table: a design-system word does not belong in master data where a translator can change it (B4.5). | Koen |

## Q&A log

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 25 Sep 2026 | Code tables per domain schema or centrally in `mdm`? (Claude) | Koen: by the rule in B4.1 — single domain → domain; master data or cross-domain → `mdm`. |
| Q2 | 25 Sep 2026 | Management screen for code lists in scope? (Claude) | Koen: no, later. |
| Q3 | 25 Sep 2026 | Is the trigger the new company/CRM tenant needing a second language, or the clean-up alone? (Claude) | Both, per A1 — foundations before new modules, and Dutch-speaking customers on an English codebase. *To confirm in A1.* |
| Q4 | 25 Sep 2026 | Are `nl`/`en` the two languages, and is `fr` in scope? (Claude) | Koen: `nl` and `en` only. |
| Q6 | 25 Sep 2026 | Gender: `O` (nl only, migration 001) next to `X` (en only, 004) — keep `X`, retire `O`? (Claude) | *open* |
| Q7 | 25 Sep 2026 | The proposed English labels in B5.3 — any to correct? (Claude) | *open* |
| Q8 | 25 Sep 2026 | Is the CR development-ready? (Koen) | Not until Part A is corrected by Koen and Q6/Q7 are answered; B4.9, B5.3 and B7.1 were added for that purpose (25 Sep). |
| Q5 | 25 Sep 2026 | May `activities.payment_method` be lower-cased once (B4.6)? (Claude) | Koen: yes — the one exception to R8. |

## Non-goals

- **No management screen** for codes or labels (Koen, 25 Sep 2026). The
  tables are shaped so that one can be added later without a schema change:
  it would edit `_labels` rows and toggle `is_active`, and call
  `reset_label_cache()`.
- **No Postgres `ENUM` type.** The code table is the list; the FK is the check.
- **No renaming of stored values**, except the single proposed case in B4.6.
- **No state machine.** Which transitions are allowed between statuses is
  CR-04 phase 2 (#236); this CR only makes the set of states closed and
  database-anchored so that phase can build on it.
- **No per-tenant code lists.** Lists are platform-wide; tenants differ in
  language only.
- **No `--strict` mypy globally.**
- **No translation of screen copy.** `_()` and the gettext catalogue are
  #407-T's track; this CR only draws the boundary (B1).
- **Mollie's statuses** (`gateway_payments.status`) get no table (B4.10);
  `action`/`source` on history tables stay free-form.

## Relationship to existing work

- **#779 (codes en enums)** — the design's first home; shortened to point
  here. Its measurements of 9 September are superseded by B9.2.
- **CR-04 / #236 (OO-domeinmodel)** — the placement rule (one field → the
  constraint/validator layer) is what puts the FK where it is; phase 2 of
  #236 (state machine) builds on the closed status set this CR delivers.
- **#755 (nulmeting)** — the B9.2 counts join the five numbers that appear in
  every release issue.
- **#780 (taalpoort)** — the ratchet shape of the gates.
- **#924 / #945 (organisatie)** — the two lists already in the target shape;
  `LegalForm` is the first enum to convert from `str, Enum`.
- **#1160 (contacttypes)** — `is_social_network` on the code table is the
  precedent for "data about a code lives on the code table".
- **#444** — moved the code tables out of `app/models/codes.py` into their
  domains; this CR moves the three that landed in `public` the rest of the way.
- **CR-06 (reporting)** — dimension labels from the label tables.
- **#669** — "Vereffend" versus "Betaald": one code, two concepts (B4.4).
- **CR-13 (OO foundation, next)** — the second foundation change before the
  CRM module; independent of this one.
