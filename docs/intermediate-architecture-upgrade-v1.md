# Intermediate Architecture Upgrade — v1

> Werkdocument. Denkkader voor de tussenstap naar een **modulair, multi-tenant
> ERP/portaal/CRM**: domeinmodules met een facade + eigen Postgres-schema (en, waar
> afsplitsbaar, een eigen migratieketen), afgedwongen grenzen, en per-tenant merk-
> autonomie. Nog **geen** release toegewezen. Gerelateerd: epic **#366** (#360–#365).

---

## 1. Doel & principes

Van **modulaire monoliet** naar componenten met een **afdwingbare buitengrens**, zodat
we er later — enkel bij een concrete driver — een aparte app van kunnen maken. Bewust
een **leertraject**: forms is het sjabloon dat we op elk volgend domein herhalen.

- **Capture → Record → Act** — publieke capture (bezoeker), record-kern (eigen data +
  regels), rol-gated back-office (act).
- **Eén verticale slice per component** in `app/domains/<c>/`, met een **facade
  (`api.py`)** als enige publieke oppervlak — geen reach-in in models/services.
- **Owned data** — eigen Postgres-schema; cross-component enkel via **facade/events**,
  nooit live ORM-objecten of cross-schema FK's.
- **Kernel** = plumbing (db, config, events, tenant-context); hangt van geen domein af.
- **Modulariteit = OO op macroschaal** — module = object; facade = encapsulation,
  events = message passing, import-linter = het ontbrekende `private`-keyword.

---

## 2. Twee onafhankelijke assen

Verwar **modularisatie** en **multi-tenancy** niet — ze staan loodrecht op elkaar:

- **Module** (verticaal): *wélk soort data?* → eigen package + **Postgres-schema**
  (`form`, `payment`, `mdm` …).
- **Tenant** (horizontaal): *van wélke vereniging?* → **`tenant_id`** (rij-niveau) in
  elke moduletabel.

De koepel snijdt dwars door beide (ziet alle tenants in alle modules) → rij-niveau
`tenant_id` is het juiste model (§7).

---

## 3. Componentenkaart

```mermaid
flowchart TB
  Public["PublicShell (bezoeker, per unit)"] --> D2
  BO["AdminShell (ADMIN / FINANCE)"] --> D2
  BO --> D1
  BO --> WB["werkbank (takeninbox,<br/>alle taken + excepties)"]
  WB --> WF
  subgraph D1["Fundamenteel (laag 1) — eigen schema + keten"]
    AUTH[auth & security]:::c
    MDM["MDM (personen, gezinnen,<br/>adressen, postcodes, organisaties)"]:::c
    MAIL[mail-logging]:::c
  end
  subgraph D2["Domeinen (laag 2)"]
    MEMBER[membership]:::c
    ACT[activities]:::c
    FORM["form engine<br/>(incl. berichten/IdeaBox)"]:::c
    WF[workflow]:::c
    PAY["payments (Mollie)"]:::c
    CMS[cms]:::c
    CHAT[chatbot / AI]:::c
  end
  subgraph CAP["Capaciteiten & cross-cutting"]
    MEDIA[media]:::x
    STT["STT (stateless → extractie-kandidaat)"]:::x
    ANA[analytics read-model]:::x
  end
  D2 --> D1
  D2 --> CAP
  D1 --> Kernel[(kernel)]
  D2 --> Kernel
  CAP --> Kernel
  MEMBER -.->|facade| MDM
  ACT -.->|"is lid?"| MEMBER
  PAY -.->|PaymentSettled| MEMBER
  FORM -.->|SubmissionCreated| WF
  WF -.->|WorkflowCompleted| MAIL
  CHAT -.->|facade| STT
  classDef c fill:#e8f0ff,stroke:#36b;
  classDef x fill:#eef7ee,stroke:#3a3;
```

Regels: schermen praten enkel met een **facade**; domeinen onderling enkel via
**facade/events**; **history** is een gedeeld kernel-patroon (geen aparte component).

---

## 4. Schermen ↔ componenten

Regel: **een scherm hoort bij de component wiens data het toont** — publiek én
back-office. Publiek vs back-office = rol/auth, geen componentgrens. Dus de
formulier-bouwer én de publieke render horen bij **form**.

| Scherm | Component | Rol |
|---|---|---|
| Formulier invullen / bouwer / inzendingen | **form** | — / ADMIN |
| Betaalflow / overzicht + **terugvordering** | **payment** | — / **FINANCE** |
| Lid/gezin inschrijven / ledenbeheer | **MDM** (+ membership) | — / ADMIN |
| Activiteiten publiek / beheer | **activities** | — / ADMIN |
| E-maillog | **mail** | ADMIN |
| Login / gebruikers & rollen | **auth** | — / ADMIN |
| CMS-pagina's | **cms** | — / ADMIN |
| **Werkbank / takeninbox** (alle taken + excepties, §20.5) | **workflow** | ADMIN / FINANCE |
| Berichten (IdeaBox: indienen / *behartigen*) | **form + workflow** | — / ADMIN |

**Frontend spiegelt de backend**: `features/<component>/` (eigen componenten, api-slice,
types); `lib/` houdt enkel gedeelde primitives (money, errors, axios).

---

## 5. Componenten in detail

**5.1 auth & security** (laag 1). `users`, rollen, tokens, JWT-uitgifte/-verificatie.
Eén aparte, apart-deploybare component; **iedereen gebruikt `auth.api`**; auth hangt
enkel van de kernel af (de kernel roept auth niet aan → geen cyclus). Rol-toewijzingen
dragen `tenant_id` als waarde.

**5.2 mail** (laag 1). `email_log` + het centrale `_send`-chokepoint + retentie. Facade
`send/list/delete`; anderen sturen via facade of `MailRequested`-event. `email_log`
blijft in `mail`/`public`, niet in `form` (correctie op migratie 062).

**5.3 MDM** (laag 1) — identiteit, **géén lidmaatschap**. Personen, gezinnen, adressen,
postcodes, organisaties (§6) + `external_numbers` + de codes `relation/contact/gender`.
Gezinssamenstelling = MDM; "is betalend lid" = membership. Facade `get_person/
find_family/resolve_postal_code/list_organizations` + `resolve/merge` (§6).

**5.4 membership** — eigen component, **zuster van activities** (niet samenvoegen, niet
in MDM). Lidmaatschaps-relatie (persoon/gezin ↔ UNIT), jaren, lidgeld, bestuurslid.
Beide steunen op MDM en voeden `payment`. `activities` vraagt membership "is lid?" via
facade (ledenkorting) → daarom apart en testbaar.

