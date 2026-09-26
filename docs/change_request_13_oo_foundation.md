# Change Request 13 — OO foundation: a rule has one home

> Supersedes CR-04 except its placement rule (see the banner there). Being
> shaped with Koen; Part A is his, and is not complete yet.

**Project:** Web Portal "Raak Millegem"
**Status:** shaping started 26 September 2026 · not development-ready · not assigned
**Applies to:** the domain layer of every module (`backend/app/domains/*`,
`app/kernel`), the entrances to each aggregate (public form, JSON API, admin
screen, import), and the shape a new module takes from its first commit.

---

# Part A — The business

> From Koen's words of 26 September 2026. **Not yet approved**; A3–A7 open.

## A1. Reason to act

The trigger is the pain of 8 September 2026, not the CRM module. A
validation round that day produced seventeen findings, and four of them —
#720, #727, #733, #681 — were the same defect: a rule enforced on one
entrance and not on another. The public form demanded a mobile number; the
JSON API accepted a registration without one; the admin screen let you erase
it. Not one of those was an oversight. The rule had no home, so it lived in
whichever function happened to run.

That is why this change is **broader than the CRM module** (Koen, 26
September): it is about every rule in every existing module having one
place, and about a new module — CRM, sales, a public site — getting that
shape from day one rather than repeating the pattern that produced the four
findings.

Decided on 26 September 2026: a fresh change request rather than a rewrite
of CR-04, because CR-04 predates the template, a third of it is obsolete
(React track, `reg_form_type` strategy), and nothing of it was built; its
placement rule is kept as the one thing that lives on.

## A2. As-is process

*To be measured, not recalled* — the five numbers of CR-04 (attribute
validators 0, check constraints 1→5, mutating routes that confirm 2 of 91,
orderings without tiebreaker ~16, `required=True` promises 88 in 25
templates) are from 8 September; #755 was to turn them into a report and is
still open. The as-is is re-measured on the branch before Part B is written.

## A3. To-be process

*Open — to be shaped with Koen (his points 3, 4 and 5 of 25 September):*

- derived values (a total, a balance, a state) computed once, as a method on
  the object that owns the data, instead of on every screen that shows them;
- whether a **module skeleton** is a deliverable — the shape a new module has
  from its first commit (`api.py`, `codes.py`, view-models, an aggregate with
  its rules) — and whether a gate enforces it;
- how hard that gate may be: ratchet on existing code, hard for new modules.

## A4. Supplied material

CR-04 (the placement rule and its five numbers), #236 and its six execution
issues (#755, #757, #758, #759, #760, #761), CR-12 (the code-list pattern
this builds next to), the validation findings of 8 September 2026.

## A5. Business requirements

*Open.*

## A6. Non-functional requirements

*Open.*

## A7. Acceptance criteria

*Open.*

---

# Part B — The solution

*Part A first; B9 is written ahead of the rest on Koen's request (27
September 2026: the rule this CR fixes must be guarded on every push from
the start), as a proposal — the gates marked "depends on" wait for his
answers to Q3–Q5.*

## B9. Rule and gatekeeper (proposal)

### B9.1 The rule

> **A rule has one home, and every entrance passes through it.** A rule that
> looks at one field is an attribute validator; at several fields of one
> object, a method on that object; at other objects or the database, a
> service function; integrity at rest, a database constraint (CR-04's
> placement rule). A derived value (a total, a balance, a state) is computed
> in one place — the object that owns the data — and shown everywhere else.
> A screen, a JSON route and an import never carry a rule of their own.

Lives in `docs/code-style.md` (the layer paragraph) and CR-04 (the
placement rule, unchanged); `CLAUDE.md`'s *Validation layers* section
points there and stops repeating it.

### B9.2 Reach and baseline

