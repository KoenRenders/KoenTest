# Flows (op termijn)

Functionele end-to-end stromen over meerdere stappen, met een admin-token.
Nog niet ingevuld — dit is de plek waar ze komen.

Geplande flows:
- Activiteit aanmaken (admin) → publiek inschrijven → betalen (Mollie test).
- Lidmaatschap aanmaken → betaalrecord → status.

Elke flow wordt een script dat `../lib.sh` gebruikt (zelfde beknopte uitvoer)
en automatisch meegenomen wordt door `tests/run-all.sh`.
