#!/usr/bin/env bash
# Applies the SHARED Caddy config and restarts the shared Caddy, so that the
# change is guaranteed and durably active.
# Run from the caddy/ checkout (e.g. /opt/raakmillegem/caddy):
#
#   ./deploy-caddy.sh              # each part from the tag of its own environment
#   ./deploy-caddy.sh v1.15.0      # everything from one explicit ref
#
# CAUTION: this Caddy serves UAT **and** PROD. A mistake here takes production down.
#
# THE CONFIG FOLLOWS THE RELEASE TAGS, NOT MASTER. If the proxy followed master, a
# small intervention would push every proxy change made since then to production,
# unasked. That nearly happened: master routes everything to the backend (React
# exit #405) while v1.14.0 still runs a separate frontend container.
#
# The config is split so that UAT may run ahead of PROD:
#   caddy/parts/snippets.caddy    shared -> tag of PROD (conservative)
#   caddy/parts/sites-uat.caddy   UAT    -> tag of UAT
#   caddy/parts/sites-prod.caddy  PROD   -> tag of PROD
# The shared part therefore changes by expand/contract; see CLAUDE.md,
# "Shared Caddy: expand/contract".
#
# The TOOLING (this script, docker-compose.caddy.yml, tests/) comes from master,
# so that a safety fix does not have to wait for a release.
#
# Four safety nets, in this order:
#   1) `caddy validate` on the new config, BEFORE the running proxy is touched;
#   2) a smoke test against PROD after the recreate;
#   3) restoring the previous config when that smoke test fails;
#   4) restoring the previous image digest, in case the Caddy VERSION itself is the
#      failure — a config rollback does not help against that.
#
# Background (#312/#314): `caddy reload` (admin API, in memory) is unreliable and
# does not survive a restart. We do `up -d --force-recreate`, which loads the config
# fresh from disk, so compression (#303) survives every restart.
set -euxo pipefail

cd "$(dirname "$0")"

COMPOSE="docker-compose.caddy.yml"

# ── Snapshot of what runs NOW, before any change at all ──────────────────────
# Both the config and the image digest. Survives the re-exec through export.
if [ -z "${CADDY_PREV_DIR:-}" ]; then
  CADDY_PREV_DIR="$(mktemp -d /tmp/caddy-prev.XXXXXX)"
  cp caddy/Caddyfile.shared "$CADDY_PREV_DIR/Caddyfile.shared"
  mkdir -p "$CADDY_PREV_DIR/parts"
  cp -a caddy/parts/. "$CADDY_PREV_DIR/parts/" 2>/dev/null || true
  export CADDY_PREV_DIR

  # The image digest of the running container. RepoDigest is stable, even if the
  # tag is reused later; for a locally built image it falls back to the image id.
  # Empty = nothing runs yet (first deploy).
  CADDY_PREV_IMAGE=""
  _cid="$(docker compose -f "$COMPOSE" ps -q caddy 2>/dev/null || true)"
  if [ -n "$_cid" ]; then
    _iid="$(docker inspect "$_cid" --format '{{.Image}}' 2>/dev/null || true)"
    if [ -n "$_iid" ]; then
      CADDY_PREV_IMAGE="$(docker image inspect "$_iid" \
        --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' 2>/dev/null || true)"
    fi
  fi
  export CADDY_PREV_IMAGE
fi

# ── Tooling on master, then one re-exec (#796, the #162 pattern) ─────────────
# This sits BEFORE every decision, and that is the whole change of #796.
#
# Why it matters, more precisely than "the old version decides": an `exec` restarts
# the script from the top, so everything before that point is simply done again by
# the new version. What does NOT come right is a path that **aborts** before the
# re-exec. Below are two `exit 1`s — the one for an unknown PROD tag, and the
# guard rail for the mixed state (#572) — and those used to sit before the
# update. An outdated guard rail could thus abort the run without the update ever
# happening, or worse: not know a case yet and carry on.
#
# That is not theory. During the v2.0.1 rollout `raak caddy v2.0.1` failed with
# "'encode' ontbreekt in caddy/Caddyfile.shared" while `encode` was there — in
# caddy/parts/snippets.caddy. The checkout was on an older master, and THAT version
# only looked in Caddyfile.shared. A second call went straight through, because the
# first had updated the checkout in the meantime.
#
# It went well then because the old guard rail was too STRICT. The opposite
# direction is the risk: an old version that does not know a case yet and carries
# on — on the shared Caddy that also serves PROD.
#
# The snapshot above does stay before it: it records what runs NOW, and
# `git reset --hard` overwrites exactly that. It survives the re-exec through export.
#
# Re-execute unconditionally, without checking WHETHER the script changed: that
# comparison is itself logic that can go stale, and one extra `exec` costs nothing.
git fetch --tags --prune origin
git reset --hard origin/master
git checkout -B master origin/master
if [ -z "${CADDY_REEXEC:-}" ]; then
  export CADDY_REEXEC=1
  exec "$0" "$@"
