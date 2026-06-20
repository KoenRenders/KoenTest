#!/usr/bin/env bash
DESC="Responses worden gecomprimeerd (Caddy encode zstd/gzip, #303)"
# Post-deploy ROOKTEST — strikt ALLEEN-LEZEN (één GET op de homepage). Veilig op PROD.
#
# Controleert dat Caddy de respons comprimeert. Bewust een GET (geen HEAD): bij
# HEAD is er geen body, dus zet Caddy ook geen Content-Encoding — dat zou een vals
# negatief geven. We vragen expliciet gzip (universeel); Caddy mag ook zstd kiezen.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

# -D - dumpt de response-headers naar stdout; -o /dev/null gooit de body weg.
hdrs=$(curl -s -D - -o /dev/null -H "Accept-Encoding: gzip" "${BASE}/" 2>/dev/null) \
  || fatal "kon ${BASE}/ niet ophalen"

enc=$(printf '%s' "$hdrs" | grep -i '^content-encoding:' | tr -d '\r' | awk '{print tolower($2)}')

case "$enc" in
  gzip|zstd) expect_true 1 "homepage gecomprimeerd (content-encoding: $enc)" ;;
  *)         expect_true 0 "homepage niet gecomprimeerd — verwacht content-encoding gzip/zstd, kreeg '${enc:-geen}'" ;;
esac

t_summary
