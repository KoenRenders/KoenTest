# Raak Millegem — Community Portal

Web portal for the Raak Millegem community association in Millegem, Belgium.

## Tech Stack

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 |
| Backend | Python 3.12 + FastAPI |
| Frontend | Next.js 14 + React + TypeScript + Tailwind CSS |
| Payments | Mollie (stub) |
| Email | Python smtplib + Gmail SMTP |
| Infrastructure | Docker Compose + Caddy reverse proxy |

## Local Development Setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2+)
- No other dependencies required — everything runs in containers

### 1. Configuration

```bash
cp .env.example .env
# Edit .env with your own passwords and API keys
```

### 2. Start the stack

```bash
docker compose up -d
```

### 3. Seed data (first run only)

```bash
# Seed Belgian postal codes
docker compose exec backend python seed_postal_codes.py

# Seed webshop products and create the initial admin user
docker compose exec backend python seed_products.py
```

Default admin credentials (change immediately):
- **Email:** `admin@your-domain.example`
- **Password:** `changeme`

### 4. Access the application

| URL | Description |
|---|---|
| http://localhost | Public website (via Caddy) |
| http://localhost/api/docs | API documentation (Swagger UI) |
| http://localhost/admin | Admin panel |

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@db:5432/raak` |
| `SECRET_KEY` | JWT signing secret | `your-secret-key-here` |
| `FRONTEND_URL` | Frontend origin for CORS | `http://localhost:3000` |
| `MOLLIE_API_KEY` | Mollie payment API key | `test_xxxx` |
| `GMAIL_USER` | Gmail address for sending email | `yourapp@gmail.com` |
| `GMAIL_APP_PASSWORD` | Gmail app password (request at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)) | `xxxx xxxx xxxx xxxx` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token TTL in minutes | `60` |

## Features

- **Homepage:** activity overview, membership registration, ideas box
- **Activities:** grouped by year, status (Open / Full / Waitlist), registration
- **Archive:** all past activities automatically listed
- **Webshop:** Bread and Games products with member vs. regular pricing
- **CMS:** admin can create information pages (How we work, Christmas Radio, …)
- **Admin dashboard:** activity management, member management, orders, ideas
- **Email:** confirmations via Gmail SMTP

## Deployment

Three server environments run from the same repository, each in its own
checkout and compose project: **HDEV** follows `master`, **UAT** and **PROD** run a
pinned release tag. One script, `deploy.sh <env> [tag]`, deploys all three; it
backs up the database, rebuilds, lets the backend apply migrations at startup
(`alembic upgrade head`), and runs a read-only smoke test.

Do not run `deploy.sh` or `docker compose` by hand on the server. Use **`raakctl`**
on the server, or **`raak`** from a laptop (same verbs over SSH): `status`,
`deploy <env> [tag]`, `logs`, `diagnose`, `backup`, `restore-test`, `caddy`. It
resolves an environment to its own checkout, so you cannot deploy PROD from the
UAT directory by mistake.

UAT and PROD sit behind one shared Caddy (`caddy/Caddyfile.shared`, which imports
`caddy/parts/`); HDEV has its own (`caddy/Caddyfile.hdev`).

The release order, who may do which step, and what to verify after a deploy are
in `CLAUDE.md` under *Releases and hotfixes* and *Deploying a release to UAT /
PROD*. They are not repeated here.

## Branches and pull requests

The rules live in one place, `CLAUDE.md` under *Development workflow* and
*Releases and hotfixes*; this section only tells you where to look. In short:

- Every deployable change goes through a GitHub issue.
- Feature work happens on its own branch (`feature/<who>-<issue>-<slug>`) and
  reaches `master` through a pull request with green CI.
- The master CLI performs every merge, and only for work that is assigned to a
  release; unassigned work waits on its branch.
- A merged branch is deleted on GitHub automatically ("Automatically delete head
  branches" is on since 30 September 2026). Clean up your local copy with
  `git fetch --prune`. A branch that still exists on GitHub is either open work
  or parked for a later release.

## Claude Code tooling

Project-specific helpers for [Claude Code](https://claude.com/claude-code) live in
`.claude/` and are versioned with the repo (so every session and contributor gets
them). They contain **no secrets** — connection details come from environment
variables only.

### Releases
There is no release skill any more. The ordered procedure — tracker issue, merge
gate, CI evidence, HDEV, GitHub Release, UAT, shared Caddy, PROD, closing the
issues — lives in `CLAUDE.md` under *Running a release from the CLI — the order*,
next to the rules it follows. Deploys go through `raakctl` on the server (or
`raak` from a laptop), which resolves an environment to its checkout; HDEV runs
autonomously, UAT and PROD only after explicit confirmation.

### Agent: `publieke-repo-bewaker`
`.claude/agents/publieke-repo-bewaker.md` — a read-only subagent that reviews a
diff **before committing** and flags anything that must not land in this **public**
repo: secrets/credentials, real server IPs/hostnames, real domain names, Storage
Box users/hosts, `.env` files with real values, personal ops/backup tooling, and
personal data (real names/e-mails/addresses). Returns a block/clear verdict with
findings per `file:line`. Use it before every commit/push.

## Documentation

- [Project Specification](docs/spec.md)
- [Change Request 01](docs/change_request_01_postal_codes.md)
- [Change Request 02](docs/change_request_02_registration_form.md)
