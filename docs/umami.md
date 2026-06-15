# Umami web-analytics (#152, laag 1)

Zelf-gehoste, **cookieloze** web-analytics voor de publieke site. Hergebruikt de
bestaande PostgreSQL via een **eigen database** (geen tweede DB-engine), draait
als Docker-service achter de bestaande Caddy en respecteert Do-Not-Track. Geen
PII: enkel anoniem bezoek + een handvol funnel-events.

> Bewust gescheiden van **laag 2** (first-party `business_events` in onze eigen
> Postgres, server-side gelogd — zie `backend/app/domains/analytics/`). Laag 1 =
> anoniem webgedrag; laag 2 = ERP-gerichte business-metrics.

## Wat zit al in de repo

- **HDEV**: `umami`-service in `docker-compose.hdev.yml` (database `umami_hdev`,
  `BASE_PATH=/umami`) + route in `caddy/Caddyfile.hdev` (`/umami/*`).
- **Frontend**: `components/Analytics.tsx` laadt de tracker **enkel** op publieke
  pagina's (nooit `/admin` of `/login`) en **enkel** wanneer geconfigureerd
  (`NEXT_PUBLIC_UMAMI_SRC` + `NEXT_PUBLIC_UMAMI_WEBSITE_ID`, build-time). DNT via
  `data-do-not-track="true"`.
- **Funnel-events** (`lib/analytics.ts` → `trackEvent`), geen PII:
  - `lid-worden-verzonden` (`{ betaalkeuze }`) — FamilyRegistrationForm
  - `inschrijving-verzonden` (`{ betaalkeuze }`) — RegistrationForm
  - `betaling-succes` / `betaling-geannuleerd` — betaalresultaat-pagina's

## Eenmalige setup op HDEV

1. **Secret** in `.env.hdev`:
   ```
   UMAMI_APP_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
   ```
2. **Database aanmaken** (het volume bestaat al, dus de init-scripts draaien niet
   opnieuw — daarom handmatig, eenmalig):
   ```
   sudo docker compose -f docker-compose.hdev.yml --env-file .env.hdev \
     exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE umami_hdev;"'
   ```
3. **Deploy** — Umami draait zelf de Prisma-migraties bij startup:
   ```
   ./deploy-hdev.sh
   ```
4. **Inloggen** op `http://YOUR_SERVER_IP:8081/umami` (standaard `admin` / `umami`
   — **meteen het wachtwoord wijzigen**).
5. **Website aanmaken** in de Umami-UI → kopieer het gegenereerde **Website ID**.
6. **Frontend koppelen** in `.env.hdev` en herbouwen:
   ```
   NEXT_PUBLIC_UMAMI_SRC=/umami/script.js
   NEXT_PUBLIC_UMAMI_WEBSITE_ID=<website-id-uit-stap-5>
   ```
   ```
   ./deploy-hdev.sh
   ```
7. **Verifiëren**: bezoek de publieke site → pageviews verschijnen in Umami.
   Controleer dat `/admin` **niet** getrackt wordt en dat een browser met DNT geen
   hits genereert.

## Privacyverklaring (verplichte stap)

Voeg in de admin (CMS → Pagina's) één regel toe aan de privacyverklaring, bv.:

> *"Deze website gebruikt Umami, een zelf-gehoste en cookieloze
> bezoekersstatistiek. Er worden geen persoonsgegevens verzameld en je IP-adres
> wordt geanonimiseerd. We respecteren de Do-Not-Track-instelling van je browser."*

## Promotie naar UAT / PROD

HDEV eerst valideren (zie boven). Daarna per omgeving:

1. **Compose** (`docker-compose.uat.yml` / `.prod.yml`): voeg een `umami`-service
   toe analoog aan HDEV, maar:
   - eigen database `umami_uat` / `umami_prod`,
   - eigen `UMAMI_APP_SECRET` per `.env`,
   - **geen** `BASE_PATH` (subdomein i.p.v. subpad),
   - sluit de service ook aan op het `raak_proxy`-netwerk zodat de gedeelde Caddy
     hem bereikt.
2. **Caddy** (`caddy/Caddyfile.shared`): subdomein-route `stats.<domein>` →
   `reverse_proxy umami:3000`.
3. **Frontend build-args**: `NEXT_PUBLIC_UMAMI_SRC=https://stats.<domein>/script.js`
   + het Website ID van die omgeving.
4. **Database** eenmalig aanmaken (`CREATE DATABASE umami_uat` / `_prod`).
5. **Backup**: controleer dat `db-backup` ook de nieuwe database meeneemt.

## Opmerkingen

- De tracker is een **no-op** zolang `NEXT_PUBLIC_UMAMI_*` leeg is — veilig in dev
  en vóór configuratie.
- `NEXT_PUBLIC_*` wordt **bij de build** geïnlined; na het wijzigen ervan moet de
  frontend opnieuw gebouwd worden (`./deploy-hdev.sh`).
