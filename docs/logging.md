# Logging

De backend logt naar stdout (zichtbaar via `docker compose logs backend`). Het
niveau is per omgeving instelbaar via `LOG_LEVEL` in het `.env`-bestand.

## Log-levels

Van meest naar minst uitgebreid:

| Niveau | Wanneer verschijnt het? | Typisch gebruik |
|---|---|---|
| **DEBUG** | Alles — elke SQL-query, elk request-detail | Lokaal een specifieke bug uitpluizen. Nooit op PROD: de logs lopen vol. |
| **INFO** | Normale bedrijfsgebeurtenissen + toegangslog (methode, pad, status, duur) | HDEV/UAT om te volgen wat er gebeurt. |
| **WARNING** | Iets onverwachts, maar de app draait door | Mislukte bevestigingsmail, afgehandelde randgevallen. Dit zijn de signalen die we willen analyseren. |
| **ERROR** | Een operatie is mislukt (app crasht niet) | Betaling aanmaken mislukt, e-mailserver onbereikbaar. |
| **CRITICAL** | Fatale fout, app kan niet verder | Momenteel niet actief gebruikt. |

## Niveaus zijn cumulatief (een drempel)

`LOG_LEVEL` zet een **drempel**: je ziet het gekozen niveau **en alles wat
ernstiger is** — niet wat minder ernstig is. Van licht naar zwaar:

```
DEBUG  →  INFO  →  WARNING  →  ERROR  →  CRITICAL
(licht)                                  (zwaar)
```

Hoe lager je de drempel zet, hoe méér je ziet:

| `LOG_LEVEL` | Toont | Verbergt |
|---|---|---|
| `DEBUG` | DEBUG, INFO, WARNING, ERROR, CRITICAL | niets |
| `INFO` | INFO, WARNING, ERROR, CRITICAL | DEBUG |
| `WARNING` | WARNING, ERROR, CRITICAL | DEBUG, INFO |
| `ERROR` | ERROR, CRITICAL | DEBUG, INFO, WARNING |
| `CRITICAL` | CRITICAL | al de rest |

Voorbeeld: met `LOG_LEVEL=INFO` zie je dus óók alle warnings, errors en
critical-meldingen — enkel de DEBUG-ruis blijft verborgen. Met `WARNING`
(de PROD-instelling) mis je geen enkel echt probleem, maar verdwijnt de
routine-INFO uit de log.

## Aanbevolen instelling per omgeving

| Omgeving | `LOG_LEVEL` | Waarom |
|---|---|---|
| DEV / HDEV | `DEBUG` of `INFO` | Volledig zicht op wat er onder de motorkap gebeurt. |
| UAT | `INFO` | Goed evenwicht tussen detail en ruis. |
| PROD | `WARNING` | Alleen echte problemen; geen persoonsgegevens in routineberichten. |

Instellen: verwijder de `#` voor `LOG_LEVEL` in het echte `.env`-bestand
(de `.env.*.example` bevatten de uitgecommentarieerde standaard) en herstart
de stack.

## Wat er gelogd wordt

- **Toegangslog** (vanaf INFO): per request één regel met methode, pad,
  statuscode en duur in ms. Health-checks worden overgeslagen. Bewust **geen**
  query-strings of request-bodies, om persoonsgegevens uit de logs te houden.
- **Onverwerkte fouten**: een globale exception-handler logt elke onverwachte
  500 met volledige traceback (`logger.exception`) en geeft de bezoeker een
  neutrale "Interne serverfout".
- **Afgehandelde randgevallen**: bv. een mislukte bevestigingsmail wordt als
  `WARNING`/`ERROR` gelogd in plaats van stil genegeerd.

## Logs ophalen voor analyse

```bash
sudo docker compose -f docker-compose.hdev.yml --env-file .env.hdev \
  logs backend --since 24h > backend_logs.txt
```

> **Let op — privacy:** productielogs kunnen persoonsgegevens bevatten
> (e-mailadressen, namen). Commit log-bestanden **nooit** naar deze publieke
> repo. Deel ze enkel via een privékanaal.