fi

# ── Which refs supply the config? ────────────────────────────────────────────
# Argument > CADDY_REF > the tag of the environment concerned. There is
# DELIBERATELY no fallback to master: that is exactly the mistake we rule out.
ref_of() {  # $1 = checkout folder; empty result = unknown
  [ -d "$1/.git" ] || return 0
  git -C "$1" describe --tags --exact-match 2>/dev/null || true
}

EXPLICIT="${1:-${CADDY_REF:-}}"
if [ -n "$EXPLICIT" ]; then
  PROD_REF="$EXPLICIT"; UAT_REF="$EXPLICIT"
else
  # Relative paths, so no server paths end up in this public repo.
  PROD_REF="$(ref_of "${PROD_CHECKOUT_DIR:-../prod}")"
  UAT_REF="$(ref_of "${UAT_CHECKOUT_DIR:-../uat}")"
fi
if [ -z "$PROD_REF" ]; then
  echo "ERROR: could not determine which tag PROD runs." >&2
  echo "Pass a ref explicitly, e.g.: ./deploy-caddy.sh v1.14.0" >&2
  echo "(or point PROD_CHECKOUT_DIR at the prod checkout)" >&2
  exit 1
fi
[ -n "$UAT_REF" ] || UAT_REF="$PROD_REF"

# ── Catch the mixed state (#572) ─────────────────────────────────────────────
# If UAT already runs a tag WITH caddy/parts/ while PROD is still on a tag from
# before the split, the code below falls back to PROD's monolithic config — and that
# also holds the UAT block, with the old routing. UAT would go down. We do not guess
# that: stop, and let the ref be chosen explicitly.
if [ -z "$EXPLICIT" ]; then
  if git cat-file -e "$UAT_REF:caddy/parts/sites-uat.caddy" 2>/dev/null &&
     ! git cat-file -e "$PROD_REF:caddy/parts/sites-prod.caddy" 2>/dev/null; then
    echo "ERROR: UAT ($UAT_REF) has caddy/parts/, PROD ($PROD_REF) does not yet." >&2
    echo "Choosing automatically would apply the old UAT routing and take UAT down." >&2
    echo "During the cutover, pass the tag whose PROD block is still backwards" >&2
    echo "compatible explicitly, e.g.: ./deploy-caddy.sh $UAT_REF" >&2
    exit 1
  fi
fi

restore_prev() {
  cp "$CADDY_PREV_DIR/Caddyfile.shared" caddy/Caddyfile.shared
  mkdir -p caddy/parts
  cp -a "$CADDY_PREV_DIR/parts/." caddy/parts/ 2>/dev/null || true
}

# ── Write the config from the chosen refs ────────────────────────────────────
git show "$PROD_REF:caddy/Caddyfile.shared" > caddy/Caddyfile.shared

if grep -q '^import /etc/caddy/parts/' caddy/Caddyfile.shared; then
  # Split config: each part from its own environment.
  mkdir -p caddy/parts
  git show "$PROD_REF:caddy/parts/snippets.caddy"   > caddy/parts/snippets.caddy
  git show "$PROD_REF:caddy/parts/sites-prod.caddy" > caddy/parts/sites-prod.caddy
  # Transition case: if UAT still runs a tag from before the split, that part does
  # not exist there. Fall back to PROD's version then (= today's behaviour) instead
  # of aborting halfway with a half-written config.
  if git cat-file -e "$UAT_REF:caddy/parts/sites-uat.caddy" 2>/dev/null; then
    git show "$UAT_REF:caddy/parts/sites-uat.caddy" > caddy/parts/sites-uat.caddy
    echo "Config: shared+PROD from $PROD_REF, UAT from $UAT_REF"
  else
    git show "$PROD_REF:caddy/parts/sites-uat.caddy" > caddy/parts/sites-uat.caddy
    echo "CAUTION: $UAT_REF has no caddy/parts/ yet — UAT part taken from $PROD_REF."
  fi
