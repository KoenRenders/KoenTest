# UI-conformiteitsmatrix (#528 as D)

SOLL versus IST per scherm, gemeten tegen de code — niet geschat. De SOLL staat in
`docs/design-system.html` (de mock) en `docs/ui-conventies.md`; deze matrix zegt
waar de code daar vandaag staat.

**Bewaakt door `backend/tests/test_ui_conventions_gate.py`.** Die test is de reden
dat deze matrix niet veroudert: zakt een kolom terug naar ⚠️, dan valt CI om. De
matrix documenteert, de gate handhaaft.

## Assen

| As | Wat wordt gecontroleerd |
|---|---|
| **Tokens** | Geen `blue-800/900`, geen rauwe hex buiten een `:root`-tokendefinitie, geen `amber-*`. Kleur komt uit `scripts/build-css.sh`. |
| **Kit-macro's** | Aantal verschillende `ui.*()`-macro's dat het scherm gebruikt. Een "—" betekent niet fout: sommige schermen zijn puur inhoud (bv. een CMS-pagina). |
| **Feedback** | Geen `alert()`/`confirm()`. Bevestiging via `ui.modal()`, melding via `ui.toast()`. |
| **Terminologie** | "Opslaan" (niet "Bewaar"/"Toevoegen"), create heet "+ Nieuwe …". |

## Matrix

| Scherm | Tokens | Kit-macro's | Feedback | Terminologie |
|---|---|---|---|---|
| `activiteiten.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `admin_activiteiten.html` | ✅ | ✅ 7 | ✅ | ✅ |
| `aanmelden.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `admin_gebruikers.html` | ✅ | ✅ 7 | ✅ | ✅ |
| `ai_context.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `raakje.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `admin_paginas.html` | ✅ | ✅ 7 | ✅ | ✅ |
| `admin_pagina.html` | ✅ | — | ✅ | ✅ |
| `betaling_resultaat.html` | ✅ | ✅ 2 | ✅ | ✅ |
| `cms_pagina.html` | ✅ | — | ✅ | ✅ |
| `home.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `admin_formulier_builder.html` | ✅ | — | ✅ | ✅ |
| `admin_formulieren.html` | ✅ | ✅ 7 | ✅ | ✅ |
| `berichten.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `formulier.html` | ✅ | ✅ 4 | ✅ | ✅ |
| `formulier_klaar.html` | ✅ | ✅ 2 | ✅ | ✅ |
| `email_log.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `leden.html` | ✅ | ✅ 8 | ✅ | ✅ |
| `leden_gezin.html` | ✅ | — | ✅ | ✅ |
| `leden_import.html` | ✅ | ✅ 5 | ✅ | ✅ |
| `admin_media.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `fotos.html` | ✅ | — | ✅ | ✅ |
| `fotos_album.html` | ✅ | — | ✅ | ✅ |
| `gezin_portaal.html` | ✅ | ✅ 8 | ✅ | ✅ |
| `lid_worden.html` | ✅ | ✅ 6 | ✅ | ✅ |
| `lid_worden_klaar.html` | ✅ | ✅ 2 | ✅ | ✅ |
| `login_verlopen.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `betalingen.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `werkbank.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `werkbank_taak.html` | ✅ | — | ✅ | ✅ |
| `admin_dashboard.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `admin_info.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `admin_ledenwijzigingen.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `admin_activiteit.html` | ✅ | — | ✅ | ✅ |
| `admin_tenant.html` | ✅ | ✅ 7 | ✅ | ✅ |
| `admin_tenants.html` | ✅ | ✅ 8 | ✅ | ✅ |

41 schermen, 37 fragmenten. Nul afwijkingen.

## Kluslijst — lokaal patroon → kit-macro

