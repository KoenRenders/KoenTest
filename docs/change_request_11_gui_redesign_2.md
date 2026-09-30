# Change Request 11 — GUI redesign 2 (parking lot)

**Project:** Web Portal "Raak Millegem"
**Status:** shaped on 20 September 2026 · brought onto the template of 30 September 2026 · on hold — a parking lot, not a work order
**Applies to:** admin list screens, the public homepage and cards, the admin assistant — GUI work deferred from the v2.5 design track (#913, #996).

> A parking lot: the place where GUI work lands that is consciously *not*
> done yet, so a release can be decided piece by piece without losing the
> rest. Nothing here is assigned; each item returns to the business for a
> separate decision before anyone builds it. When an item is picked up it
> gets its own issue or its own change request; this document remembers
> what was parked and why. The sections that a parking lot cannot fill
> keep the template's note block, as the template prescribes.

---

# Part A — The business

## A1. Reason to act — the trigger

Deciding every GUI candidate the moment it surfaces keeps widening a
release. v2.5 carried the design track plus four other work streams, so the
candidates that were not needed for v2.5 were parked here, to be decided
one by one later — "laten we dat enkel inbouwen in betalingen, de rest is
voor later; dan kunnen we stuk per stuk bekijken wat we nog doen en de rest
parkeren we naar later" (20 September 2026).

**Background that shapes the end state without being in scope:** the
platform will be used by other organisations than RAAK — a company that
wants a webshop on it, another association with its own menu and brand.
That is a separate change request (the menu structure and more are fixed
for RAAK today); nothing in this one builds for it. But the patterns and
the style decided here are the platform's, not RAAK's: the end state keeps
apart what belongs to the **kit** (behaviour patterns, layout grammar,
control shapes, icons' meanings) and what belongs to a **tenant's brand**
(colours, fonts, wordmark, the icon set's look), so a second organisation
changes the second and inherits the first.

## A2. As-is process — how it works today, and where it hurts

Not one process but the screens and the behaviour patterns of the admin and
the public site as they are lived with today. Listed with the person who
uses them daily (Koen, 30 September 2026), one row per pain: which screen or
pattern, what hurts, and — where there is one — a first idea for a solution.
An idea is not a direction: the direction is chosen in Part B, per item,
with the usability arguments beside it.

| # | Screen or pattern | What hurts today | Solution idea | Source |
|---|---|---|---|---|
| 1 | **A repeating group inside a detail** — several e-mail addresses on a person; the same shape for contact details, products under a component, dates on an activity, options on a form field, lines on an order | Every time such a group is built, its behaviour and its look are described again from scratch: where the save button sits, how "make this the main address" looks, that the row title does not repeat per row, the size of the group's heading, the "add" button to the right of the heading. The multiple e-mail addresses (this week: #1223, #1229) were first built as a different screen — ugly, taking far more room than the group deserves — and then corrected point by point, each point a decision the person asking already made elsewhere. A lot of work for the asker, for a thing the application already does several times. | Name it once and build it once: a **repeating group** pattern in the design system (§4, next to P1–P12) with one macro that renders the heading, the "add" action at its right, the rows with their row actions, the one-among-many marker ("hoofdadres") and the save behaviour — rendered live on `/admin/design-system` like the other components. Every existing instance is listed under the pattern and migrated to the macro, so an issue can say "a repeating group of e-mail addresses" and nothing more. The gate that already checks that promised macros exist then guards it. | Koen, 30 Sep 2026 |
| 2 | **Cluttered edit screens** — the activity detail with its components (`_aa_detail.html`) as the example | The screen reads as if each field, radio button and button was added one under the other as it came up: 37 labels, 32 inputs, 7 radio or check controls and 4 action bars in one 422-line template, in one column. Nothing groups what belongs together (a product's price, member price, free and pay-on-site are four separate rows), settings and content sit in one stream, and the eye finds no rhythm. It looks amateurish next to the redesigned list screens. | A **form layout grammar** in the design system, as the list screens got one (§3.2): a screen is sections with a heading, each section a grid that lays related fields side by side on a desktop and stacks on a phone; a small set of control shapes per kind of choice (a segmented control for two or three options instead of a row of radios, a switch for a yes/no, a select above five); settings apart from content; one action bar per section or one per screen, never four. Written once with a live example, then each edit screen is laid out on it — the components screen first, as the worst and the most used. | Koen, 30 Sep 2026 |
| 3 | **Rarely used, discouraged settings take the front row** — the three external links on a component (`external_register_url`, `external_registrations_url`, `info_url`) | They date from the very start, when documents lived in Google Drive and registrations ran on external systems. They are still needed for the odd case and may stay, but they are used in perhaps 2 to 5 % of components, and the platform wants to *discourage* them — yet they take half of the component's form, three full-width fields, as prominent as the name and the price. | A pattern for **the rare and the discouraged**: progressive disclosure. Such settings live in a collapsed section at the bottom of the form ("Externe koppelingen" or "Geavanceerd"), closed by default, with a one-line summary when something is set ("2 externe links") and a short note that the platform's own registration is preferred. Open it and the three fields are there as today. The same shape serves every other rarely used group, so an issue can say "in the advanced section" and be done. Measure the real share on PROD before deciding the wording — 2 % and 20 % ask for a different default. | Koen, 30 Sep 2026 |
| 4 | **Saving behaves differently per detail screen** — a CMS page has a save button at the top and stays open; a meeting saves itself while you type; almost every other screen edits per card with edit → save / cancel | Three ways of saving on screens that are all "a record in detail". The design system decided one (§3.4 record management, P1 *edit and stay*: save and cancel at the bottom, the screen stays, a toast), but two screens went their own way without a rule that says when that is allowed. The user learns three habits for one job, and each new screen is a fresh argument. | Decide **one default** and write the **deviation rule** next to it, so a deviation is a decision and not a habit. The default is P1 — and row 14 makes it "whole screen, one save" rather than per card. Deviations are allowed by kind of screen, not by taste: **autosave** where the screen is a *document* — one long text, nothing a rule can refuse, losing typed text is the real risk (meeting notes; possibly the CMS body) — and never on a *record* with fields that validation can refuse; a save button at the top only on a document long enough that the bottom is out of sight, and then the same button at the bottom too. Each detail screen names its save model in one line in §3.4's register; the gate that reads templates checks that a screen declaring "record" uses the edit-toggle macros and one declaring "document" uses the autosave form — so a fourth way cannot appear unnoticed. | Koen, 30 Sep 2026 |
| 5 | **List screens: some are tables, some are cards** — the admin lists (Betalingen a dense table since v2.5; Leden, Activiteiten and others still cards) | Two shapes for one kind of screen, and the split follows the order in which the screens were redesigned, not a rule. The person using them daily calls it his own doing and wants one choice, applied consistently — this is P2 in A6, and it carries P1 (pagination) with it, because a table and a card list page differently. | Not "tables everywhere" or "cards everywhere" but **one rule by content, applied to every list**: a **table** where the user scans and compares many rows on a few attributes and sorts or filters them (payments, members, registrations — the ERP side, where P6's sortable columns land); **cards** where each row is a thing with a face — an image, a title, a state to read at a glance — and the list is short (activities on the public side, media, meetings). §3.2 already fixes everything above the list (header, KPI row, search, filters); the rule fixes the list itself. Then classify every list screen in one table in the design system, migrate the ones on the wrong side, and let the doubt about Betalingen (P2) be settled by the rule rather than by mood. On a phone the difference shrinks: a table row stacks into a card-like block, which is what makes the table safe as the admin default. | Koen, 30 Sep 2026 |
| 6 | **Pagination is there on some lists and not on others, and sits in a different place each time** — the page-size choice (25 / 50 / 100) sometimes at the bottom, sometimes top right; the pager itself at the bottom | On Betalingen the person using it daily did not see that the list was paged at all: the pager sat bottom right, after a full scroll. Two lists page, the rest do not (P1), and where they page the controls are not where the eye looks first. The design system decided a pager (§2.3: server-side, 50 per page, `ui.pager()`, "x–y van n", hides itself when everything fits) but not its *place*, and the page-size choice is not part of it. | **One pager, two places, one rule.** The fact that there are pages must be visible **before scrolling**: a compact count "1–50 van 312" in the toolbar row at the top, right of search and filters, with the page-size choice beside it — the place where every mail client and every ERP list puts it. The page navigation (vorige / volgende) repeats at the **bottom**, where the eye arrives after reading, and never only there. Both come from the one `ui.pager()` macro (extended with the size choice), so no screen can invent a third place; on a phone the top row keeps the count and the bottom keeps the buttons. Apply it to every list that pages (P1 brings Leden and Activiteiten), and the classification table of row 5 says per list whether it pages at all. | Koen, 30 Sep 2026 |
| 7 | **Read mode hides what could be filled in** — a card in read mode shows only the fields that have a value; a yes/no that is off disappears with them | You cannot see what a card *can* hold until you press "Bewerken": an empty field is simply absent, and a switch that is off is absent too, so "off" and "does not exist" look the same, so the map of the record differs between reading and editing, and the user does not know where something sits, or that it exists, until they open the editor. | **Read and edit share one map.** In read mode a card shows every field the editor has, in the same order and the same grid, the empty ones with a quiet placeholder ("—" in grey, or "niet ingevuld") instead of vanishing; a yes/no shows its state either way — an *off* switch or "nee" in grey, not nothing — so "not set" is readable and not mistaken for "not there". Switching to edit then changes the *controls*, never the layout — nothing jumps, nothing appears. Two exceptions, both by rule: the rare-and-discouraged section of row 3 stays collapsed in both modes, and a repeating group (row 1) with no items shows its heading, its "add" action and one line "nog geen …". This is the read-side half of the layout grammar of row 2; it goes into the same design-system section and the same live example. | Koen, 30 Sep 2026 |
| 8 | **The checkbox as the control for every yes/no** — 65 raw `type="checkbox"` inputs in the domain templates; the kit has no switch macro | A checkbox looks dated next to the rest of the redesigned screens, and it is used for two different things at once: a setting that is on or off, and a choice among several. Modern web apps show a **switch** for the first, and it reads better: the state is visible at a glance, on a phone it is a larger target, and it says "this is a setting". | **One rule, two controls, one macro each.** A **switch** for every boolean *setting* on a record — is active, publicly bookable, members only, requires a team name, free, pay on site — rendered by one `ui.switch()` macro, with its label on the left and the state word ("aan" / "uit") for the screen reader, and in read mode the same switch disabled (row 7). The **checkbox** stays where it belongs: choosing several out of a list (a form's checkbox question, the rows of a bulk selection when P3 comes) and an explicit consent. The rule lives in the design system §2.2 next to the field family; the UI gate that already refuses raw hex and `alert()` learns to refuse a raw `type="checkbox"` outside those two uses, so the 65 shrink to the ones the rule allows and no new one appears. A switch inside an edit-and-stay form does not save on its own: it changes with the form and is saved with it, and the toast of P1 says when. | Koen, 30 Sep 2026 |
| 9 | **Surfaces and their colours differ per screen** — some pages grey on a grey ground, some cards white on grey with the text on the card; this morning the public registration page and the public form, two screens of one solution, came in a different colour combination (#1380) | Every template picks its own ground and card colour: 224 raw `bg-white` / `bg-gray-50` / `bg-gray-100` classes in the domain templates. Two screens built by the same team in the same week look like two products, and the volunteer who uses both sides sees no family resemblance where §3.1 promises one. | **A surface scale, three levels, named once.** Tokens for the *page ground* (one grey), the *card* (white, with its border and shadow) and the *inset* (a light grey block inside a card), each with its text and border colours — nothing else. The card macro and the page shell apply them; a template names a surface, never a colour. The same three levels on the public side and in the admin: §3.1 keeps "family, not twins" for type scale, photos and decoration, but the ground and the cards are the same, so a registration page and a form can only look alike. The UI gate that refuses a raw hex learns to refuse a raw surface class outside the kit, and the 224 become a migration list. | Koen, 30 Sep 2026 |
| 10 | **Betalingen shows its totals three times** — the KPI tiles at the top (Netto te betalen · Ontvangen · Openstaand), a total row as the last row of the table, and a summary block under the table with payments, claims and a grand total | Three places for one set of figures; the eye does not know which one to trust, and the bottom two only appear after a scroll. The KPI row at the top is the standard (§3.2: the management summary, the quick look "what is the state of this module") — the other two are leftovers. One thing must survive their removal: the **open** position must stay unmistakable. Today the "Openstaand" tile shows the *net* balance and colours orange only when that net is above zero — so when open claims and open refunds happen to cancel out, the tile shows € 0 in neutral ink and reads as "nothing to do", which is wrong. | **Totals live in the KPI row and nowhere else**, on this screen and as the rule for every list with figures (the classification table of row 5 carries a "KPI row" column). The table's total row and the summary block go. The "Openstaand" tile keeps its size and gains one small line under the amount when the two sides are not both zero: "€ 120 te ontvangen · € 120 terug te betalen" — and it colours when *either* side is open, not only when the net is positive. So a coincidental net of zero still says there is work, without a bigger bar and without a fourth place. | Koen, 30 Sep 2026 |
| 11 | **List screens are not all the same width** — some use the full width, others leave five to ten centimetres empty on each side and then scroll sideways inside the table | The admin shell defaults to a reading width (`max-w-5xl`, meant for forms, #620) and lets a screen opt into the wide one (`max-w-7xl`) by itself — so the width is a per-screen decision, and eight list templates answer the squeeze with `overflow-x-auto`: a scroll bar inside the table under a page that scrolls too. Two scrolls for one list, and the reader never knows whether the columns end where the table ends. | **Width by kind of screen, never per screen; no sideways scroll in a list.** A list screen — table or cards — always takes the wide width; the list layout sets the shell's width block itself, so no screen chooses. An edit or document screen keeps the reading width, because long lines hurt reading there. Inside a list there is no horizontal scrolling: a table fits its columns to the width, hides the secondary ones as the width shrinks (`hidden md:table-cell`, already the practice for status and balance) and stacks into blocks on a phone; what does not fit is a column too many, to be solved by the column chooser (P6), not by a scroll bar. The page scrolls vertically, with the browser, and nothing else scrolls. The gate on templates refuses `overflow-x-auto` on a list, so the eight become a migration list. | Koen, 30 Sep 2026 |
| 12 | **Detail screens differ in width and alignment too** — editing a household became wider a few releases ago; becoming a member on the public site is narrower; the public registration page (with the component chips on top) does not use its width and sits left-aligned, while the admin centres its screens | The same per-screen freedom as in row 11, on the screens where reading and editing happen. Measured: the admin shell defaults to `max-w-5xl` and three screens set `max-w-none` or `max-w-7xl` themselves; the public shell is `max-w-7xl` and the registration page narrows itself to `max-w-xl` *without* centring — hence a narrow form hugging the left edge of a wide page. Each screen chose; nobody chose for all. | **Two formats for a detail screen, fixed once**: on a **phone**, full width with the 16 px gutters the design system already prescribes; on a **desktop**, one reading width (`max-w-3xl`, about 770 px — long enough for a two-column field grid, short enough to read), **centred**, the same on the public site and in the admin. The detail layout sets it; a screen never does. Together with row 11 that gives the whole portal three widths and no more: *list — wide*, *detail — reading width, centred*, *phone — full*. The design system carries the table, the shells apply it through the layout blocks, and the template gate refuses a `max-w-*` on a screen's own root — the width is not the screen's to choose. The household form, "Word lid" and the registration page are the first three to fall in line. | Koen, 30 Sep 2026 |
| 13 | **Creating and editing the same thing differs by where you do it** — becoming a member on the public site creates a household in one screen: fill in, press save, pay, done; in the admin the same household is edited per card — the head member, the address, the members — and on some screens a single line inside a card is saved on its own | One record, two behaviours, depending on the door. The public flow is the one the volunteer finds natural; the admin makes the same person work three or four times for one change, and the difference is not a decision anyone took — the admin screens grew card by card. | **One behaviour per kind of screen, whatever the door.** The public creation and the admin editing of a household are the same screen type (a *record*) and follow the same save model — the one row 14 fixes. Where the public side is one form with one save, the admin side becomes one form with one save too; the per-card and per-line saves go, except where row 14's exception rule says so. The classification table (rows 5 and 12) gets a column "save model" per screen, public and admin on one line, so a difference is visible before it is built. | Koen, 30 Sep 2026 |
| 14 | **Too many save buttons** — 14 per-card edit toggles across the admin, and on some screens a save per line inside the card; once a change was lost because one of the small buttons was not pressed | Every card and some lines are their own editor with their own button. The user has to remember which of the several saves on the page is still open; a missed one is silent. And it contradicts the ideal the daily user names: *open the detail as a whole, change what you want, save once; what changed is written and lands in the change log; leaving the page with unsaved changes warns you.* | **One screen, one save, by default — with one rule for the exception.** A detail screen opens as a whole (read mode, row 7), "Bewerken" turns the whole screen into an editor, one save at the bottom (and at the top when the screen is long, row 4) writes everything at once; the service saves only what changed and the history rows say what — the change log already records per field. Leaving with unsaved changes warns, as a property of this editor kind (which brings back, for this kind, the promise dropped on 13 September as a *system* rule). Repeating groups (row 1) live inside that one form: add a row, change a row, remove a row, all committed with the screen. The **exception is by rule, not by size**: a part of a screen keeps its own save only when it is a *sub-record with its own lifecycle and consequences* — a payment, a registration line that reconciles money, a person's membership — because saving it is an action with effects elsewhere (P4), not an edit. Everything else, however complex, is one save. This is row 4's default made concrete: P1 becomes "whole screen, one save"; per-card editing stops being the norm and the 14 toggles become a migration list. | Koen, 30 Sep 2026 |
| 15 | **Editing a web page (CMS) is clumsy** — one long rich-text field (Trix) with its toolbar at the top: to insert an image at the bottom you scroll all the way up; indenting an image is two unobvious buttons; the whole thing reads as fiddly | The page editor is a single rich-text control stretched over a page's length, so every tool is where the page starts and not where the cursor is. Good enough for a paragraph, not for a page with headings, images and layout. Explicitly **not urgent** and only about the CMS pages; noted so it is not forgotten. | Two steps, far apart. **Now, if wanted**: a toolbar that sticks to the top of the viewport while the editor scrolls — one CSS change, no new library. **Later, when the portal aims at beautiful public pages** (a club or a company wanting it for its own site): a **block editor** instead of one rich-text field — a page is a list of blocks (heading, text, image with its alignment and width, gallery, call-to-action, embed), each with its own small toolbar where it sits, dragged to reorder. That is what makes professional pages editable by non-designers, and it changes how a page is stored, so it is its own change request. Europe First applies to the library choice then (Trix is Basecamp's; an EU-made block editor exists — TipTap, on ProseMirror, from Germany). **Parked as P8**; only the sticky toolbar is a quick win. | Koen, 30 Sep 2026 |
| 16 | **The icons on the buttons are gone** — download, upload, add and the like on the forms screens once carried an icon; after some release or refactoring they are plain text, and "+ Nieuw formulier" carries a typed plus instead | Measured: zero icons on the forms admin screens today, while the button macros *can* carry one (`lead_icon`); the labels carry a typed "+" — the loose-glyph remnant the icon rule (§1.4) already rejects for ⬇ and 📄. When the icons went is not traced; that they went unnoticed is the point: nothing says **when** a button has an icon, so a rebuild through the kit dropped them without breaking a rule. | **A rule for icons on buttons, with a vocabulary.** Three cases: a *text button* carries a lead icon **when its verb has an established glyph** — add, download, upload, delete, edit, copy, print, send, filter — and then always that glyph through `lead_icon`, never a typed "+" or arrow in the label; a *verb without a glyph* ("Formaat (voor AI)", "Importeren") stays text only; an *icon-only button* exists only in row actions and toolbars, with its `aria-label` (the gate already checks). The vocabulary is one table in §1.4, verb → Lucide glyph, next to the one-meaning-per-glyph table, and the gate learns two more things: a typed "+" at the start of a button label is red, and a label whose verb is in the vocabulary without its icon is red. The forms screens are the first to get their icons back — through the vocabulary, not by hand. | Koen, 30 Sep 2026 |
| 17 | **Importing a form from JSON: two ways in, and one step too many** — the import block offers a paste box *and* a file upload (the file wins when both are given); and the flow is: create a form, type its name, open it, import — and the import overwrites the name you just typed | The paste box was a concession that introduced a second concept for one action; the daily user wants it gone: a file can always be made, one way is simpler. And the creation step is wasted effort: a name typed only to be replaced. Low priority, noted as an optimisation. | **One way in, at the right moment.** The import is a **file upload only** — the paste box goes; `ui.upload_field` alone, as everywhere else a file comes in (§2.6). And the **creation screen offers the import as a way to create**: next to "+ Nieuw formulier" the choice "…of importeer een .json" creates the form *from* the file, name included, so nothing is typed twice; the import on an existing form stays for replacing its build-up (with #665's refusal once it has submissions). One concept — a file — in two places that make sense. | Koen, 30 Sep 2026 |
| 18 | **Two imports, one with a dry run and one without** — the member import from the national report shows what it will do and asks before it does it; the JSON import of a form replaces the form's whole build-up on one click behind a confirm text | The design system has the pattern (P6 *Import in steps*: dry run → report → an explicit commit whose label names the consequence; "forbidden: a commit without a dry run") but scopes it to "bulk input that can go wrong halfway", so the form import was built outside it — and it is exactly the kind of action where you want to see the consequences first: fields added, changed, removed, answers affected. | **Every import of data follows one behaviour: show what you are about to do, then "doe maar".** P6's "when" becomes *any upload or import that creates, updates or deletes records* — the member import, the form JSON import, and every import to come — with the report always in the same three lines: *nieuw · gewijzigd · verwijderd*, each with a count and the names, plus the consequences ("3 antwoorden op inzendingen vervallen"). The commit button names the consequence; leaving before it changes nothing. The same principle already governs the command line (`raak run`: dry run by default, `--apply` does what the dry run showed), so screen and script say the same thing. The form import is the first to be brought under it. | Koen, 30 Sep 2026 |
| 19 | **A good pattern exists in one place and not in the others** — from an activity you see its registrations, per component, on a sheet beside it, and from there the payments linked through those registrations; from a member or a household you do not see their registrations, and on the public side a family cannot see for which activities it is registered and whether it has paid | Measured: the related lists exist as four hand-built screens (registrations per activity; payments per activity, per household, per registration) and nowhere else; the family portal shows no registrations at all. Yet "for which activities are we registered, and is it paid?" is a question the association gets asked. | **The related-records pattern, named and generalised.** The detail of a core entity — activity, household, person, registration — carries one fixed set of tabs to its related records, in one order (registrations · payments · …), each tab being the *list screen* filtered on that entity, not a new screen: the same table or cards, the same KPI row, the same pager (rows 5, 6, 10, 11), with the filter shown and removable. Written once in the design system next to P8 (*list, detail, edit*), applied to the four existing screens first, then to the household and the person. The **same pattern on the public side**: the family portal gets a tab "Onze inschrijvingen" — the upcoming activities the household is registered for, with the payment state per registration (betaald · openstaand · ter plaatse) — the member's own answer to the question. Decide on the fine-tuning first (which entities, which tabs, which order), then implement where it is wanted. | Koen, 30 Sep 2026 |
| 20 | **No way to jump from a detail to the record it points at** — in a registration you read the household's name and the activity's name, but you cannot click through to the household or the activity | A detail names its related records as text. To look at the household behind a registration you leave the screen, open the list, search, open. An application designed twenty-five years ago had it: a small red mark next to every reference, one click, and you were on that record's detail. Not a priority; a pattern to fix. | **The reference is a link — always, and always the same link.** Wherever a detail shows a field that *is* another record (the household of a registration, the activity of a registration, the person of a payment, the component of a product), the value is rendered by one macro: the name as a link to that record's detail, with a small consistent glyph after it (the successor of the red mark, from the vocabulary of row 16), same hover, same colour, and the way back of P3 (*the way back*) so the jump is not a dead end. Row 19 is the same idea in the other direction — from the record to the lists that point at it; together they make the portal navigable as a graph: down to the lists, up to the owners. One macro, one rule in the design system, and the template gate flags a related name rendered as plain text where a reference macro exists. | Koen, 30 Sep 2026 |
| 21 | **A member registers publicly without logging in and nothing tells them they could** — the address they type is a member's, but they are not signed in, so the registration is not tied to their household and they miss the member price | A member who lands on the registration page from a mail or a share link fills it in as a guest. Nothing says "you are a member, sign in first". The wish: a **non-blocking** hint when the address is recognised — "Ben je lid? Log je dan eerst aan" with the link — and they can carry on regardless. Usability, and a little new functionality. | **The hint, yes — but for everyone, not on recognition.** Recognising the typed address means the public form looks it up, and today it deliberately never does (`registration_form.py`: whoever types a member's address would get the member price); a hint on recognition leaks the same fact in the other direction — type any address and learn whether it belongs to a member. So the hint is shown **unconditionally**, once, above the contact fields of every public registration and of "Word lid": *"Lid van RAAK? Log je eerst aan: dan staat de inschrijving bij je gezin en geldt de ledenprijs."* with the sign-in link that returns to this page (P3). No lookup, no leak, the same nudge for the person it is meant for; a signed-in member never sees it. The design system gets it as a small pattern (*the member nudge*) so it looks the same everywhere. | Koen, 30 Sep 2026 |
| 22 | **Buttons take too much room** — Opslaan, Verwijderen, Annuleren as three large buttons, on many cards, and on a phone they wrap and jump (#1367, #1387: buttons pushing a 390 px page to 682 px) | 34 action bars and 10 separate delete buttons across the admin, each bar three buttons of the same weight and size. Three equal buttons say nothing about which one matters; on a card they take a full row; on a phone they break the line or the page. | **Fewer bars, and a hierarchy inside the bar.** Fewer: rows 14 and 2 leave one action bar per screen (or per sub-record with its own lifecycle), so most of the 34 disappear with the per-card editors. Inside the one bar, three weights instead of three equals: **one primary** (Opslaan, filled), **cancel as a text button** (no border, no fill — it is the way back, not an action), and **delete apart** — a red text action at the far left, or in the `⋯` menu of the record header (row actions already cap at two plus `⋯`), never a third big button beside save. Sizes: `sm` in bars, `md` only for the one call to action on a public page. On a phone the bar sticks to the bottom of the viewport, primary full width, cancel as text beside it, delete in the menu — nothing wraps, nothing jumps, and the save is reachable without scrolling back. `ui.action_bar()` renders it so; the screenshot set at 390 px (the merge-gate eye) is the proof. | Koen, 30 Sep 2026 |
| 23 | **Spacing and grouping are decided per screen** — the distance between fields, the margins left and right, how many fields share a row, which fields sit together in a zone: each screen gets the best insight of its day, and no two agree | The tokens exist (§1.3: one 4 px scale — 12 field gap, 16 card padding, 24 between cards, 32 section) but nothing says *where each one goes* on a form, and nothing says what to group. Measured: 1 215 raw spacing classes in the domain templates — every template spaces itself. The address grid is the one grouping rule written down (a fixed UI decision), because it was argued once; every other grouping is improvised. | **The form grid, written once — the missing half of row 2's layout grammar.** Three rules. **Rhythm**: page gap > section gap (32) > field gap (12) > label gap (4), from the tokens, applied by the section and field macros — a template never writes a spacing class. **Columns**: at the reading width (row 12) a form is a two-column grid; a field is *half* by default, *full* when its content is long (a description, a URL, a textarea), *quarter* when it is a number or a code; on a phone everything is one column. **Grouping**: fields that describe one thing sit in one section with a heading, in the order a person would say them; fields share a *row* only when they are read together (street · number · bus; price · member price; from · to) — the address grid is the first instance, not an exception. Zones are sections; a section is a card or a heading in a card, never a nested box. The gate refuses a raw spacing class on a form element, and the 1 215 shrink as screens are laid out on the grid — the activity detail first (the pilot). | Koen, 30 Sep 2026 |
| 24 | **Small layout faults reach the person who validates** — "two labels stuck against each other", a badge out of line, a clipped plus: things that have to be *reported* after the build, screen by screen | Such a fault can only exist because a screen writes its own markup around a field: measured, 456 raw `<label>` / `<input>` / `<select>` / `<textarea>` elements in the domain templates next to the kit's macros, and every one of them is a place where a distance is the template's to get wrong. Standards on paper do not stop it; only markup that the template cannot write wrongly does. And nothing compares a screen with how it looked yesterday — the screenshot set exists, but it is looked at, not diffed. | **Two mechanical layers, so it cannot happen and, if it does, it is seen before the validator sees it.** First, **the kit owns the layout**: a field is only ever `ui.field(...)` — label, control, help and error placed by the macro on the form grid of row 23 — and a template composes sections and fields, never a raw form element; the UI gate refuses a raw `<label>`, `<input>`, `<select>` or `<textarea>` in a domain template, and the 456 become the migration list of rows 2 and 23. Two labels cannot touch when no template positions a label. Second, **visual regression in CI**: the 390 px screenshot set gets a baseline per screen in the repository and the e2e job fails on a pixel difference above a small threshold, so a spacing regression is red on the pull request — before the merge-gate eye, and long before HDEV. The eye stays for judgment; the diff catches what eyes miss on the fortieth screen. | Koen, 30 Sep 2026 |

## A3. To-be process — how it should work afterwards

> [!NOTE]
> *How the work should go afterwards: the same drawing and table as A2, the*
> *same lanes in the same order, so the difference is what the eye finds.*
> *Still no components: "the portal renders the poster", not "WeasyPrint*
> *renders the poster". A step that disappears, moves lane or turns into a*
> *choice is the change — name it under the drawing in one line each.*

## A4. Benefits — what the change earns

> [!NOTE]
> *The business side of the decision: what this change earns, in the*
> *measures the association counts in — hours of volunteer work saved per*
> *activity or per year, mistakes avoided, money collected sooner or not*
> *lost, members who would otherwise drop out, a process that becomes*
> *possible at all. One line per benefit, with the figure where it can be*
> *estimated and the reason where it cannot; a benefit that only the*
> *solution can name does not belong here. Set against the cost of B3, this*
> *is what says whether the change is worth doing, and when.*

## A5. Supplied material — and what it taught us

Where each parked item comes from, so the original context can be reread
instead of reconstructed:

| Source | What it holds |
|---|---|
| #913, #996 — the v2.5 design track and its golf packages | the screens as they were redesigned; F10 (ledenlijst as a dense table) left undecided there |
| #1059 — server-side pagination | built for Betalingen only, scoped down on 20 September 2026; Leden and Activiteiten deferred |
| #785 triage, the conventions debate (A12, A17) | sortable columns, column chooser, saved views, command palette, scopes-with-preview for bulk actions — confirmed by all three maker-round directions |
| the Cobalt sketch | the big blue hero card for a featured activity on the homepage |
| #1060 — the admin assistant with screen context | the base on which language-model insights could be built |

## A6. Business requirements — what the board asks, with MoSCoW

Every parked item is a candidate requirement. MoSCoW is **Parked** for all
of them: not a Won't (it may come), not a Could (nothing is planned). Each
row keeps its as-is and the intended direction.

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| P1 | The admin lists Leden and Activiteiten page like Betalingen does. | Parked → **raised** 30 Sep 2026 (A2 row 6) | Koen, 20 Sep 2026 | as-is: only Betalingen pages (#1059); decided **together with P2**, because a card list and a dense table page differently |
| P2 | The admin list screens have one settled shape — table or cards — for Leden, Activiteiten and Betalingen alike. | Parked → **raised** 30 Sep 2026 (A2 row 5) | Koen, 19 Sep 2026 | "Ik twijfel nog altijd of we betalingen ook niet terug moeten zetten naar de cards"; F10 waits until the dense Betalingen screen has been lived with; one decision covers both directions |
| P3 | Bulk actions on admin lists (select many, act once). | Parked | Koen, 19 Sep 2026 | "bulk selectie zou ik voorlopig niet doen"; when it comes, scopes-with-preview as sketched in the conventions debate |
| P4 | The homepage can feature one activity in a large hero card. | Parked | the Cobalt sketch; left out of golf 11 | needs a "which activity" choice by the board and sits above an agenda that already shows the same; candidate: a CMS choice once the board misses it |
| P5 | The admin assistant offers language-model insights on top of the screen context it already has (#1060). | Parked | 20 Sep 2026 | Mistral, Europe First; under the standing rule that every claim carries a clickable source and unsupported claims are dropped |
| P6 | Admin tables follow one set of conventions: sortable columns as the norm, a column chooser, saved views, a Ctrl-K command palette. | Parked | #785 triage | sized for the ERP ambition, not for one release |
| ~~P7~~ | ~~STT and TTS in the Raakje overlay~~ | **un-parked** 20 Sep 2026 | Koen | mic + read-aloud, identical to the rapporten-Raakje — "Raakje is the same everywhere; the only difference is the public security boundary"; now #1075 |
| P8 | Web pages are edited as blocks — heading, text, image, gallery, call-to-action — each with its tools where it sits, so a non-designer can make a page that looks professional. | Parked | Koen, 30 Sep 2026 | from A2 row 15; not urgent; taken up when the portal aims at public pages for a club or a company; its own change request then |

## A7. Non-functional requirements — security, privacy, house style, tenants

> [!NOTE]
> *The requirements every change request is tested against, each answered*
> *explicitly at business level, "not applicable" included. How they are met*
> *belongs in Part B:*

## A8. Acceptance criteria — what the business signs off on HDEV

> [!NOTE]
> *Criteria the business signs off on, each testable by a person on HDEV*
> *without reading code, each pointing at a requirement and at the steps of*
> *the walkthrough (B2.1) that show it. These are the business's unit tests;*
> *the developer's tests live in Part B.*

---

# Part B — The solution

*Empty by design: Part B is written per item, in that item's own issue or
change request, when it is un-parked. The headings stay so the template is
recognisable; every note block below is the template's.*

## B1. Solution outline — the solution and the decisions that shape it

> [!NOTE]
> *The solution in one paragraph, and the decisions that shape it, each with*
> *the alternatives weighed and why they lost (Europe First named where a tool*
> *or service is chosen).*

### B1.1 Functional analysis — the derived requirements

> [!NOTE]
> *The derived, finer-grained requirements the solution answers, traced to A6.*
> *This is design work by the analyst, not business input — which is why it is*
> *not in Part A.*

## B2. Architecture — three readers, three questions

> [!NOTE]
> *B2 answers three questions for three readers, in this order: the business — does the solution fit our to-be*
> *process and our requirements (B2.1)? the architect — how does the whole*
> *hang together across the modules, and what is touched (B2.2)? the build*
> *teams — what exactly must happen in each module, and what does it cost*
> *(B2.3)? Each reader should be able to stop after their section.*

### B2.1 Fit with the process and the requirements — for the business

> [!NOTE]
> *Two things. First, the **application usage drawing**: the to-be process*
> *of A3 once more — same lanes, same activities — with, in every activity*
> *box, a second line naming the screen or module that serves it, the box*
> *coloured per module (`classDef`, one legend line). Every step has a home*
> *or is marked "outside the portal"; a module no step uses is not part of*
> *this change. Two audiences (those who set up, those who use) means two*
> *drawings. Second, the **traceability matrix** — the one place where a*
> *requirement's thread is followed from left to right, so it is not kept*
> *anywhere else: one row per requirement of A6 — R · how the solution meets*
> *it, in the words of the role that will see it · the derived requirements*
> *(F, B1.1) · the module that builds it (B2.3) · the test that proves it*
> *(B7) · the acceptance criterion the business checks (A8). An empty cell*
> *is a finding: a requirement without a test, a test without a*
> *requirement. A Won't gets a row that says so. Third, the **walkthrough** — how the*
> *business tests this on HDEV: one numbered*
> *script per role of A3, in the order of the to-be process, happy path*
> *first and then the turns where it must refuse or fall back; each step*
> *names what to do and what to see — nothing else, it is a script. The*
> *link to the acceptance criteria lives in A8, whose last column names the*
> *steps that show each criterion; every criterion has at least one step.*
> *The closing comment of each issue points at the walkthrough instead of*
> *rewriting it. This is*
> *the page a board member reads to say "yes, that is how we will work, and*
> *this is how I will check it".*

### B2.2 The whole across the modules — for the architect

> [!NOTE]
> *The **application structure drawing**: one subgraph per module touched,*
> *inside it a box per layer (screen · view-model · service · entity ·*
> *facade · migration · template) — a separate box for what is **new** and*
> *for what is **changed** in that layer, and one grey box for what is only*
> *used. Here the colour is the kind of change, not the module: green new,*
> *orange changed, grey unchanged — the module is the subgraph, and B2.1*
> *already coloured per module. One legend line. Arrows between modules*
> *only through a facade (`api.py`), as the import gate enforces; external*
> *systems and data stores as their own boxes. Then the **data model at a glance**: a Mermaid `erDiagram` of the*
> *entities involved with their key columns and relationships, cardinality*
> *on the edges, soft references across schemas drawn as relationships too,*
> *and what is new or changed marked in the label. Under it, in prose: who*
> *calls whom and through which facade, the*
> *direction of every new dependency, the transaction boundary, and the*
> ***impact on the existing architecture** — which existing modules, tables,*
> *screens and contracts are touched, and how the layer rules*
> *(`docs/code-style.md`, the import gate) hold. This is where a*
> *reviewer checks that the change does not bend the architecture.*

### B2.3 Per module: what must happen — for the build teams

> [!NOTE]
> *One subsection per module touched, in build order, each with the same*
> *five headings: **screens** (which, what changes, at which width it is*
> *judged), **code** (view-model · service · entity · facade — the functions*
> *by name), **database** (schema, table, each column with its type,*
> *nullability and constraints, the `ON DELETE` of every FK, the migration*
> *and whether it is additive), **templates*
> *and mail**, **tests** (which of B7). No effort here: the effort per*
> *module and phase is the table of B3, where the cost is added up. Which*
> *requirements a module serves is read from the matrix of B2.1, not*
> *repeated here. A module that is only used, not changed, gets one line. **Reporting*
> *is always one of the modules**, touched or not: the engine reads the*
> *tables through SQL views in the `reporting` schema and through its object*
> *universe, so for every column this change adds, renames, retypes,*
> *retires or gives a new meaning, its subsection says which views and*
> *objects read it (measured, not recalled) and in which phase the view*
> *follows — a view that reads a changed column changes in the same*
> *migration as the column, or the phase says why not; a value change on a*
> *column a view reads is checked against the saved reports on every*
> *environment before the migration. "Reporting — none: no view reads these*
> *columns" is a subsection too.*

### B2.4 Cross-cutting impact — the checklist of what gets forgotten

> [!NOTE]
> *One table, every row answered, "no" included, one sentence each:*
> *reporting views and saved reports (B2.3) · existing tests, e2e*
> *golden flows and 390 px screenshots (B7) · fixed UI decisions and*
> *`CLAUDE.md` · design-system documentation · code lists · events and*
> *handlers · mail templates · migration: additive or contract*
> *(#1255) · tenant settings · env vars · JSON routes and API callers ·*
> *external services (Mollie, mail). A "yes" points at the section that*
> *handles it. The next thing that gets missed becomes the next row.*

## B3. Cost — investment and running cost, and what operations must know

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

## B4. Detailed decisions — one subsection each, with the reasons

> [!NOTE]
> *The design decisions in full, one subsection each, with their reasons.*

## B5. Privacy and security — the mechanics behind A7

> [!NOTE]
> *How A7's privacy and security answers are implemented: what leaves the*
> *system to whom, what is sanitised, what is logged.*

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
> *paths listed beside it, and an e2e test that goes red on one of them is*
> *expected, not a surprise. "None" is an answer.*

**The approach, agreed on 30 September 2026 — to be worked out once the
as-is (A2) is complete and the solution (B1, B4) is designed:**

- **An end state first.** Part B fixes where the design is going — the
  North Star — including what is not needed yet, so that every step can be
  judged by whether it moves towards it.
- **A roadmap in smart steps**, release by release, piece by piece. No
  big-bang redesign.
- **Quick wins up front**, because the portal must impress: whoever is
  shown it should say "that looks good". Rows 3, 10 and 15's sticky
  toolbar are the first candidates (list below).
- **Concept → pilot → release → roll-out.** A concept is prepared with
  screenshots first, then built on **one screen**, tested, and run through a
  release so it is lived with and tuned; only then does a developer roll it
  out everywhere. Pilots are chosen on purpose: the **activity detail**
  (the richest edit screen, rows 2, 3, 7, 8, 14), the **public household
  creation** (public, and the same record as the admin household — rows 12,
  13) **combined with the forms** (row 9). Once those are right they are the
  standard — "this is our core" — finished and then carried through.
- **External advice, at two moments, from a second model rather than a
  hired designer** (a separate Claude, ChatGPT or Mistral session — Mistral
  first, Europe First; it has been done before for laying out screens).
  Two expertises, asked separately because they answer different questions:
  **graphic design** — surfaces, type, spacing, icons, the weight of buttons
  (rows 8, 9, 16, 22) — asked once, when the end state is drafted and before
  the first pilot, on the design-system page and a handful of screenshots;
  **usability** — does the pattern do what the user expects (rows 2, 7, 14,
  19, 20) — asked per pilot, on the concept's screenshots, before it is
  built. Not at roll-out: by then the questions are answered. What such a
  review says is checked against our own measurements before it changes a
  decision (unsupported claims are dropped, as with every AI answer), and
  its dated findings land in the Q&A log. Much we can decide ourselves;
  the review is for what we cannot see because we look at it every day.
- The design system (`docs/design-system.md` and the live page) is where
  the end state is written and where each rolled-out pattern lands; this
  change request holds the roadmap.

*Remarks made while listing the as-is that concern phasing — quick wins,
what can wait, what belongs together — are collected here until the phases
are shaped:*

- Row 10 (Betalingen: totals in the KPI row only, the open tile with its two sides) is the simplification of one screen with no new component — a quick win that can go before the rest.
- Row 17 (JSON import: file only, and import as a way to create) is low priority — small, but not a quick win worth showing; it rides along when the forms screens are touched.
- Row 15 (the CMS page editor) is parked as P8; only the sticky toolbar is a quick win, the block editor is a change request of its own, later.
- Row 3 (the collapsed section for the external links) needs no data change and no new component beyond a disclosure the kit already has — a quick-win candidate, and a first instance of the layout grammar of row 2.

## B7. Tests — what the build must prove

> [!NOTE]
> *Two levels. **What the build must prove:** the*
> *new tests, each able to go red, guards proven by violation — numbered, so*
> *B2.3 can point at them per module. **Impact on the test landscape:** which*
> *existing suites, e2e golden flows and screenshot sets change or must be*
> *redone because of this change, per module, with the reason — a screen*
> *that moves, a route that changes, a fixture that no longer matches. A*
> *change that breaks no existing test says so, and why that is plausible.*

## B8. Rule and gatekeeper — what this fixes for all future work

> [!NOTE]
> *An architectural change request fixes a way of doing things, not just one*
> *instance of it. This section makes that explicit, so the decision outlives the*
> *change and the next development follows it without anyone remembering to ask.*
> *Three parts; "no gate" is an answer, with the reason.*
>
> *A rule is fixed only when its gate runs in CI on every push. A rule that lives in a document is a hope; a rule whose test*
> *goes red on the next pull request is a property of the codebase. So the gate of*
> *B8.3 is a pytest in `backend/tests/` that `backend-tests.yml` runs on every*
> *push and PR — not a script someone remembers, not a review checklist. Where*
> *that is impossible, B8.3 says so and names what catches it instead*
> *(a review agent, a release step), and that is a weaker guarantee, written*
> *down as one.*
>
> *1. The rule. One sentence a reviewer can apply, in the form the decision*
> *   takes from now on ("a code list is a code table in the owning domain's*
> *   schema, a label table per language, and an `Enum` only where code branches*
> *   on the value"). Where it ends up: `CLAUDE.md`, `docs/code-style.md` or the*
> *   architecture document — name the place.*
>
> *2. The reach and the baseline. Where the rule applies (the whole codebase,*
> *   or which modules) and how many places violate it today, measured on the*
> *   branch, not recalled. This change request brings that number down — say to*
> *   what. A number that cannot be counted is an intention, not a rule (CR-04,*
> *   Making it checkable).*
>
> *3. The gate. Which test fails when a new development breaks the rule: what*
> *   it looks at, what its message says, and the violation it was proven with*
> *   (B7). Two shapes, chosen by the baseline:*
> *   - Ratchet when the count is not yet zero: a frozen list of today's*
> *     violations that may only shrink (the #780 pattern). Nothing new may join*
> *     it; an entry that disappears from the code must leave the list.*
> *   - Hard gate when the count is zero after this change: any violation is*
> *     red.*
>
> *   Gates come last, not first (CR-04): a gate with a growing exemption list is*
> *   a dead rule, and a gate written too early freezes the wrong understanding.*
> *   Where the rule cannot be checked mechanically, say so and hand it to the*
> *   judgment layer (the `design-conformiteit-bewaker` agent, review) instead of*
> *   pretending a grep is a gate.*
>
> *   The gate is also what makes the rule cheap to follow: for a new case it*
> *   spells out the steps ("a new code list needs a table, a label row per*
> *   language, an `Enum` member and a label call") and fails on the one that was*
> *   forgotten, with the name of the missing piece.*

## B9. Prototype findings — what was measured before the build

> [!NOTE]
> *What was learnt from prototypes before the build (measurements, refusals,*
> *things that did not work).*

## B10. Decisions log — dated answers and open proposals

| Date | Decision | By |
|---|---|---|
| 20 Sep 2026 | CR-11 is a parking lot, not a work order; pagination in v2.5 on Betalingen only; the rest decided piece by piece later. | Koen |
| 20 Sep 2026 | STT/TTS in the Raakje overlay un-parked: mic + read-aloud, the same Raakje everywhere (#1075). | Koen |
| 30 Sep 2026 | Brought onto the change-request template of 30 September; the parked items are candidate requirements P1–P6 in A6. | Koen |
| 30 Sep 2026 | Background: the platform will serve other organisations than RAAK (a company's webshop among them) — a separate change request; here the end state keeps kit and brand apart. | Koen |
| 30 Sep 2026 | CR-11 becomes the GUI redesign's end state and roadmap: North Star first, quick wins up front for attraction, each concept prepared with screenshots, built on one pilot screen, run through a release and tuned, then rolled out; pilots: the activity detail, the public household creation with the forms. The as-is (A2) is listed first, the solution and the approach follow. | Koen |

## Q&A log — asked once, answered here

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 30 Sep 2026 | Does CR-11 become a real change request on the new template, or stay a parking lot from which each item gets its own CR or issue? (Claude) | Koen, 30 Sep: a real change request — the end state of the GUI and the roadmap towards it; the parked items stay in A6 as candidates, the pains are listed in A2 first, then the solution and the approach (B6). |
| Q2 | 30 Sep 2026 | Which of P1–P6 are taken up now, and is there new material — the dense Betalingen screen lived with (P2), the board missing a featured activity (P4)? (Claude) | *open* |

## Non-goals — deliberately outside this change

- Building anything from this list without an un-park decision and its own issue.
- Parking new GUI candidates on a release tracker instead of here.
- Making the platform usable by other organisations (a webshop for a company, another association's menu and brand) — its own change request; this one only keeps kit and brand apart so that one becomes possible.

## Relationship to existing work — issues and change requests

- **#913, #996** — the v2.5 design track this list was deferred from.
- **#1059** — pagination, built for Betalingen; P1 is its continuation.
- **#785** — the conventions debate; P3 and P6 come from its triage.
- **#1060** — the admin assistant's screen context; P5 builds on it.
- **#1075** — STT/TTS in the Raakje overlay, the one item un-parked so far.
- **CR-08 (visual), CR-10 (Design Studio)** — the design work this list sits next to.
