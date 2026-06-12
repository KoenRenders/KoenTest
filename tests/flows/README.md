# Flows

Functionele end-to-end stromen over meerdere stappen. Ze schrijven echte
(test)data weg, dus draai ze **enkel op HDEV/UAT, nooit op PROD**.

Elke flow `source`t `../lib.sh` (zelfde beknopte uitvoer) en wordt automatisch
meegenomen door `tests/run-all.sh`.

## Beschikbaar

| Script | Stroom |
|---|---|
| `lidmaatschap.sh` | Publiek lid worden via overschrijving (postcode -> persoon -> lidmaatschap -> betaalrecord). |
| `activiteit-inschrijving.sh` | Admin maakt een betaalde activiteit (onderdeel + betaald product) en een bezoeker schrijft zich publiek in (activiteit -> onderdeel -> product -> inschrijving -> betaalrecord; totaalbedrag = productprijs). **Vereist `ADMIN_TOKEN`** — zonder token toont de runner deze flow als SKIP. |

## Admin-token (`ADMIN_TOKEN`)

De admin-login is passwordless via een magic-link per mail en dus niet
automatiseerbaar in een script. Flows die admin-rechten nodig hebben lezen
daarom een JWT uit de omgevingsvariabele `ADMIN_TOKEN`:

1. Log in op de admin-GUI (`/admin`).
2. Open de browser-devtools -> Application/Storage -> Local Storage en kopieer
   de waarde van de sleutel `admin_token`.
3. Geef die mee bij het draaien:

   ```bash
   ADMIN_TOKEN=xxx BASE=http://localhost:8081 ./run-all.sh
   ```

Zonder `ADMIN_TOKEN` wordt de flow netjes als **SKIP** getoond i.p.v. te falen.