else
  # Old, monolithic config (tags from before the split). Then the one file also
  # holds the UAT blocks, and UAT cannot run ahead separately.
  echo "CAUTION: $PROD_REF still has the unsplit Caddyfile.shared."
  echo "         So UAT and PROD both follow $PROD_REF; UAT-first only works"
  echo "         once PROD runs a tag with caddy/parts/."
fi

# Safety check: the compression (#303) belongs in the config.
if ! grep -rq 'encode' caddy/Caddyfile.shared caddy/parts/ 2>/dev/null; then
  echo "ERROR: 'encode' is missing from the Caddy config — NOT applied." >&2
  restore_prev
  exit 1
fi

# ── Platform domains: from the app configuration, not from .env.caddy (#866) ─
# "This domain is the platform" lived in two places and drifted apart: on PROD
# Caddy served the subdomain while the app only knew the apex domain, and the
# landing page ended up on Raak Millegem. The app variable is now the source; this
# derives from it. If that fails we stop here — an empty site address makes the
# WHOLE config invalid, and then the proxy does not start.
. ./caddy/platform-domains.sh

# ── SAFETY NET 1 — validate before we touch the running proxy ────────────────
# `run --rm --no-deps` publishes no ports and starts nothing else; the env_file
# (.env.caddy) is loaded, so the {$DOMAIN} placeholders are filled in as on a
# real start.
if ! docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint caddy caddy \
     validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  echo "!! CONFIG IS INVALID — proxy not touched." >&2
  restore_prev
  exit 1
fi

docker compose -f "$COMPOSE" up -d --force-recreate caddy

# ── SAFETY NET 2 — smoke test against PROD (the gate) ────────────────────────
domain_from_env() {
  sed -nE "s/^$1=[\"']?([^\"']*)[\"']?.*/\1/p" .env.caddy | head -1
}
PROD_DOMAIN="$(domain_from_env PROD_DOMAIN)"
UAT_DOMAIN="$(domain_from_env UAT_DOMAIN)"

if [ -n "$PROD_DOMAIN" ]; then
  if ! BASE="https://$PROD_DOMAIN" ./tests/run-all.sh; then
    echo "!! SMOKE TEST FAILED on PROD after the Caddy change." >&2

    # SAFETY NET 3 + 4 — restore the previous config and the previous image.
    restore_prev
    if [ -n "$CADDY_PREV_IMAGE" ]; then
      echo ">>> Back to the previous image: $CADDY_PREV_IMAGE"
      CADDY_IMAGE="$CADDY_PREV_IMAGE" docker compose -f "$COMPOSE" up -d --force-recreate caddy
    else
      docker compose -f "$COMPOSE" up -d --force-recreate caddy
    fi

    echo "!! ROLLED BACK. The config from $PROD_REF/$UAT_REF is NOT active." >&2
    echo "!! CAUTION: this is a RUNTIME rollback. If the failure was in a new Caddy" >&2
    echo "!! version, docker-compose.caddy.yml still points at it and the next deploy" >&2
    echo "!! pulls it again. Revert the pin in git." >&2
    echo "!! Snapshot of the restored config: $CADDY_PREV_DIR" >&2
    exit 1
  fi
  echo "Smoke test OK on PROD."
else
  echo "PROD_DOMAIN unknown in .env.caddy — smoke test against PROD skipped"
fi

# UAT is tested too, but only as a warning: a UAT stack that is down for other
# reasons must not roll back a good config.
if [ -n "$UAT_DOMAIN" ]; then
  BASE="https://$UAT_DOMAIN" ./tests/run-all.sh \
    || echo "CAUTION: smoke test against UAT failed. No rollback (PROD is the gate) — check the UAT stack."
fi

echo "Shared Caddy recreated — PROD part from $PROD_REF, UAT part from $UAT_REF."
