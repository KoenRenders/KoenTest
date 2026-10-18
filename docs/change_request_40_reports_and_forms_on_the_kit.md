# Change Request 40 — Reports and Forms on the kit

**Project:** Web Portal "Raak Millegem"
**Status:** outlined on 18 October 2026 at Koen's request, after he took the form builder and the reports panel out of CR-11 phase 5 ("Dat zijn volgens mij de meest complexe schermen") · **an outline, not shaped**: Part A needs Koen's own words, no concept is drawn, no build read has been asked · on hold (#2137: on no release, with no dev) · not assigned to a release · nothing is built
**Tracking issue:** #2137 — the one place where what is open stands; this document is the design, the issue is the status
**Applies to:** the form builder (`forms/templates/_fb_builder.html`) and the field of somebody's own form (`_formulier_veld.html`); the reports panel (`reporting/templates/_rp_paneel.html` and the page that holds it)
**Reading:** not measured — an outline

---

# Part A — The business

## A1. Reason to act — the trigger

CR-11 (GUI redesign 2) puts every back-office screen on one kit. Two screens stayed out of its phase 5 on Koen's word, on 18 October 2026: *"kunnen we de forumlier editor-functionaliteit en het rapporten-paneel buiten scope laten? Dat zijn volgens mij de meest complexe schermen."* He named this change request himself, in his own words: *"Reports and Forms on kit ofzo?"*, and asked for it to be made: *"ja, maak maar aan"*.

Today the two screens carry their own markup: raw fields and checkboxes, surfaces written by the template, and spacing on form elements (A2). Every other screen of the back office has moved, or is moving on v2.17, to the kit. These two keep a second way of drawing a field and a card.

## A2. As-is process — how it works today, and where it hurts

Measured on the ratchet baseline (`tests/ui_baseline.py`) as it stood on master commit `99d8e27c`, 18 October 2026. The number is the count of violations the file holds under each rule; the rules are in the baseline's own comments.

| File | Lines | Raw form elements | Raw checkboxes | Raw surfaces | Spacing on form elements | Sideways scrolls |
|---|---|---|---|---|---|---|
| `_fb_builder.html` (the form builder) | 467 | 12 | 6 | 6 | 7 | — |
| `_formulier_veld.html` (a question on the public form) | 111 | 4 | — | — | 2 | — |
| `_rp_paneel.html` (the reports panel) | 495 | 4 | 1 | 14 | 2 | 2 |
| `_rp_raakje_antwoord.html` (the assistant's answer in the panel) | 61 | — | — | 1 | — | 1 |
| `admin_rapport_paneel.html` (the page of the panel) | 12 | — | — | — | — | — (it extends the bare shell) |

`_rp_kaarten.html` and `admin_rapporten.html` (the list of reports) are not in this change request: the list moves with CR-11 phase 5, track 2, round 3 (#2123).

Not written yet: the process drawing, the step table and the pain per step.

## A3 to A5

Not written yet.

## A6. Business requirements — what the board asks, with MoSCoW

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | The screens of the form builder and a question of somebody's own form are built from the kit: its field, switch, section and group rows. | Must | CR-11, Koen 18 Oct 2026 | the kit gap of D2 is the known exception |
| R2 | The reports panel is built from the kit. | Must | CR-11, Koen 18 Oct 2026 | |
| R3 | **What each screen can do today, it can do afterwards.** No function is lost or moved without Koen's word. | Must | Koen, 18 Oct 2026, on the Design Studio and Media: "functioneel gelijk", "het gedrag blijft identiek" | checked per screen against the template, as in CR-11 rounds 2 and 3b |
| R4 | A rendered concept of each changed screen is shown to Koen at 390 and about 1 100 px before anything is built. | Must | CR-11 phase 5, `AGENTS.md` | the concepts are the first phase |
| R5 | The listed files leave the ratchet baseline. A rule that cannot be met is named, with its reason, as a declared exception. | Must | CR-11 | the builder keeps saving per section (Q28) |
| R6 | A phone (390 px) can use both screens as far as it can today. | Should | "Mobiel is de norm" | measured, not assumed |

## A7, A8

Not written yet.

---

# Part B — The solution, for whoever approves it

## B1. Solution outline — the solution and the decisions that shape it

**In one paragraph.** The two screens are drawn on the kit in two steps, as CR-11 did for the other complex screens: a concept per screen with the real macros and made-up data, looked at by Koen; then a build by an Opus dev, screen by screen, with a check of every function against today's template.

- **D1 — a concept first, per screen.** Both screens are large (467 and 495 lines) and carry behaviour that a concept can hide, so each concept comes with a table of today's functions, as the Design Studio and Media concepts did.
- **D2 — one kit gap is already known.** The comment of `_formulier_veld.html` says that a question with a choice out of options, with several choices or with a scale keeps its own rows, because the kit's groups know no "Anders" with its own text and no scale. Closing that gap is a kit change (a new optional parameter or a new kind), which is for an Opus dev and is asked first, not built by the builder of the screen. The alternative is a declared exception.
- **D3 — forms first, then reports,** unless Koen decides otherwise (B8, Q1).

## B2 to B7

Not written yet.

## B8. Open decisions — what the approver still decides

| # | Question | Recommendation | What the answer changes |
|---|---|---|---|
| Q1 | Which screen first, the form builder or the reports panel? | The form builder: its public field is already on the kit for most kinds, so less is open. | Which concepts are drawn first. |
| Q2 | The choice out of options with "Anders", and the scale: a kit change, or a declared exception? | A kit change, asked first (D2). | Whether the public form of somebody's own form leaves the baseline completely. |
| Q3 | On which release? | Not decided. | — |

## B9. Decisions log — dated answers

| Date | Decision | By |
|---|---|---|
| 18 Oct 2026 | The form builder and the reports panel stay out of CR-11 phase 5. | Koen: "kunnen we de forumlier editor-functionaliteit en het rapporten-paneel buiten scope laten? Dat zijn volgens mij de meest complexe schermen." |
| 18 Oct 2026 | A follow-up change request, "Reports and Forms on the kit", is made. | Koen: "Maak je daar een vervolg cr van? Reports and Forms on kit ofzo?" and, to the proposal of CR-40: "ja, maak maar aan". |

---

# Part C — The build, for the master CLI and the dev CLIs

## C1. Verified premises — measured before the handover

Only A2 is measured so far, on master commit `99d8e27c`, and it is not re-measured on a handover commit. The baseline of those files may have fallen since: the devs of CR-11 phase 5, track 1, clean files of the same baseline on v2.17.

## C2 to C8

Not written yet.

## C9. Screens before the build — the concepts the approver saw

None drawn yet. The concepts of the other screens of CR-11 phase 5, track 2 stand in Koen's project folder under the CR-11 folder, one subfolder per round; these two follow the same form.

## C10. Close-out at the release

Not written yet.

## Non-goals — deliberately outside this change

- The behaviour of the form builder (sections, branching, results, the import of a definition) and of the reports (objects, filters, layouts): they stay as they are.
- The list of reports (CR-11 phase 5, round 3) and the form builder's other screens that are already on the kit.
- The shell itself (`admin_base.html`).

## Relationship to existing work — issues and change requests

- CR-11 (GUI redesign 2, #1481): this change request is the part of its phase 5 that Koen took out on 18 October 2026.
- #2111 (the remaining raw fields and surfaces): lists these files as "out of scope, to track 2".
- #2123 (six lists on the kit's list page, including Rapporten): the list of reports.
