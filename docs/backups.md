# Database back-ups (PROD)

## Hoe het werkt

De PROD-stack bevat een service `db-backup` (zie `docker-compose.prod.yml`).
Die draait `scripts/db-backup.sh`: elke nacht om **02:00 (UTC)** een `pg_dump`
van de database `raakmillegem`, gecomprimeerd weggeschreven naar de host-map
`/opt/raakmillegem/prod/backups/` als `prod-JJJJMMDD-UUMMSS.sql.gz`. Het uur is
instelbaar via `BACKUP_HOUR` in `docker-compose.prod.yml`.

Lokaal worden enkel de laatste **7 dagen** bewaard. Een off-site kopie met
langere retentie wordt apart geregeld door een back-uppijplijn die buiten deze
(publieke) repo wordt beheerd — die neemt `/opt/raakmillegem/prod/backups/` mee.

## Controleren

```bash
ls -lh /opt/raakmillegem/prod/backups/
sudo docker compose -f docker-compose.prod.yml --env-file .env.prod logs db-backup --tail=20
```

## Herstellen

1. Kies de gewenste dump (lokaal of via Restic teruggehaald).
2. Zet ze terug in de draaiende database:

```bash
gunzip -c /opt/raakmillegem/prod/backups/prod-JJJJMMDD-UUMMSS.sql.gz \
  | sudo docker compose -f docker-compose.prod.yml --env-file .env.prod \
    exec -T db psql -U "$DB_USER" raakmillegem
```

> Let op: dit speelt de dump terug bovenop de bestaande data. Voor een schone
> restore eerst de database leegmaken/hermaken, afhankelijk van de situatie.
