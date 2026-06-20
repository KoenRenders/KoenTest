#!/usr/bin/env bash
# Past de GEDEELDE Caddy-config (caddy/Caddyfile.shared) toe en herstart de
# gedeelde Caddy zodat de wijziging gegarandeerd én blijvend actief is.
# Draaien uit de caddy/-checkout (bv. /opt/raakmillegem/caddy):  ./deploy-caddy.sh
#
# Achtergrond (#312/#314) — twee valkuilen die we hier hard dichttimmeren:
#   1) `caddy reload` (admin-API, in-memory) is onbetrouwbaar en overleeft geen
#      herstart. We doen `up -d --force-recreate`, dat de config vers van schijf
#      laadt, zodat compressie (#303) elke herstart overleeft.
#   2) Een caddy-map op een DETACHED HEAD laat `git pull` stilvallen, waardoor de
#      config nooit bijwerkt. We forceren de map onvoorwaardelijk op master HEAD.
set -euxo pipefail

cd "$(dirname "$0")"

# Zet de map onvoorwaardelijk op de laatste master (werkt ook vanaf een detached
# HEAD of een vervuilde werkmap).
git fetch origin
git reset --hard origin/master
git checkout -B master origin/master

# Veiligheidscheck: de compressie (#303) hoort in de gedeelde config te staan.
# Zo niet, dan klopt de checkout niet — stoppen i.p.v. een kapotte config laden.
if ! grep -q 'encode' caddy/Caddyfile.shared; then
  echo "FOUT: 'encode' ontbreekt in caddy/Caddyfile.shared — config NIET toegepast." >&2
  exit 1
fi

# Verse container = config vers van schijf (overleeft herstarts), i.p.v. de
# onbetrouwbare in-memory `caddy reload`.
docker compose -f docker-compose.caddy.yml up -d --force-recreate caddy

echo "Gedeelde Caddy hercreëerd op master ($(git rev-parse --short HEAD)) — dekt alle domeinen."
echo "Verifieer bv.: curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' https://<domein>/ | grep -i content-encoding"
