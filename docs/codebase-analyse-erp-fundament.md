# Codebase-analyse — fundament richting ERP

> Momentopname (juli 2026, na v1.14-werk op `master`). Vier parallelle deep-dives
> (backend, frontend, security, tests/CI) gesynthetiseerd tot één beoordeling:
> waar staat de codebase, wat draagt al, en wat zijn de echte groeipijnen richting
> het modulaire multi-tenant ERP uit `intermediate-architecture-upgrade-v1.md`.
> Omvang: backend ~13.000 regels (242 py-bestanden, 49 tabellen, 68 migraties),
> frontend Next.js 15 App Router, 406 backend-tests + 2 e2e-flows.

## Eindoordeel in één alinea

Dit is een **bovengemiddeld gezonde codebase** voor haar leeftijd: de discipline
(idempotente migratieketen, drielagen-validatie, tests tegen echte Postgres met de
volledige migratieketen, tag-gepinde deploys, security-by-design config) is precies
het soort fundament waar een ERP op kan groeien. De **twee structurele schulden**
zijn bekend en al geadresseerd in het architectuurplan (#366): (1) de backend is
half by-layer / half by-domain met god-routers en circulaire domeinkoppeling, en
(2) de frontend-adminpagina's zijn monolithisch met veel gedupliceerde UI-patronen.
Security kent **geen kritieke bevindingen**; de resterende risico's zijn middel/laag
en benoembaar. De stack (Python/FastAPI + TypeScript/Next.js + Postgres) is
**geschikt** voor het ERP-doel — het probleem is nergens de taal, altijd de grens.

---

## 1. Architectuur & design

**Sterk**
- **Provider/factory-abstractie** voor externe diensten (Mollie, LLM, STT): echte
  `base.py`-interfaces met swapbare implementaties — het beste architectuurpunt en
  exact de naad die latere extractie mogelijk maakt.
- **Idempotente, lineaire Alembic-keten** (68 migraties, bestaanschecks, één head).
- **DI + rollen-uit-DB**: `require_roles()` leidt capabilities per request uit de
  data af, niet uit het token — ingetrokken rollen werken meteen door.
- **Globale soft-delete** via één ORM-event; **append-only history** die deletes
  overleeft; **secure-config-enforcement** die opstart blokkeert bij zwakke
  secrets/DEBUG/SQL_ECHO in uat/prod.
- Geen TODO's/dode markeringen; consistente HTTPException-afhandeling.

**Zwak**
- **Twee organisatiestijlen naast elkaar**: leden/activiteiten/forms/cms/media nog
  by-layer; payments/chatbot/stt/audit/analytics al by-domain. Models zijn niet mee
  verhuisd.
- **God-routers met inline businesslogica**: `routers/activities.py` (1051 regels,
  domeinregels in de router), `members.py:560-618` (volledige dedup-/lidmaatschaps-
  logica inline). De by-domain routers zijn wél dun — het bewijs dat het patroon
  werkt.
- **Circulaire domeinkoppeling**, verstopt achter functie-lokale lazy imports
  (`payment_status` ↔ `payment_gateway`; chatbot grijpt in payment-internals).
- **Geen facades / geen afgedwongen grens**: klassieke routers importeren
  domein-models rechtstreeks (`members.py`, `activities.py` → `PaymentRecord`).
- Gemengde NL/EN-naamgeving; deprecated `on_event("startup")`; gedupliceerde
  polymorfe PaymentRecord-lookup over ≥3 routers.

**Duiding richting ERP.** Alles hierboven is precies wat PR1–PR4 van de
forms-modularisatie (#360–#363) en het strangler-pad uit het architectuurdocument
oplossen. De schuld is dus geen verrassing maar de *reden* van het plan. Belangrijk
nieuw inzicht uit deze analyse: **payments is de eerste kandidaat ná forms**, want
daar zit de echte circulaire koppeling — de lazy imports verdwijnen pas met een
facade + events (`PaymentSettled`).

## 2. Datamodel

**Sterk**: genormaliseerd ledendomein met echte FK's en `RESTRICT`-vangnetten;
code-tabellen consistent met `(code, language)`-PK (i18n-klaar!); bewuste
ontkoppeling van forms (geen FK's in of uit) en auth↔leden (e-mail als brug).

**Aandachtspunt**: `PaymentRecord` gebruikt een polymorf `payable_type/payable_id`
**zonder FK** — bewuste ontkoppeling, maar de DB garandeert niet dat een betaling
naar een bestaande bron wijst. Dat is verdedigbaar (zelfde soft-ref-filosofie als
MDM §6.2), mits er ooit een integriteitstest/reconciliatie-check komt die wees-
records signaleert. Voor een ERP met geld is dat vangnet de moeite.

## 3. Security

**Geen kritieke bevindingen.** Sterk geregeld: geharde OTP-flow (lockout na 5,
enumeratie-preventie, één levende code, 15 min TTL), FINANCE/ADMIN-scheiding echt
afgedwongen, drielagen-validatie incl. DB-CHECK/UNIQUE, DOMPurify + volledige
e-mail-escaping + formule-veilige ODS (CSV verwijderd), Caddy-headers + CSP + HSTS,
backend niet publiek bereikbaar, PII-bewuste logging + email_log-retentie,
rate-limiting op álle publieke schrijf-endpoints, anti-spoof IP-bepaling.

**Resterende risico's (geprioriteerd):**

| Ernst | Risico | Nuance |
|---|---|---|
| Middel | JWT in localStorage, 24 u geldig, geen server-side revocatie | Gemitigeerd door CSP+DOMPurify; fix = HttpOnly-cookie of kortere TTL + refresh |
| Middel | CSP staat `unsafe-inline`/`unsafe-eval` toe | Next.js-realiteit; DOMPurify is daardoor de primaire XSS-verdediging |
| Middel | Containers draaien als root (geen `USER`) | Klein om te fixen; beperkte blootstelling (achter Caddy, intern netwerk) |
| Middel | In-memory rate-limiter leunt op 1-worker/1-proxy-aannames | Gedocumenteerd in de code; breekt pas bij horizontale schaling |
| Laag/middel | OTP plaintext in DB; audit-job non-blocking; geen geautomatiseerd PII-verwijdermechanisme buiten email_log | Alle drie klein en geïsoleerd aan te pakken |

## 4. GUI / frontend

**Sterk**: gecentraliseerde, getypeerde API-laag (één axios-instance +
token-interceptor, nauwelijks losse `fetch`); doordachte foutvertaling
(`parseApiError` incl. Pydantic-422 → NL-labels); volledige form-engine-typering;
herbruikbare household-subcomponenten.

**Zwak** (dit is de grootste zichtbare schuld):
- **Monolithische admin-pagina's**: formulieren 876 r., activiteiten 859 r. (26
  hooks), betalingen 753 r. — state+UI+API+modals in één bestand.
- **Duplicatie i.p.v. UI-kit**: 6+ ad-hoc status-badge-implementaties, 4 los
  gebouwde modals (verschillende backdrops), 13+ native `window.confirm()`, elke
  lijst een eigen tabel. De `.card`/`.input`/`.btn-*`-klassen bestaan maar worden
  half gebruikt; design-tokens dubbel gedefinieerd (CSS-vars ≠ tailwind.config).
- **Geen server-state-laag**: overal `useEffect+load()`, geen caching, auth-state
  per pagina herhaald.
- **A11y-gat**: geen enkele modal heeft `role="dialog"`/`aria-modal`/focus-trap.
- Type-drift: response-types verspreid over `api.ts` én `types.ts`;
  payloads als `unknown`.

**Duiding.** Dit bevestigt exact de F5-werkpakketten (UI-kit + AdminConsole- en
capture-template) uit het planningsvoorstel: één `<Modal>`, `<ConfirmDialog>`,
`<Badge>`, `<DataTable>` en een form-veld-set lossen het merendeel van de
duplicatie én het a11y-gat in één beweging op.

## 5. Testen & CI/CD

**Sterk** (dit is een echte troef):
- **406 backend-tests** die *invarianten* testen (geld, autorisatie, integriteit),
  endpoint-gedreven — refactor-bestendig. Payments/finance het zwaarst gedekt.
- Tests draaien tegen **echte Postgres 16 via `alembic upgrade head`** → elke run
  test ook de migratieketen. SAVEPOINT-isolatie die endpoint-commits overleeft.
- CI: mypy + coverage-gate (73%) + tsc blokkerend; **tag-gepinde UAT/PROD-deploys**
  met read-only smoke-tests; migraties automatisch bij containerstart.

**Gaten**:
- **Frontend nauwelijks getest**: 2 unit-bestanden (pure helpers) +
  `--passWithNoTests`; geen component-tests; e2e (2 specs) non-blocking.
- **Geen rollback-mechaniek**: smoke is `|| true` (breekt de deploy niet), geen
  pre-migratie-backup-hook in deploy-prod, geen gegarandeerd down-pad.
- **Geen architectuur-handhaving in CI** (import-linter ontbreekt) en **geen
  migratie-drift-check** (`alembic check`).
- Dun: cms/users/ideas-routers; `mock_mollie` slaat bedragverificatie standaard
  over (één mismatch-test dekt die tak).

## 6. Geschiktheid van de stack (talen & tools)

| Keuze | Oordeel | Motivering |
|---|---|---|
| **Python + FastAPI** | ✅ geschikt | Volwassen, uitstekende DX, mypy-clean codebase, Pydantic = gratis contractlaag. Sync SQLAlchemy is bij deze schaal correct (threadpool, geen async-valkuilen); async pas overwegen bij echte nood. |
| **PostgreSQL** | ✅ uitstekend | Dé ERP-database: schema's per module, RLS voor tenancy, CHECK/FK als vangnet — het architectuurplan leunt er terecht op. |
| **TypeScript + Next.js** | ✅ geschikt, met kanttekening | Sterk voor publiek (SEO/SSR, straks per-tenant sites). Kanttekening: voor de back-office is een SPA-patroon met een server-state-laag (react-query) passender dan de huidige hand-gerolde fetch-cyclus. |
| **Twee talen (py + ts)** | ⚠️ beheersbare kost | Dubbel typewerk en drift-risico. Mitigatie bestaat al half: **OpenAPI is er** — genereer de frontend-types/client uit het FastAPI-schema en de drift verdwijnt (past bij §11/§12 van het architectuurdoc). |
| **Docker Compose + Caddy** | ✅ geschikt nu | Volstaat ruim voor deze schaal; Kubernetes staat terecht out-of-scope. De 1-worker-aanname (rate-limiter) is de eerste grens bij schaling. |
| **Alembic** | ✅ geschikt | De idempotente keten is bewezen; het meerketen-plan (per afsplitsbare module) is de juiste evolutie. |

Kortom: **geen enkele her-platforming nodig**. De stack schaalt mee met het
architectuurplan; de investering hoort in grenzen en herbruik, niet in technologie.

## 7. Prioriteiten (aanbeveling)

Gesorteerd op rendement, gemapt op het bestaande plan (epic #366):

1. **Forms-modularisatie afronden als sjabloon** (#360–#363) — lost meteen het
   by-layer/by-domain-schisma en het facade-gebrek op; de import-linter (PR2) is
   de goedkoopste blijvende bewaking. *(gepland)*
2. **Payments als tweede domein** (#365) — daar zit de circulaire koppeling en de
   polymorfe-lookup-duplicatie; een facade + `PaymentSettled`-event ruimt beide op.
   Voeg een **wees-record-integriteitscheck** toe (payable_id → bestaande bron).
   *(gepland; check is nieuw)*
3. **Frontend UI-kit + AdminConsole-template** (F5) — grootste zichtbare
   duplicatie + a11y-gat in één slag; daarna de drie monoliet-pagina's ontbinden.
   *(gepland)*
4. **CI-verharding** (F2/F4 +): import-linter, `alembic check` (drift), vitest
   zonder `--passWithNoTests`, e2e op de geldflow blokkerend maken. *(deels gepland;
   drift-check en gates zijn nieuw)*
5. **Deploy-vangnet**: pre-migratie-backup-hook in `deploy-prod.sh` + smoke als
   gate (nu `|| true`) + rollback-runbook. Klein werk, groot verschil voor een
   systeem met financiële data. *(nieuw)*
6. **Security-hardening batch** (klein, gebundeld): non-root containers, OTP
   hashen, kortere JWT-TTL of HttpOnly-cookie-pad, audit-job blokkerend voor
   high-severity. *(nieuw; sluit aan op de eerdere audit-bespreking)*
7. **OpenAPI → frontend-typegeneratie** — elimineert de py↔ts-drift structureel.
   *(nieuw)*

Punten 1–3 zijn al gepland; 4–7 zijn de concrete aanvullingen uit deze analyse.

---

*Methodiek: vier parallelle code-verkenningen (backend-architectuur, frontend/GUI,
security, tests & CI/CD) met file:line-bewijs, gesynthetiseerd tegen het
architectuurdocument. Detailbevindingen met alle verwijzingen zijn opvraagbaar.*