**5.5 AI & STT** — ondersteunend, aan de rand.
- **STT** = stateless capaciteit (audio→tekst), géén schema → **eerste
  extractie-kandidaat** (zware libs/GPU): in-process nu, externe service later, zelfde
  facade (#364).
- **chatbot/AI** = laag-2 domein (schema `ai`) dat STT + LLM-providers consumeert.
- Providers achter adapters, **Europe-First**; keys = per-tenant secret.

**5.6 media** — gedeelde **capaciteit** (zoals mail), geen blad-domein. Meerdere
domeinen verwijzen via een `asset_id` (waarde). Schema `media` (metadata) + storage-
adapter (schijf/Storage Box, Europe-First). Facade `store/get_url/delete/resize`.
Tenant-scoped.

**5.7 workflow** — pluggbaar **vervolgproces + menselijke taken**. Form blijft dom
(publiceert `SubmissionCreated`); workflow luistert, start een instantie en beheert
states + taken (bewaart `submission_id` als waarde). Bouwer koppelt enkel een
`workflow_definition`-id; de procesdefinitie + takeninbox horen bij workflow. Facade
`start/advance/list_tasks/complete_task`; publiceert `WorkflowCompleted`.
**IdeaBox (beter: "berichten") = een geseed formulier + een minimale workflow met
één menselijke taak: *behartigen*** (`nieuw → behartigen → afgehandeld`; een
afwijzing is ook een afhandeling). De losse `ideas`-component vervalt. Dit is
meteen de eenvoudigste referentie-workflow: één taak, sluit door toestand.

**5.8 Cross-cutting & plaatsing van resttabellen**
- **History = gedeeld kernel-patroon** (`Historized`-mixin), per-component `*_history`
  in het eigen schema — géén centrale audit-component.
- **`business_events`**: geen meerwaarde → parkeren/verwijderen.
- **`external_numbers`** → MDM (externe identiteit).
- **Referentiecodes** → in het schema van hun eigen component (geen gedeelde
  `reference`-namespace); anderen bewaren de **waarde**.

---

## 6. MDM: organisaties, merge & soft-refs

### Organisaties (generiek, niet vzw-specifiek)
```mermaid
erDiagram
  ORGANIZATION ||--o{ ORGANIZATION : "parent (account → unit)"
  ORGANIZATION ||--o{ PERSON : "tenant_id (= unit)"
  ORGANIZATION {
    int id
    string kind "ACCOUNT | UNIT"
    string legal_form "data: VZW / bedrijf / …"
    int parent_id
  }
```
`organizations` is zelf-refererend: **ACCOUNT** = koepel/klant (wortel), **UNIT** =
operationele eenheid (bij Raak: Millegem, X, Y, Z). `legal_form` is **data** → org-type-
neutraal. Elke tenant-rij draagt `tenant_id` = UNIT; de account-scope volgt uit de boom.

### Merge & survivorship — nooit verwijderen
MDM-entiteiten worden **nooit hard verwijderd**; dubbels worden gemergd tot één *golden
record*, de verliezer blijft als **tombstone** die naar de survivor wijst.

```mermaid
flowchart LR
  REG["inschrijving<br/>person_id = 12"] -->|resolve via facade| NEW
  OLD["#12 (Koen) superseded_by 34"]:::d -->|superseded_by| NEW["#34 (Koen) survivor"]:::a
  classDef d fill:#eee,stroke:#999,stroke-dasharray:3;
  classDef a fill:#e8f7e8,stroke:#3a3;
```
- **ID-redirect**: `superseded_by_id` (self-FK, `null`=actief); `resolve()` volgt de
  keten (bij merge platgeslagen → O(1)). `merge()` idempotent.
- **Altijd actueel**: consumenten lezen via `mdm.api.get/resolve` → een oude
  inschrijving komt vanzelf bij de survivor uit.
- **Niets verloren → unmerge mogelijk**; de merge wordt gelogd (history-patroon).
- Event **`EntityMerged`** voor optionele housekeeping (niet nodig voor correctheid).

### Soft reference (zo verwijst bv. de form engine naar een persoon)
- **Waarde-kolom** `mdm_person_id` (nullable), **geen cross-schema FK** — een echte FK
  zou de schema's koppelen, onafhankelijk deployen breken én de merge-redirect
  onmogelijk maken. Concreet: `form_submissions.mdm_person_id`.
- **Optioneel** (forms mogen anoniem blijven → losse koppeling behouden); **altijd via
  de facade lezen** (redirect transparant). Het nooit-verwijderen + tombstone garandeert
  dat een id **nooit dangelt** — sterker dan een harde FK. Zelfde patroon voor
  membership/activities/payment.

---

## 7. Multi-tenant

**Klant = ACCOUNT** (generiek elk type org), **tenants = UNITs**. Drie niveaus:
**operator** (platform, ziet alles) → **account** (klant/billing) → **unit** (eigen
brand). Een klant die quasi-autonome, eigen-brand bedrijven beheert = **één account,
één unit per bedrijf**. Meerdere accounts naast elkaar is **native** (aparte
`organizations`-wortels).

```mermaid
flowchart TB
  OP["operator (ziet alles)"]:::o --> A1["ACCOUNT: Raak vzw"]:::a & A2["ACCOUNT: Bedrijvengroep"]:::a
  A1 --> U1["UNIT: Millegem"]:::u & U2["UNIT: Raak X"]:::u
  A2 --> U3["UNIT: Bedrijf A"]:::u & U4["UNIT: Bedrijf B"]:::u
  classDef o fill:#ffd,stroke:#aa0; classDef a fill:#e8f0ff,stroke:#36b; classDef u fill:#eef7ee,stroke:#3a3;
```

- **Model = rij-niveau `tenant_id`** (shared schema). Schema-/DB-per-tenant vallen af:
  de koepel moet dwars over tenants rapporteren (`WHERE tenant_id IN …` i.p.v. een
  cross-schema-union). **RLS** later als DB-vangnet.
- **Tenant-context in de kernel** (uit JWT/hostname); facades filteren standaard op de
  actieve tenant. **Rollen**: `ADMIN`/`FINANCE` per UNIT, `ACCOUNT_ADMIN` per account,
  `OPERATOR` op platformniveau.
- **Cross-account isolatie is hard**; **zichtbaarheid binnen een account is
  configureerbaar** (gedeeld: koepel ziet/deelt alles — vs geïsoleerd: units delen niet,
  account enkel oversight) — een facade-policy, geen schemawijziging.
- **Uitrol per app, niet dark/big-bang**: kernel levert de `tenant_id`-mixin + context;
  elke app adopteert dat op zijn moment, grondig getest.

### Config & secrets (multi-tenant-scheiding)
- **Per-tenant config** → **DB-beheerd** (afzendermail, Mollie-profiel, logo, branding,
  domein). Vandaag in `.env`; verhuist naar een per-tenant settings-store met `.env`-
  default tijdens de single-tenant-fase.
- **Per-tenant secrets** (Mollie-key) → **DB, versleuteld**.
- **Infra/technologie** (DB-wachtwoord, IP, SSH, `SECRET_KEY`, proxy/CA) → **`.env`**.

### Merk-autonomie & SEO — aparte site per unit
Harde eis: **elke unit is een zelfstandig indexerende site** (Google/Bing/Qwant) → een
**eigen host per unit** (geen pad-prefix):
- **Eigen domein** (`raakmillegem.be`, `raakx.be`) — aanrader, sterkste scheiding +
  domain authority. **Subdomein** kan ook. **Pad-prefix valt af** (dat is één site).
- **Hostname-resolutie** (Next.js middleware) → tenant; per unit een **canonical
  base-URL** in de per-tenant config. Cert/DNS per host via Caddy. Overstap subdomein →
  domein = config + DNS + **301-redirects**, geen code.
- **SEO is een afgeleide**: `generateMetadata`, `Organization`-JSON-LD, `sitemap.xml` en
  `robots.txt` lezen de actieve tenant. Content is al tenant-scoped (CMS + activiteiten).
  De issues #320 (JSON-LD) en #322 (og:image) worden zo **per unit**.

---

## 8. Afhankelijkheden & grens-handhaving

3-lagen-model — afhankelijkheden wijzen **enkel naar beneden**:

| Laag | Bevat | Mag afhangen van |
|---|---|---|
| **0 · Kernel** | db, config, events, tenant-context, history-mixin | niets |
| **1 · Fundamenteel** | auth, mail, MDM | enkel kernel |
| **2 · Domeinen** | form, payment, activities, membership, workflow, cms, chatbot | kernel + laag-1-facades + elkaars facades/events |

Gehandhaafd door: **(1)** import-linter in CI (mapgrens = moduulgrens); **(2)** geen
cross-schema FK's (integratietest op `information_schema`); **(3)** aparte Alembic-keten
per afsplitsbaar component (drift/één-head-tests); **(4)** later per-schema `GRANT` + RLS.

---

## 9. Ontwikkelen binnen een component — contract-stabiliteit

Het **contract** = facade-signaturen (`api.py`) + DTO's + event-schema's
(`kernel/contracts`). Alles daaronder (models, service, schema) is intern en mag vrij
wijzigen.

- **Additief = vrij** (nieuwe functie/optioneel veld/event).
- **Breaking = deprecatie-cyclus**: nieuwe variant → oude `@deprecated` → consumenten
  migreren → verwijderen; events versioneerbaar (`…V2` naast `…V1`).

> Werkregel: *onder de facade refactor je vrij; aan de facade wijzig je niets zonder
> deprecatie-cyclus én groene contract-tests.* De import-linter garandeert dat het
> contract de enige koppeling is.

---

## 10. Teststrategie

Vier lagen, van snel/lokaal naar breed:
1. **Unit** — in-component, tegen het eigen schema (validatielagen apart).
2. **Contract** (de naad) — provider bewijst dat facade/events het schema naleven; elke
   consument test tegen een **stub die aan datzelfde schema wordt gevalideerd** → een
   contract-breuk laat de consument in CI falen. Zo ontwikkel je **in isolatie**.
3. **Integratie-flow** — "golden flows" tegen de echt gewired app + alle schema's, bv.:
   *inschrijving → membership-check → betaling → mail + history*; *formulier → submission
   → confirmatiemail*; *terugvordering (FINANCE) → payment-status + mail*.
4. **Migratie/grens** — per keten: één head, autogenerate-drift, geen cross-schema FK.

CI: unit + contract + linter op elke push; integratie + migratie op PR/merge (echte
Postgres 16, alle ketens). Import-linter sluit *verborgen* koppeling uit, contract-tests
vangen *contract-breuk*, golden flows bewijzen de *samengestelde* werking.

---

## 11. Conventies (GUI · code · API)

Componenten moeten er **hetzelfde uitzien en aanvoelen** — anders krijg je N eilandjes.

- **GUI**: gedeelde **UI-kit** + twee sjablonen — **AdminConsole** (lijst+filters →
  detail → rol-gated acties + bevestiging) en **Public-capture** (token/anoniem →
  gevalideerde submit → bevestiging). Rol-bewuste UI, a11y-baseline, nl-BE + gedeelde
  formatting.
- **Code**: identieke component-structuur (`api/router/schemas/service/models`);
  validatielagen (vorm→router, regels→service, integriteit→DB); import-linter; ruff +
  mypy / eslint + prettier + tsc; **kernel-patronen hergebruiken** (tenant-mixin,
  history-mixin, soft-delete, `superseded_by`, event-dispatcher).
- **API**: `/api/v1/<component>/<resource>`; standaard error-/paginatie-envelope; DTO's
  & events als contract (`kernel/contracts`, events `<Aggregate><Verb>`); **OpenAPI** als
  waarheidsbron (`api.ts` spiegelt); idempotentie waar het telt (`merge`, Mollie-webhook);
  `created_at/updated_at` tz-aware.

---

## 12. Component-documentatie & change-impact

Prosa veroudert → **contract-als-code + een dun manifest, afgedwongen door tests.**

- **`CONTRACT.md` per component**: publiceert (facade + events), consumeert
  (afhankelijkheden), bezit (schema/config), deprecaties, `CODEOWNERS`.
- **Bron van waarheid** (manifest verwíjst ernaar): OpenAPI + DTO/event-schema's;
  contract-tests toetsen diezelfde schema's → de test *is* de handhaving.
- **Change-impact**: uit de "consumeert"-declaraties bouw je een **reverse-index**
  ("wie hangt van mij af") + de dependency-graph. Een contract-wijziging → **contract-
  tests bij de consumenten falen** → blast radius met naam; `CODEOWNERS` tagt reviewers.

> Regel: een contract wijzig je niet zonder `CONTRACT.md` bijgewerkt én groene
> contract-tests bij álle consumenten.

---

## 13. Codebase-(her)structurering

Van **package-by-layer** (form ligt versnipperd over `routers/models/services/schemas`)
naar **package-by-domain**. Je bent al begonnen (`domains/`); we maken het af.
*Eén map = één component = één schema = één toekomstige app.*

**Backend**
```
app/
  kernel/     database, config, soft_delete, security(verify),
              events, contracts, tenancy(mixin+context), history(mixin)
  domains/
    auth/  mdm/  mail/                      # laag 1
      api.py router.py schemas.py service.py models.py migrations/ CONTRACT.md
    membership/ activities/ form/ workflow/ payment/ cms/ chatbot/   # laag 2
    media/ stt/ analytics/                  # capaciteiten / read-model
  main.py     # mount enkel domains/*/router.py
  # routers/ models/ services/ schemas/ → lopen leeg en verdwijnen
```
Interne modules (cms, activities, analytics) krijgen wél een eigen schema, géén eigen
keten (§14).

**Frontend** — spiegel: `src/features/<component>/` (+ `_shared/` UI-kit); `lib/` enkel
gedeelde primitives.

**Migratiepad (strangler, geen big-bang)**: forms eerst als sjabloon (`git mv` +
facade, geen gedragswijziging) → per component één PR → kernel optrekken. **Valkuil**:
model-discovery — verplaats je models, laat `Base.metadata`/Alembic ze nog vinden
(import in `domains/__init__.py` of `env.py`).

**Data-verhuis hoort bij het pad**: bestaande tabellen verhuizen naar hun
component-schema via `ALTER TABLE … SET SCHEMA` in een migratie van de éigen keten
(expand/contract: eerst verhuizen + oude naam als view/synoniem indien nodig, dan
verwijzingen omzetten, dan opruimen). Te doen vóór/bij Fase 1 per component —
`pg_dump` blijft één commando (§13.1), de verhuis is puur namespacing.

### 13.1 Eén map per component — wat zit erin (en wat bewust niet)

Ja: **één map = álles van die module** — backend, frontend-feature, migraties,
tests, contract:

```
domains/payment/
  api.py router.py schemas.py service.py models.py   # backend
  migrations/            # eigen Alembic-keten (afsplitsbare apps)
  frontend/              # de feature-UI van dit component (schermen, hooks)
  tests/                 # unit + contract van dit component
  CONTRACT.md            # publiceert / consumeert / bezit / deprecaties
  seeds.py               # referentiedata van dit component
```

Maar in de **intermediate** fase is dat een *package*, geen *deployable*: er blijft
**één backend-proces** (FastAPI mount alle routers), **één Postgres-instance** (per
component een eigen **schema** + eigen keten) en **twee frontend-builds**. "Eigen
frontend/backend/database per app" is de **eindtoestand-optie** die deze structuur
mogelijk maakt — een component eruit tillen is dan `git mv` + eigen deploy, geen
herschrijving. We betalen de operationele kost van N processen/DB's pas als een
component er echt uit moet (§18).

**Backup blijft één commando.** Schema's zijn namespaces *binnen* één database:
één `pg_dump` van die database neemt álle schema's mee (tabellen, sequences,
indexes, grants) — één backup, één restore, één consistent point-in-time-beeld
over alle componenten heen. De bestaande `db-backup`-service werkt dus ongewijzigd
door; niets hoeft per schema gescript te worden. Pas als een component ooit een
éigen database/instance krijgt (eindtoestand-optie), splitst zijn backup mee af —
en dan bewust, met het component, niet als verborgen bijwerking.

