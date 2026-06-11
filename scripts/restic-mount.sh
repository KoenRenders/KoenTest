#!/usr/bin/env bash
# Mount de Restic-back-up (restic-raakmillegem) als een map om in te bladeren.
#
# Handig om losse bestanden of een specifieke SQL-dump terug te halen zonder
# een volledige restore. Het commando blijft op de voorgrond draaien; blader in
# een TWEEDE terminal en druk hier Ctrl-C om te ontkoppelen.
set -euo pipefail

export RESTIC_REPOSITORY="sftp:hetzner-storagebox:restic-raakmillegem"
export RESTIC_PASSWORD_FILE="/root/.config/restic/raakmillegem-password"

MOUNT_POINT="${1:-/mnt/restic-raakmillegem}"

mkdir -p "$MOUNT_POINT"

echo "Mount restic-raakmillegem op ${MOUNT_POINT}"
echo "Blader in een andere terminal; druk hier Ctrl-C om te ontkoppelen."
restic mount "$MOUNT_POINT"
