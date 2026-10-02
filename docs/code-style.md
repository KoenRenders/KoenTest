# Code style

What a formatter cannot decide. One screen, and it points elsewhere rather than
repeating what is already written down.

> **Note on this file.** Created by CR-12 phase 0 (26 September 2026) for the
> code-list rule; CR-13 phase 0a (#755) added the rule of a rule's home. Ruff —
> formatter and linter, blocking in CI — came with #781, so what ruff decides is
> not repeated here. #1464 added the rule for copied models.

## A fixed vocabulary is a code table

> A fixed vocabulary is a code table in the schema of the domain that owns it —
> in `mdm` when it is master data or used by more than one domain, in `auth`
> when it is security vocabulary — with a foreign key from every column that
> stores it, a label table per language, and a plain `Enum` in the owning domain
> wherever Python branches on the value. Labels come from `code_label()` and
> nowhere else; templates never compare a code. An external party's vocabulary
> gets an `Enum` in its adapter and a mapping to ours — never a code table: it
> is not our list.

The design and the reasoning are in
[`change_request_12_codes_and_enums.md`](change_request_12_codes_and_enums.md);
this paragraph is the rule, not a summary of the document.

Six steps for a new list, and the gate
(`backend/tests/test_codes_gate.py`) fails on whichever one was forgotten,
naming it: (1) a `_codes` table, (2) a `_labels` table with an `nl` and an `en`
row, (3) a foreign key from each storing column, (4) a `CodeList` declaration in
the domain's `codes.py`, (5) an `Enum` when the code branches, (6)
`code_label()` on every screen and export. The entry points are covered from
both sides, so whichever of the six you start with, the other five are demanded.

Three things that are deliberately *not* code lists: an external party's
vocabulary (Mollie's statuses), design and brand data with a payload (icons,
colour duos), and numbers that are not codes (a 1–5 rating scale is copy, so it
goes through `_()`). An `Enum` that is none of ours carries `TechnicalEnum` or
`ExternalVocabulary` with its reason in the docstring.

**Member names are English; values are the codes as stored.**
`RelationType.PRIMARY_MEMBER = "HOOFDLID"` — the value is data and stays, the
name is an identifier and follows the English rule.

**`CodeEnum`, never `str, Enum`** (plain `Enum` until #1280). With a `str`
subclass, `status == "paid"` stays a valid comparison that happens to be true, so
a stale literal survives unnoticed. `CodeEnum` is no `str`, but a member is its
code in every string context — an f-string, `str()`, a log line, a URL. Plain, that comparison is silently *false* — which is why the
loose-string gate is an AST walk and not a mypy rule: the models use the legacy
`Column()` style, so mypy types every column attribute as `Any` and `Any ==
"paid"` is never an error.

## A rule has one home

> **A rule has one home, and every entrance passes through it.** One field →
> an attribute validator; several fields of one object → a method on that
> object; other rows or the database → a service function; at rest → a
> constraint — and if PostgreSQL can say it about one row, it says it:
> `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, in the same change as the
> validator; never a trigger. A derived value is computed once, on the object
> that owns the data, and shown everywhere else. An entity never opens a
> session. A screen, a JSON route and an import never carry a rule of their
> own. A consequence in another domain goes through a domain event: the object
> returns what happened, the service publishes it. A domain never constructs or
> mutates another domain's mapped class; it calls the owner's command or
> publishes an event. One request is one transaction: the door service commits
> once; a called service, a facade or a handler never does. A domain package
> has the shape below.

The design is
[`change_request_13_oo_foundation.md`](change_request_13_oo_foundation.md); the
placement rule it builds on is CR-04. The gate is `backend/tests/test_rules_gate.py`,
its frozen offenders `rules_baseline.py` — a list that may only shrink.

**The four addresses.** `@validates("field")` for one field; `def check(self)`
for several fields of one object, registered with `@aggregate` from
`app/kernel/rules.py` so it runs on every flush without a caller; a service
function for anything that needs other rows; `NOT NULL`/`CHECK`/`UNIQUE`/`FOREIGN
KEY` for what must hold at rest, in the same commit as its validator. A
`check()` reads what is loaded and never queries.

**An event handler** is a `@subscribe` function. It touches the session and the
job queue, never the network, and never commits. A `@job` function is where a
mail or an HTTP call belongs.

**The module shape** — a package under `app/domains/` has:

- `api.py` — the only thing another domain imports;
- `codes.py` — its code lists (the rule above);
- `CONTRACT.md` — what it promises, one screen, with a `## Callers` section that
  names every `/api/v1` route and its machine caller, one line each:
  `` - `POST /api/v1/…` — the caller ``;
- `models.py`;
- `tests/` — the tests that exercise only this domain.

A new package without one of them is red in CI, naming the missing piece.

**Where a test lives** (CR-13 R15) follows from its imports: one domain → that
domain's `tests/`; several → `backend/tests/integration/`; none → `backend/tests/`.
A gate over several domains stays in `backend/tests/` too. Importing only the login
helpers from `auth` does not count as importing `auth`. The gate is
`backend/tests/test_tests_placement_gate.py`, and it names the folder a misplaced
file belongs in.

**Exceptions:** one class per domain, English (`ActivityError`); a Dutch `*Fout`
that existed stays as an alias of it — one class, two names.

**What belongs to a module** (CR-19) is declared once, in `app/kernel/modules.py`:
a menu item, route prefix, tile or path of a switchable module goes in its
registry entry, and its routers get `require_module` where `main.py` includes
them — never a hard-coded list in a screen. The gate is
`backend/tests/test_module_gate.py`.

## A copied model declares every column

A copy action (`copy_*`) reads what it copies from a `CopyPlan`
(`app/kernel/copying.py`) declared beside it in `COPY_PLANS`. Every mapped
column of a model it writes is in exactly one set: copied, set by the copy, or
not copied with its reason. **A new column on a copied model
is classified in the same change** — `backend/tests/test_copy_plans_gate.py`
fails, naming the model and the column, until it is. A new `copy_*` function
needs a plan, or a reason in the gate's register of functions that copy nothing
(#1464, after #1463 left `target_audience` behind).
