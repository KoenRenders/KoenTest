# Change Request 08 — The eye wants something too: a visual tightening

**Project:** Web Portal "Raak Millegem"
**Status:** Draft — brainstorm of 13 September 2026, not assigned to a release.
Open questions in §9 are genuinely open.
**Apply to:** `scripts/build-css.sh` (tokens), `_macros.html`,
`docs/design-system.md`, screen templates in batches. No backend logic.

---

## Goal

The design system solved **consistency**: every screen renders from the same
macros and tokens, gates keep it that way, and a conformity agent reviews the
judgment layer. What it deliberately never decided is whether the result is
**beautiful**. This change request adds that layer: a visual concept — chosen
by eye from strong graphical proposals, not argued in words — translated into
the token and macro layer so every screen tightens at once.

The one rule that makes this affordable, fixed up front: **aesthetics enter
through the system, never per screen.** The investment in macros and tokens is
exactly what makes a redesign a foundations project instead of a
92-screen project. A screen that needs its own styling to look good is a
finding about the system, not a licence to special-case.

## 1. Current state (measured, 13 September 2026)

| | measured |
|---|---|
| Norm | `docs/design-system.md` (917 lines, 13 sections), live at `/admin/design-system` from the real macros (#783) |
| Enforcement | lint gate (`test_ui_conventions_gate.py`) for mechanical rules; `design-conformiteit-bewaker` agent for judgment, on request |
| Conformity batches mid-flight | search on 3 of 15 lists (#758); toast on 6 of 92 routes (#760) |
| Brand | 8 fixed colours from the huisstijlgids (`scripts/build-css.sh`); Radio Canada Big display + Inter body (deliberate readability deviation); RaaK wordmark |
| Audience | 80% of public visits is mobile — the phone is the design norm; `/admin/rapporten` is the one recorded desktop exception |
| Own imagery | activity photo albums (media module) and the yearly flyers — real material, no stock needed |
| Open design decision riding along | design-system §12.1: product brand vs tenant brand in the admin shell — decide on mockups |

## 2. Principles

1. **Mockups decide, words don't.** Taste cannot be specified but it can be
   pointed at. The concept round produces full-page visuals of the same
   screens in distinct directions; the decision is "this one, but…" — not an
   adjective list.
2. **Aesthetics through the system.** The chosen direction lands as token
   values and macro changes first, screens second. Per-screen bespoke styling
   remains forbidden; the gates keep enforcing that during and after.
3. **The brand is the anchor.** The eight huisstijl colours and the wordmark
   are constraints, not suggestions; a concept may *propose* a brand
   adjustment, but that proposal goes to the board explicitly and is never
   slipped in as a token change.
4. **Mobile is the judging viewport.** A direction is evaluated on a phone
   frame first; the wide screen is the adaptation. (The recorded exception
   for the reports screen stands.)
5. **The redesign absorbs the running conformity work.** The unfinished
   batches (#758, #760) finish *inside* the rollout phases — restyling a
   screen and skipping its missing search would touch every file twice.

## 3. The concept round — strong graphical proposals via external AI

Explicitly wished for (13 September 2026): use ChatGPT to generate strong
graphical proposals before any code changes.

- **What is asked of it**: three visually distinct directions, each shown as
  full-page mockups of the same four canonical screens — home, activities
  list, word-lid, one admin list screen — phone frame first, wide second.
  Input: the huisstijlgids, screenshots of the current screens, the
  mobile-first norm, and the fixed UI decisions that are out of bounds (§7).
- **Data rule, absolute**: no member data in any prompt to any external
  design tool. Screenshots are of public pages, or of admin screens filled
  with seeded fake data. The same masking rule as for the public repo.
- **Europe First, stated honestly**: OpenAI is a non-EU service. For visual
  concept generation there is no comparable EU alternative today (Mistral has
  no design-grade image work). The exception is defensible because the content
  is public material and the engagement is exploration, not processing —
  but it is an exception, named here as the rule requires. Claude (also
  non-EU) is available in-session as a second lane: design-canvas artboards
  to iterate the *chosen* direction into precise screens, under the same
  data rule.
- **Deliverable of the round**: one chosen direction (mixing allowed), with
  the choice and its "but…" notes recorded in this document; the §12.1
  admin-brand decision taken on the same mockups.

## 4. Translation — direction → system

1. **Tokens** (`build-css.sh`, design-system §1): spacing rhythm, type scale,
   radii, shadows, surface colours, the temperature of grays. This is where
   "strakker" mostly lives.
2. **Macros** (`_macros.html`, §2): whatever the direction changes about
   buttons, cards, tables, badges, modals — once, for everyone.
3. **Screen types** (§3): the composition rules per type follow the
   direction; `docs/design-system.md` is updated *in the same commits* — the
   norm document and the norm never diverge.
4. **Gates**: rules that changed (a colour, a spacing class) update the lint
   gate in the same phase; the e2e golden flows guard behaviour throughout.

## 5. Rollout

Batch-wise, public first (the face, and 80% mobile), admin second wave — each
batch reviewed on a phone, with the conformity agent before and after, and the
open batch work (#758, #760) completed per screen as it is touched.

## 6. Phasing (each phase shippable)

0. **Concept** — the external proposal round (§3), the choice, the §12.1
   decision. No code.
1. **Foundations** — tokens + macros + design-system.md, behind no flag (the
   change is visual, reversible by revert).
2. **Public screens** — batch-wise, absorbing conformity work.
3. **Admin screens** — including whatever §12.1 decided.

## 7. Out of bounds (fixed decisions that stand)

The fixed UI decisions of CLAUDE.md hold unless a concept explicitly proposes
otherwise *and* the proposal is accepted per item: address grid, postal-code
dropdown, registration as a narrow modal, hard redirect to Mollie, row-action
caps, confirmation copy rules. The Inter-for-readability deviation stands.
No new frontend stack, no client framework — the redesign changes CSS, macros
and templates, nothing about how screens are rendered.

## 8. Non-goals

- A rebrand. The huisstijl is input, not output (§2.3).
- Dark mode — unless declared in scope in §9.
- Per-screen artisanal styling, ever.
- New screen functionality smuggled in as "while we're here".

## 9. Open questions

1. Which screens bother the eye most today? A handful of named examples
   (screenshot + one sentence) sharpens the brief for the proposal round more
   than any general direction.
2. Public first, admin second — agreed, or should one admin screen join the
   first wave as proof?
3. Should the concept round be allowed to propose changes to the huisstijl
   itself (to bring to the board), or is it strictly within the eight
   colours?
4. Own photography as a design element (hero images, activity cards) — in
   scope for the concept round?
5. Dark mode: in or out?