**Leeg** (#580 afgewerkt). Wat er is omgezet:

| Scherm | Was | Nu |
|---|---|---|
| `leden.html` | eigen zoekveld | `ui.search()` |
| `_leden_lijst.html` | eigen vorige/volgende-knoppen | `ui.pager()` met "x–y van n" |
| `email_log.html` | rauwe `<h1>` + filterformulier met eigen zoekinput | `ui.page_header()` + `ui.filter_bar()` + `ui.search(standalone=False)` |
| `_email_log_lijst.html` | eigen vorige/volgende-knoppen | `ui.pager()` in de modus zonder totaal |
| `_me_lijst.html` (Media) | filters bóven de actieknop, upload in een `bg-blue-50`-blok | knop los en bovenaan, upload in `ui.modal()` |
| `admin_activiteiten.html`, `_gu_lijst.html`, `admin_paginas.html` | "+ Nieuwe …" in een `bg-blue-50`-blok met uitklapformulier | knop los, formulier in `ui.modal()` |
| `leden.html` (#582) | master-detail, geen KPI's, geen filters, secundaire importknop als enige actie | KPI-rij (incl. "nog niet vernieuwd" met doeljaar), primaire "+ Nieuw lid" + importknop, `ui.search()` + statuschips + data-gedreven lidmaatschapsjaar, kaarten → `leden_gezin.html` |
| `admin_paginas.html` (#587) | secundaire knop, geen zoek/filter, master-detail met Trix op de lijstpagina | primaire knop, `ui.search()` + statuschips, kaarten → `admin_pagina.html` (Trix verhuisde mee) |
| `_me_lijst.html` (#588) | knop + filters in het kaartfragment, geen zoek | kop/knop/filterbalk op de pagina, `ui.search()` + `ui.chips()`; fragment = enkel kaarten, met filterstand in verborgen velden |
| `_gu_lijst.html` (#589) | idem, geen zoek of rolfilter | idem, plus filter op rol en actief-status |
| `admin_ledenwijzigingen.html` (#590) | losse "Toon"-knop, "Actor (e-mail)" als gewoon veld | live filteren via `ui.filter_bar()`, actor als `ui.search()`, export als secundaire kit-knop bij de titel |
| `admin_tenants.html` (#584) | "+ Nieuwe tenant" secundair (outline) | primaire (blauwe) knop, zoals §3.2 voorschrijft |
| `admin_activiteiten.html` (#586) | scope-chips binnen de smalle master-detail-lijst, geen zoek, secundaire "+ Nieuwe activiteit" | `ui.btn_primary()`, `ui.search()` op titel/locatie + `ui.chips()` in `ui.filter_bar()`, kaarten → paginabrede editor `admin_activiteit.html`; `_aa_lijst.html` verdween |
| `admin_formulieren.html` (#585) | permanent "Nieuw formulier"-veld bovenaan, master-detail-lijst, "Formaat (voor AI)" als losse link, geen zoek/filter | primaire "+ Nieuw formulier" met naam in `ui.modal()`, `ui.search()` + statusfilter in `ui.filter_bar()`, kaarten → paginabrede builder; `_fb_lijst.html` verdween |

**Correctie op de vorige versie van deze lijst.** Daar stonden `formulier.html` en
`fotos_album.html` als "eigen paginering". Dat was fout: die treffers waren een
"Volgende"-knop in een meerstaps publiek formulier en een lightbox-pijl in het
fotoalbum — geen paginering. De lijst was gebaseerd op een te losse zoekopdracht;
bij het uitvoeren van #580 bleken er twee échte pagineringen te zijn (leden en
e-maillog), en één scherm dat níét in de lijst stond maar wel afweek: Media.

## Wat dit niet meet

De gate vangt wat machinaal te zien is. Drie dingen uit het design system blijven
menselijk oordeel en horen bij de HDEV-validatie:

- **Layout en ritme** — geneste kaarten, witruimte, sticky zijbalk (#526).
- **Gedrag** — read↔edit-toggle, htmx-targets, filter-state die met de lijst
  meeloopt.
- **Toegankelijkheid** — focusvolgorde en schermlezer-labels. De gate kijkt naar
  klassen, niet naar wat een gebruiker ervaart.

## Hoe deze matrix opnieuw te maken

De cijfers komen uit een scan over `backend/app/ui/templates/` en
`backend/app/domains/*/templates/`, met dezelfde patronen als de gate. Draai de
gate (`pytest backend/tests/test_ui_conventions_gate.py`) om te bevestigen dat er
niets is teruggezakt; die is autoritatief.
