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
| `admin_activiteiten.html` | ✅ | ✅ 4 | ✅ | ✅ |
| `aanmelden.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `admin_gebruikers.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `ai_context.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `raakje.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `admin_paginas.html` | ✅ | ✅ 4 | ✅ | ✅ |
| `betaling_resultaat.html` | ✅ | ✅ 2 | ✅ | ✅ |
| `cms_pagina.html` | ✅ | — | ✅ | ✅ |
| `home.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `admin_formulier_builder.html` | ✅ | — | ✅ | ✅ |
| `admin_formulieren.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `berichten.html` | ✅ | ✅ 1 | ✅ | ✅ |
| `formulier.html` | ✅ | ✅ 4 | ✅ | ✅ |
| `formulier_klaar.html` | ✅ | ✅ 2 | ✅ | ✅ |
| `email_log.html` | ✅ | — | ✅ | ✅ |
| `leden.html` | ✅ | ✅ 2 | ✅ | ✅ |
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
| `admin_instellingen.html` | ✅ | ✅ 5 | ✅ | ✅ |
| `admin_ledenwijzigingen.html` | ✅ | ✅ 3 | ✅ | ✅ |
| `admin_tenants.html` | ✅ | ✅ 9 | ✅ | ✅ |


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
