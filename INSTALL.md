# Installation

How to stand up this stack from scratch. Day-to-day releases and deploys are
covered in `CLAUDE.md` (*Releases and hotfixes*, *Deploying a release to UAT /
PROD*); build and validation in `BUILDING.md`.

This file deliberately contains **no host names, IP addresses, server paths or
account details** — this repository is public. Everything host-specific lives in
the `.env.<env>` files, which are never committed.

## Environments

| Environment | Env file | Compose file | Reverse proxy |
|---|---|---|---|
| dev | `.env.dev` | `docker-compose.dev.yml` | own Caddy (`caddy/Caddyfile.dev`) |
| hdev | `.env.hdev` | `docker-compose.hdev.yml` | own Caddy (`caddy/Caddyfile.hdev`), published on port 8081 |
| uat | `.env.uat` | `docker-compose.uat.yml` | shared Caddy |
| prod | `.env.prod` | `docker-compose.prod.yml` | shared Caddy |

UAT and PROD publish no application ports of their own: both are served by one
shared Caddy (`docker-compose.caddy.yml`, project `caddy`) that terminates HTTPS
for every domain. Its config is split per environment under `caddy/parts/`; see
`CLAUDE.md` → *Shared Caddy: expand/contract*.

## Local development

```bash
git clone https://github.com/KoenRenders/KoenTest.git
cd KoenTest
cp .env.dev.example .env.dev     # fill in the values
./deploy-dev.sh
```

## A fresh server

Requirements: a Linux host with Docker Engine and Compose v2, plus `git`. Expose
only 80 and 443 (and 8081 if you want HDEV reachable). Do **not** expose the
database (5432) or the backend (8000) — both are reachable through the proxy.

1. **One directory per environment**, plus one for the shared Caddy. The paths
   are your choice: the deploy scripts operate on the directory they live in.
2. **Clone the repository into each** of those directories.
3. **Create the shared proxy network once**, before the first start:
   ```bash
   docker network create raak_proxy
   ```
4. **Fill in the environment files**: copy each `.env.<env>.example` to
   `.env.<env>` and complete it. The compose files use `${VAR:?...}` guards, so a
   missing variable fails the command instead of starting a half-configured
   stack. The shared Caddy has its own `.env.caddy` holding the domain names.
5. **Deploy**, from the matching directory:
   ```bash
   ./deploy.sh hdev              # follows master
   ./deploy.sh uat  vX.Y.Z       # exact release tag
   ./deploy.sh prod vX.Y.Z
   ```
   Extra arguments are passed through to `docker compose up`.
6. **Bring up the shared Caddy** from its own checkout: `./deploy-caddy.sh`.

Database migrations need no separate step: the backend container runs
`startup.sh`, which does `alembic upgrade head` before starting Uvicorn.

Sign-in is by magic link, handled by the auth domain
(`backend/app/domains/auth/`).

## Diagnostics

After a deploy, `./logging.sh <env>` bundles container status, `alembic
heads`/`current`, disk space, an error filter and the recent backend and proxy
logs into `/tmp/<env>-diagnostics.log`.

## Backups

The HDEV and PROD compose files ship a `db-backup` service. Off-site backup is
deliberately **not** described here: it is operational tooling that belongs on
the server, outside this public repository.
