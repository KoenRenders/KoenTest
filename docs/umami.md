# Umami web-analytics (#152, laag 1)

Zelf-gehoste, **cookieloze** web-analytics voor de publieke site. Hergebruikt de
bestaande PostgreSQL via een **eigen database** (geen tweede DB-engine), draait
als Docker-service achter de bestaande Caddy en respecteert Do-Not-Track. Geen
PII: enkel anoniem bezoek + een handvol funnel-events.

> Bewust gescheiden van **laag 2** (first-party `business_events` in onze eigen
> Postgres, server-side gelogd — zie `backend/app/domains/analytics/`). Laag 1 =
> anoniem webgedrag; laag 2 = ERP-gerichte business-metrics.

> **Waarschuwing bij het lezen (10 september 2026).** De onderdelen hieronder die
> over de **frontend** gaan (`components/Analytics.tsx`, `lib/analytics.ts`,
> `NEXT_PUBLIC_UMAMI_*`) stammen uit het React-tijdperk en bestaan niet meer sinds de
> React-exit (#405). Het trackingscript wordt sinds #808 server-rendered uit de
> **tenant-instellingen** gerenderd. De omgevings- en Caddy-stappen kloppen nog wel;
> die zijn hieronder bijgewerkt. Deze doc integraal herschrijven is eigen scope.

## Wat zit al in de repo

- **HDEV: niets, en dat is een keuze (#820).** De `umami`-service stond daar tot
  10 september 2026 op poort 8082 en had sinds 13 juli van dat jaar niets meer
  geregistreerd — de dag waarop HDEV server-rendered werd. Het trackingscript draait
  sinds #808 alleen waar tenant-instellingen zijn, en HDEV heeft die bewust niet,
  zodat testverkeer nooit in de productiecijfers belandt. Er werd dus niet alleen
  niets gemeten, er zál ook niets gemeten worden. Zet hem niet terug zonder eerst dat
  te wijzigen — anders staat er weer 156 MiB stil te draaien.
- **Frontend**: zie de waarschuwing hierboven; dit is vervangen door #808.
- **Funnel-events** (`lib/analytics.ts` → `trackEvent`), geen PII:
  - `lid-worden-verzonden` (`{ betaalkeuze }`) — FamilyRegistrationForm
  - `inschrijving-verzonden` (`{ betaalkeuze }`) — RegistrationForm
  - `betaling-succes` / `betaling-geannuleerd` — betaalresultaat-pagina's

## Eenmalige setup op HDEV

Vervallen met #820: er is geen Umami op HDEV meer, en de database `umami_hdev` is
verwijderd. Wil je analytics testen, doe dat op UAT — dáár draait een instance die
ook werkelijk verkeer ziet.

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

UAT en PROD draaien achter de **gedeelde Caddy** (`raak_proxy`); HDEV heeft sinds
#820 geen Umami meer. Elke omgeving houdt haar **eigen** instance — samenvoegen is met
#259 bewust afgewezen. Umami zit daar op een **eigen
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
  frontend opnieuw gebouwd worden (`./deploy.sh hdev`).
