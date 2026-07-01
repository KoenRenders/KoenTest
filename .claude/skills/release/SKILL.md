---
name: release
description: Begeleidt een Raak Millegem-release volgens CLAUDE.md — maakt/onderhoudt het release-tracking-issue, verifieert dat alle issues gemerged + CI-groen zijn, haalt CI-evidence op, begeleidt de GitHub Release (HDEV → tag → UAT → PROD) en sluit de issues. Kan de deploy optioneel over SSH op de server draaien (env-gated: DEPLOY_SSH_HOST/USER/KEY; HDEV automatisch, UAT/PROD enkel na bevestiging; DEPLOY_DRY_RUN=1 print de commando's i.p.v. ze uit te voeren) en de backend-logs binnentrekken + analyseren. Gebruik dit bij het starten of afronden van een release (bv. "start release v1.x.0" of "rond v1.x.0 af").
---

# Release-begeleiding Raak Millegem

Deze skill volgt strikt de regels in `CLAUDE.md` (secties *Releases en hotfixes*,
*Deploying a release to UAT / PROD*, *Testen en test-evidence*). De deploy-scripts
(`deploy-hdev.sh`, `deploy-uat.sh`, `deploy-prod.sh`, `deploy-caddy.sh`) draaien op
de **server** door Koen — Claude draait ze niet. Claude's rol: het tracker-issue
beheren, CI-evidence verzamelen, de GitHub Release begeleiden en issues sluiten.

## Stap 0 — bepaal de fase
Vraag (of leid af): **start** van een release (tracker opzetten) of **afronden**
(deployen + sluiten)? Werk daarna de juiste stappen af.

## Stap 1 — release-tracker-issue (single source of truth)
Maak of update een issue `Release vX.Y.Z — <korte omschrijving>` met:
- **Eén checkbox per issue**: `- [ ] #NN (korte omschrijving)`. NOOIT twee
  checkboxes per issue. De zin *"getest op HDEV door Koen"* hoort NERGENS.
- Eén intro-zin: *"De checkbox hieronder vink jij af zodra je het op HDEV
  gevalideerd hebt."*
- De volledige **deploy-checklist** (zie stap 4).
- Een **CI-evidence**-sectie (run-id + link + `N passed`) apart van de issuelijst.
- Aandachtspunten: migraties (`NNN -> NNN+1`), nieuwe/gewijzigde **env vars**
  (niet auto-toegevoegd aan echte `.env.<env>` — per host zetten), feature flags,
  Caddyfile-wijzigingen (#312/#314 → `deploy-caddy.sh` nodig).

## Stap 2 — merge-gate (feature-branches)
Voor élk issue met feature-branch-werk: bevestig dat de PR **gemerged naar
`master`** is en dat de CI-run **groen** was. Onthoud: feature-werk komt pas in de
pijplijn na de merge (HDEV deployt `master` HEAD). Merge enkel op vraag van Koen.

## Stap 3 — CI-evidence verzamelen
Haal per gemergde PR de geslaagde `backend-tests.yml`-run op en noteer in het
tracker-issue: **run-id + link** en de **pytest-samenvatting** (`N passed`). De CI
draait tegen echte Postgres 16 — dat is het bewijs, geen lokale claim.

## Stap 4 — deploy-checklist (volgorde HDEV → Release → UAT → PROD)
Zet deze als checkboxes in het tracker-issue en begeleid Koen erdoorheen:
1. [ ] **Env vars per host** bijwerken indien de release die toevoegt/wijzigt
   (naam expliciet noemen; niet auto-toegevoegd).
2. [ ] HDEV test tegen master: `./deploy-hdev.sh` — **vóór** het tag-moment.
3. [ ] **GitHub Release `vX.Y.Z`** aanmaken (Draft → Choose tag → *Create new tag
   on publish* → Target `master` = de op HDEV geteste commit → Publish). Dit maakt
   de tag server-side; **geen** `git push origin <tag>` (403 in remote env).
   Her-check het exacte doelcommit — master kan intussen bewogen zijn.
4. [ ] UAT: `./deploy-uat.sh vX.Y.Z`.
5. [ ] **Gedeelde Caddy** reloaden met `./deploy-caddy.sh` **enkel** als de release
   `caddy/Caddyfile.shared` raakt (één recreate dekt UAT + PROD).
6. [ ] PROD: `./deploy-prod.sh vX.Y.Z`.
7. [ ] Backend-logs verifiëren: `Running upgrade NNN -> NNN+1` (bij nieuwe
   migratie) + `Uvicorn running on http://0.0.0.0:8000`, geen ERROR/traceback.
   Commando: `sudo docker compose -f docker-compose.<env>.yml --env-file
   .env.<env> logs backend --tail=80`.
8. [ ] Functionele smoke per issue (schrijf per issue wat Koen concreet checkt).

## Stap 4b — SSH-deploy + loganalyse (optioneel, env-gated)
Deze stap draait de deploy **rechtstreeks op de server** en analyseert de logs —
maar **alleen** als de omgeving het toelaat. Anders val je terug op "print de
commando's, Koen voert ze uit, plak de logs, ik analyseer".

**Voorwaarden (alle vier), anders overslaan en commando's printen:**
1. `ssh` (en `scp`) zijn beschikbaar in de omgeving.
2. Connectiegegevens staan in **env-variabelen** (NOOIT in de repo — public; zie
   `.deploy.env.example`). Eén Hetzner-server → gedeelde SSH-gegevens, per-milieu
   checkout-mappen:
   - Gedeeld: `DEPLOY_SSH_HOST`, `DEPLOY_SSH_USER`, `DEPLOY_SSH_KEY` (pad naar de
     private key), optioneel `DEPLOY_SSH_PORT` (default 22).
   - Per milieu: `DEPLOY_HDEV_DIR`, `DEPLOY_UAT_DIR`, `DEPLOY_PROD_DIR` en
     `DEPLOY_CADDY_DIR`. Kies de map die bij het doelmilieu hoort. (Legacy:
     `DEPLOY_REPO_DIR` geldt als fallback voor `DEPLOY_HDEV_DIR`.)
3. Het doelmilieu is bevestigd (zie guardrail hieronder).
4. Test eerst de verbinding niet-destructief:
   `ssh -i "$DEPLOY_SSH_KEY" -p "${DEPLOY_SSH_PORT:-22}" "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST" 'echo ok && hostname'`

**Guardrail per milieu:**
- **HDEV** — mag automatisch (integratielijn, geen tag).
- **UAT / PROD** — **enkel na expliciete bevestiging van Koen in dit gesprek**, en
  enkel met een reeds op HDEV geteste **release-tag**. Nooit PROD "en passant".

**Files verplaatsen (scp).** De code komt via `git` op de server (de deploy-scripts
doen `git fetch`/`checkout`), dus scp is enkel voor bestanden die **bewust niet in
git** zitten — bv. een bijgewerkt `.env.<env>` met echte waarden. Verplaats zulke
bestanden vanaf een lokale, niet-gecommitte bron; **print of commit hun inhoud
nooit**:
`scp -i "$DEPLOY_SSH_KEY" -P "${DEPLOY_SSH_PORT:-22}" ./local/.env.hdev "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST:$DEPLOY_REPO_DIR/.env.hdev"`

**Dry-run (droog doorlopen).** Als `DEPLOY_DRY_RUN` gezet is op `1`/`true`/`yes`,
voer je de deploy-, scp- en Caddy-commando's **NIET** uit — je **print** ze exact
(met de ingevulde host/user/paden, maar zonder key-inhoud) zodat Koen ziet wat er
zou gebeuren. De **verbindingstest en de log-fetch blijven wél echt draaien** (die
zijn read-only en veranderen niets). Sluit af met een duidelijke regel:
"DRY-RUN — niets uitgevoerd. Zet `DEPLOY_DRY_RUN` uit om echt te deployen."

**Deploy draaien** — kies de checkout-map die bij het milieu hoort
(`${DEPLOY_HDEV_DIR:-$DEPLOY_REPO_DIR}` / `$DEPLOY_UAT_DIR` / `$DEPLOY_PROD_DIR`):
- HDEV: `ssh -i "$DEPLOY_SSH_KEY" -p "${DEPLOY_SSH_PORT:-22}" "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST" 'cd "${DEPLOY_HDEV_DIR:-$DEPLOY_REPO_DIR}" && ./deploy-hdev.sh'`
- UAT (na bevestiging + tag): `ssh … 'cd "$DEPLOY_UAT_DIR" && ./deploy-uat.sh vX.Y.Z'`
- PROD (na bevestiging + tag): `ssh … 'cd "$DEPLOY_PROD_DIR" && ./deploy-prod.sh vX.Y.Z'`

**Caddy — twee verschillende gevallen (belangrijk):**
- **HDEV heeft zijn EIGEN Caddy** binnen de hdev-stack (`caddy/Caddyfile.hdev`,
  bind-mount). `deploy-hdev.sh` herlaadt die **zelf** (`… exec -T caddy caddy
  reload`) → bij een HDEV-deploy is er **geen** aparte Caddy-stap.
- **UAT en PROD delen één externe Caddy** (`caddy/Caddyfile.shared`, netwerk
  `raak_proxy`). Enkel wanneer **`Caddyfile.shared`** wijzigt (#312/#314) is een
  aparte stap nodig: `ssh … 'cd "$DEPLOY_CADDY_DIR" && ./deploy-caddy.sh'`. **Eén**
  recreate dekt UAT én PROD. Draai dit **niet** voor HDEV.

(Bij `DEPLOY_DRY_RUN` → enkel printen, niets uitvoeren.)

**Logs binnentrekken + analyseren — gebruik de dedicated `logging-<env>.sh`.**
Er zijn kant-en-klare diagnosescripts (`logging-hdev.sh`, `logging-uat.sh`,
`logging-prod.sh`) die alles bundelen in `/tmp/<env>-diagnostics.log`:
containerstatus, `alembic heads`/`current`, schijfruimte, een ERROR/Traceback-
foutfilter, en de backend-/frontend-/caddy-logs (voor UAT/PROD komen de caddy-logs
uit het gedeelde `docker-compose.caddy.yml`-project). **Gebruik deze i.p.v. een
hand-geschreven `docker compose logs`.** Draai het script en trek het bestand op:
- `ssh -i "$DEPLOY_SSH_KEY" -p "${DEPLOY_SSH_PORT:-22}" "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST" 'cd <checkout-map van het milieu> && ./logging-<env>.sh'`
  (checkout-map = `${DEPLOY_HDEV_DIR:-$DEPLOY_REPO_DIR}` / `$DEPLOY_UAT_DIR` /
  `$DEPLOY_PROD_DIR`; het script tee't de output ook naar je scherm).
- Haal het volledige bestand op: `scp -i "$DEPLOY_SSH_KEY" -P "${DEPLOY_SSH_PORT:-22}" "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST:/tmp/<env>-diagnostics.log" ./`

Analyseer het rapport en meld:
- ✅ Containers allemaal `running`/`healthy` — geen `restarting`/`exited`.
- ✅ **Precies één** `alembic head`, en `alembic current` == die head. Bij een
  nieuwe migratie: de verwachte `Running upgrade NNN -> NNN+1` in de backend-logs
  (geen nieuwe migratie → geen upgrade-regels, dat is normaal).
- ✅ `Uvicorn running on http://0.0.0.0:8000`.
- ❌ Elke `ERROR`/`Traceback`/`Exception` in de foutfilter of backend-logs → deploy
  verdacht; benoem de regel(s) en **stop de promotie** naar het volgende milieu.
Draai ook de read-only smoke test als die er is (`tests/run-all.sh`) en meld het
resultaat.

**Nooit** een secret, key-inhoud of `.env`-waarde naar de chat, een commit of een
issue schrijven. Faalt de SSH-verbinding? Meld het en val terug op het
print-de-commando's-pad.

## Stap 5 — issues sluiten
Zodra CI groen is, **sluit Claude elk geïmplementeerd issue zelf** met een
afsluit-comment: wat gerealiseerd is + hoe te testen op HDEV. De ene checkbox in
het tracker-issue (Koens HDEV-validatie) vinkt **Koen zelf** af — nooit Claude.

## Stap 6 — release afronden
Sluit het tracker-issue zodra de release op PROD staat en de logs geverifieerd zijn.

## Belangrijke vangrails
- **Nooit** een ongetest commit taggen: de tag is de single source of truth voor
  UAT/PROD en moet naar een op HDEV geteste `master`-commit wijzen.
- **Nooit** secrets/IP's/domeinen in commits of issues (repo is PUBLIC).
- Bij een **hotfix op een released tag**: `git checkout -b hotfix/1.x.x v1.x.x`,
  fix, merge terug naar `master` na groene CI, dan GitHub Release op `master`.