**De GUI-orchestrator**: twee dunne **shells** die zelf géén domeincode bevatten —
**AdminShell** (navigatie, login, layout, UI-kit, rol-gating) en **PublicShell**
(publieke site per unit). Een shell *componeert* de `frontend/`-features van de
componenten (elke component registreert zijn nav-items + routes; de shell mount ze).
Nieuw component = map toevoegen + registreren, de shell wijzigt niet.

**Tests op twee niveaus**: per component `domains/<c>/tests/` (unit + contract,
draaien tegen enkel het eigen schema + gestubde facades); overkoepelend
`tests/integration/` op repo-niveau (de **golden flows** van §10, tegen de echt
gewirede app met álle schema's). Een component-map is groen te krijgen zonder de
rest te draaien; de golden flows bewijzen de samenstelling.

### 13.2 Eén bouwcommando — build · migrate · test · gate

Eén ingang (`make ci` / `./build.sh`) die lokaal en in CI **identiek** is:

1. **Build** — backend-image (alle componenten, incl. `check_imports`),
   AdminShell + PublicShell (`tsc` + `next build`).
2. **Migrate** — alle Alembic-ketens in laagvolgorde (kernel → laag 1 → laag 2),
   per keten: precies één head + autogenerate-drift-check.
3. **Test** — per component zijn eigen suite (parallelliseerbaar, CI-matrix per
   map: alleen gewijzigde componenten + hun consumenten hoeven te draaien) → daarna
   de golden flows.
4. **Gates** — import-linter (mapgrens), geen-cross-schema-FK-check, OpenAPI-drift
   (§19.4), publieke-repo-guard.

Groen = mergebaar; de stappen zijn de definitie van "af". Gedocumenteerd op één
plaats (`BUILDING.md` op repo-root) — de component-mappen documenteren enkel hun
eigen contract (`CONTRACT.md`, §12).

---

## 14. Roadmap & backlog

**Nog geen issues aangemaakt** — dit wordt op go sub-issues onder #366. Vast sjabloon
per component-PR: `facade → import-linter → eigen schema (+ keten waar afsplitsbaar) →
contract-/integratietests → frontend-feature → CONTRACT.md`.

**Kritiek pad**: F (fundering) → Fase 0 (forms-sjabloon) → mail/auth → MDM → tenancy.
De rest kan grotendeels **parallel** zodra fundering + sjabloon staan.

| Blok | Werkpakketten | Status |
|---|---|---|
| **F · Fundering** | kernel optrekken (events/contracts/tenancy/history/security); import-linter-harness; component-scaffold + `CONTRACT.md`-template; test-harness (contract + golden-flow); UI-kit + templates | nieuw |
| **0 · Form-sjabloon** | forms→`domains/forms` + facade; import-linter; schema `form` + handoff; 2e keten + integratietests | **#360–#363** |
| **1 · Cross-cutting** | mail-component; auth-component (laag 1) | nieuw |
| **2 · MDM** | MDM (+ `external_numbers`) + schema/keten; merge/survivorship; soft-ref-patroon | nieuw |
| **3 · Payments** | `domains/payments` (gateway+status) + FINANCE-refund; **wees-record-check** op `payable_id` (§19) | **#365** |
| **4 · Domeinen** | membership (+`is_member`); activities; workflow + IdeaBox; media; cms; chatbot | nieuw |
| **5 · Multi-tenant** | organizations (ACCOUNT/UNIT); per-tenant config/secrets-store; `tenant_id` per app + context + rollen; meerdere accounts + hostname-resolutie + per-unit SEO | nieuw |
| **6 · Extractie** | STT → externe service (bij driver) | **#364** |
| **H · Operationele hardening** (§19, kan vóór alles) | deploy-vangnet (pre-migratie-backup, smoke als gate, rollback-runbook); security-batch (non-root containers, OTP-hash, JWT-TTL/HttpOnly, blokkerende audit); CI-gates vervroegen (vitest-gate, e2e-geldflow blokkerend, `alembic check`); observability (error-tracking/logs/uptime/alerts); restore-oefening per release | nieuw |
| **O · Opruiming** (§19, kan vóór alles) | `business_events` verwijderen; `domains/common/` + stale docs weg; dead-endpoint-sweep. (`ideas` → formulier + minimale workflow verhuist naar fase 4: vereist de workflow-component) | nieuw |

---

## 15. Ontwerpkeuzes (register)

> **Vorm (ADR-light)**: elke nieuwe beslissing krijgt vier regels — *datum ·
> context · gekozen (met verworpen alternatief) · heropener* (wat zou ons van
> gedachten doen veranderen). §18 en §20.4 tonen het patroon; bestaande regels
> hieronder blijven zoals ze zijn.

- ✅ **Package-by-domain**; facade `api.py`; grens via **import-linter**.
- ✅ **Frontend-eindbeeld = één taal, server-rendered (htmx + Jinja + Alpine)** via
  het pilotpad; form-builder het langst als React-eiland; JSON/OpenAPI-facade
  blijft — volledig ADR in **§21.5**.
- ✅ **Eigen Alembic-keten** voor afsplitsbare apps (auth, mail, MDM, form, payment);
  interne modules enkel een eigen schema.
- ✅ **auth = één fundamentele component** (niet gesplitst; verify-mechanisme in kernel).
- ✅ **MDM**: `master`→MDM; bevat `external_numbers`; **nooit verwijderen +
  merge/survivorship**; anderen verwijzen via **soft-ref** (waarde-id).
- ✅ **membership = eigen component** (zuster van activities), **niet**
  `activities_membership`.
- ✅ **AI/STT gesplitst** (STT capaciteit/extractie-kandidaat; chatbot domein).
- ✅ **media = gedeelde capaciteit**; **workflow = eigen component**; **IdeaBox
  ("berichten") = form + minimale workflow met één menselijke taak *behartigen***
  (`ideas` vervalt; mét workflow, niet zonder).
- ✅ **history = kernel-patroon** per component; **`business_events` schrappen**.
- ✅ **Referentiecodes in eigen component-schema** (geen gedeelde namespace).
- ✅ **Multi-tenant = rij-niveau `tenant_id`**; **geen dark tenant_id** (per app,
  getest); **RLS later**. **Meerdere accounts native**; rollen `ACCOUNT_ADMIN`/`OPERATOR`.
- ✅ **Org-model generiek** (`ACCOUNT_ADMIN`, `legal_form` als data).
- ✅ **Config-scheiding**: per-tenant config/secrets in DB (secrets versleuteld); infra
  in `.env`.
- ✅ **Aparte site per unit** (eigen host, hostname-resolutie; geen pad-prefix).
- ✅ **Frontend per fase/component** (`features/<c>/` samen met de backend).

---

## 16. Kostenefficiëntie voor AI-assisted development

De grootste kostendrijver is *hoeveel er gelezen moet worden om veilig te handelen*.
Kleine componenten verkleinen dat leesoppervlak → **lagere kost per taak** (een
investering, geen automatische korting).

- **Daalt door**: begrensde context (`domains/<c>/` i.p.v. de hele repo); **contract
  i.p.v. implementatie** lezen (`CONTRACT.md`/facade); scherpe feedback (linter +
  contract-tests wijzen breuk met naam aan); kleinere test-/CI-scope.
- **Kost of helpt niet**: upfront-herstructurering; cross-cutting wijzigingen; vereist
  discipline (grenzen echt afgedwongen); iets meer boilerplate per triviale change.

> Een typische taak verschuift van *"lees een groot deel van de repo"* naar *"lees één
> map + een paar contracten"* — dáár zit de winst, en dat maakt latere agentische/
> parallelle ontwikkeling per component haalbaar.

---

## 17. Waarom — korte & lange termijn

**Korte termijn**: stop de fragiliteit/data-verlies (bv. #357: bewerken wiste
inzendingen); sneller & goedkoper ontwikkelen; makkelijker redeneren en overdragen
(facade + `CONTRACT.md`); en de concrete noden nu (form engine, betalingen/refund,
kernel-fundering).

**Lange termijn**: modulair ERP/portaal/CRM met onafhankelijk evoluerende, afsplitsbare
componenten; multi-tenant SaaS (meerdere accounts, aparte site per unit — **nieuwe
klant = config, geen code**); herbruikbare componenten; toekomstbestendig voor
AI/agentisch werk; beheersbare compliance/isolatie; en géén "big ball of mud".

> De strangler-aanpak laat KT-waarde en LT-fundering **samenvallen**: elke stap lost nu
> iets op én legt een steen voor later.

---

## 18. Out-of-scope — bewust (nog) niet

Levend register: "LT" = heroverwegen zodra de trigger opduikt.

| Idee | Waarom nu niet / trigger |
|---|---|
| Microservices / aparte DB's / message broker | Modulaire monoliet volstaat; splits enkel bij een concrete driver. Naden liggen klaar. |
| DB-/schema-per-tenant | Rij-niveau gekozen; enkel bij harde isolatie-eis. |
| Postgres RLS | Eerst facade-filtering; als hardening ná Fase 5. |
| Externe IdP / SSO | Eigen `auth` volstaat; bij klantvraag. |
| Volledige BPM-engine (Camunda…) | Start met lichte eigen `workflow`. |
| Event-sourcing / CQRS | Enkel read-models waar nuttig. |
| Extra betaalproviders | Mollie (EU) volstaat; adapter maakt uitbreiding triviaal. |
| Volledige i18n | nl-BE nu; bij markt-/tenantvraag. |
| Mobiel/native, real-time (websockets) | Web-first; bij behoefte. |
| BI / datawarehouse | Simpele `analytics` nu. |
| `business_events` → audit-platform | Geschrapt (§5.8). |
| GDPR-self-service | Na tenancy + MDM; nu admin-verwijderen (MDM = tombstone, nooit hard). |
| Feature-flag-platform | Lichte config-vlaggen volstaan. |
| Kubernetes / auto-scaling | Docker-compose volstaat; bij schaalnood. |
| "Dark" `tenant_id` vervroegd | Bewust niet (per app, getest). |

---

## 19. Aanvullingen uit de codebase-analyse (juli 2026)

De analyse (`codebase-analyse-erp-fundament.md`, vier deep-dives met
file:line-bewijs) **valideert dit plan**: de lazy-import-cykels bewijzen de
payments-facade, de frontend-duplicatie bewijst de UI-kit (§11), de CI-gaten
bewijzen §8/§10. Drie concrete aanvullingen + een vereenvoudigingsregister:

### 19.1 Operationele hardening (backlog-blok H)
- **Deploy-vangnet** — pre-migratie-backup-hook in `deploy-prod.sh`, post-deploy
  smoke als **gate** (nu `|| true`), rollback-runbook. Klein werk, essentieel met
  financiële data; vereist de modularisatie niet.
- **Security-batch** — non-root containers (`USER` in Dockerfiles), OTP-codes
  gehasht opslaan, kortere JWT-TTL of HttpOnly-cookie-pad, dependency-audit
  blokkerend voor high-severity. (Geen kritieke bevindingen; dit is hardening.)
- **CI-gates vervroegen** — de goedkope gates uit §10/§11 nu al aanzetten:
  vitest zonder `--passWithNoTests`, e2e-geldflow blokkerend, `alembic check`
  (drift). De import-linter volgt met Fase 0.
- **Observability** — de werkbank vangt *business*-excepties, maar technische
  signalen hebben een eigen kanaal nodig: error-tracking (Europe-First:
  **GlitchTip** of self-hosted Sentry), gestructureerde logs, uptime-check per
  site, alert bij gefaalde Mollie-webhooks/mails. Zonder dit hangt "iets is stuk"
  af van wie het toevallig meldt.
- **Restore-oefening** — een backup die nooit is teruggezet, is een hoop. Per
  release (of periodiek): restore naar een wegwerp-DB + read-only smoke test.
  Sluit de keten backup → bewezen herstelbaar.

### 19.2 Integriteit polymorfe refs
`payment_records.payable_type/payable_id` is een soft-ref zónder de
MDM-tombstone-garantie (§6): een wees-record is vandaag mogelijk. Toevoegen aan de
grens-/integratietests (§10 laag 4): **check dat elke payable_id naar een bestaande
bron wijst** (reconciliatie-query, faalt luid).

### 19.3 Vereenvoudiging & afscheid (register, backlog-blok O)
Snoeien is ook architectuur. Levend register, zelfde geest als §18:

| Actie | Winst |
|---|---|
| **`business_events` verwijderen** (beslist, §5.8 — nu uitvoeren) | −1 tabel, −PII-guard-service, −6 emit-sites in 5 flows, −admin-stats-endpoint, −13 tests |
| **`ideas` ("berichten") → geseed formulier + minimale workflow** (beslist; mét workflow — één menselijke taak *behartigen*, zie §5.7) | −router, −model+tabel, −admin-pagina, −IdeaBox-component, −idea_limiter |
| **`domains/common/` (leeg) + `docs/change_request_0X.md`** opruimen | minder dode structuur |
| **Dead-endpoint-sweep**: backend-routes vs. werkelijk `api.ts`-gebruik | kleiner API-oppervlak (kandidaat: 32 routes in `activities.py`) |
| **Consolidaties die code verwijderen** (vallen onder F/§11): UI-kit (6 badges→1, 4 modals→1, 13 `confirm()`→1), OpenAPI-codegen (handgeschreven `api.ts` + dubbele types weg), één PaymentRecord-lookup-helper, design-tokens één bron | netto mínder regels, zelfde gedrag |

**Niet snoeien** (lijkt vereenvoudiging, is het niet): migraties squashen (CI test
nu de hele keten — dat is waarde), history-tabellen/e-maillog-body (audit-waarde,
bewuste keuzes met retentie), tests, `member_import` (bevestigd terugkerend, #377 —
blijft; alleen het testadres-vangnet is verwijderd).

### 19.4 py↔ts-drift structureel voorkomen (OpenAPI-codegen + gate)
1. **Stap 0 — conventie**: elk endpoint een `response_model` (kale dicts genereren
   leeg schema; bv. form-results/inzendingen-view).
2. **Export**: script dumpt `app.openapi()` deterministisch naar `openapi.json`
   (gecommit; geen draaiende server nodig).
3. **Genereren, gefaseerd**: eerst `openapi-typescript` → één `api-types.gen.ts`
   (types only, nul runtime) en de handgeschreven/dubbele types verwijderen;
   later per component volledige client-gen (nette `operation_id`s) die de
   `api.ts`-wrappers vervangt.
4. **CI-drift-gate — de eigenlijke preventie**: export + codegen + `git diff
   --exit-code` op de gegenereerde bestanden → schema gewijzigd zonder
   regeneratie = build rood. Zelfde filosofie als import-linter/`alembic check`.

Codegen bewaakt de **vorm**; de contract-tests (§10) bewaken de **betekenis**.
Geen runtime-validatie (zod) in de frontend — de server valideert al; een tweede
schema zou een tweede waarheid zijn. Stappen 0/2/3a/4 = klein zelfstandig pakket
(past in blok H, vóór de modularisatie); volledige client-gen per component mee
met `features/<c>/`.

### 19.5 Test/CI-recept (concreet, volgorde = rendement)
1. **Deploy-vangnet** (½ dag): `scripts/db-backup.sh` hooken vóór de rebuild in
   `deploy-uat/prod.sh`; smoke-`|| true` weg + auto-rollback naar de vorige tag
   (loop-guard). **Voorwaarde**: expand/contract-regel — binnen een release enkel
   additieve migraties (drop/rename pas een release later), anders is rollback
   schijnveiligheid en is de backup het enige pad.
2. **CI-gates** (uur): `alembic check` na de migratie-stap; vitest zonder
   `--passWithNoTests`; `npm audit --audit-level=high` blokkerend + pip-audit met
   ignore-lijst daarna blokkerend. Import-linter wacht op Fase 0 (zou nu falen op
   de bestaande lazy-import-cykels — dat is het bewijs, niet het obstakel).
3. **Frontend gericht testen** — géén component-tests voor monoliet-pagina's die
   met de UI-kit herbouwd worden:
   a. pure logica onder vitest: `parseApiError`, `money.ts`, en
      `toEditForm`/`toPayload` uit de form-builder extraheren + round-trip-testen;
   b. golden-flow-e2e: inschrijving mét betalend product, formulier mét branching,
      admin-login → daarna e2e blokkerend;
   c. component-tests enkel voor de UI-kit-primitieven (één keer de kit testen
      verslaat elke pagina testen).
4. **`mock_mollie`-gat**: happy-path-test mét bedragverificatie (nu enkel een
   mismatch-test; de mock slaat de controle standaard over).

### 19.6 Usability & vormgeving (advies, convergeert op de UI-kit)
Oordeel: functioneel degelijk, visueel utilitair, organisch gegroeid — consistentie
zit in conventie, niet in componenten. Sterk: nl-BE + `parseApiError`-vertalingen,
vast paginaritme, wizard/builder/matrix-patronen. Adviezen:
1. **Actie-overdaad in lijstrijen** (formulieren: 8 tekstlinks/rij) → 1–2 zichtbaar
   + "⋯"-menu; Verwijderen altijd apart (rood, met object-naam in de bevestiging).
2. **Feedback normaliseren**: 11× native `alert()/prompt()` + 13× `confirm()` →
   één Toast- + ConfirmDialog-patroon.
3. **Nav groeperen**: 15 platte admin-items → 3–4 clusters die de componentenkaart
   spiegelen (Leden / Activiteiten & Formulieren / Financieel / Site & systeem);
   bereidt rol-gebaseerde menu's voor.
4. **Mobiel**: 3/6 admin-tabellen zonder `overflow-x-auto`; publieke formulieren
   worden op telefoons ingevuld → expliciete mobiele check van het capture-pad.
5. **Laad-/empty-states**: 13× kale "Laden…" → gedeelde `<Loading>`/`<Empty>`.
6. **A11y**: modals missen `role="dialog"`/focus-trap/Escape — lift mee met dé ene
   `<Modal>`.
7. **Semantische design-tokens** op één plek (nu dubbel gedefinieerd; `blue-700`
   32× hardcoded) — tevens voorwaarde voor per-tenant branding (§7.2).
8. **Dark mode: niet doen** (kost veel, levert hier niets).
Alles behalve 1 en 3 lost de geplande **UI-kit + AdminConsole-template** (F/§11)
in één beweging op; 1 en 3 zijn de enige nieuwe ontwerpkeuzes.
De volledige IST-inventaris + normatieve conventies (knoppen, kleuren, labeling,
zoeken, paging, verwijderen, feedback) staan in **`ui-conventies.md`** (Deel A admin, Deel B publiek/ledenportaal) —
dat document is de specificatie van de UI-kit.

---

## 20. Navigatiepatroon: fichebak × proces ("record-centric, process-overlay")

Twee historische benaderingen, elk met een gat:
- **Data-gedreven navigatie** (van elk scherm via een grid naar elk gerelateerd
  record): perfect vindbaar, maar kent geen *proces* — het systeem weet niet wat
  de volgende stap is.
- **Wizard-gedreven proces**: perfecte begeleiding, maar nadien is niets terug te
  vinden of te wijzigen — de wizard is een silo.

De synthese bestaat en is het kernpatroon van moderne ERP's (Odoo, Salesforce
"Path", Dynamics BPF): **records zijn de waarheid, processen zijn overlays.**

