# Umami web-analytics (#152, laag 1)

Zelf-gehoste, **cookieloze** web-analytics voor de publieke site. Hergebruikt de
bestaande PostgreSQL via een **eigen database** (geen tweede DB-engine), draait
als Docker-service achter de bestaande Caddy en respecteert Do-Not-Track. Geen
PII: enkel anoniem bezoek + een handvol funnel-events.

> Bewust gescheiden van **laag 2** (first-party `business_events` in onze eigen
> Postgres, server-side gelogd — zie `backend/app/domains/analytics/`). Laag 1 =
> anoniem webgedrag; laag 2 = ERP-gerichte business-metrics.

## Wat zit al in de repo

- **HDEV**: `umami`-service in `docker-compose.hdev.yml` (database `umami_hdev`)
  op een **eigen poort `8082`** (root-served, geen subpad/Caddy-route). Het prebuilt
  image past runtime-`BASE_PATH` niet toe, daarom geen `/umami`-subpad.
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
4. **Inloggen** op `http://YOUR_SERVER_IP:8082/` (standaard `admin` / `umami`
   — **meteen het wachtwoord wijzigen**).
5. **Website aanmaken** in de Umami-UI → kopieer het gegenereerde **Website ID**.
6. **Frontend koppelen** in `.env.hdev` en herbouwen:
   ```
   NEXT_PUBLIC_UMAMI_SRC=http://YOUR_SERVER_IP:8082/script.js
   NEXT_PUBLIC_UMAMI_WEBSITE_ID=<website-id-uit-stap-5>
   ```
   ```
   ./deploy-hdev.sh
   ```
7. **Verifiëren**: bezoek de publieke site → pageviews verschijnen in Umami.
   Controleer dat `/admin` **niet** getrackt wordt en dat een browser met DNT geen
   hits genereert.

## Privacyverklaring

Een gepubliceerde privacypagina wordt geseed via migratie 048 (slug `privacy`,
bereikbaar op `/privacy`, gelinkt vanuit de footer, niet in de hoofdnavigatie).
Ze bevat al de vereiste regel over de cookieloze analytics:

> *"Deze website gebruikt Umami, een zelf-gehoste en cookieloze
> bezoekersstatistiek. Er worden geen persoonsgegevens verzameld en je IP-adres
> wordt geanonimiseerd. We respecteren de Do-Not-Track-instelling van je browser."*

De tekst is een **template** — pas hem aan via CMS → Pagina's (en laat hem zo
nodig juridisch nakijken). De seed is idempotent en raakt een al aangepaste
pagina niet meer aan.

## Promotie naar UAT / PROD (#176)

In tegenstelling tot HDEV (eigen poort 8082, geen gedeelde Caddy) draaien UAT/PROD
achter de **gedeelde Caddy** (`raak_proxy`). Umami zit daar op een **eigen
subdomein op root** (geen subpad — het prebuilt image negeert runtime-`BASE_PATH`).

Wat al in de repo zit:
- `umami`-service in `docker-compose.uat.yml` (DB `umami_uat`, alias `uat-umami`) en
  `docker-compose.prod.yml` (DB `umami_prod`, alias `prod-umami` + een aparte
  `umami-db-backup`-service, prefix `prod-umami`).
- Caddy-routes `{$STATS_UAT_DOMAIN}` / `{$STATS_PROD_DOMAIN}` in
  `caddy/Caddyfile.shared`.
- `NEXT_PUBLIC_UMAMI_*` build-args op de uat/prod-frontend.

Stappen per omgeving:

1. **DNS (Versio)**: A/AAAA-record voor `stats.uat` resp. `stats` naar de server-IP.
   **Geen underscore** in de hostnaam (Let's Encrypt weigert dat).
2. **`.env.caddy`**: zet `STATS_UAT_DOMAIN=stats.uat.<domein>` /
   `STATS_PROD_DOMAIN=stats.<domein>` **vóór** je de Caddy herlaadt — een lege
   waarde breekt de Caddy-config voor álle sites. Daarna de gedeelde Caddy herladen.
3. **`.env.<omgeving>`**: `UMAMI_APP_SECRET` zetten (en `UMAMI_DATABASE_URL` met
   `%23` als het DB-wachtwoord een `#` bevat).
4. **Database** eenmalig aanmaken:
   ```
   sudo docker compose -f docker-compose.<omgeving>.yml --env-file .env.<omgeving> \
     exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE umami_uat;"'
   ```
   (op PROD: `umami_prod`).
5. **Deploy** → `https://stats.<omgeving>/` toont de Umami-login (geldig TLS-cert).
   Inloggen (`admin`/`umami` → meteen wijzigen), **website aanmaken**, Website ID
   kopiëren.
6. **Frontend koppelen** in `.env.<omgeving>` en herbouwen:
   ```
   NEXT_PUBLIC_UMAMI_SRC=https://stats.<omgeving>/script.js
   NEXT_PUBLIC_UMAMI_WEBSITE_ID=<website-id>
   ```
   → opnieuw deployen. Verifieer dat pageviews binnenkomen, `/admin` en `/login`
   niet getrackt worden, en DNT geen hits geeft.
7. **PROD-backup**: na de nachtelijke run staat er een `prod-umami-*.sql.gz` in
   `./backups` (de `umami-db-backup`-service draait om 03:00).

## Opmerkingen

- De tracker is een **no-op** zolang `NEXT_PUBLIC_UMAMI_*` leeg is — veilig in dev
  en vóór configuratie.
- `NEXT_PUBLIC_*` wordt **bij de build** geïnlined; na het wijzigen ervan moet de
  frontend opnieuw gebouwd worden (`./deploy-hdev.sh`).
