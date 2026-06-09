# Deployment handleiding — Raak Millegem

## Omgevingen

| Omgeving | `.env` bestand | `docker-compose` bestand | Caddyfile | URL |
|---|---|---|---|---|
| DEV (lokaal) | `.env.dev` | `docker-compose.dev.yml` | `caddy/Caddyfile.dev` | http://localhost |
| UAT (Hetzner) | `.env.uat` | `docker-compose.uat.yml` | `caddy/Caddyfile.uat` | http://128.140.125.218:8080 |
| PROD (Hetzner) | `.env.prod` | `docker-compose.prod.yml` | `caddy/Caddyfile.prod` | http://128.140.125.218 |

---

## Versiestrategie (Git branches)

```
feature/mijn-wijziging   ← Claude ontwikkelt hier
        ↓ merge
develop                  ← UAT-omgeving
        ↓ merge + tag
main                     ← Productie
```

### Nieuwe feature deployen naar UAT
```bash
git checkout develop
git merge feature/mijn-wijziging
git push origin develop
# Op server: cd /opt/raakmillegem/uat && git pull && docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d
```

### UAT goedgekeurd → naar PROD
```bash
git checkout main
git merge develop
git tag v1.2.0
git push origin main
git push origin v1.2.0
# Op server: cd /opt/raakmillegem/prod && git pull && docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d
```

### Hotfix op productie (zonder UAT-wijzigingen mee te nemen)
```bash
git checkout -b hotfix/v1.2.1 v1.2.0
# fix de bug
git tag v1.2.1
git push origin hotfix/v1.2.1
git push origin v1.2.1
# Deploy naar PROD, daarna merge terug naar develop:
git checkout develop
git merge hotfix/v1.2.1
```

---

## DEV — lokale installatie (pc of laptop)

```bash
git clone -b develop https://github.com/KoenRenders/KoenTest.git
cd KoenTest
cp .env.dev.example .env.dev
# Pas .env.dev aan indien nodig
docker compose -f docker-compose.dev.yml --env-file .env.dev up --build -d
```

Bereikbaar op http://localhost en http://localhost/admin/login

---

## Eerste installatie op Hetzner

### 1. Server aanmaken
- Cloud server: Ubuntu 24.04, minimaal CX22 (2 vCPU, 4 GB RAM)
- SSH-sleutel toevoegen bij aanmaken
- IP: 128.140.125.218

### 2. Firewall instellen in Hetzner controlepaneel
Ga naar je server → **Firewalls** → nieuwe firewall:

| Richting | Protocol | Poort | Bron |
|---|---|---|---|
| Inkomend | TCP | 22 | Any (of beperk tot jouw IP) |
| Inkomend | TCP | 80 | Any |
| Inkomend | TCP | 443 | Any |
| Inkomend | TCP | 8080 | Any (UAT) |

Poort 5432 (PostgreSQL) en 8000 (backend) **niet** openzetten.

### 3. Server voorbereiden
```bash
ssh -i ~/.ssh/raak-millegem-hetzner root@128.140.125.218
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git
systemctl enable --now docker
mkdir -p /opt/raakmillegem/prod /opt/raakmillegem/uat
```

### 4. PROD installeren
```bash
cd /opt/raakmillegem/prod
git clone -b main https://github.com/KoenRenders/KoenTest.git .
cp .env.prod.example .env.prod
nano .env.prod   # vul alle waarden in
docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d
```

### 5. UAT installeren
```bash
cd /opt/raakmillegem/uat
git clone -b develop https://github.com/KoenRenders/KoenTest.git .
cp .env.uat.example .env.uat
nano .env.uat    # vul alle waarden in
docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d
```

### 6. Inloggen
- PROD: http://128.140.125.218/admin/login
- UAT:  http://128.140.125.218:8080/admin/login

Log in met `koen.renders@gmail.com` — je ontvangt een magic link via e-mail.

---

## Reguliere updates

### PROD updaten
```bash
ssh -i ~/.ssh/raak-millegem-hetzner root@128.140.125.218
cd /opt/raakmillegem/prod
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d
```

### UAT updaten
```bash
ssh -i ~/.ssh/raak-millegem-hetzner root@128.140.125.218
cd /opt/raakmillegem/uat
git pull
docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d
```

---

## Database backup

Dagelijkse pg_dump ophalen naar je pc (uitvoeren vóór je restic-backup):

```bash
#!/bin/bash
ssh -i ~/.ssh/raak-millegem-hetzner root@128.140.125.218 \
  "docker exec \$(docker ps -qf name=prod-db-1) pg_dump -U postgres raakmillegem | gzip" \
  > ~/backups/raakmillegem_$(date +%Y%m%d).sql.gz
```

Voeg `~/backups/` toe aan je restic-configuratie zodat de dump automatisch meegenomen wordt.

---

## Later: domeinnaam + HTTPS

Pas `caddy/Caddyfile.prod` aan:
```
raakmillegem.be {
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle {
        reverse_proxy frontend:3000
    }
}
```

En update `FRONTEND_URL` en `PUBLIC_URL` in `.env.prod` naar `https://raakmillegem.be`.
