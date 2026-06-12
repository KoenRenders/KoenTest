# Tests

Drie lagen, elk met een eigen scope en trigger. Alles zit in submappen hier.

## Structuur

```
tests/
├── unit/          Pytest — pure functies, geen netwerk of DB. Draait bij elke build.
├── integration/   Pytest + test-DB — endpoints in-proces. Draait in CI.
└── smoke/         Curl-scripts tegen een draaiende omgeving — na een deploy.
```

## Lagen

### unit/
Pure functies geïsoleerd van I/O. Geen Caddy, geen DB, geen Mollie.
Draait automatisch bij elke Docker-build (backend Dockerfile).
Als dit faalt, faalt de build — snelste vangnet.

**Wat er in hoort:** prijsberekening, validatielogica, statusmapping, helpers.

### integration/
Backend + test-DB samen, endpoints in-proces via FastAPI's TestClient.
Draait in CI (GitHub Actions) bij elke push.
Vereist: een `test`-variant van de Docker-stack of een ephemere test-DB.

**Wat er in hoort:** endpoint-gedrag end-to-end, betaalstromen, auth-grenzen.

### smoke/
Curl-scripts tegen een **draaiende** omgeving (HDEV/UAT) na een deploy.
Heeft Caddy + backend + DB nodig — kan niet automatisch bij de build draaien.
Draai altijd `run-all.sh` na een deploy op HDEV voordat je naar UAT/PROD gaat.

**Wat er in hoort:** kritieke paden die echte HTTP-responses testen.

## Afspraken

- Elke bug die we fixen, krijgt een test. Label de testfunctie of het script
  met wat het dekt, zodat duidelijk is welke regressie het bewaakt.
- Smoke-scripts lezen de doel-URL uit `BASE` (default `http://localhost:8081`).
- Exit-code 0 = OK, 1 = fout. Bruikbaar in scripts en later in CI.
- Geen secrets in tests — gebruik `example.com`-adressen en publieke endpoints.

## Smoke-tests draaien

```bash
cd /opt/raakmillegem/hdev/tests/smoke
BASE=http://localhost:8081 ./run-all.sh
```
