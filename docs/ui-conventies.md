# UI-conventies — IST en kluslijsten (historisch)

> **De norm staat sinds 9 september 2026 in [`docs/design-system.md`](design-system.md).**
> Alle conventies, gedragsregels en beslissingen die hier stonden zijn daarheen
> verhuisd, in het Engels, met hun issuenummer en hun reden. Dit bestand houdt
> alleen wat géén norm is: de IST-inventarissen van juli 2026 en de kluslijsten
> per pagina. De volledige Nederlandse tekst van vóór de verhuis staat in de
> git-geschiedenis (`git show 31219f31:docs/ui-conventies.md`).
>
> Handhaving en gemeten stand: `backend/tests/test_ui_conventions_gate.py` en
> [`docs/ui-conformiteit.md`](ui-conformiteit.md).

*IST/SOLL* is analistenjargon: **IST** = de huidige, feitelijke toestand;
**SOLL** = de gewenste doeltoestand. De SOLL staat in `design-system.md`; de
kluslijst is telkens het pad van IST naar SOLL, en wordt per scherm uitgevoerd
bij de omklap van dat scherm.

---

# Deel A — Admin

## 1. IST — de tien grootste inconsistenties (juli 2026, op gebruikersimpact)

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

Veel hiervan is intussen opgelost door de kit (v2.0.0); de gemeten stand per
scherm staat in `ui-conformiteit.md`. Wat structureel overblijft — 85 mutaties
zonder bevestiging, zoeken en paging per lijst — zit in #760 en #758.

## 2. Kluslijst per pagina (IST → SOLL)

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
| **betalingen** | zoekveld + paging; titel `text-blue-700`; disabled-verwijderen met reden i.p.v. verbergen; geel i.p.v. amber |
| **gebruikers** | kop: `h1 text-blue-700` + `btn-sm`; rij-acties normale maat; "Actief" als Badge; succes-toast |
| **ledenwijzigingen** | titel `text-blue-700`; `alert()` bij download → banner |
| **analyse / info** | titelkleur; verder conform (read-only) |

**Record-detail/editor-patroon (#510), adoptie:** ✅ activiteiten-inschrijvingen
(#510); betalingen (deels — "Toon inschrijvingsdetails" gebruikt al
`detail_disclosure`-gedrag); leden-detail (via #503); producten (#507/#509).

---

# Deel B — Publieke site & ledenportaal

## B1. IST — de tien grootste inconsistenties (juli 2026, op bezoeker-impact)

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
   `online`/`transfer`).
7. **Prijsweergave gefragmenteerd**: eigen `formatPrice` naast rauwe
   `€…toFixed(2)`.
8. **Geen actieve-link-markering in de navigatie.**
9. **Succesfeedback wisselt**: verdwijnende banner (5 s, homepage) vs blijvend
   bedankscherm (gezin/idee/formulier).
10. **Wizard vs one-page** voor vergelijkbare meerstaps-invoer (DynamicForm-wizard
    vs FamilyRegistrationForm-scrollpagina).

Kleiner: "Bezig…" grotendeels uniform maar gezin zegt "Bewaren…"; laden-teksten
wisselen ("Activiteiten laden…" vs "Laden…"); leeg-teksten deels italic.

## B2. Kluslijst publiek

| Waar | Aanpassen |
|---|---|
| **betaling/geannuleerd** | ⚠ link `/word-lid` (404!) → bron of `/`; tekst uniformeren |
| **ActivityList** | Inschrijven → `btn-primary btn-sm`; leeg-teksten de-italiceren; "Wie doet er mee?" = compacte inline regel (#601) |
| **RegistrationForm** | inschrijven opent als smalle popup/modal (max-w-md, ×/Esc/backdrop) (#601); rode `*`; banner i.p.v. kale tekst |
| **FamilyRegistrationForm** | rode `*`; succes-tekstpatroon; codes → canoniek |
| **homepage** | 5s-banner → bedankscherm-patroon |
| **leden/gezin** | `alert()`/`confirm()` → banner/ConfirmDialog; "Bewaren…" → "Bezig…" |
| **OrderLineEditor** | knoppen → kit-stijl; "Bezig…"-state; prijs via één formatter |
| **IdeaBox / PersonFields / AddressFields** | rode `*` |
| **Navigation** | actieve-link-markering (#608, gedaan) |
| **ChatWidget / login** | fouttekst-fallback uniform |