### 20.1 De vier bouwstenen

**1 · Objectpagina (de fiche).** Elk kernrecord (persoon, gezin, activiteit,
inschrijving, betaling, formulier-inzending) heeft één canoniek adres
(`/admin/<component>/<id>`, deep-linkbaar) met een vaste opbouw:
kop (identiteit + statusbadge + acties) → detailvelden → **gerelateerde grids**
→ **tijdlijn**. De AdminConsole-template (§11) krijgt er zo een zuster bij:
de **ObjectPage-template**.

**2 · Relatienavigatie (de fichebak).** Elke gedeclareerde relatie — de
soft-refs en de "consumeert"-lijsten uit `CONTRACT.md` (§12) zijn samen al een
**machine-leesbare relatiegraaf** — verschijnt op de fiche als *smart button*
(label + aantal: "Betalingen (3)") die een **gefilterd grid** opent; elke
grid-rij klikt door naar díe fiche. Zo is elk record vanaf elk record bereikbaar
via zijn echte datarelaties, zonder per scherm navigatie te programmeren: de
grids worden **afgeleid uit de declaraties**, niet handgebouwd. Een
**broodkruimelpad** onthoudt de afgelegde route (gezin → lid → inschrijving →
betaling) zodat teruglopen triviaal is.

**3 · Proces als overlay (de wizard, getemd).** Een proces bezit géén data; het
is een **statusveld + taken op bestaande records** (workflow-component, §5.7):
- Op de fiche: een **statusbalk** (nieuw → in behandeling → in orde) met de
  toegestane overgangen als knoppen — het proces is *zichtbaar op het record*.
