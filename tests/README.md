# Tests

Een groeiende testset tegen een **draaiende** omgeving (HDEV/UAT, niet PROD).
Bedoeld om dingen te bewaken die je niet (vlot) via de GUI kunt nagaan, en om
regressies te vangen. Geen secrets; alles via publieke endpoints of een
onbevoegde call om afscherming te testen.

## Structuur

```
tests/
├── lib.sh        Gedeelde helpers — stil bij succes, gericht bij falen.
├── run-all.sh    Draait alles en toont één beknopt overzicht.
├── smoke/        Korte checks tegen een live stack (na een deploy).
└── flows/        Functionele end-to-end stromen (op termijn).
```

## Draaien

```bash
cd /opt/raakmillegem/hdev/tests
BASE=http://localhost:8081 ./run-all.sh
```

Werkt `localhost:8081` niet door Caddy's TLS/Host-eisen, gebruik dan het
domein: `BASE=https://hdev.jouw-domein ./run-all.sh`.

## Uitvoer

Per test één regel: `PASS` / `FAIL` / `SKIP`. Bij `FAIL` of `SKIP` toont de
runner onderaan, onder **"Te behartigen"**, enkel de uitvoer van díe test —
geen muur van geslaagde checks om één probleem te vinden. Exit-code 0 = alles
OK, 1 = minstens één test faalde (bruikbaar in scripts/CI later).

## Beschikbare tests

### smoke/ — korte checks, geen neveneffecten

| Script | Wat het controleert |
|---|---|
| `betaling-veiligheid.sh` | Vals `product_id` -> 400 "Ongeldig product"; refresh-endpoint eist admin-auth. |
| `rate-limiting.sh` | Login-limiter geeft 429 na te veel pogingen per minuut. |
| `input-validatie.sh` | Ongeldig e-mailadres -> 422; negatief en absurd hoog aantal -> 400. |

### flows/ — functionele stromen

| Script | Wat het controleert |
|---|---|
| `lidmaatschap.sh` | Publiek lid worden via overschrijving: postcode -> persoon -> lidmaatschap -> betaalrecord. Status `registered`, lidgeld > 0. |

> **Let op:** flows schrijven echte (test)data weg (bv. een testlid). Draai ze
> enkel op HDEV/UAT, **nooit op PROD**. Op HDEV is dat geen probleem; je kunt de
> omgeving altijd opnieuw opzetten.

## Afspraken

- Elk script `source`t `../lib.sh` en eindigt met `t_summary` voor uniforme,
  beknopte uitvoer.
- Elk script begint met `DESC="…"` — één Nederlandse zin die zegt wat het
  garandeert. `run-all.sh` toont die zin in het overzicht, zodat je in één
  oogopslag leest wat er getest is (niet enkel een bestandsnaam).
- Comments en omschrijvingen in het Nederlands (nl-BE), zoals de rest van de code.
- Doel-URL via `BASE` (default `http://localhost:8081`).
- Exit: 0 = OK, 1 = check gefaald, 2 = kon niet draaien (setup).
- Een nieuw script in `smoke/` of `flows/` wordt automatisch meegenomen door
  `run-all.sh` — niets te registreren.
- Geen secrets; gebruik `example.com`-adressen.
- Vereist op de server: `curl` en `jq`.

## Niet via een script

Flows die een echte betaling of admin-login vereisen, test je handmatig.
Voorbeeld — de positieve "Status verversen": doe één online inschrijving, log
in op `/admin/betalingen` en klik bij die betaling op **Status verversen**;
de status moet overeenkomen met wat Mollie toont.
