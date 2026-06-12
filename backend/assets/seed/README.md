# Seed-assets

Statische afbeeldingen die bij het opstarten van de backend (eenmalig) in de
`media_assets`-tabel geseed worden, zodat elke omgeving (HDEV/UAT/prod) ze
automatisch heeft zonder handmatige upload.

## Sponsorlogo Mona

Bestand: `mona.jpg` (JPG of PNG mag; PNG met transparantie geeft het mooiste
resultaat in de footer).

`seed_sponsors.py` (aangeroepen vanuit `startup.sh`) voegt het toe als sponsor
in de footer zodra het bestand aanwezig is en er nog geen sponsor met titel
"Mona" bestaat. Ontbreekt het bestand, dan wordt het stilletjes overgeslagen.
Wil je een ander bestand gebruiken, pas dan de `SPONSORS`-lijst in
`seed_sponsors.py` aan.

> Alleen publieke, niet-vertrouwelijke logo's horen hier. Geen persoonsdata of
> geheimen — deze repo is publiek.