- Cross-record: de **takeninbox** ("wat wacht op mij?") verwijst naar fiches.
- De **wizard bestaat alleen als capture-modus** (publieke inschrijving,
  formulier): een begeleide walk die gewone records aanmaakt. Na afloop bestaat
  de wizard niet meer — er zíjn alleen records, dus wijzigen/terugvinden loopt
  altijd via de fiche. Hervatten = de fiche openen, niet de wizard herstarten.

**4 · Vindbaarheid.** Drie ingangen, alle drie eindigend op een fiche:
relatienavigatie (blader), **globale zoek/command-palette** (Ctrl+K: naam, id,
e-mail → fiche), en de **takeninbox** (proces). De **tijdlijn** op elke fiche
(gratis uit de history-mixin, §5.8: wie/wat/wanneer, incl. procesovergangen)
beantwoordt "wat is hier gebeurd?" zonder zoeken.

```mermaid
flowchart LR
  T["takeninbox<br/>(proces)"] --> F
  Z["zoek / Ctrl+K"] --> F
  F["FICHE<br/>kop + status(balk) + acties<br/>tijdlijn"] -->|"smart button (n)"| G["gefilterd grid<br/>gerelateerde records"]
  G -->|rij| F2["andere FICHE"]
  F2 -. broodkruimel terug .-> F
  W["wizard (enkel capture)"] -->|maakt records| F
```

