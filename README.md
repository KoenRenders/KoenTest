# Raak Millegem — Web Portal

Webapplicatie voor de Raak-Millegem (KWB Millegem) vereniging.

## Stack

| Laag | Technologie |
|---|---|
| Database | PostgreSQL 16 |
| Backend | Python 3.12 + FastAPI |
| Frontend | Next.js 14 + React + TypeScript + Tailwind CSS |
| Payments | Mollie (stub) |
| Email | Python smtplib + Gmail SMTP |
| Infra | Docker Compose + Caddy |

## Snel starten

### 1. Configuratie

```bash
cp .env.example .env
# Pas .env aan met jouw wachtwoorden
```

### 2. Starten

```bash
docker compose up -d
```

### 3. Seed data (eerste keer)

```bash
docker compose exec backend python seed_products.py
```

Dit maakt de webshop-producten aan en een admin-gebruiker:
- **Gebruikersnaam:** `admin`
- **Wachtwoord:** `changeme` → **direct aanpassen!**

### 4. Openen

| URL | Beschrijving |
|---|---|
| http://localhost:3000 | Website |
| http://localhost:8000/docs | API documentatie (Swagger) |
| http://localhost:3000/admin | Admin paneel |

## Functionaliteiten

- **Homepage:** activiteitenoverzicht, lid worden, ideeënbus
- **Activiteiten:** per jaar gegroepeerd, status (Open/Vol/Wachtlijst), inschrijven
- **Archief:** automatisch alle verleden activiteiten
- **Webshop:** Brood en Spelen producten, leden- vs. reguliere prijs
- **CMS:** admin kan informatiepagina's aanmaken (Werking, Kerstradio, ...)
- **Admin:** dashboard, activiteitenbeheer, ledenbeheer, bestellingen, ideeën
- **E-mail:** bevestigingen via Gmail SMTP

## Hosting (productie)

Hetzner CX22 (€6/mnd) — Ubuntu 26.04 LTS, 4 Docker containers via Caddy reverse proxy.

Zie `caddy/Caddyfile` voor domeinconfiguratie.
