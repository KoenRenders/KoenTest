# Seed-assets

Statische afbeeldingen die bij het opstarten van de backend (eenmalig) in de
`media_assets`-tabel geseed worden, zodat elke omgeving (HDEV/UAT/prod) ze
automatisch heeft zonder handmatige upload.

## Sponsorlogo Mona

Zet hier het bestand:

    mona.png

De seed-migratie voegt het toe als sponsor (in de footer) zodra het bestand
aanwezig is en er nog geen sponsor met titel "Mona" bestaat. Ontbreekt het
bestand, dan slaat de migratie het stilletjes over.

> Alleen publieke, niet-vertrouwelijke logo's horen hier. Geen persoonsdata of
> geheimen — deze repo is publiek.
