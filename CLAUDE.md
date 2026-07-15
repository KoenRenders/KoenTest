# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Raak Millegem web portal

Community association website with public activity registration, family membership, Mollie payment integration, and an admin dashboard. Language: Dutch (nl-BE).

## This repository is PUBLIC

Never commit secrets, credentials, or operational/infrastructure details to this
repo. Specifically NOT in git:
- Server IPs, real domain names, Storage Box users/hosts → use placeholders or env vars.
- Personal backup/ops tooling (Restic scripts, off-site backup pipelines, server
  runbooks, systemd units for personal infra). Keep those local on the server only,
  outside the git checkout.
- Any `.env*` file with real values (only `.env.*.example` with placeholders).

App-stack infrastructure that ships with the deployable stack (e.g. the
`db-backup` service in docker-compose, generic scripts without secrets) may stay
in the repo, as long as it contains no secrets or personal infra details.

## Development workflow

The user runs this after every session:
```bash
git pull && sudo docker-compose up --build -d
```

All commits and pushes are done by Claude — the user never does this manually.

**There are two kinds of working copy, and they have different branch rules:**

- **The master worktree/CLI** (the canonical checkout) works **directly on
  `master`**. Routine work, quick fixes, and integration land here straight on
  `master`, committed and pushed by Claude.
- **Worktree CLIs** (feature worktrees, e.g. a `claude/...` or `feature/...`
  branch) work on a **feature branch**. That branch runs the full CI validation
  and is **merged into `master` only after it goes green** — and, per the
  feature-branch norm, only once Koen asks for the merge. Never commit feature
  work straight onto `master` from a worktree CLI.

In short: **decide by which working copy you are in.** Master worktree → commit on
`master`. Feature worktree → commit on its branch, merge to `master` after CI
passes. The only branch exception on the master side is a hotfix on a released tag
— see "Releases and hotfixes" below.

**Every deployable code change goes through an issue.** Before implementing
anything that ships in the deployable stack (backend, frontend, migrations,
deploy/infra config), there must be a GitHub issue covering it — either create a
new one, or add the work as a checklist item / comment on an existing open issue.
No "drive-by" commits without an issue. After implementing, reference the issue in
the commit/PR and tick it off in the release tracking issue. This keeps the issue
tracker the single source of truth for *why* every change was made.

This rule is about **deployable code only**. Meta/process edits that don't ship —
e.g. workflow tweaks to this `CLAUDE.md`, memory notes, local tooling config — do
not require an issue and may be committed directly when Koen asks for them.

After completing a task:
1. In the master worktree: commit and push directly to `master`. In a feature
   worktree: commit and push to the feature branch, let CI run, and merge to
   `master` once it is green (and Koen has asked for the merge).

