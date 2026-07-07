# Admin-UI-conventies (stijlgids & interactiepatronen)

> Normatief document voor de admin-GUI. Gebaseerd op een volledige inventaris van
> alle 15 admin-pagina's (juli 2026, file:line-bewijs beschikbaar). Structuur:
> **IST** (wat er nu is, waar het schuurt) → **SOLL** (de conventie) →
> **uitzonderingen** → **kluslijst per pagina**. Uitvoering loopt mee met de
> UI-kit (architectuurdoc §11/§19.6); dit document is de specificatie ervan.

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
- `<h1>` met `text-blue-800`, gevolgd door een optionele grijze subtitel-regel.
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
- In tabellen: **tekstlinks** `text-blue-700 hover:underline`, normale tekstmaat
  (geen `text-xs`), max **2 zichtbaar** + rest in een **"⋯"-menu**.
- **Verwijderen: altijd laatst, altijd rood** (`text-red-600`), in het ⋯-menu
  zodra dat bestaat. Nooit een emoji, nooit verstopt — indien niet toegestaan
  (bv. geld bewoog): tonen maar disabled met tooltip-reden.

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
| info / rol | blauw (`blue-100/800`) | ADMIN, FINANCE |

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
| **betalingen** | zoekveld + paging; titel `text-blue-800`; disabled-verwijderen met reden i.p.v. verbergen; geel i.p.v. amber |
| **gebruikers** | kop: `h1 text-blue-800` + `btn-sm`; rij-acties normale maat; "Actief" als Badge; succes-toast |
| **ledenwijzigingen** | titel `text-blue-800`; `alert()` bij download → banner |
| **analyse / info** | titelkleur; verder conform (read-only) |

---

## 5. Koppeling met de UI-kit (architectuurdoc §11, F-blok)
De conventies hierboven zíjn de specificatie van de kit:
`PageHeader` · `DataTable` · `SearchInput` · `Pager` · `ReorderButtons` ·
`RowActions` (+ ⋯-menu) · `ConfirmDialog` · `Toast` · `Badge` · `Loading` /
`Empty` · `FormActions` (Opslaan/Annuleren). Elke component één keer gebouwd =
elke pagina die hem adopteert automatisch conform. De kluslijst (§4) is dan per
pagina grotendeels "vervang lokaal patroon door kit-component".
