# Change Request 11 — GUI redesign 2 (parking lot)

> Deliberately a **parking lot**, not a work order (Koen, 20 September 2026):
> the place where GUI work lands that we consciously do NOT do in v2.5, so the
> v2.5 scope can be decided piece by piece without losing the rest. Nothing on
> this list is assigned; each item returns to Koen for a separate decision
> before anyone builds it. When an item is picked up, it gets its own issue —
> this document only remembers what was parked and why.

**Project:** Web Portal "Raak Millegem"
**Status:** shaped with Koen on 20 September 2026 · on hold (parking lot)
**Applies to:** admin list screens, the public homepage/cards, the admin
assistant — GUI work deferred from the v2.5 design track (#913, #996).

---

# Part A — The business

## A1. Reason to act

In Koen's words (20 September 2026, deciding the pagination scope):

> "laten we dat enkel inbouwen in betalingen, de rest is voor later (bekijken
> we dan samen met de cards). [...] Dan kunnen we stuk per stuk bekijken wat
> we nog in v2.5 doen en de rest parkeren we naar later."

v2.5 carries the design track plus four other work streams. Deciding each GUI
candidate the moment it surfaces would keep widening the release; parking them
here keeps v2.5 decidable and nothing gets lost.

## A2. As-is / A3. To-be

Not applicable in process terms — this is a collection CR. Per item the as-is
and the intended direction are noted inline below.

## A4. Parked items

Each item names its source, so the original context can be reread instead of
reconstructed.

1. **Pagination on Leden and Activiteiten.** v2.5 builds pagination on
   Betalingen only (#1059, scoped down 20 Sep). The other two lists follow
   later, decided **together with item 2** — paginating a card list and a
   dense table are different designs.
2. **Lists vs. cards, reconsidered.** Koen (19 Sep): *"Ik twijfel nog altijd
   of we betalingen ook niet terug moeten zetten naar de cards."* And F10
   (ledenlijst densify to table, #996) stays deliberately undecided until he
   has lived with the dense Betalingen screen. One future decision covers
   both directions — table-ward or card-ward — for the admin list screens.
3. **Bulk selection on admin lists.** Meetronde candidate; Koen (19 Sep):
   *"bulk selectie zou ik voorlopig niet doen."* The conventions debate
   (A17 on #785) already sketches scopes-with-preview when it comes.
4. **Featured activity on the homepage.** The big blue hero card from the
   Cobalt sketch — deliberately left out of golf 11 (needs a "which
   activity" choice and the agenda sits directly below). Candidate: a CMS
   choice once the board misses it.
5. **AI insights, phase 2.** v2.5 gives the admin assistant the screen
   context it is called from (#1060, "niet meer, niet minder"). Parked:
   language-model *insights* on top of that context (Mistral, Europe First),
   under the standing rule that every claim carries a clickable source and
   unsupported claims are dropped.
6. ~~STT/TTS in the Raakje overlay~~ — **un-parked 20 September 2026**:
   Koen chose mic + read-aloud, identical to the rapporten-Raakje, with the
   wider principle "Raakje is the same everywhere; the only difference is the
   public security boundary". Now issue #1075 (scheduled via the master CLI).
7. **Table conventions from the conventions debate** (#785 triage, A12/A17):
   sortable columns as the norm, column chooser, saved views, Ctrl-K command
   palette. Independently confirmed by all three maker-round directions;
   sized for the ERP ambition, not for one release.

# Part B — The solution

Empty by design. Part B is written per item, in that item's own issue, when
Koen un-parks it.
