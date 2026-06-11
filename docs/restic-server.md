# Restic-back-up op de PROD-server (Hetzner Storage Box)

De server maakt dagelijks een `pg_dump` (zie `backups.md`). Dit document zet
op dat **`/opt/raakmillegem`** via Restic off-site naar de Hetzner Storage Box
gaat, met dezelfde retentie als je desktop-back-up.

`/opt/raakmillegem` bevat de code-checkouts (prod/uat/hdev), de `.env`-files
(secrets, niet in git) en de `pg_dump`-SQL-dumps. Samen met die SQL-dump heb je
alles voor een volledige, consistente restore. De live PostgreSQL-datafiles
(Docker-volume) worden bewust niet rauw mee gekopieerd — daarvoor dient juist
de dump; andere `/opt`-software (bin, lib) is herinstalleerbaar.

Bestanden in de repo:
- `scripts/restic-backup.sh` — de back-uprun (aparte repo `restic-raakmillegem`)
- `scripts/systemd/raakmillegem-restic.service` + `.timer` — dagelijkse run om 03:30

## Eenmalige setup op de server

Voer alles als **root** uit.

### 1. Restic installeren

```bash
apt update && apt install -y restic
```

### 2. SSH-toegang tot de Storage Box

De Storage Box gebruikt SFTP over SSH op **poort 23**. Vervang hieronder
`<BOX_USER>` door je eigen Storage Box-gebruiker (vorm `uXXXXXX`) — die hoort
niet in deze (publieke) repo, dus vul hem enkel lokaal op de server in.

```bash
# Sleutel aanmaken (indien nog niet aanwezig)
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N ""

# Publieke sleutel op de Storage Box plaatsen (vraagt eenmalig je box-wachtwoord)
cat /root/.ssh/id_ed25519.pub | ssh -p 23 <BOX_USER>@<BOX_USER>.your-storagebox.de install-ssh-key
```

Maak een SSH-alias `hetzner-storagebox` aan in `/root/.ssh/config`:

```
Host hetzner-storagebox
    HostName <BOX_USER>.your-storagebox.de
    User <BOX_USER>
    Port 23
    IdentityFile /root/.ssh/id_ed25519
```

Test de verbinding:

```bash
sftp hetzner-storagebox
# 'exit' om af te sluiten
```

### 3. Restic-wachtwoord

Kies een sterk wachtwoord voor de repo en bewaar het in een bestand:

```bash
mkdir -p /root/.config/restic
# Genereer of plak je eigen wachtwoord:
openssl rand -base64 32 > /root/.config/restic/raakmillegem-password
chmod 600 /root/.config/restic/raakmillegem-password
```

> Bewaar dit wachtwoord óók ergens veilig buiten de server (bv. je
> wachtwoordmanager). Zonder dit wachtwoord zijn de back-ups onherstelbaar.

### 4. Script uitvoerbaar maken

```bash
chmod +x /opt/raakmillegem/prod/scripts/restic-backup.sh
```

### 5. Eerste run (initialiseert de repo)

```bash
/opt/raakmillegem/prod/scripts/restic-backup.sh
```

Bij de eerste run maakt het script de repo aan en plaatst de eerste snapshot.

### 6. Systemd-timer installeren

```bash
cp /opt/raakmillegem/prod/scripts/systemd/raakmillegem-restic.service /etc/systemd/system/
cp /opt/raakmillegem/prod/scripts/systemd/raakmillegem-restic.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now raakmillegem-restic.timer
```

Controleer:

```bash
systemctl list-timers raakmillegem-restic.timer
```

## Herstellen

```bash
export RESTIC_REPOSITORY="sftp:hetzner-storagebox:restic-raakmillegem"
export RESTIC_PASSWORD_FILE="/root/.config/restic/raakmillegem-password"

restic snapshots                          # overzicht
restic restore latest --target /tmp/herstel   # nieuwste snapshot terugzetten
```

De teruggezette SQL-dump speel je dan in de database af zoals beschreven in
`backups.md`.

## Handmatig draaien / loggen

```bash
systemctl start raakmillegem-restic.service        # nu draaien
journalctl -u raakmillegem-restic.service --tail=50
ls -lh /var/log/raakmillegem/                      # scriptlogs
```
