# UI-conventies (geschreven norm & interactiepatronen)

> **Het uiterlijk staat in [`docs/design-system.html`](design-system.html)** — de
> enige bron voor kleur, typografie, componenten en referentieschermen. Dit
> document is de geschreven norm ernaast: de conventies en gedragsregels die je
> niet uit een mock kunt aflezen. De oude `stijlgids.html` is daarin opgegaan
> (#528 as E). Handhaving: `backend/tests/test_ui_conventions_gate.py`, stand in
> [`docs/ui-conformiteit.md`](ui-conformiteit.md).

> Normatief document voor de volledige GUI: **Deel A = admin**, **Deel B =
> publieke site + ledenportaal**. Gebaseerd op volledige inventarissen (juli
> 2026, file:line-bewijs beschikbaar). Structuur per deel: **IST** (waar het
> schuurt) → **SOLL** (de conventie) → **uitzonderingen** → **kluslijst**.
>
> *IST/SOLL* is analistenjargon (uit het Duits): **IST** = de huidige,
> feitelijke toestand ("zo ís het nu"); **SOLL** = de gewenste doeltoestand
> ("zo móét het worden"). De kluslijst is telkens het pad van IST naar SOLL.
> Uitvoering loopt mee met de UI-kit (architectuurdoc §11/§19.6); dit document
> is de specificatie ervan. De conventies zijn **technologie-neutraal**; sinds de
> frontend-beslissing (architectuurdoc §21: htmx + Jinja + Alpine) wordt de UI-kit
> gebouwd als **design-tokens + Jinja-macro's**, en worden de kluslijsten per
> pagina uitgevoerd **bij de omklap van dat scherm** — niet meer als
> React-verbouwing vooraf.

---

## 0. Design-tokens — één bron van waarheid

De merkkleuren en het merkfont hebben **één canonieke bron**: de Tailwind-config
in `scripts/build-css.sh` (die de `blue-*`-schaal op de merkblauw zet en de
`brand.*`-tokens definieert). De browser rendert wát daar staat — dat is dus de
waarheid, niet een hex of klasse die elders wordt herhaald.

- **Merkblauw = Ocean Blue = `#0051a4` = `blue-700`.** Koppen, de header-band, de
  primary-knop-rust en rol-/info-badges dragen deze tint. `blue-800` (`#02407c`)
  is bewust **donkerder** en enkel de hover-staat van de primary-knop — nooit de
  rustkleur van chrome of koppen.
- **Link-tint = `#2367bd` = `blue-500` = token `--link`/`text-link`.** Tekst-/prose-links
  (o.a. CMS-content) dragen deze **fellere** merk-tint (afgeleid van de ocean-schaal),
  altijd **onderstreept**, zodat ze onderscheidend "poppen" naast het diepe merkblauw
  van koppen/chrome. Bewust géén generiek Tailwind-linkblauw (#1e40af/#2563eb) — dat is
  off-brand. Contrast op wit ≈ 5,5:1 (AA), en de underline draagt het link-signaal.
- **Regel:** conventies en templates **verwijzen naar de token** (de
  `blue-700`/`brand`-klasse); ze herschrijven nooit een losse hex of een
  afwijkende `blue-*`-klasse. Zo toont het design system
  (`docs/design-system.html`) de kleur zonder dat een tweede plek ervan kan
  afdrijven. Wijkt een klasse hieronder toch af, dan is de token leidend.

---

# Deel A — Admin

---

## 1. IST — de tien grootste inconsistenties (op gebruikersimpact)

1. **Zoeken op 3/15 pagina's**, terwijl grote ongepagineerde lijsten (betalingen,
   activiteiten, ledenwijzigingen) niets hebben.
2. **Paging enkel op leden + e-mails**, elk met een éigen knopstijl; de rest laadt
   alles.
3. **Succes-feedback willekeurig**: groene banner / groene tekst / `alert()` /
   transient ✓ / niets (paginas, gebruikers, activiteiten, ideeën).
4. **Fouten stil ingeslikt** op de zwaarste pagina: leden (en dashboard) vangen
   álle API-fouten met `.catch(()=>{})`.
5. **Drie fout-stijlen** (rode banner, inline rode tekst, `alert()`) — soms binnen
   één pagina.
6. **Create-knop onvoorspelbaar**: mét/zonder "+", `btn-sm` of niet, in de kop, in
   een subsectie, of afwezig.
7. **Drie herorden-glyphs** voor dezelfde handeling: ▲▼ (activiteiten), ◀▶
   (media), ↑↓ (formulieren).
8. **Rij-acties**: boxed knoppen vs tekstlinks vs 🗑️-emoji; Verwijderen soms
   laatst-rood, soms verstopt.
9. **Tien verwijder-bevestigingen** in drie taalvormen; enkel betalingen/import
   leggen het gevolg uit.
10. **Opslaan heet ook "Bewaar" en "Toevoegen"**; Annuleren staat meestal rechts
    maar in de formulieren-editor links.

Kleiner maar reëel: titelkleur wisselt (`blue-800`/`blue-900`/`gray-900`),
badge-geel vs -amber door elkaar, e-mail-statusbadge toont rauwe code i.p.v. NL,
leeg-teksten wisselen tussen "Geen …" en "Nog geen …" en tussen italic en niet.

---

## 2. SOLL — de conventies

### 2.1 Paginakop
- `<h1>` met `text-blue-700` (de merkblauw-token, §0), gevolgd door een optionele
  grijze subtitel-regel.
- **Primaire actie rechtsboven**: `btn-primary btn-sm`, label **"+ Nieuwe <item>"**
  (mét plus, mét btn-sm — geen uitzonderingen). Read-only pagina's hebben geen
  create-knop; een create in een subcontext (bv. "+ Persoon" per gezin) mag
  *náást* maar vervangt nooit de kopconventie.

### 2.2 Lijstweergave
- **Standaard = tabel** (DataTable) voor records; kaarten enkel voor hiërarchische
  of visuele inhoud (zie §3). Tabelkop: `text-left text-gray-500 border-b`.
- Elke tabel in een `card` met `overflow-x-auto` (mobiel).

### 2.3 Zoeken
- **Elke lijst die kan groeien krijgt een zoekveld** (vuistregel: >20 items
  mogelijk). Referentie-implementatie = leden: `type="search"`, placeholder
  **"Zoek op <velden>…"**, server-side, debounce 250 ms, geen aparte Zoek-knop.
- Filters (status-pills, dropdowns) staan links van/onder het zoekveld, in één
  filterbalk boven de lijst.

### 2.4 Sortering & handmatig herordenen
- Kolomsortering pas met de DataTable (kolomklik); tot dan vaste, gedocumenteerde
  volgorde (nieuwste eerst voor logs, alfabetisch/sort_order voor beheer).
- **Handmatig herordenen = één component** (`ReorderButtons`): glyphs **▲▼** voor
  verticale lijsten, **◀▶** voor grids — richting volgt de layout, stijl is
  identiek.

### 2.5 Paging
- **Server-side, 50/pagina**, zodra een lijst kan groeien. Eén Pager-component,
  e-mails-stijl: `btn-secondary btn-sm` "Vorige" / "Volgende" + "pagina x / y".

### 2.6 Rij-acties
- **Lijstschermen (herhalende rijen):** houd de rij scanbaar — toon **2–3 acties
  zichtbaar** en laat de rest overlopen naar een **"⋯"-menu** (`row_actions`, param
  `max_visible`, default 2). Dit is een **richtlijn, geen harde grens**: bij weinig
  rijen op een breed scherm mag alles inline.
- **Detailschermen / toolbars:** **geen cap** — een detail-kop met zijn hoofdacties
  mag ze gewoon inline tonen (dan gebruik je `row_actions` niet, of `max_visible` hoog).
  Een ⋯-menu dat maar één actie verbergt is slechter dan alles tonen.
- **Verwijderen: altijd laatst, altijd rood** (`text-red-600`), in het ⋯-menu
  zodra dat bestaat. Nooit een emoji, nooit verstopt — indien niet toegestaan
  (bv. geld bewoog): tonen maar disabled met tooltip-reden.
- **Symbool-knoppen** (×, ⚙, …) krijgen altijd een `aria-label` (screenreader).

### 2.7 Verwijderen (bevestiging)
- Eén `ConfirmDialog` met vaste template, infinitief + objectnaam:
  **«<Type> "<naam>" definitief verwijderen?»** + één gevolg-regel waar relevant
  («Alle inzendingen worden mee verwijderd.» / «Het feit blijft in de
  audit-historie bewaard.»). Knop in de dialog: rood "Definitief verwijderen",
  secundair "Annuleren".

### 2.8 Formulieren (create/edit)
- **Klein** (≤ ~8 velden): inline `card` bovenaan de lijst. **Groot** (builders):
  aparte view. Modals enkel voor read-only detail (e-mailpreview) — niet voor
  bewerken.
- Knoppen **onderaan links**, vaste volgorde: **[Opslaan] [Annuleren]**
  (`btn-primary` / `btn-secondary`). Label is altijd **"Opslaan"** — nooit
  "Bewaar"; "Toevoegen" mag enkel op een sub-item-form dat direct toevoegt.
  Uitzondering: onomkeerbare wizard-commits benoemen het gevolg ("Definitief
  importeren").

### 2.9 Feedback
- **Fout**: altijd `parseApiError` → **rode banner** (`bg-red-50 text-red-700
  rounded-lg p-3`) bovenaan de pagina of het formulier. Nooit `alert()`.
- **Succes**: **toast** "Opgeslagen ✓" (tot de toast bestaat: transient groene
  notice, betalingen-stijl). Elke mutatie geeft feedback — "gewoon herladen" is
  geen feedback.
- **Verboden**: `.catch(()=>{})` — elke load/save-fout is zichtbaar.

### 2.10 Badges & kleuren (semantisch, altijd NL-label)
Eén `<Badge>`-component; pill `px-2 py-0.5 rounded-full text-xs font-semibold`.

| Betekenis | Kleur | Voorbeelden |
|---|---|---|
| ok / actief / betaald / behandeld | groen (`green-100/800`) | Open, Betaald, ✓ Behandeld |
| in behandeling / wachtend | **geel** (`yellow-100/800`) — amber vervalt | Openstaand, Gewijzigd |
| fout / verwijderd / vol | rood (`red-100/800`) | Mislukt, Verwijderd |
| concept / inactief / uit | grijs (`gray-100/600`) | Concept, Overgeslagen |
| info / rol | blauw (`blue-100` bg / `blue-700` tekst) | ADMIN, FINANCE |

### 2.11 Laden & leeg
- Laden: uniform **"Laden…"** via één `<Loading>`-component (vaste hoogte, geen
  layout-sprong).
- Leeg: **"Geen <items> gevonden."** na zoeken/filteren; **"Nog geen <items>."**
  als er nooit iets was. Niet italic; via één `<Empty>`-component.

### 2.12 Terminologie (vast)
Opslaan · Annuleren · Bewerken · Verwijderen · "+ Nieuwe <item>" ·
"Zoek op <velden>…" · Vorige/Volgende · "Laden…" · "(Nog) geen <items>…".
Titels en badges altijd Nederlands; nooit rauwe statuscodes tonen.

---

## 3. Gesanctioneerde uitzonderingen
- **leden**: master-detail (gezinnenlijst + detail) — blijft; krijgt wel de
  standaard zoek/paging/feedback.
- **media**: thumbnail-grid + ◀▶ (grid-richting) — blijft; upload-feedback via
  banner/toast i.p.v. `alert()`.
- **leden-import**: twee-staps wizard (droogloop → commit) — blijft, incl.
  expliciet commit-label.
- **paginas**: TipTap-editor — blijft.
- **activiteiten**: geneste kaarten (activiteit → datums/onderdelen → producten) —
  kaartvorm blijft, maar acties/glyphs/feedback volgen §2.
- **Read-only pagina's** (dashboard, analyse, info, ledenwijzigingen): geen
  create; verder gewone conventies.

---

## 4. Kluslijst per pagina (IST → SOLL)

| Pagina | Aanpassen |
|---|---|
| **dashboard** | fouten niet meer stil (`.catch(()=>{})` weg) |
| **activiteiten** | 🗑️-emoji → rode tekstlink laatst; `alert()` → banner/toast; ⋯-menu bij >2 acties; zoekveld; succes-toast |
| **leden** | `.catch(()=>{})` weg → banners; "Toevoegen" ok (sub-item) maar hoofdedits "Opslaan"; paging-knoppen → Pager-stijl |
| **leden-import** | conform (wizard-uitzondering); banners al goed |
| **paginas** | succes-toast na opslaan; verwijder-tekst naar template |
| **media** | Verwijderen als nette actie (geen `ml-auto`-linkje); `alert()` weg; ◀▶ via ReorderButtons |
| **ai-context** | "Bewaar" → "Opslaan"; "Sluiten ✕" → "Annuleren"; Verwijder-positie laatst |
| **ideeen** | Verwijderen als losse laatste actie; succes-feedback |
| **formulieren** | kop-knop → "+ Nieuw formulier"; rij-acties → 2 + ⋯-menu; `alert()` → toast; Opslaan/Annuleren-volgorde omdraaien (editor-kop); ↑↓ → ReorderButtons |
| **emails** | statusbadge NL-labels i.p.v. rauwe code; zoekveld zonder aparte knop (debounce) |
| **betalingen** | zoekveld + paging; titel `text-blue-700` (§0); disabled-verwijderen met reden i.p.v. verbergen; geel i.p.v. amber |
| **gebruikers** | kop: `h1 text-blue-700` (§0) + `btn-sm`; rij-acties normale maat; "Actief" als Badge; succes-toast |
| **ledenwijzigingen** | titel `text-blue-700` (§0); `alert()` bij download → banner |
| **analyse / info** | titelkleur; verder conform (read-only) |

---

## 5. Koppeling met de UI-kit (architectuurdoc §11, F-blok)
De conventies hierboven zíjn de specificatie van de kit:
`PageHeader` · `DataTable` · `SearchInput` · `Pager` · `ReorderButtons` ·
`RowActions` (+ ⋯-menu) · `ConfirmDialog` · `Toast` · `Badge` · `Loading` /
`Empty` · `FormActions` (Opslaan/Annuleren). Elke component één keer gebouwd =
elke pagina die hem adopteert automatisch conform. De kluslijst (§4) is dan per
pagina grotendeels "vervang lokaal patroon door kit-component".

### 5.1 De kit in Jinja — `_macros.html` (stand v2.0.0)

Importeer met `{% import "_macros.html" as ui %}`. Beschikbaar:

| Groep | Macro's |
|---|---|
| Structuur | `page_header` · `section_header` · `section_bar` · `card` · `nested_panel` · `tabs` · `detail_disclosure` |
| Lijsten | `search` · `filter_bar` · `grouped_filter` · `pager` · `row_actions` · `reorder` · `empty_state` · `loading` |
| Formulieren | `field_input` · `field_select` · `field_textarea` · `label` · `person_fields` · `export_links` |
| Feedback | `toast` · `toast_host` · `success_banner` · `error_banner` · `modal` · `badge` |
| Knoppen | `btn_primary` · `btn_secondary` · `btn_outline` · `btn_danger` · `button` · `btn_class` |

Drie daarvan zijn nieuw in v2.0.0 (#528 as C) en verdienen toelichting:

**`ui.search(hx_get, hx_target, value="", name="q", placeholder="Zoeken…")`** —
zoekveld voor elke groeibare lijst. Debounce van 300 ms, zodat htmx niet per
aanslag een verzoek doet. De parameter heet standaard `q`, zodat de serverkant
overal dezelfde naam leest.

**`ui.pager(page, per_page=…, total=…, …)`** — toont "x–y van n" met
vorige/volgende. Bewust géén paginanummers: bij een groeiende lijst zegt een reeks
knoppen weinig en breekt ze op mobiel. Verbergt zichzelf als alles op één pagina
past, zodat een lijst met drie rijen geen navigatie krijgt.

Twee modi. **Mét `total`** leidt hij zelf af of er nog een pagina is. **Zonder
totaal** geef je `has_prev`/`has_next` mee en toont hij enkel "Pagina n" — voor
lijsten die bewust geen `COUNT` doen maar één rij extra ophalen, zoals het
e-maillog. Een `COUNT` afdwingen zou die optimalisatie slopen voor een cijfertje.

**`ui.filter_bar(hx_get, hx_target)`** — call-macro die zoekveld én filters in
één formulier omhult, zodat htmx alle waarden samen meestuurt en de filter-state
niet uit de pas loopt met de lijst. Gebruik de velden erbinnen met
`standalone=False`, anders doet het zoekveld nog een eigen verzoek en gaan er twee
requests per aanslag uit:

```jinja
{% call ui.filter_bar("/admin/e-maillog/lijst", "#email-log-lijst") %}
  <div>{{ ui.search(value=recipient, name="recipient", standalone=False) }}</div>
  <div class="flex flex-wrap gap-3">…selects…</div>
{% endcall %}
```

### 5.2 Lijst-index — vaste volgorde (design-system C1)

Elk beheerscherm met records heeft dezelfde volgorde in de inhoudskolom, van
boven naar onder: **paginatitel → "+ Nieuwe …" → zoeken → filters → record-kaarten.**

Twee expliciete correcties op wat HDEV toonde:

- De "+ Nieuwe …"-knop staat **los**, niet in een `bg-blue-50`-blok met een
  uitklapformulier eronder. Het aanmaakformulier opent in een `ui.modal()` (of als
  paginabrede editor).
- Filters staan **altijd onder** "Nieuwe" en het zoekveld, nooit erboven.

**`ui.toast(message, kind="success", timeout=4000)`** — hét bevestigingspatroon;
`alert()` is verboden (§2.9) en de lint-gate keurt het af. Rendert als los
fragment, dus een htmx-antwoord kan hem out-of-band meesturen:

```html
<div hx-swap-oob="afterbegin:#toasts">{{ ui.toast(_("Opgeslagen")) }}</div>
```

`ui.toast_host()` staat al in `site_base.html` en `admin_base.html`; die hoef je
niet zelf te plaatsen. Een `kind="error"` verdwijnt **niet** vanzelf — een fout
wil je niet missen — de andere soorten na `timeout` ms.

---

# Deel B — Publieke site & ledenportaal

## B1. IST — de tien grootste inconsistenties (op bezoeker-impact)

1. **De kernactie "Inschrijven" oogt het zwakst**: in de activiteitenlijst is het
   een klein `text-xs`-bordje, terwijl "Word lid"/"Contacteer ons" volle
   `btn-primary`-knoppen zijn.
2. **Verplicht-markering twee stijlen**: rode `*` (DynamicForm) vs kleurloze `*`
   in de labeltekst (inschrijven/gezin/idee).
3. **Foutweergave drie vormen**: kale rode tekst / rode banner / `alert()`
   (ledenportaal-gezin).
4. **Modal-sluitgebaren inconsistent**: RegistrationForm alleen via "Annuleren"
   (geen X/Esc/backdrop); PhotoGallery wél backdrop + X.
5. **`/betaling/geannuleerd` linkt naar `/word-lid` — die route bestaat niet
   (404)**; bovendien verkeerd voor wie via een activiteit kwam. *(bug, geen
   stijl)*
6. **Betaalmethode-codes verschillen per flow** (`ONLINE`/`OVERSCHRIJVING` vs
   `online`/`transfer`) — backend vertaalt correct, maar één vocabulaire is het
   niet.
7. **Prijsweergave gefragmenteerd**: `money.ts` wordt publiek niet gebruikt;
   RegistrationForm heeft een eigen `formatPrice`, elders rauwe `€…toFixed(2)`.
8. **Geen actieve-link-markering in de navigatie.**
9. **Succesfeedback wisselt**: verdwijnende banner (5 s, homepage) vs blijvend
   bedankscherm (gezin/idee/formulier).
10. **Wizard vs one-page** voor vergelijkbare meerstaps-invoer (DynamicForm-wizard
    vs FamilyRegistrationForm-scrollpagina).

Kleiner: "Bezig…" grotendeels uniform maar gezin zegt "Bewaren…" en
OrderLineEditor wisselt niet; laden-teksten wisselen ("Activiteiten laden…" vs
"Laden…"); leeg-teksten deels italic.

## B2. SOLL — de conventies

1. **CTA-hiërarchie**: de kernactie van een pagina is altijd `btn-primary`
   (`btn-sm` in lijstcontext) — de Inschrijven-knop in de activiteitenlijst wordt
   dus een echte knop. Secundair = `btn-secondary`; ternair (Info ↗, Wie doet er
   mee?) mag tekstlink blijven.
2. **Verplicht = rode `*`** (`<span class="text-red-600">*</span>`) overal —
   DynamicForm-stijl wint.
3. **Fouten**: rode banner (`bg-red-50 text-red-700 rounded-lg p-3`) boven het
   formulier, via `parseApiError`. `alert()`/`confirm()` ook publiek verboden;
   het ledenportaal gebruikt dezelfde ConfirmDialog als de admin.
4. **Succes**: one-shot captures (lid worden, formulier, idee) → **blijvend
   bedankscherm** dat het formulier vervangt, patroon: «✅ <wat> ontvangen!» +
   wat volgt («Je ontvangt een bevestiging per e-mail…»). Kleine acties → toast.
   De homepage-inschrijfflow volgt dus het bedankscherm, niet de 5s-banner.
5. **Bezig-states**: submitknop disabled + label **"Bezig…"** — overal, ook
   ledenportaal en OrderLineEditor.
6. **Modals**: dezelfde `<Modal>` als de admin (X + Esc + backdrop, `role=dialog`).
7. **Betaalflow**: geannuleerd → **terug naar de bron** (of `/` als die onbekend
   is) — nooit naar een niet-bestaande route; succes → `/` blijft. Widget-teksten
   uniform: online = redirect-uitleg, overschrijving = «rekeninggegevens per
   e-mail».
8. **Betaalmethode-vocabulaire**: één set codes over alle flows (voorstel:
   backend-canoniek `online`/`transfer`, frontend-labels "Online betalen"/
   "Overschrijving") — opruimen bij de htmx-omklap van de betrokken schermen
   (de TS-codegen uit §19.4 is geschrapt; het machinecontract-schema borgt de
   canonieke codes).
9. **Prijs**: álle prijsweergave via `money.ts` (`formatPrice` daarheen
   verhuizen/uitbreiden met "gratis" + ledenprijs-variant); nergens rauwe
   `toFixed(2)`.
10. **Navigatie**: actieve link gemarkeerd (onderstreping of vaste achtergrond);
    hamburger-gedrag blijft.
11. **Wizard-regel**: wizard enkel bij secties/branching (DynamicForm — is al zo);
    korte captures = one-page met secties. FamilyRegistrationForm blijft one-page
    (gesanctioneerd), maar met de veld-/fout-/succes-patronen hierboven.
12. **Toon & microcopy**: je/jij (bevestigd, is al consistent); sentence case;
    één fouttekst-fallback: «Er is iets misgelopen. Probeer opnieuw.»; laden =
    "Laden…", leeg = "(Nog) geen <items>…" — zelfde regels als Deel A §2.11/2.12.
13. **De kernactie van een activiteit heet "Inschrijven"** — op de kaartknop, in de
    modaltitel én op de submit. Niet "Schrijf je in": dat leest rommelig onder een
    titel die al "Inschrijven — <onderdeel>" zegt, het is de PROD-taal uit v1.14, en
    de foutteksten in `messages.po` gebruiken hetzelfde woord. Het design-system
    toonde tot september 2026 "Schrijf je in" in referentiescherm B1; die mock is
    rechtgezet, de code was al juist.

## B3. Gesanctioneerde uitzonderingen
- **FamilyRegistrationForm** one-page (geen wizard) — bewust.
- **ChatWidget**: eigen compacte stijl (zwevend paneel), maar kit-kleuren en
  dezelfde fouttekst-fallback.
- **PhotoGallery-lightbox**: donkere overlay (`bg-black/80`) mag afwijken; krijgt
  wel Esc.
- **Login**: gedeeld leden/admin-scherm met privacy-neutrale copy — blijft.

## B4. Kluslijst publiek

| Waar | Aanpassen |
|---|---|
| **betaling/geannuleerd** | ⚠ link `/word-lid` (404!) → bron of `/`; tekst uniformeren — *kandidaat v1.14* |
| **ActivityList** | Inschrijven → `btn-primary btn-sm`; leeg-teksten de-italiceren; **"Wie doet er mee?" = compacte inline regel** *N ingeschreven — naam · naam · …* (geen verticale lijst), **klein/gedempt** `text-xs text-gray-600` (telkop `font-medium`) — PROD v1.14-pariteit (#601) |
| **RegistrationForm** | **inschrijven opent als smalle popup/modal** (max-w-md, ×/Esc/backdrop) — nooit een inline getint blok dat de kaart verbreedt (#601); rode `*`; banner i.p.v. kale tekst; eigen `formatPrice` → `money.ts` |
| **FamilyRegistrationForm** | rode `*`; succes-tekstpatroon; codes → canoniek |
| **homepage** | 5s-banner → bedankscherm-patroon |
| **leden/gezin** | `alert()`/`confirm()` → banner/ConfirmDialog; "Bewaren…" → "Bezig…" |
| **OrderLineEditor** | knoppen → kit-stijl; "Bezig…"-state; prijs via `money.ts` |
| **IdeaBox / PersonFields / AddressFields** | rode `*` |
| **Navigation** | actieve-link-markering |
| **ChatWidget / login** | fouttekst-fallback uniform |

## B5. Relatie met Deel A
Dezelfde UI-kit bedient beide werelden: `Modal`, `ConfirmDialog`, `Toast`,
`Badge`, `Loading`/`Empty`, `FormActions` en de token-set zijn gedeeld; publiek
komt daar het **Public-capture-sjabloon** bij (architectuurdoc §11): veldenset →
gevalideerde submit → bedankscherm (+ evt. capability-link). Consistentie tussen
publiek en admin is geen luxe: de vrijwilliger die beide kanten gebruikt, leert
één interactietaal.

---

## Conventie: tenant-branding vs. vaste content-slugs (#493/#519)

Twee soorten "waar komt deze content vandaan", bewust verschillend behandeld:

- **Tenant-branding = config, GEEN hardgecodeerde default.** `site_tagline`,
  `facebook_url` (en `instagram_url`/`tiktok_url`/`privacy_url`) komen uit de
  tenant-settings (`get_setting`). Er is **geen** afdelingsspecifieke fallback:
  leeg = niet tonen. Millegem-waarden als default lieten die branding naar andere
  tenants lekken (multi-tenancy-fout, #519). Elke tenant zet zijn eigen waarden
  via de instellingen-UI (#453); de footer/hero tonen een element enkel als het
  gezet is (`{% if facebook_url %}`, `{% if site_tagline %}`).
- **Vaste inline-content = slug-conventie, geen pointer.** De site-footer en de
  home-intro zijn *inline CMS-content op exact één vaste plek*. Die worden
  geadresseerd via een **vaste slug** (`site-footer`, `home-intro`) — de content
  is per-tenant bewerkbaar via de CMS-editor (#457), enkel de slug-*naam* ligt
  vast. Dit is bewust **geen** configureerbare pointer (in tegenstelling tot de
  privacy-**link** van #493, die logisch naar een te kiezen pagina wijst): voor
  content met één natuurlijke plek is een conventie eenvoudiger dan config.

---

## CMS-editor: Trix (self-hosted, #520)

De CMS-pagina-editor gebruikt **Trix** (37signals, MIT) i.p.v. het deprecated
`document.execCommand`. **Europe-First-afweging:** Trix is een *client-side,
open-source* library die we **self-hosted vendoren** onder
`backend/app/static/vendor/` (`trix.min.js` + `trix.css`) — geen CDN, geen
externe dienst, **geen data die de EU verlaat** (alle bewerking gebeurt in de
browser; opslaan gaat naar onze eigen backend). Daarmee voldoet het aan Europe
First: een lokaal gevendorde lib zonder data-egress is EU-proof, ongeacht de
herkomst van de code. Nul-Node: we committen het vooraf-gebouwde bestand, geen
`npm`-build.

- Geladen op paginaniveau in `admin_paginas.html` (CSP `default-src 'self'` dekt
  `/static/...`; `script-src` heeft al `'unsafe-inline'`/`'unsafe-eval'` voor
  Alpine, dus **geen nonce nodig**).
- Bestandsbijlagen zijn **uitgeschakeld** (`trix-file-accept` → `preventDefault`,
  attach-knop verborgen): afbeeldingen via de media-component zijn aparte scope
  (#459). Zonder upload-hook zouden ze data-URI's worden die de sanitisatie toch
  strippen.
- De opgeslagen HTML wordt **server-side gesanitiseerd** (nh3-allowlist in
  `cms/render.py`, #476) op élk publiek renderpunt — de XSS-guard staat los van de
  editorkeuze en dekt ook Trix-output (regressietest in `test_cms_sanitize.py`).

---

## Filterbalk-conventie: één gegroepeerde dropdown (#549)

De **canonieke filtervorm voor een hiërarchische as** (categorie → subtype) is
**één gegroepeerde `<select>`** met een `<optgroup>` per categorie ("Alle <cat>" +
de subtypes), niet twee losse velden. Geïmplementeerd als de gedeelde macro
**`grouped_filter(name, top_options, groups, current, hx_get, hx_target)`** in
`_macros.html`, gebruikt door **Werkbank** (`kind`, categorie→subtype) én
**Betalingen** (`context`, heterogene groepen jaar/onderdeel). Zo kan de
visualisatie niet meer per scherm uiteenlopen.

- **Eén waarde encodeert beide niveaus.** Werkbank: `membership` = hele categorie
  (prefix-match), `membership.reminder` = exact. Betalingen: `membership` /
  `year-2026` / `comp-5`.
- **Wanneer wél losse velden?** Enkel voor **onafhankelijke assen** (bv. bij
  Betalingen staat de `status`-filter náást de gegroepeerde `context` — dat zijn
  twee orthogonale dimensies). Een hiërarchische categorie→subtype is altijd één
  gegroepeerde dropdown.
- **hx-gedrag.** Staat de select los, geef dan `hx_get`/`hx_target` aan de macro;
  zit hij in een omhullende `<form hx-get … hx-trigger="change">`, laat de hx-*
  weg (de form vangt de change). De polling draagt de filter mee via
  `hx-include="[name='<name>']"`.

---

## Record-detail/editor-conventie (#510)

Waar een lijst **concrete records** toont (inschrijvingen, betalingen, leden,
producten) geldt één patroon: **toon → in-lijn bewerken**, met gedeelde macro's zodat
adopteren = automatisch conform.

- **Rij-acties** via `row_actions(actions=[…], delete_attrs=…, delete_label=…, max_visible=2)`
  (design-system §2.4): op lijstrijen **2–3 zichtbaar + ⋯-menu** voor de rest (richtlijn,
  configureerbaar via `max_visible`); detailschermen mogen alles inline tonen. **"Verwijderen"
  staat altijd laatst en rood**. De primaire actie is meestal **"Bewerken"/"Detail"**.
- **"Bewerken" opent de editor in-lijn** via `detail_disclosure(load_url, target_id)`:
  een trigger die het **gedeelde** detailfragment (bv. `_inschrijving_detail.html`)
  één keer via `hx-get` inlaadt in een doel-element — het scherm **herbouwt de editor
  niet zelf**. In een tabel: de trigger in de actie-cel, het doel in een detail-`<tr>`
  binnen dezelfde `<tbody x-data="{ open: false }">`.
- **Binnen de editor**: `[Opslaan/Bewaar] [Annuleren]` onderaan, **Verwijderen**
  laatst/rood; de **server herberekent** afgeleide waarden (totaal) — nooit client-side.

**Kluslijst (adopteren van het patroon):** ✅ activiteiten-inschrijvingen (#510);
betalingen (deels — "Toon inschrijvingsdetails" gebruikt al `detail_disclosure`-gedrag);
leden-detail (via #503); producten (#507/#509).
