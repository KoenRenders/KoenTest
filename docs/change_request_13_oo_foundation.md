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

*Not started; Part A first.*

## B11. Decisions log

| Date | Decision | Who |
|---|---|---|
| 26 Sep 2026 | Fresh CR-13 instead of reworking CR-04; CR-04 keeps only the placement rule. | Koen |
| 26 Sep 2026 | Trigger: the pain of 8 September (a rule enforced on one entrance, not another); therefore broader than the CRM module. | Koen |

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
