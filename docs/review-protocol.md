# Review protocol — how a review of this repository is asked for and given

> One trigger, one answer, one place: a review is asked for with the
> **`ai-review`** label plus one sentence on the PR or the tracking issue,
> and it is answered as a comment on that PR or issue. It is *advisory*:
> nothing blocks a merge but CI, and the platform owner decides what is
> taken in. Any reviewer — an AI tool or a human — gets the same scope.
> Never automatic: a review starts only when asked.

## The request

On the PR (a code review) or the tracking issue (a change request review):

1. Add the label **`ai-review`**.
2. Comment: *review please, <scope>* — the scope is "the document" for a
   change request, or "the diff against CR-<NN>" for a PR.

## The answer

One comment, headed **"Review — <date>, <scope>"**, findings grouped by
weight, each with file and line or section. End with the verdict list:
every finding marked **take in**, **already decided**, or **not taken,
with the reason**. The shaping CLI processes the comment on the PR and
records the verdicts in the change request's decisions log.

## Checklist — a change request

Read the document in the repository; verify premises against the code.

1. **Premises measured** (the template's rule 1): every claim of the form
   "as X already does", "no migration", "the key refuses it" is measured
   in the code with file and line in C1. Where the answer differs from
   the claim, say so with the measurement.
2. **Exceptions named once** (rule 2): every rule the design needs an
   exception from stands in B4, with the mechanism.
3. **Screens shown or waived** (rule 3): C9 shows a concept per changed
   screen, or names the waiver and who waived it.
4. **The user's words in A3** (rule 4): button labels, titles, menu names
   decided in Part A; Part A names no component, library or table.
5. **The shape holds**: the Won'ts are deliberate and recorded; the ACs
   are walkable; the reading budget (A ≤ 1 500, B ≤ 2 500) holds; old
   decisions do not linger against new ones in the text.
6. **The tests could go red**: C6's tests fail when the thing they prove
   is broken (CLAUDE.md, *Testen en test-evidence*).

## Checklist — a PR with code

Read the description, then the diff, then the conventions it must hold.

1. **The description states its claim**: the CR or issue it implements,
   what changed per module, the evidence (CI run, tests added, gates
   proven by violation).
2. **Scope**: the diff stays inside what the CR it names decides; no
   unrelated work rides along.
3. **Conventions**: `CLAUDE.md` (code style, workflow, fixed UI
   decisions), `docs/code-style.md`, and the domain's `CONTRACT.md`
   hold; screens go through facades, services through facades.
4. **Tests**: every new test could go red; no green-without-proof
   (the three forms CLAUDE.md names: mutates nothing, looks nowhere,
   tests the failure not the reason).
5. **No copy-paste shapes the gates forbid**: no duplicated fact the
   codebase keeps in one place ("twee keer dezelfde reparatie").

## Sources — the protocol invents nothing

Every item above points at: `docs/change_request_template.md` (the five
rules), `CLAUDE.md` (workflow, test-evidence, fixed UI decisions),
`docs/code-style.md`, the domains' `CONTRACT.md` files, and the CR the
PR implements. A reviewer who finds a convention nowhere in those writes
it as an observation, not a finding.
