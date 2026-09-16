# Change Request 10 — Design Studio: posters and social images from an activity

**Project:** Web Portal "Raak Millegem"
**Status:** Shaped with Koen on 16 September 2026 (brainstorm on
`feature/designstudio`). All decisions in §3 are settled; §8 records Koen's
answers. **Phase 0** (the registration deadline, §3.8a) is #974 and
assigned to **v2.5** (#925). The Design Studio itself (phases 1–4) is not
on a release yet.
**On hold (Koen, 16 September 2026, late evening):** before issues are written
or anything is built, the CR gets a review from all sides with Fable 5.1, and a
look at existing template tools for concepts worth borrowing. The prototypes
so far started from the unit's own posters. The proposals awaiting Koen's
answer are listed in §8a.
**Apply to:** a new `designstudio` domain (backend + admin screens), a
contacts table on `activities`, two new media kinds, and the name search
moving into MDM. The registration deadline column is phase 0 (#974). Rendering reuses
WeasyPrint (#258); text proposals reuse the Mistral provider (chatbot).

---

## Goal

Units announce their activities with a printed poster (A3/A4) and with
images on Facebook and Instagram. About half of the posters are printed at
home. The rest are ordered from online print services. Today each poster is made by hand — in Word, Canva, LibreOffice
Draw, or by asking a chatbot — and each one looks different. A chatbot
poster cannot be amended a week later: "add this line" gives a new poster.

This change request adds a **Design Studio**:

1. **Start from an activity.** Title, dates, times, location, price and
   registration link come from the activity. Nobody retypes them.
2. **Pick a template and a colour pair.** Templates are designed centrally
   in the Raak house style. Units choose one; they do not edit it.
3. **Fill in what the activity does not know**: a subtitle, a few
   highlights, an image — uploaded, taken from the activity's photo archive,
   or generated.
4. **Render every format at once**: a print PDF for borderless home
   printing and images for social media.
5. **Mark one design final.** It becomes the activity's poster on the
   website (and, once the landscape layout exists, its share image). When the activity changes afterwards, the
   design says it is stale and re-renders with one click.

AI helps in two places, always as a proposal: **text suggestions**
(Mistral) and **illustrations** (Black Forest Labs, EU endpoint, with a
quota per unit).

## 1. The source material (measured, 16 September 2026)

Koen collected the input in his Nextcloud project folder
(`designstudio/huisstijl Raak en Raak Millegem`). It stays there: the
example posters carry names, phone numbers and addresses, and none of that
enters this repository.

### 1.1 The Raak house style guide (9 pages, for local groups)

- **Eight colours, all equal** — no primary or secondary colour. The
  general rule is **at most 4 or 5 colours per design**.

  | Name | HEX | RGB | CMYK | PMS |
  |---|---|---|---|---|
  | Golden Yellow | `#ffce00` | 255 207 1 | 0 18 100 0 | Yellow 012 |
  | Pumpkin Orange | `#f16532` | 242 101 51 | 0 75 89 0 | 1645 |
  | Cool Green | `#3aba9b` | 58 187 155 | 70 0 51 0 | 3255 |
  | Dark Green | `#005d29` | 0 93 41 | 100 0 100 56 | 348 |
  | Hot Pink | `#f17fb2` | 242 127 178 | 0 64 0 0 | 237 |
  | Ocean Blue | `#0051a4` | 0 82 164 | 100 77 0 0 | 2935 |
  | Watermelon Red | `#ee3a37` | 239 59 55 | 0 92 84 0 | Red 032 |
  | Indigo | `#460359` | 70 3 89 | 68 100 0 47 | 2617 |

  (The guide's RGB and HEX differ by one unit in places; HEX is used.)

- **Twelve permitted duo combinations** for text on a background, usable in
  both directions (light text on dark, dark text on light):

  | Light | Dark |
  |---|---|
  | Golden Yellow | Ocean Blue · Indigo · Dark Green · Pumpkin Orange · Watermelon Red |
  | Cool Green | Ocean Blue · Indigo · Dark Green |
  | Hot Pink | Ocean Blue · Indigo · Dark Green |
  | Watermelon Red | Indigo |

  The guide also shows a page of *forbidden* combinations. The duo rule
  covers text on a background. It does not apply to graphic elements or
  backgrounds.

- **Logos:** the wordmark without a baseline, the wordmark with a baseline,
  the pin, and the wordmark with the local group's name. The group name
  always goes into the baseline as "Beleef meer in <group>", split over two
  lines when it is long.
  - The **pin** is always placed on a coloured field, **never on an image**.
  - The wordmark in the pin **stays white** on every combination.
  - The pin is not combined with a baseline or group name.
  - A monochrome logo exists for black-and-white print.

- **Typeface:** Radio Canada Big (Google Fonts, OFL) for all text, in
  regular, medium, semibold and bold.

### 1.2 The unit's assets

- **Official SVG lockups** for Raak Millegem, supplied on 16 September 2026.
  There are five: four colour variants and one monochrome.
  - Each is a coloured tile with the white wordmark and the baseline
    "Beleef meer in Millegem". The file name gives the tile colour first,
    then the baseline colour.
  - The four colour variants are Ocean Blue/Golden Yellow, Ocean Blue/Hot
    Pink, Golden Yellow/Indigo and Dark Green/Golden Yellow. All four are
    permitted duos (§1.1).
  - The monochrome variant is black/white.
- **Measured:** all five files have the same structure — the same viewBox
  (702 × 451), 17 paths, and no embedded bitmaps, scripts or external
  references. They differ **only in their fill values**: the tile colour,
  the baseline colour, and white.
- The older `.ai` and `.png` files are superseded.
- **The neutral Raak lockup** (wordmark with the baseline "Beleef meer!", no
  unit name), supplied on 16 September 2026:
  - **24 PNG files**, 6090 × 4060 px;
  - they are **exactly the twelve permitted duos of §1.1, each in both
    directions** (tile colour / baseline colour). Raak itself thus offers the
    lockup in every permitted duo.
  - **One SVG** followed the same day: Ocean Blue tile, Golden Yellow
    baseline. It has a 2048 × 1365 viewBox, 15 paths, no bitmaps, scripts or
    external references, and the same structure as the unit lockups. It is
    the master for recolouring, so the PNGs are no longer needed.

  (In the file names, "appelblauwzeegroen" is Cool Green and "groen" is Dark
  Green.)

### 1.3 Four example posters, and what they share

| Example | Made with | Format | Bleed | Character |
|---|---|---|---|---|
| Play afternoon + summer bar | chatbot (image) | A3 | none | line illustration, date badge, icon list, price badge, footer bar with contacts, supporter logo |
| Walking group | LibreOffice Draw (chatbot image) | A3 | none | icon list, photo + inset photo, **grid of six concrete dates**, recurrence line ("every 2nd Monday") |
| Father-and-son evening | Canva | A3 | trim box only | full-bleed photo, colour wave, text bottom, **responsible publisher (V.U.)**, funder logo |
| Bowling | Word | A4 | none | text flyer: "… organiseert", title, date-time-location, long explanation, photo, registration deadline, contact persons |

None of them has a real bleed: in all four, the trim box equals the page.

A Word "flyer template" names the text flyer's slots:
- "RAAK Millegem organiseert", title, date-hour-location, extra info;
- explanation part 1, image(s), explanation part 2;
- "register via the website until …";
- "more info from <name>, <phone>, <e-mail>".

The chatbot brief that produced the first two posters asks for:
- the house style, and line drawings when the supplied photos do not fit;
- **"printable on A3 with 5 mm bleed so a borderless print cuts off no colour
  and leaves no white edge"**;
- an Instagram format;
- delivery both as an image and as a borderless A3 PDF;
- no rounded corners.

### 1.4 Content blocks, derived from the examples

| Block | In examples | Source |
|---|---|---|
| Kicker ("RAAK <unit> organiseert") | 1 | unit name, toggle |
| Title (large, 1–3 words per line) | 4 | activity |
| Subtitle ribbon ("Wandelen", a place name) | 3 | design |
| When: one date + time range, **or** a recurrence line + concrete dates | 4 | activity dates; recurrence line from design |
| Where | 4 | activity |
| Highlights: icon + short line, up to six | 2 | design |
| Price badge ("Gratis", "Alles aan 1 euro") | 2 | activity prices; wording from design |
| Welcome line ("Iedereen welkom!") | 2 | design |
| Explanation, one or two paragraphs | 1 | design |
| Registration: link, QR code, deadline | 2 | activity |
| Contact: website, e-mail, contact persons | 4 | the activity's contacts: members and/or the association |
| Supporter / funder logos | 2 | media, kind `sponsor` |
| Responsible publisher (V.U.) | 1 | out of scope for now (§3.10) |
| Image slot, optional inset image | 4 | design |

## 2. What exists to build on

| | measured |
|---|---|
| PDF | **WeasyPrint 70** is in the backend image (#258) with Pango/Cairo. It supports CSS Paged Media, including `@page { bleed; marks }` and trim/bleed boxes. |
| Fonts | `backend/app/static/fonts/` already holds **Radio Canada Big** (variable) and Inter. |
| Icons | Lucide (ISC) through `ui.icon()` — one line style, already the UI norm. |
| Activity | `name`, `slug` (#884, stable share link), `location`, `poster_url`, several `ActivityDate` rows (date + optional time range), and components with `price` / `member_price` / `is_free`. **There is no public description** — `notes` exists but no screen uses it. **There is no registration deadline.** |
| Poster slot | `MediaAsset(kind="activity_poster")` — an image or PDF that takes precedence over `poster_url` and is already shown publicly (#223). |
| Photos | `MediaAsset(kind="activity_photo")` — the activity's archive; `kind="sponsor"` — supporter logos. |
| Image processing | `media/images.py` resizes every upload to **1600 px** on the longest side. That is too small for print (A3 at 300 dpi is 3508 × 4961 px). |
| Organisation | website and e-mail as the organisation's contact details (#945); the person↔organisation relation arrives with CR-09 §3.11. |
| LLM | `chatbot/providers` — the Mistral provider behind an `LLMProvider` interface, plus a mock. |
| Secrets | `kernel_tenant_settings` with encrypted values (Fernet). |
| Pillow | 12.3, already a dependency. |

## 3. Decisions

### 3.1 Templates, not free generation

A poster is **data rendered through a template**. The alternative — asking a
chatbot for a complete poster — cannot be amended, cannot keep facts in
sync with the activity, and gets text in images wrong. AI supplies
*ingredients* (an illustration, text proposals). It never supplies the
poster.

### 3.2 Template technology: Jinja + CSS → WeasyPrint, ornaments in SVG

- A template is a **Jinja HTML file plus a stylesheet**, rendered by the
  WeasyPrint that is already in the image. Logos, waves, pins and badges are
  **SVG files** embedded in that HTML, and can be edited in Inkscape.
- **Why not pure SVG:** SVG has no text flow. A long title or a longer
  location overflows its box instead of wrapping or shrinking. The examples
  are full of text whose length varies per activity.
- **Why not ODF / LibreOffice headless:** it adds several hundred MB to the
  image, placeholder replacement in ODG cannot fit variable text, and it
  would be a second rendering stack next to WeasyPrint.
- **Templates live in the repository**, versioned (`key` + `version`). They
  are code: designed centrally, reviewed, tested. A design records the
  template version it was rendered with, so an old design still re-renders
  the way it looked.

Europe First: WeasyPrint is open source, self-hosted, and maintained by
CourtBouillon (FR). This was already approved for CR-09.

### 3.3 The house style is data, and a gate checks it

- The eight colours, with CMYK and PMS, and the twelve duos (§1.1) become
  **one constant in code**. Templates reference them by name, never by hex.
- A design picks **one duo**. The template derives its palette from that
  duo plus at most two accents drawn from the eight colours. The picker
  offers only permitted duos, so a forbidden pair cannot be chosen.
- **Enabled for now: three duos** (Koen, 16 September 2026 — the ones the
  unit uses today):

  | Tile | Baseline |
  |---|---|
  | Ocean Blue | Golden Yellow |
  | Dark Green | Golden Yellow |
  | Golden Yellow | Indigo |

  The constant holds all twelve; a short list of enabled duos limits the
  picker. Enabling another duo is a one-line change. (The baseline on the
  yellow tile is Indigo, as in the unit's own yellow lockup.)
- A gate test fails when a template contains a hex value outside the eight
  colours, and when a template declares more than five colours. This is the
  same shape as the existing css gate.
- **Logo rules are template rules:**
  - the pin sits only on a coloured field;
  - the wordmark in the pin is white;
  - no pin together with a baseline.

  The lint gate enforces what it can mechanically. The rest is template
  review.
- **Logos are tenant assets, not repository files.** Each unit uploads its
  lockups as SVG (colour variants and monochrome). The repository ships a
  neutral placeholder only.

  **The lockup is recoloured per duo** (approved by Koen, 16 September
  2026). A unit uploads **one** SVG. The
  engine sets the tile colour and the baseline colour from the design's duo,
  in either direction; the wordmark stays white. That gives one source
  instead of 24 files, and the logo tile always matches the poster.

  The basis is §1.2: the unit's variants differ only in those two fill
  values, and Raak's own neutral set covers every permitted duo in both
  directions. The recolouring needs a structured master — the tile and the
  baseline recognisable by an id — and the upload check refuses an SVG
  without it. The monochrome variant stays a separate upload for
  black-and-white print.

- **The neutral lockup is the fallback** for a unit without its own lockup.
  It is a platform asset in the database, like the unit lockups, and not a
  repository file. It is the supplied SVG (§1.2), recoloured in the same way.

  **Uploaded SVG is sanitised** — no `<script>`, no event attributes, no
  external references — because an SVG served to a browser is active
  content. The sanitiser gets a test that proves a scripted SVG is refused.

- **The poster follows the Raak house style guide**, not the site's
  design-track palette (#913): a poster carries the Raak brand outside the
  website. Koen supplied the guide as the input for this CR.

### 3.4 One design, several layouts — no cropping

Cropping one master does not work across the ratios involved. A portrait A
page is 1 : 1.41; a Facebook event cover is 1.91 : 1, so cropping would
remove more than half of the page. Instead, **each template defines one
layout per ratio**. All layouts use the same content, the same image and the
same duo.

| Layout | Ratio | Serves | Size |
|---|---|---|---|
| `print_a` | 1 : √2 | A3 and A4 print — **one layout**, because all A sizes share the ratio. Units and type scale with the page. **Phase 1.** | 297 × 420 / 210 × 297 mm |
| `feed_portrait` | 4 : 5 | Instagram / Facebook feed. **Phase 1.** | 1080 × 1350 px |
| `square` | 1 : 1 | Instagram / Facebook post (phase 4) | 1080 × 1080 px |
| `landscape` | 1.91 : 1 | Facebook event cover **and** the share image (`og:image`) (phase 4) | 1920 × 1005 px |
| `story` | 9 : 16 | Stories (phase 4) | 1080 × 1920 px |

- **Blocks carry a priority.** Smaller layouts drop blocks from the bottom of
  the list:
  1. the explanation;
  2. the concrete-dates grid, replaced by the recurrence line;
  3. highlights beyond three;
  4. contacts.

  Title, date, place, image and the link are never dropped.
- **Social layouts keep text inside a safe zone**, because Facebook crops the
  event cover differently on mobile.
- **The image has one focal point**, stored as x/y percentages. Each layout
  crops the image around that point (`object-position`), so the swing stays
  in view in every layout.

**Phase 1 renders A3, A4 and 4:5** (Koen, 16 September 2026). The Facebook
event cover and the square format come later. **A5 is not a separate
output:** it has the same ratio as A4, so the A4 PDF prints on A5 paper at
reduced size.

### 3.5 Print: one PDF for borderless home printing

Decided by Koen on 16 September 2026: **borderless printing at home is the
target**, and it works well on his printer. Units that use a printer order
online, where a bleed file is not a must. **Print-shop output — bleed,
crop marks, CMYK/PDF-X — is out of scope for now.**

- The PDF page is **exactly A3 (or A4)** and the colour runs to the page
  edge. A borderless printer enlarges the page slightly and prints past the
  paper edge, so a few millimetres are lost on each side. Text therefore
  stays inside a **safe zone of at least 8 mm**.
- A PDF with bleed would be the wrong file for this printer: its page is
  10 mm larger, so the driver shrinks it or cuts it unpredictably. This
  resolves the "5 mm bleed" wording in the brief (§1.3): what the brief
  wants is colour to the edge, and the home PDF delivers that.
- Validation includes one real borderless print on Koen's printer, to
  measure how much the printer actually crops. The safe zone is a single
  template constant, adjusted to that measurement.
- **Measured on 16 September 2026** with an edge-test page (numbered marks
  1–12 mm from each edge). The lowest visible mark was 5 at the top, 2 at the
  bottom, and 3 on each side, so the printer crops less than 5, 2 and 3 mm
  respectively. **The 8 mm safe zone stands**: it leaves at least 3 mm
  everywhere. The crop is not symmetrical, so an A3 that is correct on one
  printer is not proof for another; the edge-test page ships with the
  Design Studio as a download.
- Adding a bleed variant later is cheap. The layout already extends its
  colour fields to the edge, and WeasyPrint supports `@page { bleed }`.

**Colour: RGB, deliberately.** Koen asked for CMYK straight away if it is
feasible, and otherwise a route that does not force a change of modules
later.
- For the target printer, **RGB is the right output, not a compromise**.
  An inkjet driver takes RGB and does its own conversion to its inks. A CMYK
  PDF is converted back by the driver, and colours usually get worse.
- CMYK matters for offset print, which is out of scope (above).
- **The route to CMYK needs no module change.** A CMYK or PDF/X file is a
  post-processing step on WeasyPrint's PDF: Ghostscript converts it with an
  ICC print profile. Ghostscript is an apt package and self-hosted, but its
  maintainer, Artifex, is US-based, so the Europe First comparison is made
  when that step is added. The CMYK and PMS
  values stay recorded in the palette constant (§3.3), so the brand values
  are there when that step is added.

**Image resolution:** a rendered print design reports the effective dpi of
every image at its placed size. Below 150 dpi, the editor shows a warning.
It does not block the render.

### 3.6 Raster output

WeasyPrint no longer writes PNG. Images are produced by **rendering the
layout's PDF to a bitmap with `pypdfium2`** (Apache-2.0/BSD, a
self-contained wheel, in-process), then encoding it with Pillow:
- **JPEG** for photos and illustrations;
- **PNG** where the palette is flat.

The alternative, poppler's `pdftoppm`, needs a subprocess and an apt
package. Neither option sends data anywhere.

A design can be downloaded file by file, or as one ZIP. File names follow
`<activity-slug>_<layout>_<size>.<ext>`.

### 3.7 Facts stay live; design text belongs to the design

One place per fact:
- **From the activity, always live:** title, dates and times, location,
  prices, registration link and QR code (from `slug`), registration
  deadline, contacts.
- **From the organisation:** logo lockup, unit name, and — when the
  association is a contact — its website, e-mail and mobile number.
- **Only on the design:**
  - a title override (for line breaks: "SPEELNAMIDDAG / EN / ZOMERBAR");
  - tagline, explanation, subtitle, recurrence line, highlights, welcome
    line;
  - price-badge wording;
  - images and focal point;
  - supporter logos;
  - the kicker toggle.

A design stores its **inputs, not its renders**. "Add this line a week
later" is an edit plus a re-render.

### 3.8 Tagline and explanation live on the design, for now

Koen, 16 September 2026: the activity is **not** extended with a tagline or
a public description yet. Both are entered **in the Design Studio**:
- `tagline` — one short line (≤ 90 characters), the hook under the title;
- `explanation` — plain text with paragraphs, for the layouts that have
  room for it.

The public website does not change. Later, the activity can get these
fields in the activities module, and the Design Studio will read them from
there instead. When that happens, the design fields become overrides or
disappear, so that there is one place per fact.

`notes` is not repurposed: its meaning was never defined, and reusing an
undefined column reintroduces the ambiguity. Whether to remove it is outside
this CR.

A **registration deadline** is added as a real rule — see §3.8a.

A recurrence engine is **not** added. The concrete dates are the existing
`ActivityDate` rows. The phrase "every 2nd Monday" is design text.

### 3.8a A registration deadline that the form enforces

Koen, 16 September 2026: some activities have a deadline (bowling, a wine
estate visit, …). Today it cannot be entered, and **after that date,
registering must no longer be possible**. A deadline printed only on a
poster would be a promise the form does not keep, so the deadline is a rule
of the activities domain first, and a poster field second.

- **One field on the activity:** `registration_closes_on` (a date, null for
  no deadline). The date is **inclusive**: registering is possible through
  the end of that day, Belgian time.
  - It is an activity-level date, because the examples (bowling, wine
    estate) are activity-wide.
  - A deadline per component is not added until an activity needs one.
- **The service decides whether registration is open.** Today the
  "no longer open for registration" check (no future date left) sits inline
  in the registration route, and the public card works out by itself
  whether to show the button. With a second reason to be closed, both
  conditions move into **one service function**. The route and the public
  screens call it, so they can never disagree about whether an activity is
  open.
- **Enforced on every path that creates a registration.** The public form
  and the JSON API refuse a registration after the deadline with a clear
  message, not a generic 400.
  - Corrections in the back office to *existing* registrations stay
    possible. They are corrections, not new registrations.
- **Public screens.** After the deadline, the activity card shows
  "Inschrijvingen afgesloten" instead of the registration button, the same
  mechanism as the 'Volzet' badge (#451). The link to an **external
  registration form** is hidden as well. The external form itself cannot be
  closed from here.
- **Before the deadline**, the card and the modal say "Inschrijven kan tot
  <date>".
- **On the poster**, the registration block prints "Inschrijven tot <date>"
  when the field is set. The date is part of the stale fingerprint
  (§3.14).
- **Server date.** The existing check uses `date.today()`, which follows the
  container's time zone. The shared function uses the Belgian date
  explicitly, so a deadline does not close at 01:00 or 02:00 local time
  instead of midnight.

This part changes registration behaviour and **ships on its own**, ahead
of the Design Studio (§6, phase 0): **#974**, assigned to v2.5 (#925) by
Koen on 16 September 2026 and built by the finetuning CLI. At Koen's
request, the same service function also refuses a **cancelled** activity.
Until now only the card hid its button; the server accepted the
registration.

### 3.9 Contacts belong to the activity: a member or the association

Koen, 16 September 2026, after two earlier drafts: contacts are recorded
**on the activity**. A contact is either **a member**, optionally with a
different mobile number or e-mail address, or **the association itself**.

- **On the activity.** Who answers questions about an activity is a fact
  about that activity, so every design of it shows the same contacts.
  Changing a contact marks the final design stale (§3.14), like a changed
  date.
- **Two kinds of contact.** Each contact row points to exactly one party:
  - **A member.** The name is shown. Mobile number and e-mail come from the
    person's `ContactDetail` rows, **unless the contact row overrides
    them**. Per channel, the row can also leave it off the poster —
    someone may be fine with their e-mail but not their number.
  - **The association (Raak).** **The name is not shown**. The contact
    shows the organisation's website, e-mail and mobile number, taken from
    its own `ContactDetail` rows (#945 — the organisation already has
    EMAIL, MOBILE and WEBSITE). This is what some posters already do.
- **Exactly one party per row.** Following `ContactDetail` and `Address`,
  exactly one of `person_id` and `organization_id` is filled, enforced by a
  CHECK. The association can be added at most once per activity.
- **The picker follows the meeting circle** (CR-09). It has a search field
  over names, a short result list and an "Add" button, plus one fixed
  option, "Raak (de vereniging)". Added contacts form an ordered list; each
  row has the two override fields, the two show toggles, and a remove
  button. The picker marks a member who has neither a mobile number nor an
  e-mail.
- **Members only.** This is the difference with the circle, which
  deliberately admits non-members. A candidate is a person in a household
  (`MemberPerson`). **Every person in a household counts as a member**
  (Koen, 16 September 2026), regardless of whether this year's fee is
  paid.
- **One search, not two.** The circle screen filters `list_persons` inside
  its UI module; its comment says a search argument in MDM "would be a
  second contract for one caller". With this second caller, the name search
  moves into MDM as one function with a members-only option, and the circle
  calls it too. Two copies of the same filter would drift apart.
- **Where contacts are shown: only on posters and social images** (Koen,
  16 September 2026). There, the contact block follows the layout priority
  (§3.4). **They are not shown on the public website**, which is indexed and
  stays online.

A member's number printed on a poster is personal data made public. The
picker says so, and contact details are never sent to an LLM (§5).

### 3.10 Responsible publisher — out of scope for now

One of the examples carries a responsible publisher (V.U.: name and
address); the others do not. **Koen put the V.U. out of scope on
16 September 2026.** No setting, no block, no warning.

If it comes back, the shape is already clear: it would be a unit setting,
rendered on the print layout only and never on social images.

### 3.11 Images: three sources, one media kind

- **Sources:**
  - an upload;
  - a photo from the activity's archive (`activity_photo`);
  - an AI generation (§3.12).
- The chosen image is copied into a new media kind, **`design_image`**,
  which is **exempt from the 1600 px resize**. It is stored at up to 4096 px
  on the longest side, with a thumbnail as usual.
- A design has one main image and, optionally, one inset image (the walking
  poster uses one).
- The pin logo is never placed on the image area — a template rule (§3.3).

### 3.12 AI illustrations — Black Forest Labs, EU endpoint, with a quota

Approved by Koen on 16 September 2026, with a limit.

- **Provider:** Black Forest Labs (Freiburg, DE), model **FLUX.2 [pro]**,
  through the **EU endpoint `api.eu.bfl.ai`**, which exists for GDPR data
  residency.
  - Pricing is per megapixel, from about **$0.03 per image** (1 credit =
    $0.01). The response reports the actual cost, and that cost is stored
    per generation.
  - **Measured on 16 September 2026** (§6a): 4.5 credits ($0.045) and
    15–21 seconds for a 1920 × 1072 px image.
- **Flow:** the request is asynchronous and the response contains a
  `polling_url`. **Result URLs expire after about 10 minutes**, so the
  worker downloads the image into `design_image` immediately and never
  stores or serves a BFL URL. The screen polls with htmx.
- **Four variants per request.** The person picks one and discards the rest.
  Unpicked results are not kept.
- **House style through references:**
  - each template carries a small set of **style reference images** (up to
    eight inputs are accepted);
  - each template carries a fixed **style suffix**: "clean line
    illustration, fresh colours, palette <the design's duo>, white
    background, **no text, no letters, no logos**".

  Text belongs to the template. Image models render text unreliably.
- **Prompt:** Mistral drafts it from the activity title, the design's
  tagline and explanation, and a few **mood keywords** the person types ("playground,
  climbing house, swing, lemonade bar"). The person can edit it before
  sending.

  The editor warns that the prompt leaves the platform, and that it must not
  contain names.
- **Size:** the generation covers the largest image slot of the template's
  layouts, at the ratio of the `print_a` slot, and the other layouts crop
  around the focal point. Expected print resolution is 150–200 dpi for a
  half-page A3 image. That is acceptable for line illustrations, and the dpi
  warning (§3.5) makes it visible.
- **Budget, not a count** (Koen, 16 September 2026):
  - a **monthly budget in euro per unit**, **configurable**, set to
    **€50 per month** while testing;
  - **the budget lives in `.env`** (`DESIGNSTUDIO_AI_MONTHLY_BUDGET_EUR`,
    default 50), the same pattern as `max_registrations_per_email`: a
    default in `app/config.py` that the environment file overrides. A
    **tenant setting** can override it per unit; only OPERATOR can change
    that setting. Without a tenant value, the `.env` value applies;
  - BFL reports the cost of each request in credits (1 credit = $0.01).
    That cost is stored in the AI call log (#978). **The month's spend is
    read from that log** with #978's read function, converted to euro at a
    configured rate;
  - **before sending**, the service estimates the cost of the request (known
    price per megapixel × four variants). It refuses the request when the
    estimate would take the month over budget, so the budget is never
    exceeded by more than a rounding difference;
  - the editor shows what is left this month;
  - a platform-wide **kill switch** turns generation off everywhere.

  BFL prices FLUX.2 per megapixel, from about $0.03 for a small image, so
  €50 buys a few hundred images. Print-sized images cost more; the build
  takes the rate per megapixel from BFL's price list.

  **Every generation is logged in the existing AI call log**
  (`ai.ai_call_log`, CR-07), through the same seam as the Mistral calls,
  with tenant, provider, endpoint, user, prompt, credits, cost, duration and
  time. **#978** adds those columns to the log. The Design Studio builds on
  that issue and keeps no cost log of its own: two logs would record the same
  fact twice.
- **Key:** one platform key (`BFL_API_KEY` in `.env`), since the platform
  holds the contract. A per-unit encrypted key can be added later through
  tenant settings if a unit ever pays for its own usage.
- **Safety:** BFL's default `safety_tolerance`. The style suffix asks for
  illustration, not photorealism. There are no recognisable faces and no
  realistic children.

### 3.13 AI text proposals — Mistral

- One action, "Suggest text", sends the activity's title, dates, place and
  price, plus whatever the design already has as tagline, explanation or
  mood keywords, to the existing Mistral provider.
- It returns proposals for:
  - title line breaks;
  - subtitle;
  - up to six highlights, each with an icon name from the template's Lucide
    subset;
  - welcome line;
  - a shortened explanation.
- **Proposals are shown next to the fields, and nothing is applied until the
  person takes it.** The request carries no registrations, no persons and no
  contact details.

### 3.14 Lifecycle: draft → final → stale

- An activity has **zero or more designs**. A design is `draft` or `final`.
  **At most one design per activity is final.**
- **Draft:** the editor shows a live preview per layout — a low-resolution
  PNG that is re-rendered on change and not stored.
- **Mark final:**
  - every chosen layout and PDF is rendered and stored;
  - the A3 PDF becomes the activity's **`activity_poster`**;
  - **if the activity already has a poster**, the person is asked first. The
    confirmation says explicitly that the current poster — possibly
    uploaded by hand — will be replaced (Koen: "the user in control").
    Declining still finalises the design, without touching the poster;
  - once the `landscape` layout exists (phase 4), its image becomes the
    activity page's **share image**.
- **Stale:**
  - a final design stores a **fingerprint of the facts it used** (§3.7);
  - when the activity changes those facts (a new date, a changed time, a
    changed price), the design shows *stale* in the list and on the activity
    detail;
  - **Re-render** makes it current again, with the same inputs and the new
    facts.

  Nothing re-renders automatically: a poster that is already printed should
  not silently differ from the file.
- **Reopen:** a final design can go back to draft. The published poster
  stays until the design is marked final again.

### 3.15 Screens and roles

- The entry point is the activity detail: a **"Ontwerpen"** section with
  the list of designs (template, duo, status, stale flag, thumbnail) and
  **"Nieuw ontwerp"**.
- **Editor** (back office, so desktop-first with a usable phone variant):
  - fields on the left, grouped by block;
  - preview on the right with a layout switcher;
  - an image panel with the three sources;
  - a download panel.

  It uses the design-system macros throughout.
- **Access:** `require_admin_ui` (ADMIN/OPERATOR), scoped to the tenant.
  The quota setting and the kill switch are OPERATOR only.
- **Paths are Dutch** (`/admin/activiteiten/{id}/ontwerpen`,
  `/admin/ontwerpen/{id}`). Code is English (`designstudio`, `Design`,
  `render_design`).

## 4. Data model (sketch)

A new schema, `designstudio`. Repeatable things get their own table (the
modelling rule in `CLAUDE.md`).

```
designstudio.designs
  id, tenant_id, activity_id (soft ref), template_key, template_version,
  duo_code, status (draft|final), title_override, tagline (90),
  explanation, subtitle, recurrence_line, welcome_line, price_badge_text,
  show_kicker, main_image_id, main_focus_x, main_focus_y,
  inset_image_id, facts_fingerprint, finalised_at, finalised_by,
  created_at, updated_at, created_by

designstudio.design_highlights      -- up to six, ordered
  id, design_id, sort_order, icon_code, text

designstudio.design_supporters      -- supporter / funder logos
  id, design_id, media_asset_id, sort_order

designstudio.design_renditions      -- stored only for final designs
  id, design_id, layout_code, variant (pdf|jpeg|png),
  size_code (A3|A4|1080x1350|…), media_asset_id, rendered_at,
  min_effective_dpi

designstudio.image_generations      -- which design asked, and what was picked
  id, design_id, ai_call_log_id, seed, width, height,
  picked_media_asset_id
  -- tenant, provider, model, prompt, user, credits, cost, status and time
  -- live in ai.ai_call_log (#978), not here

activities.activities
  + registration_closes_on  date         null   -- inclusive, Belgian date (§3.8a)

activities.activity_contacts        -- ordered; a member or the association
  id, tenant_id, activity_id, sort_order,
  person_id        (soft ref, null)   -- a member
  organization_id  (soft ref, null)   -- the association; name not shown
  mobile_override  varchar(50)  null
  email_override   varchar(255) null
  show_mobile, show_email       boolean
  check: exactly one of person_id, organization_id
  unique (activity_id, person_id), unique (activity_id, organization_id)
media.media_assets.kind
  + design_image   (no 1600 px resize; see §3.11)
  + design_render  (rendered PDF / image)
```

Codes (`duo_code`, `layout_code`, `icon_code`) are validated in code against
the constants of §3.3 and the template's icon subset. There are no
cross-schema foreign keys, as elsewhere.

Environment: `DESIGNSTUDIO_AI_MONTHLY_BUDGET_EUR` (default 50, the budget
per unit per month) and `BFL_USD_EUR_RATE` (the cost conversion).
Tenant setting: `ai_image_monthly_budget_eur` — an optional per-unit
override of the `.env` budget.
Environment: `BFL_API_KEY`, `DESIGNSTUDIO_AI_IMAGES_ENABLED` (the kill
switch, default off).

## 5. Privacy

| Leaves the platform | To | Contains |
|---|---|---|
| Text proposal request | Mistral (EU) | activity facts only — no persons, no registrations |
| Image prompt | BFL, EU endpoint | a prompt the person has seen and may edit; the editor warns against names |
| Style references | BFL, EU endpoint | template-owned reference illustrations — never member photos |

- **Uploaded photos and archive photos are never sent to BFL** (no image
  editing of member photos). Doing that would be a separate decision.
- Contacts are rendered locally and never sent anywhere.
- BFL's zero-retention option is an enterprise offer. The standard API keeps
  results for about 10 minutes.

## 6. Phasing

Each phase ships on its own.

0. **Registration deadline** (§3.8a). This phase is independent of the
   Design Studio and useful without it:
   - the field on the activity;
   - one service function that decides "open for registration";
   - enforcement in the registration route;
   - the closed state and the "until" line on the public screens;
   - the admin field.
1. **Engine and first template.**
   - Domain, the contacts table, the media kinds, and the house-style
     constant with its gate.
   - One template, **"Illustratie"** (the play-afternoon and walking-group
     family), with the `print_a` layout (borderless A3 and A4 PDF) and the
     `feed_portrait` layout (4:5).
   - Images from upload or archive, QR code, contacts, supporter
     logos.
   - Draft, final, stale; the final design becomes the poster, after
     confirmation; downloads.
   - Logo upload with sanitising.
2. **Text proposals** (Mistral).
3. **AI illustrations** (BFL): quota, kill switch, audit, style references.
4. **More templates and formats:**
   - "Beeld" — a photo-led template like the father-and-son poster;
   - "Tekstflyer" — the A4 text flyer from the Word template;
   - the `landscape` layout (Facebook event cover and share image), the
     `square` layout, and the `story` layout.

New dependencies:
- phase 1: `pypdfium2`, plus a QR library — **`segno`** (BSD, pure Python,
  no dependencies) or `qrcode`; the build weighs them under Europe First;
- phase 3: an HTTP client for BFL, which the codebase already has.

## 6a. Prototype findings (16 September 2026)

Six iterations of throwaway prototypes, rendered with the real stack
(WeasyPrint 70, pypdfium2, segno, Radio Canada Big). The results and scripts
are in Koen's Nextcloud project folder (`designstudio/iteraties/`) and not in
this repository: they contain photos and test data from real posters. What the
build takes from them:

- **Three templates carry the Design Studio.**
  - **"Beeld"**: a photo on top, the subtitle curving along a brand wave, a
    colour corner holding the logo and the QR code.
  - **"Tekstflyer"**: an A4 text flyer with a header, a photo, a "Praktisch"
    box and a contact footer. Koen: "mooi zo".
  - **"Illustratie"**: built from zones, with the date and a concrete
    location next to the logo, three short messages, and a registration or
    "Meer info" block that depends on the activity.
- **Zones, not free positioning.** A layout is a column of fixed-height
  zones, with normal flow and flexbox inside each zone. **After layout, a
  check walks the box tree and fails the render when any box leaves its
  zone.** The pages use `overflow: hidden`, which would otherwise hide such
  a box silently.
  - The check caught three real faults during the prototypes.
  - It must treat only block boxes as zones: line and text boxes inherit
    their block's element, and a check that misses this compares a box with
    itself.
- **Title size is fitted on real glyph advances** from the font's `hmtx`
  table, not on a character count.
- **Curved text is set glyph by glyph.** WeasyPrint ignores SVG `<textPath>`
  and draws the text straight. The subtitle along the wave is therefore
  built from the font's glyph outlines (fontTools, with the variable font
  instanced at the wanted weight). Each glyph is placed with its own
  translation and rotation along the curve. The output is plain vector
  paths; if the text is longer than the curve, the render fails.
- **Radio Canada Big's weight axis ends at 700.** A weight above that renders
  as 700, so templates never ask for more.
- **QR codes keep their quiet zone** (`border=4`, on white).
- **AI images need a whitening step.** FLUX returns a near-white background
  (RGB 253), which shows as a pale block on a white page. The import step
  lifts near-white to pure white before the image is stored.
- **AI colours are close to the palette, not on it.** The yellow tends
  towards ochre. That is acceptable for an illustration, because text and
  colour fields stay in exact brand colours in the template, and the image
  never carries text.
- **A style reference makes the difference.** Prompt-only line art came
  out grey and generic. With a cut-out of the unit's own poster illustration
  passed as `input_image`, the style matched what Koen liked (6 credits per
  image instead of 4.5, because the reference counts as input).
- **Counts and single objects are unreliable.** "Exactly two children and
  one adult", "one ladder golf set" and "one ball": in the final round, one
  of four variants followed all of it, while the style was right in all four.
  The four variants per request (§3.12) are therefore a requirement, not a
  convenience.
- **Moderation is intermittent.** With a reference image and children in the
  prompt, one request was refused ("Content Policy Violation") and later
  requests with the same combination passed. The client handles a refusal
  per request (`status` `moderated` in the log, #978) and carries on with
  the other variants; the screen says which variant was refused.
- **Words that mean something else in US English.** "Football" came back as
  an American football and "torch" as a burning torch. The prompt says
  "round soccer ball" and "electric LED flashlight". Prompts are written in
  English and checked for such words.
- **A fourth template, "Reeks", for recurring activities** (built as
  "Stappen en Klappen", iterations 10–13, approved by Koen). Its parts:
  - a frame in Dark Green, with the unit's wordmark in a rounded corner of
    that frame;
  - a speckled, slightly rotated two-word title, where "en" sits in a speech
    bubble;
  - a brush-edged bar under the title;
  - icon bullets with dotted rules, with one date bullet and one place
    bullet emphasised;
  - a ragged-edged main photo and a polaroid inset;
  - a "DATA IN <year>" table filled from the activity's dates;
  - a handwritten note ("Zet het in je agenda!");
  - a brush-edged footer.

  How the pieces are built:
  - **Speckles:** WeasyPrint cannot use text as a clip path, so the title is
    glyph outlines with white dots. A dot is placed only where a raster of
    the same glyph says "inside".
  - **Bolder titles:** Radio Canada Big stops at weight 700, so the letters
    get a stroke in their own colour. The stroke width must be converted into
    glyph units, because a stroke scales with the glyph transform.
  - **Frame and corner as one shape:** the page minus the paper with its
    rounded notch. Two overlapping shapes left a visible hairline seam.
  - **The wordmark without its tile:** the tile is a separate path in the
    lockup and is left out. The crop must match the wordmark's real bounds,
    and the SVG's width and height attributes must change with the viewBox.
    Otherwise the wordmark stays letterboxed, or is clipped. The render check
    therefore measures the wordmark's full height, not only its offsets.
  - **Handwriting:** Caveat (OFL), as vector outlines.
  - **Title split:** "X en Y" titles get the bubble; any other title falls
    back to a plain title.
- **Colours checked, not assumed.** Every colour code in the rendered poster
  is one of the guide's colours or white. The ChatGPT original used a darker
  green (about `#014411`). The official Dark Green is `#005d29`, which is
  the value in Koen's colour list with a typo removed.
- **Decorations that belong to the scene live in the scene.** When the image
  has its own sun or bunting, a sticker placed over the image collides with
  it. The price therefore sits in a zone (a bar next to the registration
  block), not on the image.

## 7. Test set — what the build must reproduce

With **seed data only**, the "Illustratie" template must reproduce the
structure of two of the examples in §1.3:

- **a one-day activity:** date badge with a time range, five highlights, a
  price badge, a supporter logo, and a footer with two contacts — one member
  and the association;
- **a recurring activity with six dates:** recurrence line, dates grid,
  highlights, and an inset image.

The tests must be able to go red:
- a long title (40 characters) still fits `print_a` and `feed_portrait`;
- the six-date grid collapses to the recurrence line in `feed_portrait`;
- finalising a design for an activity that already has a poster does not
  replace it without the confirmation — tested through the route;
- the A3 PDF's page is exactly 297 × 420 mm, and a coloured background
  reaches all four page edges;
- a text box placed inside the 8 mm safe zone makes the safe-zone check
  fail — the guard is proven by that violation;
- a template with a hex value outside the palette fails the gate;
- a forbidden duo is refused by the service, not only hidden in the picker;
- a scripted SVG upload is refused;
- changing an activity date marks its final design stale — tested through
  the activity service, not by calling the fingerprint function directly;
- changing an activity's contacts also marks its final design stale;
- a registration at 23:30 Belgian time on the deadline day is accepted
  through the public route;
- one at 00:30 Belgian time the next day is refused, even though the UTC
  date is then still the deadline day (summer time);
- after the deadline, the public card shows "Inschrijvingen afgesloten" and
  neither the registration button nor the external link;
- a back-office correction to an existing registration still succeeds
  after the deadline;
- an override wins over the member's own number, and removing the override
  brings the member's number back;
- an association contact renders website, e-mail and mobile, and no name;
- a row with both or neither of person and organisation is refused by the
  database, not only by the form;
- the picker refuses a person who is not a member — tested through the
  route, because the picker only hides non-members;
- the meeting circle still finds non-members after the name search moves to
  MDM;
- marking a design final replaces the activity's poster — tested through the
  public activity page;
- the quota refuses the generation after the limit, and the kill switch
  refuses every generation — with the BFL client mocked.

## 8. Koen's answers (16 September 2026)

| Question | Answer | Where |
|---|---|---|
| House style for posters | the Raak house style guide | §3.3 |
| Print | borderless home print, **A3 required**; print shops out of scope | §3.5 |
| CMYK | RGB for now; CMYK later as a post-processing step, no module change | §3.5 |
| Responsible publisher (V.U.) | out of scope for now | §3.10 |
| Logo recolouring | approved; three duos enabled to start | §3.3 |
| Neutral lockup as SVG | supplied | §1.2 |
| AI image provider | Black Forest Labs, with a limit | §3.12 |
| AI limit | configurable monthly budget, €50 while testing | §3.12 |
| Registration deadline | a real, enforced field on the activity — #974, v2.5 | §3.8a |
| Contacts | on the activity; a member (with overrides) or the association | §3.9 |
| Who is a member | every person in a household | §3.9 |
| Contacts on the website | no — posters and social images only | §3.9 |
| Tagline on yellow tile | Indigo, as in the unit's yellow lockup | §3.3 |
| Formats in phase 1 | A3 + A4 borderless and 4:5; Facebook cover and square later; A5 is the A4 PDF | §3.4 |
| Replacing an existing poster | only after an explicit confirmation | §3.14 |
| Tagline and explanation | on the design for now, not on the activity or the website | §3.8 |

No open questions remain for phase 1.

## 8a. Proposals awaiting Koen (16 September 2026, not yet confirmed)

1. **v2.5 scope:** the design editor with the four templates (Beeld,
   Tekstflyer, Illustratie, Reeks); own photos and photos from the
   activity's archive; A3, A4 and 4:5; contacts; "final" becomes the poster
   after confirmation; AI images once #978 has landed. Later: Mistral text
   proposals, the Facebook cover, the square format.
2. **Contacts** are stored in the Design Studio module, per activity, so the
   activities module does not change. They can move to the activity later.
3. **Caveat** (OFL) goes into the repository. Reference drawings per
   template and the unit logo are uploaded through the screen and never
   committed.
4. **HDEV:** Koen creates a BFL key in `.env.hdev`. The AI kill switch is off
   by default.
5. **Test material:** fictitious data and drawn test images only. No photos
   of real people in the repository.

Clarified in the same conversation:
- **Facts stay on the activity:** the dates table is built from the
  activity's dates, and the price comes from the activity. A price text of
  the design's own (such as "Drankje of ijsje € 1") is an optional exception.
- **The editor has fields only for design text:** title with line breaks and
  colours, labels and bar, tagline, explanation, recurrence line, icon lines
  with emphasis, welcome line, price override and handwritten note. Each
  template shows only the fields it uses.

## Non-goals

- A free-form editor (Canva-like). Units choose templates; they do not move
  boxes.
- Posting directly to Facebook or Instagram through their APIs.
- Video (BFL offers it; not here).
- Editing member photos with AI.
- A recurrence engine for activity dates.
- Templates that units edit themselves.
- Text inside AI images.
- Print-shop output: bleed, crop marks, CMYK/PDF-X (§3.5).
- The responsible publisher (V.U.) on print (§3.10).

## Relationship to existing work

- **#258 / CR-09:** WeasyPrint and its Dockerfile packages; the meeting
  circle picker whose pattern and name search §3.9 reuses.
- **#223:** the poster media slot that a final design fills.
- **#884:** the stable slug behind the QR code and the share link.
- **#945:** the organisation's website and e-mail.
- **#913 (design track):** the site's palette. Posters deliberately follow
  the Raak house style guide instead (§3.3).
- **CR-05 (newsletter):** a final design's `landscape` image (phase 4) is a natural
  illustration for the activity in a newsletter. That link belongs to CR-05.