### 20.2 Waarom dit hier bijna gratis is
- **Relatiegraaf**: soft-refs (waarde-id's) + `CONTRACT.md`-declaraties bestaan al
  in het ontwerp — de related-grids zijn er een *afleiding* van. Nieuwe relatie
  gedeclareerd = nieuwe smart button, nul schermcode.
- **Tijdlijn**: de history-mixin levert de feed per record.
- **Proces**: de workflow-component levert status + taken; de statusbalk is er de
  fiche-weergave van.
- **Grens blijft intact**: een related-grid toont data van een ánder component
  via diens facade/list-API (gefilterd op de soft-ref) — geen reach-in; de
  navigatie respecteert de moduulgrenzen.

### 20.3 Regels (samenvatting)
1. Elk kernrecord heeft één canonieke, deep-linkbare fiche.
2. Navigatie wordt **afgeleid uit gedeclareerde relaties**, nooit per scherm
   gebouwd.
3. Een proces bezit geen data: status op het record, taken in de inbox, wizard
   enkel als capture-modus.
4. Alles wat een wizard aanmaakt, is nadien via de fiche vindbaar én wijzigbaar
   (binnen de businessregels).
5. Elke fiche toont zijn tijdlijn.

**To-do's (backlog, sluit aan op F/§11)**: ObjectPage-template + smart-button/
related-grid-afleiding uit de relatie-declaraties + broodkruimelpad; statusbalk +
takeninbox mee met de workflow-component (Fase 4); command-palette later (nice to
have).

### 20.4 Bewerken: formulier of actie — inline bewust niet
Twee modaliteiten, geen drie:
- **Formulier** ("Bewerken", review-vóór-opslaan): álle veldwijzigingen — ook
  losse velden. Samenhang (adres als geheel), cross-veld-invarianten en geld
  sowieso.
- **Actie-knop**: alles met een gevolg — mail, betaling, procesovergang,
  verwijderen. Expliciet + bevestiging. (Directe knopjes als ↑/↓-volgorde zijn
  acties, geen inline-edit.)
- **Inline click-to-edit: bewust NIET voorzien** (YAGNI). De inline-geschikte
  velden zijn hier schaars (geen samenhang/geld/proces), het kost een dure
  UI-kit-feature (per-veld save/fout-states), en een laagfrequent gebruikte
  back-office is meer gebaat bij één voorspelbaar patroon. **Heropener**: toont
  de werkbank later een frequente één-veld-edit, dan is dát de gemeten reden om
  inline voor precies dat geval toe te voegen.
- Harde randen blijven: **procesvelden enkel via de statusbalk-overgangen**, en
  elke wijziging door **dezelfde facade/validatie**.

### 20.5 De werkbank — zero-touch & management by exception
**Ideaal ERP-scenario = zero-touch**: de happy path loopt volledig automatisch
(inschrijving → betaling → bevestiging: nul menselijke stappen). Menselijk werk is
per definitie een **exceptie of een expliciete beslissing** — en dat landt op
precies één plek: de **werkbank**.

- **Eén takeninbox over álle workflows/componenten heen**: workflow-taken (§5.7)
  én systeem-excepties — betaal-mismatches, te bevestigen refunds (bestaat al als
  pending-refund-wachtrij), ledenwijzigingen-review, import-conflicten, gefaalde
  mails, MDM-merge-kandidaten, wees-records (§19.2). Vandaag verspreide
  proto-wachtrijen → geconsolideerd.
- **Per taak**: wat + waarom (context), prioriteit/deadline, deep-link naar de
  fiche, en waar mogelijk de beslissing inline (goedkeuren/afwijzen vanaf de
  werkbank).
- **Mail is een notificatiekanaal-optie** (per gebruiker: per taak of digest),
  nooit de bron van waarheid — de werkbank is dat.
- **Ontwerpdoel: leeg.** Elke flow wordt ontworpen als "geen taak tenzij
  exceptie". Een lege werkbank = gezond systeem; terugkerende exceptie-types zijn
  de volgende automatiseringskandidaten (de werkbank meet zijn eigen overbodig-
  wording).
- Bouwt op de workflow-component (Fase 4): taken krijgen een uniforme vorm
  (bron-component, record-ref, type, status, toegewezen rol) zodat elke component
  excepties kan publiceren zonder eigen inbox-scherm.
- **Taken sluiten door toestand, niet door afvinken** (vertrouwensvoorwaarde):
  *toestandstaken* (excepties, bv. een niet-afgeboekte refund) zijn een afgeleide
  query op de data — lost de toestand op (via werkbank, fiche óf automatisch,
  bv. Mollie-webhook), dan verdwijnt de taak per definitie; *beslistaken*
  (workflow) hebben een eigen record maar abonneren zich op het onderliggende
  record en sluiten/annuleren automatisch als de beslissing elders valt of de
  grond vervalt. De taak volgt het record, nooit omgekeerd — één stale taak en
  niemand vertrouwt "werkbank leeg = niets te doen" nog.
- **Losse koppeling & uitval**: de werkbank bezit niets — hij *federeert* per
  component via de facade (uniforme taakvorm). Valt een component uit, dan
  blijven de taken van de overige componenten verschijnen en toont het
  uitgevallen component expliciet "niet bereikbaar — taken onbekend" (optioneel
  laatst-gekende snapshot + tijdstempel); **"leeg" en "onbekend" nooit vermengen**.
  Openstaan is toestand ín het component, dus uitval kost enkel tijdelijk
  zichtbaarheid, nooit correctheid — komt het component terug, dan verschijnen de
  nog-relevante taken vanzelf (geen replay/reconciliatie). In de monoliet is dit
  theoretisch (één proces); het contract wordt nu al zo vastgelegd voor latere
  extractie.
- **Taakcontract: één DTO, veel providers.** In `kernel/contracts`:
  `{bron, taak-type, titel, record-ref+deeplink, vereiste_rol, prioriteit,
  ontstaan_op, acties[]}`; elk component implementeert dezelfde facade
  (`list_tasks`). De variatie zit ín de componenten (hun afleidings-query), nooit
  in het contract — de werkbank kent nul taak-types en filtert op **rol** (en
  later tenant) via het `vereiste_rol`-veld. Nieuw component met taken = één
  facade-functie, nul werkbank-code.
- **Een afwijzing is ook een beslissing**: oordeelt een mens "geen probleem"
  (bv. "geen dubbel"), dan wordt dat oordeel zélf toestand (bewaarde markering),
  anders herrijst de afgeleide taak eeuwig.
- **Technische fouten: wél als er een businessactie is, anders niet.** De toets:
  *kan iemand met een rol er iets aan doen, en heeft het businessgevolgen als
  niemand het doet?* Gefaalde bevestigingsmail → taak "opnieuw versturen / lid
  verwittigen"; gemiste Mollie-webhook → "betaling verifiëren"; halverwege
  gefaalde import → "hervatten of terugdraaien". Zulke taken sluiten zichzelf
  door toestand (retry gelukt → taak weg). Puur technische defecten
  (stacktraces, logging-pipeline, container-herstart) horen **niet** in de
  werkbank maar in het observability-kanaal (§19.1) richting de beheerder —
  anders vervuilt onbegrijpelijke ruis het ontwerpdoel "leeg". De brug werkt in
  twee richtingen: een defect mét business-impact steekt over als taak, en een
  *terugkerend* exceptie-type in de werkbank is het signaal van een defect
  eronder (de werkbank meet zijn eigen overbodigwording).
- **Voorbeeld inschrijving → nationaal Raak-programma**: (a) *beslistaak*
  "mogelijke dubbel" (gelijkenis zonder merge óf geen-dubbel-markering; sluit
  door merge of bewaard besluit); (b) *toestandstaak* "persoon nog niet in het
  nationale programma" (geen `external_number` voor die bron, na N dagen
  respijt) — de bestaande ledenrapport-import upsert op `(source, external_id)`
  en sluit de taak **zonder menselijke handeling**; draait de import regelmatig,
  dan wordt hij meestal niet eens zichtbaar.

