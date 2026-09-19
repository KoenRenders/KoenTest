# designstudio — component contract (CR-10, #1007)

**Purpose.** Posters and social images made from an activity, in the Raak house
style, by the unit itself: one template "Affiche" in two layouts (print A3/A4,
Instagram 4:5), photos or AI line drawings, an editable SVG to download and
upload, and a numbered version that can be published as the activity's poster.

## Facade (`api.py`) — the only door for other components

- **Read**: `list_designs`, `get_design`, `facts_for` (what the poster takes
  from the activity and the association, plain values), `fingerprint`,
  `is_stale`, `content_for` (the `PosterContent` value), `check_design`,
  `preview_png`, `image_options`, `sponsor_options`, `budget`, `edited_svg_for`,
  `rendition`.
- **Write**: `create_design`, `save_design`, `delete_design`, `make_version`
  (all-or-nothing, Inkscape as authority), `publish` (async — copies the A3 PDF
  onto the activity through `media.replace_activity_poster`),
  `upload_edited_svg`, `remove_edited_svg`, `add_design_image` (async),
  `request_images` (BFL, four variants, budget reserved first),
  `pick_generation`.
- **Brand**: `COLOURS`, `DUOS`, `ENABLED_DUOS`, `palette_for`, `check_template`
  (the gate), `ICONS`.
- **Errors**: `DesignError` (input, may carry several messages), `RenderError`
  (Inkscape missing or failed), `ImagingError` (budget, kill switch, provider).
- **Models as type**: `Design`, `DesignVersion`, `DesignRendition`,
  `ImageGeneration`.

## What this component uses from others (through their facades only)

| Component | For |
|---|---|
| `activities.api` | `get_activity` (title, dates, place, deadline, cancelled), `organisers_for` (#1004: the contacts on the poster) |
| `media.api` | `list_activity_photos`, `list_media` (kinds `design_image`, `sponsor`), `upload_media` (kind `design_image`, #1005), `add_document` (kind `design_render`: PDF, PNG, SVG — an SVG is cleaned by media's one allowlist, #1011), `delete_media`, `replace_activity_poster` (publishing), `MediaAsset` (bytes of an image by id) |
| `mdm.api` | `organization_details` (website, e-mail, gsm of the association) |
| `chatbot.api` | `sink_for` (the AI log, #978) and `cost_per_period` (the month's spend) |
| `kernel` | `tenant_home_url` (the QR target, https), `current_tenant_id`, `jobs` (`designstudio.generate`) |

## What other components take from here

Today: nothing. The activity keeps its poster through `media`, unchanged; the
Design Studio is invisible to it. A newsletter may later read a version's PNG
through `rendition`.

## Invariants

- **A design stores inputs, never facts and never renders.** Title, dates,
  place, deadline, organisers and the association's lines are read at render
  time; each version keeps `facts_fingerprint`, and "verouderd" is computed on
  read (`is_stale`). Nothing in `activities` calls into this schema.
- **Templates use colours by name only.** `brand.check_template` refuses any
  hex outside the eight colours, white and black, and more than five brand
  colours per template. The rendered poster passes the same gate (test).
- **Overflow is reported, never cut.** The planner reports vertical overflow
  ("te veel inhoud"); the font-metric estimate (an upper bound, iteration 16)
  and `inkscape --query-all` (the authority, via the 100 mm reference
  rectangle) report horizontal overflow per text id. A version is only made
  when every layout passes with the authority.
- **A version is all-or-nothing** and at most three per design; the published
  one is never pruned.
- **Publishing is a copy with confirmation**: the A3 PDF goes through the
  same door as a hand-made upload.
- **An uploaded SVG is cleaned by media's one allowlist** (#1011: "drawing
  versus doing" — this component carries no cleaner and does not rely on
  byte-identical storage), must have the layout's page size, replaces the
  merge for that layout, and is named "handmatig bewerkt". The brand check on
  it warns only.
- **AI images**: kill switch (`DESIGNSTUDIO_AI_IMAGES_ENABLED`) and monthly
  budget per unit (`DESIGNSTUDIO_AI_MONTHLY_BUDGET_EUR`) plus platform cap
  (`DESIGNSTUDIO_AI_PLATFORM_BUDGET_EUR`) are checked before any call; a click
  reserves its cost (`reserved_cents`) until the job writes the real cost to
  the AI log. States: requested → fetched → picked | discarded, or refused
  (moderation) | failed. One attempt, never a paid retry.
- **No cross-schema foreign keys** (`test_schema_boundaries`): `activity_id`,
  `media_asset_id`, `ai_call_log_id` are soft references.

## Rendering (B1.3)

Inkscape 1.4 as a subprocess (apt package in the image; fonts Radio Canada
Big and Caveat made visible to fontconfig), PDF with text kept and fonts
embedded, PNG at a pixel width. Never `--export-text-to-path` (Inkscape reads
`=false` as true). Effects are native SVG: pattern speckles (one tile per
title), `textPath`, `feTurbulence` + `feDisplacementMap` on a mask for ragged
photo edges, stroke with `paint-order` for bolder titles.

## Screens

`/admin/ontwerpen` (list, new design per activity) and
`/admin/ontwerpen/{id}` (the editor: form, preview per layout, violations,
images, AI variants, versions, publish, SVG download/upload). ADMIN/OPERATOR
only (`require_admin_ui`).
