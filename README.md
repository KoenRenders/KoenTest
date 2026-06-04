# Raak Millegem — Community Portal

Web portal for the Raak Millegem (KWB Millegem) community association in Millegem, Belgium.

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
- **Email:** `admin@raakmillegem.be`
- **Password:** `changeme`

### 4. Access the application

| URL | Description |
|---|---|
| http://localhost:3000 | Public website |
| http://localhost:8000/docs | API documentation (Swagger UI) |
| http://localhost:3000/admin | Admin panel |

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@db:5432/raak` |
| `SECRET_KEY` | JWT signing secret | `your-secret-key-here` |
| `FRONTEND_URL` | Frontend origin for CORS | `http://localhost:3000` |
| `MOLLIE_API_KEY` | Mollie payment API key | `test_xxxx` |
| `GMAIL_USER` | Gmail address for sending email | `yourapp@gmail.com` |
| `GMAIL_APP_PASSWORD` | Gmail app password | `xxxx xxxx xxxx xxxx` |
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

## Documentation

- [Project Specification](docs/spec.md)
- [Change Request Log](docs/change_request_01.md)