### 20.6 Proces- & regelnotatie: BPMN/DMN als taal, niet als motor
- **DMN**: geen rule-engine — taak-regels zijn queries in het eigenaar-component
  (code, getest). Wél het **beslistabel-formaat** als visueel/doc-formaat per
  taak-type (condities → taak/rol/prioriteit), met de regel-*catalogus* als data
  voor werkbank/docs; later exporteerbaar als DMN-XML.
- **BPMN**: de lichte workflow-state-machine (§5.7) blijft, maar de begrippen
  worden **uitgelijnd op BPMN-vocabulaire** (user task, service task, gateway,
  event) zodat een latere engine-overstap een mapping is, geen herbouw.
- **Visueel = genereren, niet tekenen**: uit de workflow-definitie wordt
  automatisch een procesdiagram gerenderd (Mermaid in de admin); de bouwer is een
  eenvoudige stappen/overgangen-editor (zoals de form-builder), geen BPMN-canvas.
- **Export**: BPMN-XML (definities) en DMN (beslistabellen) als uitwisselings-/
  documentatieformaat — goedkoop, houdt het model eerlijk. Import pas mét engine.
- **Heropener → echte engine** (past bij §18): parallelle takken,
  timers/escalaties, compensatie, langdurige multi-rol-processen. Europe-First-
  kandidaten: Camunda (DE), Flowable (CH), of Python-native SpiffWorkflow (OSS).

### 20.7 Gegenereerde relatienavigatie (conventies + register)
Eén declaratie per relatie (de soft-refs uit de CONTRACT-manifesten vormen het
**relatieregister**) genereert navigatie in **beide richtingen**:
- **Uitgaand**: een soft-ref is nooit platte tekst — overal `<RecordLink>` (chip
  met component-icoontje + naam → fiche).
- **Inkomend**: de doel-fiche toont automatisch een **smart button**
  "Inschrijvingen (n)" → gefilterd grid, afgeleid uit andermans declaratie.
- **Indirect**: directe refs automatisch; meer-hop-paden (gezin ⇒ personen ⇒
  inschrijvingen, "Inschrijvingen gezinsleden") enkel op **expliciete
  pad-declaratie** — geen transitieve sluiting (explosie/betekenisloos).

Conventies die het generiek en grens-veilig houden:
1. **Het doel-component bezit zijn eigen rijweergave** (kolommen/badge één keer
   gedefinieerd; gast-fiches embedden die — nul kennis van andermans data).
2. **Grid via de facade van de eigenaar** (list + ref-filter) en **erft diens
   autorisatie** (FINANCE-only relatie → teller zonder doorklik of verborgen).
3. **Route- & icoonconventie**: `/admin/<component>/<id>` + vast icoon per
   component; `<RecordLink>` resolvet puur op `(component, id)`.

Mechaniek: register = data (kernel-endpoint, afgeleid uit CONTRACT-declaraties);
ObjectPage-template rendert smart buttons + embedded grids generiek. **Nieuwe
relatie declareren = link + knop + grid, nul schermcode.** Proces prikt erdoor:
statusbalk op de fiche, statusbadges in grids, werkbank-taken deep-linken naar
dezelfde fiches.

### 20.8 Afgeleide relaties op e-mail — suggestie, geen identiteit
Anonieme captures (inschrijving/formulier) met een e-mailadres dat in MDM
voorkomt: **tonen, maar als aparte suggestie-laag** — een e-mail-match is een
claim, geen geverifieerde identiteit (en vaak gezinsbezit → op gezinsniveau
sterker dan op persoonsniveau).
- **Drie zekerheidsniveaus**: bevestigd (soft-ref gezet: ingelogd/geverifieerd of
  admin-bevestigd) → gewone smart button; **gesuggereerd** (e-mail-match) →
  visueel apart "Mogelijk gerelateerd (op e-mail): n", nooit vermengd;
  afgewezen → bewaard besluit (suggestie blijft weg).
- **Acties**: "Koppel" (zet de soft-ref; beslistaak/één klik) of "Negeer"
  (bewaarde markering — §20.5: een afwijzing is ook een beslissing).
- **Matching blijft afgeleid** (query op weergavemoment): e-mail-wijzigingen en
  MDM-merges bewegen automatisch mee; pas bevestigen materialiseert.
- **Ledenportaal-uitzondering**: na magic-link/OTP-login is het mailbezit
  bewezen → daar mag een match auto-claimen ("deze inschrijving is van jou?") of
  stil koppelen.

---

## 21. Frontend-technologie: React/Next vs. htmx — afwegingskader

Status: **BESLIST** (2026-07-07, zie 21.5): richting **één taal, server-rendered
(htmx + Jinja + Alpine)**, uitgevoerd via het pilotpad van 21.4. De vraag is
wezenlijk niet "React of htmx" maar **"twee talen (SPA + API) of één taal
(server-rendered)"** — al de rest zijn varianten.

### 21.1 De afweging per dimensie

