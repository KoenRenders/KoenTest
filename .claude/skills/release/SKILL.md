---
name: release
description: Begeleidt een Raak Millegem-release volgens CLAUDE.md — maakt/onderhoudt het release-tracking-issue, verifieert dat alle issues gemerged + CI-groen zijn, haalt CI-evidence op, begeleidt de GitHub Release (HDEV → tag → UAT → PROD) en sluit de issues. Gebruik dit bij het starten of afronden van een release (bv. "start release v1.x.0" of "rond v1.x.0 af").
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