**Autonoom een release afwerken (geen "mag ik doorgaan?").** Zodra Koen werk aan
een release toewijst — of dat nu de lopende of de volgende release is (bv. "dit is
voor v1.x.0", "zet dit in de volgende release") — werkt Claude **alle** issues van
die release **autonoom** af: implementeren → tests → CI groen → mergen naar `master`
zodra CI groen is → issues sluiten → de release-tracker bijwerken. **Niet** telkens
vragen of je mag doorgaan of mergen; de release-toewijzing ís de toestemming.
Onderbreek enkel voor (a) een echte inhoudelijke ontwerpkeuze die Koens input nodig
heeft, of (b) een onomkeerbare/risicovolle stap — met name een **UAT- of
PROD-deploy**, die altijd expliciete bevestiging vereist. HDEV mag autonoom.

**NOOIT vinkjes uitvinken die Koen heeft aangevinkt.** De checkboxes in een
release-tracker/issue (m.n. de HDEV-validatie) vinkt **Koen zelf** af. Bij het
bijwerken van een tracker: **haal eerst de huidige body op** en **behoud** de
bestaande checkbox-status — reset NOOIT `- [x]` terug naar `- [ ]`. Werk bij
voorkeur **incrementeel** (voeg regels toe of wijzig alleen de nodige regels) i.p.v.
de hele body te herschrijven; als je toch de body vervangt, neem dan de reeds
aangevinkte vakjes exact over.

**Always create a release tracking issue** when starting a new batch of work
(e.g. "Release v1.x.0 — <short description>"). List all planned issues with
checkboxes, and add the full deploy checklist (HDEV test → GitHub Release →
UAT → PROD → verify logs). Close the issue when the release is on PROD.
This is the single source of truth for what's in a release and how to deploy it.

At the start of each session, sync with master:
```bash
git fetch origin master && git reset --hard origin/master
```

## Releases and hotfixes

**Feature-branch work only enters the release pipeline once it is merged to
`master` (after CI is green).** HDEV deploys `master` HEAD and the release tag
targets `master`, so nothing on an unmerged feature branch can ever reach HDEV,
UAT, or PROD. The merge-to-`master` is the gate into a release — do it (per the
feature-branch norm, when Koen asks) before any HDEV test or tag step below.

### Handoff from a feature worktree to master

The merge to `master` is also a **handoff**: the feature-worktree CLI holds all
the context for going live; the master CLI that runs the release starts cold. So
the merging PR body (mirrored into the release tracking issue) must carry a
short **"Na de merge"** block capturing everything CI cannot:

- **Migration?** the new alembic head (e.g. `058 -> 059`).
- **New/changed env vars?** name them — they are NOT auto-added to the real
  `.env.<env>` files; each host must be updated before deploy.
- **Feature flag / kill-switch?** name it + intended default per environment
  (dark-launch vs. live).
- **One-off script?** (backfill, data fix) — what runs, when, where.
- **Manual validation?** anything an external dependency (Mollie/Gmail/Mistral)
  needs that the read-only smoke test does not exercise.

The master CLI taking over reads that block first, then drives HDEV → UAT → PROD.
From the merge onward the master CLI owns tagging and issue-closing; the feature
worktree does not tag.

**HDEV deploys `master` HEAD; UAT and PROD deploy a pinned tag.** `deploy-hdev.sh`
does `git reset --hard origin/master` (integration line). `deploy-uat.sh` and
`deploy-prod.sh` take a release tag as argument and check it out detached — they
do NOT assume master equals the latest release, because master may already be
ahead. A release tag is the **single source of truth** for what runs on UAT/PROD.

**Test on HDEV against master BEFORE creating the Release tag.** The release
tag is the single source of truth for UAT/PROD, so it must point at a commit
that has already been validated on HDEV — never tag an untested commit. Correct
order: (1) deploy master to HDEV (`./deploy-hdev.sh`), (2) test on HDEV,
(3) only then create the GitHub Release targeting that tested master commit.
Re-check the exact target commit at tag-time — master may have moved since the
work started.

**Mark each release with a GitHub Release (not a manual `git tag` push).**
Creating a Release on GitHub creates the tag **server-side**, so there is no
separate `git push origin <tag>` step (which is also blocked in the Claude
remote environment with a 403 on tag refs). Steps:
1. GitHub → **Releases** → **Draft a new release**.
2. **Choose a tag** → type `v1.x.x` → *"Create new tag: v1.x.x on publish"*.
3. **Target** → `master` (the commit you're releasing — must contain the fix).
4. Title `v1.x.x`, write notes, reference issues with `Fixes #NN`.
5. **Publish release** → the tag is created on the target commit.

For a hotfix on a released version while newer work is in progress (this is the
**master-side exception**: a hotfix branch may merge straight back into `master`
on urgency, without waiting for the feature-branch merge-on-request norm — but
still only after CI is green):
1. `git checkout -b hotfix/1.x.x v1.x.x`
2. Apply fix, commit, merge back into master once CI is green.
3. Publish a GitHub Release `v1.x.x` targeting master.

## Deploying a release to UAT / PROD

UAT and PROD pin an exact tag (passed as argument). Promote in order:
HDEV → UAT → PROD. On the server, in the repo checkout:

```bash
# HDEV — always tracks master (integration; no tag)
./deploy-hdev.sh

# UAT — deploy a specific tag
./deploy-uat.sh v1.x.x        # fetch --tags && checkout --detach <tag> && compose up --build -d

# PROD — same tag, after UAT looks good
./deploy-prod.sh v1.x.x
```

Each UAT/PROD script does `git fetch --tags --prune` then `git checkout --detach
<tag>` (detached HEAD is intended — you run an exact commit, not a moving branch),
then rebuilds with the matching compose + env file and runs a **read-only**
post-deploy smoke test (`tests/run-all.sh`) that creates no data. The backend runs
`alembic upgrade head` on startup, so DB migrations (e.g. 031) apply automatically
during the rebuild.

> **Shared Caddy: a release that changes `caddy/Caddyfile.shared` needs an extra
> step (#312/#314).** `deploy-uat.sh`/`deploy-prod.sh` run in the `uat/`/`prod/`
> checkout and do **not** touch the shared Caddy (a separate stack, `name: caddy`,
> serving all domains). Run, in the `caddy/` checkout: `./deploy-caddy.sh` — it
> forces the checkout onto `master` (also from a detached HEAD), checks that
> `encode` is present, and does `up -d --force-recreate caddy` (loads the config
> fresh from disk). It deliberately avoids `caddy reload`: that admin-API reload is
> in-memory only and does **not** survive a restart, which is what kept silently
> reverting the #303 compression. The compression smoke test
> (`tests/smoke/compression.sh`) is the safety net. One recreate covers UAT **and**
> PROD (same shared Caddy).

> First-time note: the tag must contain these tag-aware deploy scripts. For a
> release predating them, run the equivalent by hand once:
> `git fetch --tags origin && git checkout --detach v1.x.x && docker compose -f
> docker-compose.uat.yml --env-file .env.uat up --build -d`.

### Verifying a deploy via the backend logs

After every rebuild, check the backend logs to confirm migrations applied and
Uvicorn started cleanly. Always pass the matching `-f`/`--env-file` pair:

```bash
sudo docker compose -f docker-compose.<env>.yml --env-file .env.<env> logs backend --tail=80
# add -f instead of --tail to follow live (Ctrl+C to stop)
```

What to look for:
- `Running upgrade NNN -> NNN+1` lines → the new migrations applied. These show
  **only the first time** a migration runs; on a restart with no new migrations
  there are no "Running upgrade" lines and that is normal.
- `Uvicorn running on http://0.0.0.0:8000` → the app started.
- **No** tracebacks / `ERROR` lines between those two — a failed migration or
  import error aborts startup.

## Docker stack

| Service | Port | Notes |
|---|---|---|
| db | 5432 | PostgreSQL 16, volume-backed |
| backend | 8000 | FastAPI + Uvicorn — serveert óók alle HTML (server-rendered, #405) |
| caddy | 80/443 | Reverse proxy; all browser traffic goes through Caddy |

Sinds de React-exit (#405) is er **geen frontend-container meer**: alle
pagina's zijn server-rendered (Jinja + htmx/Alpine) vanuit de backend, en de
Caddy-catch-all wijst naar `backend:8000`. API-paden blijven `/api/v1/…`.

Check logs after changes:
```bash
sudo docker-compose logs backend --tail=50
```

The backend runs `startup.sh` on container start, which runs `alembic upgrade head` then `uvicorn`. Build-time import check runs via `check_imports.py` in the Dockerfile — if any import fails, the Docker build fails.

### Running `docker compose` commands on the server (IMPORTANT)

This deployment uses **per-environment compose files** (`docker-compose.hdev.yml`,
`.uat.yml`, `.prod.yml`) with **per-environment env files** (`.env.hdev`, etc.).
The compose files use `${VAR:?...}` guards (e.g. `FRONTEND_URL`), so any
`docker compose` command **fails unless you pass the matching env file**. Always
include `-f docker-compose.<env>.yml --env-file .env.<env>`:

```bash
sudo docker compose -f docker-compose.hdev.yml --env-file .env.hdev <cmd>
```

**Elk compose-bestand zet een expliciete projectnaam via de top-level `name:`-key**
(`caddy`, `dev`, `hdev`, `uat`, `prod`) (#155). Daardoor is de projectnaam
onafhankelijk van de map waaruit je `docker compose` draait: de gedeelde Caddy
(`name: caddy`) en de prod-stack (`name: prod`) kunnen veilig uit dezelfde map
draaien zonder elkaars containers als "orphans" te zien. Gevolg: **geen
`Found orphan containers`-warnings meer**, en `--remove-orphans` op één stack kan
een andere stack niet meer slopen. Bij de eerste deploy ná deze wijziging verhuist
`prod-caddy-1` naar het project `caddy` (= `caddy-caddy-1`); ruim de oude
`prod-caddy-1` één keer handmatig op als die blijft staan.

The DB user/password are **not** the defaults — they come from `DB_USER`/
`DB_PASSWORD` in the env file. Never hardcode `postgres:postgres`. Instead derive
credentials from the container's own environment:

`psql -U <user>` defaults to a database named after the user, which doesn't
exist here — always pass `-d "$POSTGRES_DB"` (the real DB, e.g.
`raakmillegem_hdev`) to connect:

```bash
# Run psql as the real superuser, connected to the real DB
... exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "..."'

# Run the test suite against a throwaway raaktest DB (derives creds from DATABASE_URL)
... exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE raaktest;"'
... exec backend sh -c 'export TEST_DATABASE_URL=$(echo "$DATABASE_URL" | sed "s#postgresql://#postgresql+psycopg2://#; s#/[^/]*\$#/raaktest#") && pip install -q -r requirements-dev.txt && python -m pytest -v'
```

The pytest suite **drops and recreates the schema** of its target DB, so it must
only ever point at a separate `raaktest` database — never the real one.

> Note: this repo uses Docker Compose v2 (`docker compose`, space), not v1
> (`docker-compose`, hyphen). The older `docker-compose` examples elsewhere in
> this file are legacy; prefer `docker compose`.

### CI

`.github/workflows/backend-tests.yml` runs the pytest suite on every push/PR to
`master`, using a disposable Postgres 16 service container. Green/red shows up
per commit on GitHub.

### Testen en test-evidence (conventie)

- **Elke functionele wijziging in een release krijgt waardecreërende pytests** —
  geen tests pro forma, wel de invarianten die ertoe doen (security, geld,
  autorisatie, datakoppelingen).
- **Test-evidence in het release-issue:** na de push haalt Claude de geslaagde
  CI-run op (`backend-tests.yml`) en noteert in het release-issue de **run-id +
  link** en de **pytest-samenvatting** (`N passed`). De CI draait tegen een echte
  Postgres 16 — dat is het bewijs dat de suite groen was, niet een lokale claim.
- **Release-tracker format — één checkbox per issue.** Elk issue staat als één
  regel `- [ ] #NN (korte omschrijving)`. **NIET** twee checkboxes per issue, en
  de zin **"getest op HDEV door Koen" hoort NERGENS** in een issue of tracker.
  Claude **sluit** elk geïmplementeerd issue zelf zodra CI groen is — met een
  afsluit-comment dat beschrijft wat gerealiseerd is + hoe te testen op HDEV. De
  ene checkbox in het tracker-issue staat voor Koens HDEV-validatie en vinkt
  **Koen zelf** af (nooit Claude). Eén intro-zin volstaat: *"De checkbox hieronder
  vink jij af zodra je het op HDEV gevalideerd hebt."* Geen
  "PR groen / gemerged naar master"-ruis in de issuelijst — CI-evidence (run-id +
  `N passed`) mag in een aparte sectie van het tracker-issue.


## Backend architecture (FastAPI + SQLAlchemy)

**Entry point:** `backend/app/main.py` — registers all routers under `/api/v1`.

**Routers** (`backend/app/routers/`):
- `auth.py` — Login, seed-admin
- `members.py` — Family/person/membership CRUD; `POST /families` is the public registration endpoint
- `activities.py` — Activity CRUD, sub-registrations, public registration (`POST /activities/{id}/register`)
- `ideas.py` — Public idea submission
- `cms.py` — CMS pages (public read, admin write); also serves `/api/v1/postal-codes`
- `admin.py` — Dashboard stats

**Payment domains** (`backend/app/domains/`):
- `payment_gateway/` — Mollie integration. `MollieProvider.create_payment()` creates a Mollie payment. Webhook URL is skipped when running on localhost (Mollie can't reach it). Uses `payment_metadata` column (not `metadata` — reserved by SQLAlchemy).
- `payment_status/` — Internal `PaymentRecord` tracking. `create_payment_record()` is called from routers after a registration is saved.

**Key models:**
- `Member` = household (family unit); has `board_member_id` FK
- `Person` = individual; linked to Member via `MemberPerson` junction (with `relation_type`: "hoofdlid", "partner", "(meerderjarig) kind")
- `Person` does NOT have a `mobile` column — mobile is stored as a `ContactDetail` with `contact_type_code = "mobile"`
- `Address` → normalized via `PostalCode` table; always use postal code from the lookup table
- `Activity` → `ActivitySubRegistration` (2-level); sub-registrations can have their own `price`, `max_participants`, `products` (`reg_form_type` is legacy/ongebruikt sinds de v2.0-unificatie — zie "Activity registration form")
- `Registration` → `RegistrationItem` (één regel per gekozen product/aantal)
- `GatewayPayment.payment_metadata` (JSON column — NOT `metadata`)

**Auth:** JWT Bearer tokens voor de JSON-API (`get_current_admin` op alle admin-endpoints); de server-rendered schermen gebruiken de HttpOnly-sessiecookie + CSRF via `app.domains.auth.api` (`require_admin_ui`, `require_csrf`).

**Pydantic v2:** use `model_validate()`, `model_dump(exclude_none=True)`.

## Alembic migrations

Chain: `001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009 → 010 → 011`

Never modify a migration that has already been merged to master. Always create a new migration file for schema changes. Make migrations idempotent (check if table/column exists before creating).

After adding a migration, verify the chain:
```bash
sudo docker-compose exec backend alembic heads
```
There must be exactly one head.

## Activity registration form (unified in v2.0)

**Sinds de React-exit (v2.0, #405) is er één geünificeerd inschrijfformulier**
(`_inschrijf_form.html`) — géén vertakking meer op `reg_form_type`. Het React-tijdperk
kende zes vormtypes (`INDIVIDUAL`, `TEAM`, `GROUP`, `PAID_PER_PERSON`,
`PAID_PRODUCTS`, `AGE_CATEGORY`); die zijn **bewust vereenvoudigd** weg. Het ene
formulier dekt alle gevallen via twee onderdeel-eigenschappen:

- **Contact** (naam, e-mail, mobiel) — altijd.
- **Ploegnaam** — enkel als `component.team_name_required` (vervangt het oude `TEAM`).
- **Producten als regelitems** — `component.products`, elk met aantal-invoer; totaal
  wordt **server-side** herberekend bij elke wijziging (`/…/totaal`, §19.3 — geen
  drift) en inline vastgelegd als `RegistrationItem` bij commit (NIET via
  `registration.items` — die is niet gevuld vóór commit). Dit dekt de betaalgevallen
  die het oude `PAID_PRODUCTS`/`PAID_PER_PERSON` verzorgden; gratis producten
  (`is_free`/`price == 0`) of `pay_on_site` maken het regelitem gratis resp. ter
  plaatse te betalen.

De oude group-size- en leeftijdscategorie-tellers (`GROUP`, `AGE_CATEGORY`,
`age_category_config`) zijn er in v2.0 niet meer. Wil je zoiets terug, dan is dat
**nieuwe scope** (nieuw issue), geen bestaand gedrag dat hersteld moet worden.

> **Volzet-status** komt van `max_participants` per onderdeel (#451): de bezetting
> (som van de item-hoeveelheden) wordt batched berekend in `list_activities` en zet
> `is_full`, waarna de kaart een 'Volzet'-badge toont i.p.v. de inschrijfknop. De
> `isPaid`-regel (positieve onderdeel-/productprijs → betalend) staat onder "Fixed
> UI decisions".

## UI-architectuur (server-rendered, React-exit #405)

Er is geen Next.js/Node meer. Elke component levert zijn schermen als
`ui.py`/`admin_ui.py` (routes bouwen een view-model en kiezen een template) +
`templates/` (Jinja; htmx voor interactie, Alpine voor kleine client-state).
Conventies: `docs/ui-conventies.md` (#396) en de UI-kit-macro's in
`backend/app/ui/templates/_macros.html`. De publieke schil is
`site_base.html` (+ `app.ui.site_context(db)`), de beheer-schil
`admin_base.html` (+ `app.ui.admin_nav(active)`). CSS wordt gegenereerd met
`scripts/build-css.sh` (Tailwind standalone-CLI, nul Node) → commit
`backend/app/static/app.css` mee na template-wijzigingen. E2e-golden-flows:
playwright-python in `backend/tests_e2e/` (aparte CI-job).

## Fixed UI decisions — do not change these

- **Address grid layout:** 4-column grid. Row 1: Straat (col-span-2) + Huisnummer (col-1) + Bus (col-1). Row 2: Postcode (col-span-4, full width). Bus number is always on the same row as house number, to the right of it.
- **Postal code field:** Always a **`<select>`-dropdown** gevuld uit de
  postcodetabel (`PostalCode`) — nooit een vrij tekstveld. Consistent in héél v2.0
  (word-lid én gezinsportaal). `form.postal_code` is enkel gezet als de gebruiker
  een geldige optie kiest; submit is geblokkeerd zonder geldige postcode. (In v1.14
  was dit een autocomplete-invoer; v2.0 vereenvoudigde het bewust tot een dropdown —
  bevestigd door Koen, juli 2026.)
- **Payment default:** Default payment method is online (Mollie). On success with a `checkout_url`, do a **hard redirect** — server-rendered schermen zetten de `HX-Redirect`-header (nooit een soft/client-side navigatie) zodat de browser echt naar Mollie gaat.
- **`isPaid` check:** sub-registrations can have their own price independent of the parent activity price — a positive sub-registration price makes the flow paid.

## Choosing new tools / dependencies — Europe First

Before proposing **or** adding any new tool, library, service, model or external
dependency, **first check whether a European (EU) alternative exists, and prefer
it.** Europe First.

- This applies to cloud services, APIs, hosted models and SaaS, **and** to
  self-hosted options (where the audio/data stays within the EU).
- Always surface the EU-vs-non-EU options in the proposal, with the chosen option
  and the reason.
- Prefer, in order: data stays in the EU → EU-based vendor → open-source that we
  self-host on our own EU infrastructure. Avoid sending personal data to non-EU
  cloud services.
- If no viable EU option exists, say so explicitly and explain the trade-off
  before adding the non-EU dependency.

## Code change discipline

- Only change what was explicitly requested. Nothing more.
- If something looks odd or suboptimal but wasn't mentioned, say so in chat and wait for approval — do not change it.
- Never "clean up" surrounding code while fixing something else.
- If a requested change requires touching something adjacent, explain what and why before doing it.

## Common mistakes to avoid

- Do not add `mobile` as a kwarg to `Person(...)` — it's not a column on Person.
- Do not add `orders = relationship("Order", ...)` to Member — the Order model was removed.
- Do not use `metadata` as a column name on SQLAlchemy models — it's reserved. Use `payment_metadata`.
- Do not compute `total_amount` from `registration.items` after `db.flush()` — the ORM relationship is not populated yet. Compute inline while creating the items.
- Do not use `datetime.utcnow()` — use `datetime.now(timezone.utc)`.
- After any change to `backend/app/main.py` router includes or domain imports, verify `check_imports.py` would pass by checking that all imported modules exist.
- Never name a Pydantic field the same as its type **when it has a default** —
  e.g. `date: Optional[date] = None`. Python binds `date = None` in the class
  namespace before evaluating the annotation, so the field type silently becomes
  `NoneType` and Pydantic rejects every value with 422 "Input should be None".
  Alias the type import instead (`from datetime import date as Date`, mirroring
  `time as Time`). This bit us in `ActivityUpdate` (hotfix v1.2.1). The blanket
  fix `from __future__ import annotations` per schema file is tracked in #100.

## Validation layers — DB vs. service vs. router

Three layers, each with one job. Put each check where it belongs; don't collapse
them into one.

1. **Router (HTTP-laag)** — the doorman. Only cares about the *request*: is the
   caller authenticated/authorised (`get_current_admin`), does the JSON parse into
   the Pydantic schema (shape/types/required fields → automatic 422), and shaping
   the *response*. It does NOT contain business rules. Pydantic schemas live here:
   they validate **form** (is `price` a number? is `email` an email?), not
   **meaning**.
2. **Service / domain-laag** — the rulebook. Business invariants that need other
   data or domain knowledge: "can this member be reminded twice?", "does
   `amount_paid` match the expected total?", "is this sub-registration still
   open?". These are the rules that must hold no matter *which* router calls them,
   so they live in `app/services/` or `app/domains/`, never inline in a router.
   A rule enforced only in the router can be bypassed by any other caller.
3. **Database (laatste vangnet)** — the safety net. Constraints that must be true
   even if a bug slips past the code: `UNIQUE`, `NOT NULL`, `CHECK (price >= 0)`,
   foreign keys. The DB is the last line; it guarantees integrity at rest even if
   two requests race or a migration/script writes directly. Tracked broadly in #94.

Rule of thumb: **form → router (Pydantic); meaning → service; integrity-at-rest →
DB.** A critical invariant (e.g. no negative price) is often worth enforcing in
*both* the schema (nice 422 for the user) and the DB (hard guarantee) — that's
defence in depth, not duplication.
