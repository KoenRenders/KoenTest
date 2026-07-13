#!/usr/bin/env bash
DESC="Responses worden gecomprimeerd (Caddy encode zstd/gzip, #303)"
# Post-deploy ROOKTEST — strikt ALLEEN-LEZEN (één GET op de homepage). Veilig op PROD.
#
# Controleert dat Caddy de respons comprimeert. Bewust een GET (geen HEAD): bij
# HEAD is er geen body, dus zet Caddy ook geen Content-Encoding — dat zou een vals
# negatief geven. We vragen expliciet gzip (universeel); Caddy mag ook zstd kiezen.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

# Post-deploy draait deze test meteen na een `caddy reload`-equivalent (recreate).
# Die allereerste GET kan de reload/cold-start net missen en ongecomprimeerd
# terugkomen — een valse negatief (#381). Daarom herproberen we de homepage-GET
# een paar keer met een korte pauze en falen we pas als het ná alle pogingen nog
# steeds niet lukt. Een blijvend niet-gecomprimeerde respons faalt dus nog steeds.
# -D - dumpt de response-headers naar stdout; -o /dev/null gooit de body weg.
enc=""
for attempt in 1 2 3 4 5; do
  hdrs=$(curl -s -D - -o /dev/null -H "Accept-Encoding: gzip" "${BASE}/" 2>/dev/null) \
    || fatal "kon ${BASE}/ niet ophalen"
  enc=$(printf '%s' "$hdrs" | grep -i '^content-encoding:' | tr -d '\r' | awk '{print tolower($2)}')
  case "$enc" in
    gzip|zstd) break ;;
  esac
  sleep 1
done

case "$enc" in
  gzip|zstd) expect_true 1 "homepage gecomprimeerd (content-encoding: $enc)" ;;
  *)         expect_true 0 "homepage niet gecomprimeerd — verwacht content-encoding gzip/zstd, kreeg '${enc:-geen}' (na 5 pogingen)" ;;
esac

t_summary
