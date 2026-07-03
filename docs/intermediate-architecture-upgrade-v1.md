# Intermediate Architecture Upgrade — v1

> Werkdocument / bespreekstuk. Beschrijft de tussenstap-architectuur richting een
> **modulair ERP/portaal/CRM**, met domeinmodules, moduulafzondering (facade +
> eigen Postgres-schema + eventueel eigen migratieketen), de toekomstige aparte
> apps (login & security, mail-logging, master data) en een **multi-tenant**
> opzet (Raak vzw met sub-verenigingen). Nog **geen** release toegewezen; dit is
> het denkkader waaruit we issues afleiden en inplannen.
>
> Gerelateerd: epic **#366** + sub-issues **#360–#365**.

---

## 1. Doel & leidraad

We groeien van een goed-gestructureerde **modulaire monoliet** naar een architectuur
waarin elk domein een echte module is met een **afdwingbare buitengrens**, zodat we
later — en enkel wanneer een concrete driver dat vraagt — een module als aparte app
kunnen afsplitsen. Het is bewust een **leertraject**: elke stap leert ons het
sjabloon dat we op het volgende domein toepassen.

Kernprincipes (de rode draad door alles hieronder):

- **Capture → Record → Act.** Elk domein heeft een publieke *capture*-kant
  (bezoeker), een *record*-kern (eigen data + regels) en een back-office *act*-kant
  (rol-gated console).
- **Eén verticale slice per module** in `app/domains/<domein>/`, met een **facade**
  (`api.py`) als enige publieke oppervlak. Geen reach-in in models/services.
- **Owned data**: elke module bezit zijn tabellen in een **eigen Postgres-schema**;
  cross-module verkeer via **events/DTO's**, nooit via live ORM-objecten of
  gedeelde FK's.
- **Kernel** apart: auth, database, config, events/contracts — alles hangt van de
  kernel af, de kernel van geen enkel domein.
- **Rol-as** als enige divergentie in de back-office: `ADMIN` vs `FINANCE`
  (penningmeester), later per sub-vereniging.
- **Modulariteit = OO op macroschaal**: een module is een object; facade =
  encapsulation, events = message passing, import-linter = het `private`-keyword dat
  Python over packages mist.

---

## 2. Twee onafhankelijke assen (belangrijkste inzicht)

Verwar **modularisatie** en **multi-tenancy** niet: het zijn twee loodrechte assen.

| As | Vraag | Mechanisme |
|---|---|---|
| **Module** (verticaal) | *Wélk soort data/gedrag?* (forms, betalingen, master data …) | Eigen package + eigen **Postgres-schema** (`form`, `payment`, `master` …) |
| **Tenant** (horizontaal) | *Van wélke vereniging?* (Millegem, Achterbos, Mol-Centrum …) | **`tenant_id`** (rij-niveau) binnen elke moduletabel |

```mermaid
flowchart LR
  subgraph Modules["Module-as → Postgres-schema's"]
    M1[master]:::m
    M2[form]:::m
    M3[payment]:::m
    M4[mail]:::m
    M5[auth]:::m
  end
  subgraph Tenants["Tenant-as → tenant_id per rij"]
    T1[Raak Millegem]:::t
    T2[Raak Achterbos]:::t
    T3[Raak Mol-Centrum]:::t
  end
  Modules -. elke moduletabel draagt tenant_id .-> Tenants
  classDef m fill:#e8f0ff,stroke:#3b6;
  classDef t fill:#fff3e0,stroke:#e90;
```

