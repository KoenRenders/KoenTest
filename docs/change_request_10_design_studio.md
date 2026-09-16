# Change Request 10 — Design Studio: posters and social images from an activity

**Project:** Web Portal "Raak Millegem"
**Status:** Shaped with Koen on 16 September 2026 (brainstorm on
`feature/designstudio`). Not assigned to a release. Decisions in §3 are
settled unless marked *open*; §8 lists what still needs Koen.
**Apply to:** a new `designstudio` domain (backend + admin screens), two
columns on `activities.activities`, two new media kinds. Rendering reuses
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
   website and its share image. When the activity changes afterwards, the
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
  - **24 PNG files**, 6090 × 4060 px, raster only — there is no SVG yet;
  - they are **exactly the twelve permitted duos of §1.1, each in both
    directions** (tile colour / baseline colour). Raak itself thus offers the
    lockup in every permitted duo.

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
| Explanation, one or two paragraphs | 1 | activity description; design may shorten |
| Registration: link, QR code, deadline | 2 | activity |
| Contact: website, e-mail, contact persons | 4 | organisation; contact lines typed on the design |
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
  offers only the twelve duos, so a forbidden pair cannot be chosen.
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

  **The lockup is recoloured per duo.** A unit uploads **one** SVG. The
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
  repository file. Until Raak supplies it as SVG, the 6090 px PNGs are
  sharp enough for A3. They cannot be recoloured, so the engine picks the
  PNG that matches the design's duo — all 24 exist.

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
| `print_a` | 1 : √2 | A3, A4, A5 print — **one layout**, because all A sizes share the ratio. Units and type scale with the page. | 297 × 420 mm, etc. |
| `feed_portrait` | 4 : 5 | Instagram / Facebook feed | 1080 × 1350 px |
| `square` | 1 : 1 | Instagram / Facebook post | 1080 × 1080 px |
| `landscape` | 1.91 : 1 | Facebook event cover **and** the share image (`og:image`) | 1920 × 1005 px |
| `story` | 9 : 16 | Stories (phase 4) | 1080 × 1920 px |

- **Blocks carry a priority.** Smaller layouts drop blocks from the bottom of
  the list:
  1. the explanation;
  2. the concrete-dates grid, replaced by the recurrence line;
  3. highlights beyond three;
  4. contact lines.

  Title, date, place, image and the link are never dropped.
- **Social layouts keep text inside a safe zone**, because Facebook crops the
  event cover differently on mobile.
- **The image has one focal point**, stored as x/y percentages. Each layout
  crops the image around that point (`object-position`), so the swing stays
  in view in both the square and the landscape layout.

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
- Adding a bleed variant later is cheap. The layout already extends its
  colour fields to the edge, and WeasyPrint supports `@page { bleed }`. The
  CMYK values stay recorded in the palette constant (§3.3) for the same
  reason.

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
  prices, registration link and QR code (from `slug`), description, tagline.
- **From the organisation:** website, e-mail, logo lockup, unit name.
- **Only on the design:**
  - a title override (for line breaks: "SPEELNAMIDDAG / EN / ZOMERBAR");
  - subtitle, recurrence line, highlights, welcome line;
  - price-badge wording, a shortened explanation;
  - images and focal point;
  - contact lines and supporter logos;
  - the kicker toggle.

A design stores its **inputs, not its renders**. "Add this line a week
later" is an edit plus a re-render.

### 3.8 Two new activity fields — useful on the website as well

- `tagline` — one short line (≤ 90 characters), the hook under the title on
  the poster *and* on the activity card.
- `description` — the public explanation, plain text with paragraphs. The
  activity page shows it as well.

`notes` is not repurposed: its meaning was never defined, and reusing an
undefined column reintroduces the ambiguity. Whether to remove it is outside
this CR.

A **registration deadline** appears in the examples, but a deadline that
only exists on a poster is a promise the registration form does not keep.
See §8.

