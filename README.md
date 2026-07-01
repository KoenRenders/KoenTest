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

Production target: Hetzner CX22 (Ubuntu, 4 Docker containers behind Caddy reverse proxy).

```bash
# On the server
git pull
docker compose -f docker-compose.yml up -d --build
docker compose exec backend alembic upgrade head
```

See `caddy/Caddyfile` for domain configuration.

## Claude Code tooling

Project-specific helpers for [Claude Code](https://claude.com/claude-code) live in
`.claude/` and are versioned with the repo (so every session and contributor gets
them). They contain **no secrets** — connection details come from environment
variables only.

### Skill: `/release`
`.claude/skills/release/SKILL.md` — guides a release end to end, following the
rules in `CLAUDE.md`: create/maintain the release-tracking issue, verify every
issue is merged and CI-green, collect CI evidence, guide the GitHub Release
(HDEV → tag → UAT → PROD) and close the issues. Invoke it in a session with
`/release` (e.g. "start release v1.x.0" or "wrap up v1.x.0").

Optionally it can run the deploy **over SSH** on the server and pull + analyse the
backend logs — but only when it runs in an SSH-capable environment and the
connection is provided via env vars (never committed):

| Env var | Purpose |
|---|---|
| `DEPLOY_SSH_HOST` / `DEPLOY_SSH_USER` / `DEPLOY_SSH_KEY` | SSH target + private-key path |
| `DEPLOY_SSH_PORT` | optional, default 22 |
| `DEPLOY_REPO_DIR` / `DEPLOY_CADDY_DIR` | checkout paths on the server |
| `DEPLOY_DRY_RUN` | optional; `1`/`true` prints the deploy commands instead of running them (connection test + log fetch still run) |

Guardrail: **HDEV runs automatically; UAT/PROD only after explicit confirmation**
and with a validated release tag. In an environment without SSH (e.g. Claude Code
on the web) it falls back to printing the exact commands and analysing pasted logs.

### Agent: `publieke-repo-bewaker`
`.claude/agents/publieke-repo-bewaker.md` — a read-only subagent that reviews a
diff **before committing** and flags anything that must not land in this **public**
repo: secrets/credentials, real server IPs/hostnames, real domain names, Storage
Box users/hosts, `.env` files with real values, personal ops/backup tooling, and
personal data (real names/e-mails/addresses). Returns a block/clear verdict with
findings per `file:line`. Use it before every commit/push.

## Documentation

- [Project Specification](docs/spec.md)
- [Change Request 01](docs/change_request_01.md)
- [Change Request 02](docs/change_request_02.md)