De VZW-koepel snijdt dwars door beide: **Raak vzw ziet alle tenants** in alle
modules. Daarom is rij-niveau (`tenant_id`) het juiste model — een schema-per-tenant
zou de koepelblik pijnlijk maken (union over N schema's). Zie §7.

---

## 3. Componentenkaart (doelbeeld)

```mermaid
flowchart TB
  subgraph Public["Publieke site (bezoeker)"]
    PUB_FORM[Formulier invullen]
    PUB_PAY[Betalen Mollie]
    PUB_REG[Lid/gezin inschrijven]
    PUB_ACT[Activiteiten bekijken/inschrijven]
  end

  subgraph BO["Back-office console (ADMIN / FINANCE)"]
    BO_FORMBUILD[Formulier-bouwer]
    BO_PAY[Betalingen & terugvordering]
    BO_MEMBERS[Leden & gezinnen]
    BO_ACT[Activiteiten-beheer]
    BO_MAIL[E-maillog]
    BO_USERS[Gebruikers & rollen]
  end

  subgraph Kernel["Kernel (gedeeld, hangt van geen domein af)"]
    K_DB[(database)]
    K_EVENTS[event-bus / contracts]
    K_CFG[config]
  end

  subgraph Domains["Domeinmodules — elk eigen schema + facade api.py"]
    D_AUTH["auth & security<br/>schema: auth"]
    D_MASTER["master data<br/>schema: master<br/>(personen, gezinnen, postcodes,<br/>feit. verenigingen, vzw)"]
    D_FORM["form engine<br/>schema: form"]
    D_PAY["payments (Mollie)<br/>schema: payment"]
    D_MAIL["mail-logging<br/>schema: mail"]
    D_MEMBER["membership<br/>schema: member"]
    D_ACT["activities<br/>schema: activity"]
    D_CMS["cms<br/>schema: cms"]
    D_AI["AI/STT + chatbot<br/>(stateless / schema: ai)"]
    D_ANALYTICS["analytics (read-model)"]
  end

  Public --> Domains
  BO --> Domains
  Domains --> Kernel

  %% cross-module enkel via facade/events
  D_MEMBER -. facade .-> D_MASTER
  D_PAY -. event PaymentSettled .-> D_MEMBER
  D_FORM -. event SubmissionCreated .-> D_MAIL
  D_MASTER -. levert tenant-context .-> D_AUTH
```

**Legenda / regels op de pijlen:**
- Publieke en back-office schermen praten enkel met een **module-facade**, nooit
  rechtstreeks met andermans models.
- Domeinen praten onderling **enkel via facade-calls of events** (gestippeld).
- Alles mag op de **kernel** steunen; de kernel steunt op niets domein-specifiek.

---

## 4. Schermen ↔ componenten

Je intuïtie klopt: het **formulier-bouwscherm hoort bij de form-component**, en de
publieke rendering óók. Algemene regel: **een scherm hoort bij de module wiens data
het toont/bewerkt**, ongeacht of het publiek of back-office is. Publiek vs
back-office is een *rol/authenticatie*-onderscheid, geen *component*-grens.

| Scherm | Kant | Component (eigenaar) | Rol |
|---|---|---|---|
| Formulier invullen (`/formulier/[token]`) | publiek | **form** | — (capability-token) |
| Formulier-bouwer (`/admin/formulieren`) | back-office | **form** | ADMIN |
| Inzendingen bekijken/verwijderen | back-office | **form** | ADMIN |
| Betaalflow / redirect Mollie (`/betaling/*`) | publiek | **payment** | — |
| Betalingen-overzicht + **terugvordering** | back-office | **payment** | **FINANCE** |
| Lid/gezin inschrijven (publiek) | publiek | **master data** (+ membership) | — |
| Leden & gezinnen beheren (`/admin/leden`) | back-office | **master data** | ADMIN |
| Activiteiten bekijken/inschrijven | publiek | **activities** | — |
| Activiteiten-beheer | back-office | **activities** | ADMIN |
| E-maillog (`/admin/emails`) | back-office | **mail-logging** | ADMIN |
| Gebruikers & rollen (`/admin/gebruikers`) | back-office | **auth & security** | ADMIN |
| Login (`/login`, `/admin/login`) | beide | **auth & security** | — |
| CMS-pagina's (`/[slug]`, `/admin/paginas`) | beide | **cms** | ADMIN |

> **Frontend-consequentie:** spiegel de backend. Vandaag zit UI verspreid over
> `components/` + `lib/api.ts` + `lib/types.ts`. Doel: `features/<component>/` met
> eigen componenten, `api`-slice en types. `lib/` houdt enkel gedeelde primitives
> (money, errors, axios-client). Eén feature-map = één component, publiek én
> back-office samen.

```mermaid
flowchart LR
  subgraph FE["Frontend features/"]
    F_FORM["features/forms<br/>bouwer + publieke render"]
    F_PAY["features/payments<br/>betaalflow + console"]
    F_MASTER["features/master<br/>inschrijving + ledenbeheer"]
  end
  subgraph API["Facades (backend api.py)"]
    A_FORM[form.api]
    A_PAY[payment.api]
    A_MASTER[master.api]
  end
  F_FORM --> A_FORM
  F_PAY --> A_PAY
  F_MASTER --> A_MASTER
```

---

## 5. Toekomstige aparte apps (jouw wensen)

Drie domeinen die je expliciet als aparte app ziet — ze zijn **cross-cutting** en
lenen zich goed voor vroege afzondering:

### 5.1 Login & Security (`auth`) — één fundamentele component
- Bevat: `users`, `user_roles`, `role_codes`, login-tokens, JWT-uitgifte/-verificatie,
  `require_roles`.
- **Eén aparte component/app** `domains/auth/` met eigen schema `auth` + eigen keten +
  facade: `authenticate()`, `issue_token()`, `verify_token()`, `require_roles()`,
  gebruikersbeheer. **Elke** andere component gebruikt die via `auth.api`.
- **Positie = laag 1 (fundamenteel)**, zie §8: auth hangt **enkel van de kernel af**
  (db, config), van geen enkel domein. De kernel roept auth niet aan — de
  `require_roles`/`verify`-check is een *route-dependency* die elke domein-router uit
  `auth.api` haalt. Zo is er geen cyclus (kernel ← auth ← domeinen) en blijft de
  kernel dunne plumbing.
- Multi-tenant: rol-toewijzingen dragen een `tenant_id` (UNIT) als **waarde**, geen
  harde FK naar `master` — auth blijft los van master.

### 5.2 Mail-logging (`mail`)
- Bevat: `email_log` + het centrale `_send`-chokepoint + retentie
  (`EMAIL_LOG_RETENTION_DAYS`).
- Vandaag al een chokepoint — ideale kandidaat. Facade: `send(email)` +
  `list_logs()` + `delete_log()`. Elke module publiceert "stuur mail" via deze
  facade (of via een `MailRequested`-event), zodat de logging één plek blijft.
- **Belangrijk:** bij de form-schema-migratie **blijft `email_log` in `public`/`mail`**,
  niet in `form` (correctie op het mengen uit migratie 062).

### 5.3 Master Data (`master`)
- Bevat vandaag: **personen, gezinnen, adressen, postcodes**.
- Groeit met: **feitelijke verenigingen** en de **vzw** zelf (§6–7).
- Los van **lidmaatschap**: een persoon/gezin bestaat onafhankelijk van of ze lid
  zijn. `membership` wordt een *aparte* module die naar master-data verwijst (via id,
  niet via harde cross-schema FK).
- Facade: `get_person()`, `find_family()`, `resolve_postal_code()`,
  `list_organizations()`.

```mermaid
flowchart TB
  subgraph master["master (schema)"]
    P[persons]
    F[families]
    A[addresses]
    PC[postal_codes]
    ORG[organizations<br/>vzw + feit. verenigingen]
  end
  subgraph member["member (schema)"]
    MEMB[memberships → person_id, tenant_id]
  end
  MEMB -. verwijst via id .-> P
  MEMB -. verwijst via id .-> ORG
```

---

## 6. Data: master data met organisaties

`organizations` wordt de spil van zowel de **koepelstructuur** als de **tenancy**.
Het model is bewust **generiek** (niet vzw-specifiek): de app moet voor elk type
organisatie werken. Twee structurele niveaus, en het juridische type is **data**.

```mermaid
erDiagram
  ORGANIZATION ||--o{ ORGANIZATION : "parent (account → unit)"
  ORGANIZATION {
    int id
    string kind "ACCOUNT | UNIT (structurele rol)"
    string legal_form "vrij label: VZW / feit. vereniging / bedrijf / …"
    string name "Raak vzw / Raak Millegem"
    int parent_id "null voor de account-wortel"
  }
  ORGANIZATION ||--o{ PERSON : "tenant_id (= unit)"
  ORGANIZATION ||--o{ FAMILY : "tenant_id (= unit)"
  PERSON ||--o{ FAMILY_MEMBER : ""
  FAMILY ||--o{ FAMILY_MEMBER : ""
  PERSON {
    int id
    int tenant_id "= UNIT"
  }
  FAMILY {
    int id
    int tenant_id
  }
```

- **`organizations`** is zelf-refererend met een structurele `kind`:
  - **ACCOUNT** = de koepel/klant (billing-entiteit). Bij Raak: "Raak vzw".
    Wortel (`parent_id = null`).
  - **UNIT** = een operationele eenheid onder een account. Bij Raak: de feitelijke
    verenigingen (Millegem, Achterbos, Mol-Centrum, Mol-Rauw …).
- **`legal_form`** is een vrij label (VZW, feitelijke vereniging, bedrijf, …) → de
  juridische invulling is **data**, geen schema-aanname. Zo werkt de app net zo goed
  voor niet-vzw-klanten.
- Elke tenant-scoped rij (persoon, gezin, later activiteit/formulier/betaling) draagt
  een **`tenant_id`** = de **UNIT**. De **ACCOUNT**-scope leid je af door de boom op
  te lopen (`unit.parent_id`).

---

## 7. Multi-tenant opzet

**Klant = Raak vzw**; **tenants = de sub-verenigingen**; de vzw heeft **zicht op
alles**.

**Klant = een ACCOUNT** (bij Raak: Raak vzw, maar generiek elk type organisatie);
**tenants = de UNITs** (sub-verenigingen); de account heeft **zicht op alles**.

```mermaid
flowchart TB
  VZW["ACCOUNT<br/>(bv. Raak vzw — ziet ALLES)"]:::vzw
  VZW --> M1["UNIT: Raak Millegem"]:::sub
  VZW --> M2["UNIT: Raak Achterbos"]:::sub
  VZW --> M3["UNIT: Raak Mol-Centrum"]:::sub
  VZW --> M4["UNIT: Raak Mol-Rauw"]:::sub
  M1 --> L1["leden • gezinnen • activiteiten • formulieren • betalingen"]
  M2 --> L2["leden • gezinnen • …"]
  classDef vzw fill:#ffd,stroke:#aa0,stroke-width:2px;
  classDef sub fill:#e8f0ff,stroke:#36b;
```

### Gekozen model: **rij-niveau tenancy (shared schema + `tenant_id`)**

| Optie | Isolatie | VZW-koepelblik | Ops-last | Verdict |
|---|---|---|---|---|
| **Rij-niveau `tenant_id`** | via app + (optioneel) Postgres **RLS** | **triviaal** (query over tenants) | laag | ✅ **aanbevolen** |
| Schema-per-tenant | sterk | pijnlijk (union over N schema's) | hoog (N×M schema's) | ❌ |
| DB-per-tenant | maximaal | zeer pijnlijk | zeer hoog | ❌ |

Waarom rij-niveau past: de koepel **moet** dwars over tenants rapporteren; dat is een
`WHERE tenant_id IN (…)` i.p.v. een cross-schema-union. Isolatie versterk je later
optioneel met **Postgres Row-Level Security** (policy op `tenant_id`), zodat de DB
zélf lekken tussen tenants blokkeert — dezelfde "DB als vangnet"-filosofie als de
per-schema `GRANT`.

### Tenant-context als kernel-concern
- De **actieve tenant** (en of de gebruiker koepel-breed mag kijken) komt uit het
  JWT / de sessie en wordt door de **kernel** in een request-context gezet.
- Elke module-facade filtert standaard op de actieve tenant; een **VZW-rol** kan de
  filter verruimen tot "alle tenants".
- Rol-model breidt uit: `ADMIN`/`FINANCE` **per UNIT**, plus een generieke koepel-rol
  **`ACCOUNT_ADMIN`** die over alle units van zijn account heen kijkt (org-type-neutraal
  — bewust niet `VZW_ADMIN`, want de app moet voor elk soort organisatie werken).

> **Uitrol per app, niet dark en niet big-bang.** Tenancy raakt elke module (as-2 uit
> §2), maar we voeren `tenant_id` **niet** vervroegd "dark" in. De kernel levert het
> *gereedschap* (een `tenant_id`-mixin + tenant-context), en **elke app adopteert dat
> op zijn eigen moment van rijpheid, met een grondige testronde** per app. Zo blijft
> elke introductie beheersbaar en getest i.p.v. een grote gelijktijdige omschakeling.

### 7.1 Configuratie & secrets: DB-beheerd per tenant vs. `.env`-infra

Multi-tenant dwingt een scherpe scheiding af tussen *wat per vereniging verschilt* en
*wat bij de deployment/technologie hoort*:

| Soort | Waar | Voorbeelden |
|---|---|---|
| **Per-tenant config** | **DB-beheerd** (per ACCOUNT/UNIT) | afzender-mailadres, Mollie-account/profiel, logo, branding, organisatienaam, domein, retentie-voorkeuren |
| **Per-tenant secret** | **DB, versleuteld at rest** (of secrets-store per tenant) | Mollie API-key, evt. per-tenant SMTP-credentials |
| **Infra / technologie** | **`.env`** (per deployment) | DB-wachtwoord, server-IP, SSH-sleutel, `SECRET_KEY`, proxy/CA-bundle |

- Vandaag zit config als `mailadres`, `mollie-code`, `logo` in `.env`; die verhuizen
  naar een **per-tenant settings-store** (tabel in `master` of een eigen `config`-
  component), gelezen via de tenant-context met een `.env`-**default** tijdens de
  single-tenant-fase.
- **Per-tenant secrets** (Mollie-key) horen in de DB **versleuteld**, nooit in klare
  tekst — consistent met de publieke-repo-regel (`.env` = enkel infra; geen secrets in
  git).
- **`.env` blijft** voor alles wat technologie-/deployment-gebonden is en niet per
  vereniging verschilt.

---

## 8. Afhankelijkheden & grens-handhaving

**3-lagen-afhankelijkheidsmodel** (afhankelijkheden wijzen enkel naar beneden):

| Laag | Bevat | Mag afhangen van |
|---|---|---|
| **0 · Kernel** | db, config, events, tenant-context (plumbing) | niets |
| **1 · Fundamenteel** | **auth/security** (en later evt. mail, master) | enkel kernel |
| **2 · Domeinen** | form, payment, activities, cms, membership | kernel + laag-1-facades + elkaars facades/events |

Auth/security is een **fundamentele component** (laag 1): één aparte, apart-deploybare
app die iedereen via `auth.api` gebruikt, en die zelf enkel op de kernel steunt. De
kernel roept auth niet aan → geen cyclus.


```mermaid
flowchart TB
  subgraph K["kernel (plumbing)"]
    KDB[(db)]
    KEV[events]
    KTEN[tenant-context]
    KCFG[config]
  end

  AUTH["domains/auth<br/>(laag 1: verify + rollen)"]
  MASTER[domains/master]
  FORM[domains/form]
  PAY[domains/payment]
  MAIL[domains/mail]
  MEMBER[domains/member]

  AUTH --> K
  MASTER --> K
  FORM --> K
  PAY --> K
  MAIL --> K
  MEMBER --> K

  MEMBER -.->|auth-facade| AUTH
  FORM -.->|auth-facade| AUTH
  PAY -.->|auth-facade| AUTH
  MEMBER -.->|facade| MASTER
  PAY -.->|event| MAIL
  FORM -.->|event| MAIL

  X1["verboden: FORM naar MASTER.models"]:::bad -.-> MASTER
  classDef bad fill:#fee,stroke:#c33,stroke-dasharray:4;
```

Gehandhaafd door:
1. **import-linter** in CI (mapgrenzen = moduulgrenzen).
2. **Geen cross-schema FK's** — geverifieerd door een integratietest
   (`information_schema`).
3. **Aparte Alembic-keten per module** (waar we dat kiezen) — twee ketens kunnen
   fysiek geen tabel delen; drift/één-head-tests falen bij een fout.
4. Later: **per-schema `GRANT`** en **RLS per tenant** als DB-afgedwongen vangnet.

---

## 9. Roadmap (fasering — nog geen releasenummers)

```mermaid
flowchart LR
  P0["Fase 0<br/>form engine als sjabloon<br/>#360–#363"] --> P1
  P1["Fase 1<br/>mail-logging + auth afzonderen<br/>(cross-cutting eerst)"] --> P2
  P2["Fase 2<br/>master data als module<br/>(personen/gezinnen/postcodes)"] --> P3
  P3["Fase 3<br/>payments/Mollie + refund<br/>#365"] --> P4
  P4["Fase 4<br/>organizations in master<br/>(ACCOUNT + UNIT, generiek)<br/>+ per-tenant config/secrets uit .env"] --> P5
  P5["Fase 5<br/>multi-tenant per app introduceren<br/>(tenant_id + context, grondig getest)<br/>+ ACCOUNT_ADMIN-rol (RLS later)"] --> P6
  P6["Fase 6<br/>AI/STT extractie<br/>#364 (bij driver)"]
```

**Waarom deze volgorde**
- **Fase 0** eerst: forms is best geïsoleerd → leert ons het volledige sjabloon
  (facade → linter → schema → 2e keten + integratietests).
- **Fase 1** cross-cutting (mail, auth) vroeg, want elke andere module leunt erop;
  hoe langer verweven, hoe duurder later.
- **Fase 2–4** master data vóór tenancy: je hebt eerst `organizations` nodig als
  ophangpunt van `tenant_id`.
- **Fase 5** multi-tenant als kernel-brede stap (mixin + context + rol), pas nadat de
  modules hun eigen schema hebben.
- **Fase 6** echte extractie (STT stateless → HTTP/queue-service) enkel bij een
  concrete driver (zware runtime/dependencies).

**Per fase, vaste stappen (het sjabloon):**
`facade → import-linter-contract → eigen schema + handoff-migratie → (optioneel) 2e
Alembic-keten + integratietests → frontend-feature-map`.

---

## 10. Ontwerpkeuzes

**Beslist:**
- ✅ **Generieke org-naamgeving**: geen `VZW_ADMIN` maar **`ACCOUNT_ADMIN`**; org-type
  (`legal_form`) is data, niet schema. De app is org-type-neutraal (§6–7).
- ✅ **RLS later**: eerst tenant-filtering in de facade-laag; Postgres Row-Level
  Security pas als hardening ná Fase 5 (stabiele tenant-logica = vangnet, geen
  struikelblok).
- ✅ **Eigen Alembic-keten = kandidaat-standalone-apps**: **auth, mail, master, form,
  payment** krijgen elk een eigen schema **én** een eigen migratieketen (apart
  deploybaar). Puur **interne** modules (cms, activities, analytics) krijgen enkel een
  eigen **schema** op de kern-keten (geen aparte keten → geen extra ops-last waar het
  niet loont).

- ✅ **Auth/security = één fundamentele component** (laag 1), niet gesplitst: eigen
  schema `auth` + eigen keten + facade; iedereen gebruikt `auth.api`; auth hangt enkel
  van de kernel af. (Geen `kernel/security`-split — de kernel roept auth niet aan, dus
  geen cyclus.)

- ✅ **Geen "dark" tenant_id**: tenancy wordt **per app** ingevoerd op het juiste
  moment, telkens grondig doorgetest (de kernel levert enkel het gereedschap:
  mixin + context). Zie §7 en §7.1.
- ✅ **Config-scheiding**: per-tenant config **DB-beheerd** (mailadres, Mollie, logo,
  branding), per-tenant secrets **DB versleuteld**, technologie/infra in **`.env`**
  (DB-wachtwoord, IP, SSH-sleutel, `SECRET_KEY`). Zie §7.1.
- ✅ **Frontend per fase/component**: `features/<component>/` wordt samen met de
  backend van dat component afgerond (geen aparte opkuis-slag later), zodat de grens
  in één keer volledig dicht is.

*Alle ontwerpkeuzes beslist — klaar om de fasen in issues om te zetten.*

---

## 11. Samenvatting

- **Twee assen**: module (verticaal, eigen schema) × tenant (horizontaal, `tenant_id`).
  Niet verwarren.
- **Schermen horen bij hun component**, publiek én back-office; rol bepaalt toegang,
  niet de componentgrens.
- **Master data** wordt de spil: personen, gezinnen, postcodes én `organizations`
  (vzw + feitelijke verenigingen) — de ophanging voor multi-tenancy.
- **Cross-cutting eerst** afzonderen (mail, auth), dan master data, dan de rest.
- **Multi-tenant = rij-niveau** (shared schema + `tenant_id`, optioneel RLS), want de
  vzw-koepel moet dwars over alle tenants kijken.
- Alles gefaseerd, elk met hetzelfde sjabloon; issues hangen aan epic **#366**.
