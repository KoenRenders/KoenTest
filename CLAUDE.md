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

All commits and pushes are done by Claude — the user never does this manually. Work directly on `master`. No feature branches, no PRs.

After completing a task:
1. Commit and push directly to `master`

At the start of each session, sync with master:
```bash
git fetch origin master && git reset --hard origin/master
```

## Releases and hotfixes

Tag each release before deploying to production:
```bash
git tag v1.x.x && git push origin v1.x.x
```

For a hotfix on a released version while newer work is in progress:
1. `git checkout -b hotfix/1.x.x v1.x.x`
2. Apply fix, commit, tag as `v1.x.x`, push
3. Merge back into master

## Docker stack

| Service | Port | Notes |
|---|---|---|
| db | 5432 | PostgreSQL 16, volume-backed |
| backend | 8000 | FastAPI + Uvicorn |
| frontend | 3000 | Next.js standalone build |
| caddy | 80/443 | Reverse proxy; all browser traffic goes through Caddy |

All API calls from the browser go through Caddy (not directly to :8000). Frontend uses `/api/v1/…` paths, Caddy proxies them to `backend:8000`.

Check logs after changes:
```bash
sudo docker-compose logs backend --tail=50
sudo docker-compose logs frontend --tail=50
```

The backend runs `startup.sh` on container start, which runs `alembic upgrade head` then `uvicorn`. Build-time import check runs via `check_imports.py` in the Dockerfile — if any import fails, the Docker build fails.

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
- `Activity` → `ActivitySubRegistration` (2-level); sub-registrations can have their own `reg_form_type`, `price`, `max_participants`
- `Registration` → `RegistrationItem` (for PAID_PRODUCTS form type)
- `GatewayPayment.payment_metadata` (JSON column — NOT `metadata`)

**Auth:** JWT Bearer tokens. `get_current_admin` dependency used on all admin endpoints. Token stored in localStorage on the frontend.

**Pydantic v2:** use `model_validate()`, `model_dump(exclude_none=True)`.

## Alembic migrations

Chain: `001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009 → 010 → 011`

Never modify a migration that has already been merged to master. Always create a new migration file for schema changes. Make migrations idempotent (check if table/column exists before creating).

After adding a migration, verify the chain:
```bash
sudo docker-compose exec backend alembic heads
```
There must be exactly one head.

## Activity registration form types

`reg_form_type` on `Activity` or `ActivitySubRegistration` controls the registration form:

| Code | Behaviour |
|---|---|
| `INDIVIDUAL` | Single name/contact only |
| `TEAM` | Adds team name field |
| `GROUP` | Adds group size (no price) |
| `PAID_PER_PERSON` | Group size × unit price; uses `active_sub.price` if set, else `activity.price` |
| `PAID_PRODUCTS` | Sub-registrations as line items; total computed inline while creating `RegistrationItem` records (NOT from `registration.items` relationship — it's not populated before commit) |
| `AGE_CATEGORY` | Per-category counters (JSON); config in `activity.age_category_config` |

For `PAID_PRODUCTS`: `paidProducts` on the frontend are sub-registrations where `is_free=false` AND `reg_form_type` is null. Sub-registrations that have their own `reg_form_type` are separate registration paths, not product line items.

## Frontend architecture (Next.js 15 App Router)

**API layer:** `frontend/src/lib/api.ts` — Axios instance with JWT Bearer interceptor. All backend calls go through named exports here. Never call `fetch()` directly; always add new functions to `api.ts`.

**Key utilities:**
- `src/lib/money.ts` — `formatPrice(str)`, `isPositivePrice(str | undefined)`
- `src/lib/errors.ts` — `parseApiError(err, fallback)` for user-facing error messages
- `src/lib/types.ts` — Shared TypeScript interfaces (`Activity`, `SubRegistration`, `CmsPage`, etc.)

**Pages:**
- `/` (homepage) — activity list, "Word lid" membership form, IdeaBox
- `/archief` — archived activities
- `/[slug]` — dynamic CMS pages
- `/admin/` — protected dashboard (login required); subpages: leden, activiteiten, ideeen, paginas
- `/betaling/succes` and `/betaling/geannuleerd` — Mollie payment result pages

**Components of note:**
- `RegistrationForm.tsx` — Modal for activity registration; handles all form types, computes and displays total amount, redirects to Mollie `checkout_url` on success
- `FamilyRegistrationForm.tsx` — Multi-person household registration with postal code autocomplete dropdown
- `ActivityList.tsx` — Displays activities with status badges; shows sub-registration buttons

## Fixed UI decisions — do not change these

- **Address grid layout:** 4-column grid. Row 1: Straat (col-span-2) + Huisnummer (col-1) + Bus (col-1). Row 2: Postcode (col-span-4, full width). Bus number is always on the same row as house number, to the right of it.
- **Postal code field:** Always an autocomplete dropdown — never a free-text input. Fetches from `/api/v1/postal-codes`. The `form.postal_code` is only set when the user selects a valid option from the dropdown. Submit is blocked if no valid postal code is selected.
- **Payment default:** Default payment method in `RegistrationForm` is `"MOLLIE"` (online). On success with `checkout_url`, do `window.location.href = checkout_url` — never use `router.push()` for Mollie redirect.
- **`isPaid` check:** Must include `isPositivePrice(subRegistration?.price)` — sub-registrations can have their own price independent of the parent activity price.

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