| Dimensie | React/Next (huidig) | htmx + Jinja (+ Alpine) | Weging |
|---|---|---|---|
| **Browser-compat** | Build/transpile regelt het | Gewone HTML over de draad; htmx ondersteunt alle moderne browsers | Non-issue, beide kanten |
| **Rijke UX** | Alles kan | 95% van CRUD/formulieren prima (autocomplete, totalen, modals, wizards); **echt rijke client-state** (drag&drop-formulierbouwer!) is de uitzondering | htmx dekt bijna alles; de **form-builder** is óns moeilijkste scherm → als React-eiland behouden kan |
| **i18n** | react-i18next e.d. | Server-side i18n (gettext/Babel) is het oudste, rijpste model dat bestaat | Non-issue; server-side eerder een vóórdeel |
| **Security** | JWT in localStorage (zwakte, §19.1); XSS-oppervlak via `dangerouslySetInnerHTML` (gesaneerd) | HttpOnly-sessiecookie (beter), Jinja auto-escape; **vereist wel klassieke CSRF-tokens** | Licht voordeel htmx, mits CSRF correct |
| **Performance** | Meer JS naar de client | Minder JS → sneller op goedkope toestellen; server rendert meer (verwaarloosbaar op onze schaal) | Licht voordeel htmx |
| **Drift/dubbel werk** | py↔ts-drift is structureel (heel §19.4 + codegen bestaat hierom); totaalberekening 2× (frontend-weergave + backend-waarheid) | Eén taal, één berekening (server rendert het totaal met dezélfde functie die de betaling maakt) — de drift-probleemklasse **vervalt** | **Sterkste argument pro htmx** |
| **Discipline-risico** | API-grens dwingt scheiding af *per constructie* — frontend kán niet in de backend grabbelen | Eén codebase → reëel risico: businesslogica lekt naar templates/routes, "backend-dev mixt stiekem door de lagen". Mitigatie = dezelfde als overal in dit document: schermen praten **enkel met facades** (import-linter dekt ook UI-routes), view-model in Python, templates dom (macro's als componenten, lint op logica-in-templates) | **Sterkste argument pro React** — bij htmx is de grens afspraak+linter i.p.v. fysiek |
| **Template-kluwen** | JSX kan óók verkluwen | Reëel bij naïef gebruik; beheersbaar met Jinja-macro's als component-bibliotheek + fragments-patroon (de UI-kit van §11, maar dan server-side) | Gelijkspel: beide vragen dezelfde UI-kit-discipline |
| **Ecosysteem & churn** | Enorm ecosysteem; maar hoge churn (App Router/Server Components elke paar jaar een migratie) | Klein maar stabiel; htmx is bewust "boring tech", piepkleine API | Future-proof-punt voor htmx; ecosysteem-punt voor React |
| **AI-assisted dev** | Meeste trainingsdata | Ruim voldoende gekend; minder totaal-volume | Licht voordeel React, krimpend |
| **Mobiel** | Responsive nu; native zou JSON-API hergebruiken | Responsive idem; **PWA** (installeerbaar, push, offline-lite) werkt op server-rendered net zo goed | Zie 21.2 — geen beslisser, mits de JSON-facade blijft |

### 21.2 Mobiel — expliciet meegewogen
Voor een vereniging is een **PWA** (installeerbaar icoon, pushnotificaties,
basis-offline) vrijwel zeker het eindstation — geen app-store-app. Een PWA staat
volledig los van React-vs-htmx: beide serveren HTML + een manifest + service
worker. Zou er óóit een native app komen, dan heeft die een **JSON-API** nodig —
en dat is de belangrijkste hedge van deze hele keuze: **de OpenAPI/JSON-facade
blijft bestaan ongeacht de frontend-keuze** (integraties, chatbot, toekomstige
apps). htmx-routes komen er dan *naast* (zelfde service-laag, andere presentatie),
niet in de plaats van het contract.

### 21.3 Is er een derde piste?
- **Astro (islands)** — server-first met React/Alpine-eilandjes enkel waar nodig.
  Elegant, maar houdt de tweede taal + toolchain → lost het kernprobleem niet op.
- **SvelteKit/Vue** — lichter dan React, zelfde dual-stack-taks → zijwaartse stap.
- **htmx + Alpine.js** — dit is geen derde piste maar de *volwassen invulling* van
  de htmx-piste: Alpine (~8 kB, declaratief in HTML) dekt lokale client-state
  (dropdown open/dicht, tab-wissel) waar htmx server-rondjes overkill zijn.
- **Hybride per shell** — de reële derde piste: **AdminShell server-side (htmx),
  PublicShell blijft Next** zolang herbouw daar niet loont; §13.1 maakt shells
  onafhankelijk, dus dit kan per shell én per component beslist worden.

Conclusie: er is geen verborgen betere derde weg; het speelveld is
**één-taal-server-side (htmx+Alpine) ↔ hybride ↔ status quo (Next)**.

### 21.4 Uitvoeringspad (zo voeren we de beslissing uit)
1. **Pilot, geen geloofskwestie**: bouw bij de start van de AdminShell (fase 4)
   één echt component-adminscherm als htmx-pilot (kandidaat: de **werkbank** —
   nieuw scherm, dus geen herbouwkost) naast de bestaande React-schermen.
2. **Meet**: ontwikkelsnelheid (AI-assisted), regels code, gedrag op mobiel,
   en of de facade-discipline standhoudt (import-linter op UI-routes).
3. **Beslis per shell** (21.3-hybride is een geldig eindstation); de
   form-builder blijft in elk scenario het langst een React-eiland.
4. **Onvoorwaardelijk, nu al**: JSON-facade/OpenAPI als contract behouden (21.2)
   en de UI-kit-inspanning (§11) technologie-neutraal formuleren (patronen en
   tokens, niet React-componenten alléén) — dan is niets van dat werk weggegooid,
   welke kant dit ook opvalt.

### 21.5 Beslissing & waarom (ADR)

- **Datum**: 2026-07-07.
- **Context**: één ontwikkelaar + AI; laagfrequente back-office + klassieke
  publieke site; horizon 10+ jaar richting **ERP/WMS/logistiek** (21.7); de
  dual-stack-taks (drift-gate, codegen, dubbele types/berekeningen/toolchains/
  testrunners) is structureel en bewezen (§19.4 bestaat er alleen om).
- **Gekozen**: **één taal, server-rendered — htmx + Jinja + Alpine** voor beide
  shells als eindbeeld; verworpen: status quo (Next/React, dual-stack-taks
  blijft), Astro/SvelteKit (lossen de tweede taal niet op), big-bang-herbouw
  (risico zonder noodzaak).
- **Doorslaggevend**: het sterkste pro-React-argument (API-grens dwingt
  discipline fysiek af) lost een probleem op dat we al opgelost hebben —
  facades + import-linter gelden sowieso backend-intern. Het sterkste
  pro-htmx-argument laat een hele probleemklasse *verdwijnen* in plaats van ze
  te managen. Een opgelost probleem weegt niet op tegen een verdwenen probleem.
  Daarbij: security licht beter (HttpOnly-sessie i.p.v. JWT-in-localStorage),
  i18n rijper, minder churn ("boring tech" op een 10-jaarshorizon), SEO minstens
  gelijkwaardig, Mollie/mobiel/responsive neutraal (21.1–21.2).
- **Uitvoering**: pilotpad 21.4 — nú niets herbouwen; werkbank (fase 4) als
  eerste htmx-scherm (nul herbouwkost); daarna admin per component op natuurlijke
  momenten; publieke site als laatste; form-builder het langst als React-eiland;
  JSON/OpenAPI-facade blijft onvoorwaardelijk. De hybride periode is begrensd
  doordat het omklappen meelift met de modularisatie-fases. **Eindstreep,
  meetbaar**: de frontend-container (Next/Node) vervalt — de stack gaat per
  omgeving van 4 naar 3 services (db, backend serveert HTML+JSON, caddy);
  tijdens de hybride periode blijft hij gewoon draaien.
- **Heropener**: de pilot zelf — valt de werkbank-pilot tegen op
  ontwikkelsnelheid, discipline (logica lekt naar templates ondanks linter) of
  UX, dan terug naar status quo/hybride zonder verlies (er is dan niets
  herbouwd). Plus de scenario's uit 21.6: offline-first, zware realtime-
  samenwerking, app-store-app als kernproduct, of een apart frontend-team —
  elk daarvan is een signaal om de SPA-piste te herwegen.

### 21.6 Twee tegenwerpingen, expliciet gewogen

**"Codegen (§19.4) lost de drift toch al op — waarom dan nog ombouwen?"**
Codegen lost *type*-drift op (hernoemd veld → CI faalt), maar niet de rest van de
taks: **logica-duplicatie** blijft (totaalberekening 2×: types genereren ≠ gedrag
genereren), de **tweede toolchain** blijft integraal (Node-build, vitest/eslint
naast pytest/ruff, React/Next-churn), en de gate zelf is blijvend onderhoud.
Kortom: **codegen verlaagt de taks van "gevaarlijk" naar "duur"; één taal schaft
ze af.** §19.4 stap 1–2 (response_models + OpenAPI-export) blijft óók in het
eindbeeld waardevol — dat is het machinecontract (21.2); enkel de
TypeScript-generatiestappen vervallen op termijn.

**"Waarom gebruikt de hele wereld dan React/Angular?"**
Omdat de meeste React-adopters een ander probleem hebben dan wij: (1) **aparte
frontend/backend-teams** — de API-grens is daar een *organisatorische* grens
(Conway); wij zijn één ontwikkelaar + AI en betalen die grens zonder de baten;
(2) **app-achtige producten** (Figma/Gmail-klasse client-state) — een
formulieren-en-lijsten-portaal is dat niet; (3) **arbeidsmarkt/momentum** —
netwerkeffect, geen technisch argument. En de wereld is minder eensgezind dan ze
lijkt: de tegenbeweging is mainstream (Next zelf terug naar de server met Server
Components; Rails Hotwire, Phoenix LiveView, Laravel Livewire; GitHub/Basecamp
grotendeels server-gerenderd). We volgen geen exoot maar de server-side-
renaissance, met htmx als kleinste, stabielste vertegenwoordiger.

**"AI kent beide talen — ondergraaft dat het één-taal-argument niet?"**
Het neemt één argument weg (geen frontend-specialist nodig) en verzwakt de
*urgentie* (daarom: pilotpad, geen urgente migratie). De kern blijft: de taks
zit niet in het *schrijven* maar in het *bestaan* van twee synchroon te houden
artefacten — per feature 2× oppervlak (schema's, logica, tests, builds), de
verificatielast valt op de ene mens (kleinere één-talige diffs reviewen sneller),
drift is een synchronisatie- geen kennisprobleem (ook een AI vergeet een
handgeschreven kopie, zeker over sessies heen), churn-migraties blijven werk
zonder productwaarde, en het kost letterlijk meer credits (§16: twee stacks =
meer context/tokens per wijziging). AI versterkt het kostenargument dus eerder
dan het te ondermijnen.

### 21.7 Getoetst aan de lange-termijnhorizon: ERP / WMS / logistiek

De doelklasse op termijn is **bedrijfssoftware** (ERP, WMS, logistiek) — dat
*versterkt* de keuze eerder dan ze te ondermijnen:

- **ERP-schermen zíjn dit profiel**: fiches, grids, formulieren, taken,
  statusovergangen (§20) — precies waar server-rendered excelleert. Niet
  toevallig is de referentie-inspiratie (Odoo-achtige smart buttons, SAP-achtige
  werklijsten) functioneel, niet frontend-technologisch.
- **WMS-specifiek** past goed: scanner-handhelds zijn goedkope toestellen waar
  mínder JavaScript een feature is; barcodescanners werken als toetsenbord-input
  (keyboard wedge) op een gewoon server-rendered formulier; snelheid per
  transactie (scan → bevestig → volgende) is een latentiekwestie, geen
  framework-kwestie. Live-borden (orders, dockplanning) kunnen met **SSE**
  (htmx heeft daar een standaard-extensie voor) — geen SPA nodig.
- **De echte WMS-waakvlam is offline**: haperende magazijn-wifi + door-blijven-
  scannen = het offline-first-scenario dat al als heropener in 21.5 staat. Dat
  wordt dan een bewust eiland (lokale wachtrij op het scanscherm), niet een
  reden om het hele platform SPA te maken.
- De rest van dit document is al op die horizon ontworpen: componenten met
  facades (§5), MDM (§6), multi-tenant (§7), workflow/werkbank/taakcontract
  (§20.5), BPMN/DMN als taal (§20.6) — de frontend-keuze sluit daar nu op aan:
  één taal van magazijnvloer tot back-office.