A recurrence engine is **not** added. The concrete dates are the existing
`ActivityDate` rows. The phrase "every 2nd Monday" is design text.

### 3.9 Contact lines are typed on the design

Koen, 16 September 2026: contacts are **typed in the Design Studio**, not
selected from the member records. Not everyone wants their phone number on a
poster, and some prefer to be reachable as "Raak" rather than by their own
name. What goes on a poster is therefore the person's own choice, not a copy
of their record.

- **A design has up to three contact lines.** Each line has a free label
  (a first name, "Raak Millegem", …), an optional phone number and an
  optional e-mail address. A line needs a label and at least one of the two.
- **The default is the organisation.** A design without contact lines shows
  the organisation's website and e-mail (#945) — the footer the examples
  already have.
- **Convenience, not a second source.** A new design of an activity starts
  with the contact lines of that activity's most recent design, so they are
  not typed twice. After that, each design owns its own lines.
- **Design text, not a fact.** Contact lines do not count toward the stale
  fingerprint (§3.14).

This is personal data printed in public. The editor says so next to the
fields. Contact lines are never sent to an LLM (§5), and the phone and
e-mail fields are validated for format only.

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
- **Prompt:** Mistral drafts it from the activity title, tagline,
  description, and a few **mood keywords** the person types ("playground,
  climbing house, swing, lemonade bar"). The person can edit it before
  sending.

  The editor warns that the prompt leaves the platform, and that it must not
  contain names.
- **Size:** the generation covers the largest image slot of the template's
  layouts, at the ratio of the `print_a` slot, and the other layouts crop
  around the focal point. Expected print resolution is 150–200 dpi for a
  half-page A3 image. That is acceptable for line illustrations, and the dpi
  warning (§3.5) makes it visible.
- **Quota:**
  - a monthly number of generations per unit, where one request with four
    variants counts as four;
  - the limit is a tenant setting that only OPERATOR can change;
  - the platform default is set at go-live (§8);
  - a platform-wide **kill switch** turns generation off everywhere.

  Every generation is logged with model, seed, prompt, cost and user.
- **Key:** one platform key (`BFL_API_KEY` in `.env`), since the platform
  holds the contract. A per-unit encrypted key can be added later through
  tenant settings if a unit ever pays for its own usage.
- **Safety:** BFL's default `safety_tolerance`. The style suffix asks for
  illustration, not photorealism. There are no recognisable faces and no
  realistic children.

### 3.13 AI text proposals — Mistral

- One action, "Suggest text", sends the activity's title, tagline,
  description, dates, place and price to the existing Mistral provider.
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
  - the `print_a` PDF (home-print variant) becomes the activity's
    **`activity_poster`**, replacing the one that was there;
  - the `landscape` image becomes the activity page's **share image**.
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
  duo_code, status (draft|final), title_override, subtitle,
  recurrence_line, welcome_line, price_badge_text, explanation_override,
  show_kicker, main_image_id, main_focus_x, main_focus_y,
  inset_image_id, facts_fingerprint, finalised_at, finalised_by,
  created_at, updated_at, created_by

designstudio.design_highlights      -- up to six, ordered
  id, design_id, sort_order, icon_code, text

designstudio.design_contact_lines  -- up to three, ordered, typed
  id, design_id, sort_order, label, phone, email

designstudio.design_supporters      -- supporter / funder logos
  id, design_id, media_asset_id, sort_order

designstudio.design_renditions      -- stored only for final designs
  id, design_id, layout_code, variant (pdf|jpeg|png),
  size_code (A3|A4|1080x1350|…), media_asset_id, rendered_at,
  min_effective_dpi

designstudio.image_generations      -- audit + quota
  id, tenant_id, design_id, provider, model, prompt, seed,
  width, height, cost_credits, status, picked_media_asset_id,
  requested_by, requested_at

activities.activities
  + tagline      varchar(90)  null
  + description  text         null
media.media_assets.kind
  + design_image   (no 1600 px resize; see §3.11)
  + design_render  (rendered PDF / image)
```

Codes (`duo_code`, `layout_code`, `icon_code`) are validated in code against
the constants of §3.3 and the template's icon subset. There are no
cross-schema foreign keys, as elsewhere.

Tenant setting: `ai_image_monthly_quota`.
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
- Contact lines are rendered locally and never sent anywhere.
- BFL's zero-retention option is an enterprise offer. The standard API keeps
  results for about 10 minutes.

## 6. Phasing

Each phase ships on its own.

1. **Engine and first template.**
   - Domain, the two activity fields, the media kinds, and the house-style
     constant with its gate.
   - One template, **"Illustratie"** (the play-afternoon and walking-group
     family), with the `print_a` (borderless home PDF), `feed_portrait`, `square`
     and `landscape` layouts.
   - Images from upload or archive, QR code, contact lines, supporter
     logos.
   - Draft, final, stale; the final design becomes the poster and share
     image; downloads.
   - Logo upload with sanitising.
2. **Text proposals** (Mistral).
3. **AI illustrations** (BFL): quota, kill switch, audit, style references.
4. **More templates and formats:**
   - "Beeld" — a photo-led template like the father-and-son poster;
   - "Tekstflyer" — the A4 text flyer from the Word template;
   - the `story` layout.

New dependencies:
- phase 1: `pypdfium2`, plus a QR library — **`segno`** (BSD, pure Python,
  no dependencies) or `qrcode`; the build weighs them under Europe First;
- phase 3: an HTTP client for BFL, which the codebase already has.

## 7. Test set — what the build must reproduce

With **seed data only**, the "Illustratie" template must reproduce the
structure of two of the examples in §1.3:

- **a one-day activity:** date badge with a time range, five highlights, a
  price badge, a supporter logo, and a footer with website, e-mail and one
  contact line;
- **a recurring activity with six dates:** recurrence line, dates grid,
  highlights, and an inset image.

The tests must be able to go red:
- a long title (40 characters) still fits `print_a` and `square`;
- the six-date grid collapses to the recurrence line in `square`;
- the A3 PDF's page is exactly 297 × 420 mm, and a coloured background
  reaches all four page edges;
- a text box placed inside the 8 mm safe zone makes the safe-zone check
  fail — the guard is proven by that violation;
- a template with a hex value outside the palette fails the gate;
- a forbidden duo is refused by the service, not only hidden in the picker;
- a scripted SVG upload is refused;
- changing an activity date marks its final design stale — tested through
  the activity service, not by calling the fingerprint function directly;
- a contact line with only a label is refused by the service;
- a new design of an activity starts with the previous design's contact
  lines, and editing them does not change the previous design;
- marking a design final replaces the activity's poster — tested through the
  public activity page;
- the quota refuses the generation after the limit, and the kill switch
  refuses every generation — with the BFL client mocked.

## 8. Open questions

1. **Registration deadline.** Add a real `registration_closes_on` that the
   registration form enforces, so the poster can print "until …"? That is
   new behaviour, outside the poster, with its own issue. Or leave the
   deadline out of the posters for now?
2. **Default AI quota.** How many generations per unit per month? (One
   request = four images, about $0.12–0.20.)
3. **Neutral lockup as SVG.** Can Raak supply the neutral lockup ("Beleef
   meer!") as SVG? Until then the PNGs serve (§3.3).

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

- **#258 / CR-09:** WeasyPrint and its Dockerfile packages.
- **#223:** the poster media slot that a final design fills.
- **#884:** the stable slug behind the QR code and the share link.
- **#945:** the organisation's website and e-mail.
- **#913 (design track):** the site's palette. Posters deliberately follow
  the Raak house style guide instead (§3.3).
- **CR-05 (newsletter):** a final design's `landscape` image is a natural
  illustration for the activity in a newsletter. That link belongs to CR-05.
