# CR-11 — conceptschermen van de eindtoestand

Aangemaakt op 30 september 2026, fase 0 van CR-11 (GUI redesign 2).

Open `index.html` in een browser: de overzichtspagina linkt naar zes
concepten en toont drie ervan in een telefoonkader van 390 px.

| Bestand | Toont |
|---|---|
| `01-lijst-betalingen.html` | de lijstpagina (piloot A): titelrij met tegels, één werkbalkrij, tabel, rij als ingang |
| `02-record-activiteit-lezen.html` | de recordpagina in leesmodus: terugweg, recordkop, samenvatting rechts, tabbladen, elk veld zichtbaar |
| `03-record-activiteit-bewerken.html` | dezelfde pagina als editor: raster, herhalende groepen, ingeklapte externe koppelingen, één actiebalk |
| `04-record-activiteit-betalingen.html` | het tabblad Betalingen: de ingebedde lijst in hetzelfde kader |
| `05-document-vergadering.html` | de documentpagina: leesbreedte, plakkende werkbalk, autosave, Versturen… |
| `06-publiek-inschrijven.html` | de publieke formulierpagina (piloot B): ledenduw, wie · wat · vragen · betalen |

De pagina's laden de echte kit-stylesheet van het portaal
(`backend/app/static/app.css`, relatief vanuit deze map — open ze vanuit
een checkout, dan renderen ze met de echte kleuren en letters; GitHub toont
alleen de bron; en de lettertypes laden alleen achter de draaiende server,
want `app.css` verwijst er absoluut naar — buiten de server vallen de
pagina's terug op het systeemlettertype, wat lichter oogt dan Inter en
Radio Canada Big in het echte portaal); `concept.css` is de laag erbovenop met wat de eindtoestand
nieuw introduceert. Alle namen, initialen en cijfers zijn verzonnen.

Het ontwerp waar deze schermen bij horen: `docs/design-system-end-state.md`
in de repo; de pijnen die ze beantwoorden: CR-11 A2 (de rijnummers staan
onderaan elk scherm).