Reach: every aggregate in every domain, and every module that follows.
The baseline is CR-04's five numbers, taken on 8 September 2026 and to be
**re-measured by the gate itself** in phase 0 (the #755 report becomes the
gate's first run — "measured, not recalled", as in CR-12):

| | 8 Sep 2026 (by hand) | gate, phase 0 | after this CR |
|---|---|---|---|
| attribute validators (`@validates`) | 0 | — | one per field-level rule |
| database check constraints | 1 (5 on 26 Sep, #94) | — | every critical invariant |
| `required=True` promises in templates without a server-side counterpart | 88 promises, counterpart **unmeasurable** | — | 0 |
| entrances to an aggregate (public form, JSON API, admin, import) that bypass its rules | unmeasured — #720, #727, #733, #681 were four | — | 0 |
| derived values computed in more than one place (total, balance, state) | unmeasured | — | 0 |
| mutating UI routes without a confirmation | 2 of 91 | — | all |
| orderings without a unique tiebreaker | ~16 | — | 0 (#761 may gate at once) |
| new domain packages missing the module skeleton | — | — | 0 (hard gate for new modules — *depends on Q4*) |

### B9.3 The gate

`backend/tests/test_rules_gate.py`, run by `backend-tests.yml` on every push.
Ratchets while a count is above zero (`rules_baseline.py`, entries may only
be removed, the same shape as CR-12's `codes_baseline.py`); hard once zero.
*Depends on Q5 for the split ratchet/hard between existing and new modules.*

| Gate | Looks at | Message on violation |
|---|---|---|
| Promise kept | every `required=True` / `pattern=` / `min=` in a template maps to a validator, a schema field or a constraint on the column the field posts to (the template-variables gate already knows which view-model field a template reads; this walks it back to the column) | "`_inschrijf_form.html:42` promises `mobile` is required; `Registration.mobile` has no validator and no constraint" |
| One entrance rule | every route that mutates an aggregate (AST: `db.add`/attribute assignment on a mapped class in `router.py`/`admin_ui.py`/`import_service.py`) calls that aggregate's rule method or the service function registered for it — never validates inline | "`activities/router.py:885` writes `Registration` without passing `Registration.check()`" |
| One owner per derived value | a registry of derived values (`Registration.total`, `.balance`, `Activity.state`, …) with their owner; the AST finds a second computation of the same shape (`sum(... * ...)` over the same relationship, a status decided from `paid_at`/`amount`) outside the owner | "`payment/admin_ui.py:120` recomputes a registration total — use `registration.total()`" |
| No rule in a router | a `router.py`/`ui.py` function with an `if` on a domain attribute followed by a `raise HTTPException`/`flash` is a rule living at the door (the layer gate already forbids `db` in `ui.py`; this extends it to rules) — ratchet | "`membership/register_router.py:61` decides `mobile` is required — move it to `Person`" |
| Module skeleton (*depends on Q4*) | every package under `app/domains/` has `api.py`, `codes.py`, `CONTRACT.md`, `models.py`, a `tests/` counterpart, and no import of another domain's internals (extends `test_import_boundaries.py`) — **hard for a package created after this CR, ratchet for the existing ones** | "`app/domains/crm/` has no `CONTRACT.md`" |
| Tiebreaker | every `order_by` ends in a unique column (#761) — may be hard at once | "`activities/service.py:210` orders by `date` without a tiebreaker" |
| Confirmation | every mutating UI route sets a confirmation (#760) — ratchet from 89 | "`forms/admin_ui.py:77` mutates and confirms nothing" |

Each gate proven by an **additive** violation (CR-12 B8: a destructive one can
take the suite down and come back green) and each ratchet checked to look
somewhere (#678). Where a gate cannot be mechanical — whether a rule *should*
exist, whether two derived values are one concept — it goes to review, and
B9.3 says so.

### B9.4 Why this gate is not "gates come last"

CR-04 warned against closing a rule with a gate while eighty-five routes
violate it: the exemption list is where a rule dies. The ratchet answers
that — the list is frozen, may only shrink, and disappears — and CR-12
proved the shape on twelve gates in one week. What remains true: a **hard**
gate on existing code waits until its count is near zero; a hard gate on
**new** modules (Q5) can start on day one, because there is nothing to
exempt.

## B11. Decisions log

| Date | Decision | Who |
|---|---|---|
| 26 Sep 2026 | Fresh CR-13 instead of reworking CR-04; CR-04 keeps only the placement rule. | Koen |
| 26 Sep 2026 | Trigger: the pain of 8 September (a rule enforced on one entrance, not another); therefore broader than the CRM module. | Koen |
| 27 Sep 2026 | The rule this CR fixes is guarded in CI on every push from the start; B9 written ahead of the rest of Part B, as a proposal. (Template: B9 now says a rule is fixed only when its gate runs in CI.) | Koen |

## Q&A log

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 25 Sep 2026 | Trigger: CRM, or the 8 September pain? (Claude) | Koen (26 Sep): the 8 September pain; broader than CRM. |
| Q2 | 25 Sep 2026 | A selection from CR-04 or broader? (Claude) | Koen (26 Sep): broader. |
| Q3 | 25 Sep 2026 | "Methods and lambdas to get at things": derived values once, on the object? (Claude) | *open — to discuss 27 Sep* |
| Q4 | 25 Sep 2026 | A module skeleton as deliverable, with a gate? (Claude) | *open — to discuss 27 Sep* |
| Q5 | 25 Sep 2026 | How hard may the gate be: ratchet on existing, hard for new? (Claude) | *open — to discuss 27 Sep* |

## Relationship to existing work

- **CR-04** — the placement rule lives on there; everything else is
  reconsidered here.
- **#236 (OO-tracker)** — becomes the pointer to this CR once Part A is
  approved; its six execution issues are decided per item here.
- **CR-12 (codes en enums)** — the sibling foundation change; independent,
  but its `Mapped[]` columns and enums are what the aggregate methods here
  will compare against.
- **#94** — the constraint layer of the placement rule.
