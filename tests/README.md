# Tests

Twee lagen, met een duidelijke taakverdeling:

| Laag | Waar | Wanneer | Wat |
|---|---|---|---|
| **pytest** (`backend/tests/`) | In-process, wegwerp-Postgres | CI bij elke push + lokaal | Alle logica/regressie: registratie, audit, betalingen, media, beveiliging, validatie, rate-limiting, end-to-end flows. |
| **rooktest** (`tests/`) | Echte HTTP tegen de live stack | Automatisch ná elke deploy | Dunne, **alleen-lezen** check dat de échte draaiende omgeving leeft (Caddy, DB, app antwoordt, admin afgeschermd). |

De rooktest **maakt nooit data aan** (geen leden, pagina's, betalingen of
inschrijvingen) en heeft **geen ADMIN_TOKEN** nodig. Daardoor is hij veilig op
**elke** omgeving, PROD inbegrepen. Alles wat data zou wegschrijven of admin-auth
vereist, zit bewust in de pytest-suite.

## Structuur

```
tests/
├── lib.sh        Gedeelde helpers — stil bij succes, gericht bij falen.
├── run-all.sh    Draait alles en toont één beknopt overzicht.
└── smoke/        Alleen-lezen checks tegen een live stack.
    └── live.sh   Health + publieke GET's = 200; admin zonder token = 401/403.
```

## Draaien

De deploy-scripts (`deploy-*.sh`) draaien de rooktest automatisch ná
`docker compose up`. Handmatig kan ook:

```bash
cd /opt/raakmillegem/hdev/tests
BASE=http://localhost:8081 ./run-all.sh
```

`BASE` wijst naar de te testen omgeving. Op HDEV werkt `localhost:8081`; op
UAT/PROD gebruik je de publieke URL (de deploy-scripts leiden die af uit
`PUBLIC_URL` in het env-bestand).

## Uitvoer

Per test één regel: `PASS` / `FAIL` / `SKIP`. Bij `FAIL`/`SKIP` toont de runner
onderaan enkel de uitvoer van díe test. Exit-code 0 = alles OK, 1 = minstens
één test faalde.

## Afspraken

- Elk script `source`t `../lib.sh` en eindigt met `t_summary`.
- Elk script begint met `DESC="…"` — één Nederlandse zin die zegt wat het garandeert.
- **Alleen-lezen**: een script in `smoke/` mag uitsluitend GET's doen (plus
  afscherming-checks die 401/403 verwachten). Niets dat data aanmaakt of wijzigt
  — anders is het niet veilig op PROD en hoort het in pytest thuis.
- Doel-URL via `BASE` (default `http://localhost:8081`).
- Geen secrets; vereist op de server: `curl`.
