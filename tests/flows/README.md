# Flows

Functionele end-to-end stromen over meerdere stappen. Ze schrijven echte
(test)data weg, dus draai ze **enkel op HDEV/UAT, nooit op PROD**.

Elke flow `source`t `../lib.sh` (zelfde beknopte uitvoer) en wordt automatisch
meegenomen door `tests/run-all.sh`.

## Beschikbaar

| Script | Stroom |
|---|---|
| `lidmaatschap.sh` | Publiek lid worden via overschrijving (postcode -> persoon -> lidmaatschap -> betaalrecord). |

## Op termijn

- Activiteit aanmaken (admin) -> publiek inschrijven -> betalen (Mollie test).
  Vereist een admin-token; daarvoor breiden we `lib.sh` later uit met een
  login-helper.
