# Smoke-tests

Snelle rooktests tegen een **draaiende** omgeving (HDEV/UAT, niet PROD).
Het zijn geen unit tests — ze bevestigen dat de belangrijkste endpoints zich
correct gedragen na een deploy. Geen secrets; alles via publieke endpoints of
een onbevoegde call om afscherming te testen.

## Conventie

- Elk script leest de doel-URL uit de omgevingsvariabele `BASE`.
- Default is `http://localhost:8081` (HDEV's eigen Caddy). Werkt dat niet door
  Caddy's TLS/Host-eisen, gebruik dan het domein:
  `BASE=https://hdev.jouw-domein ./script.sh`.
- Exit-code 0 = alles OK, 1 = er ging iets mis (bruikbaar in CI later).
- Vereist: `curl` en `jq`.

## Draaien

```bash
cd /opt/raakmillegem/hdev/scripts/smoke
BASE=http://localhost:8081 ./betaal-hardening.sh
```

## Beschikbare tests

| Script | Wat het controleert |
|---|---|
| `betaal-hardening.sh` | Product-id-validatie bij inschrijving (vals id -> 400), regressie geldige inschrijving, en dat het refresh-endpoint admin-auth eist. |

## Wat smoke-tests bewust níet doen

Flows die een admin-login of een echte Mollie-betaling vereisen, worden
handmatig getest. Voorbeeld: de *positieve* "Status verversen"-test — doe één
online inschrijving, log in op `/admin/betalingen` en klik bij die betaling op
**Status verversen**; de status moet overeenkomen met wat Mollie toont.
