#!/usr/bin/env bash
# VEROUDERD — gebruik `./deploy.sh hdev [tag]`. Deze wrapper bestaat voor precies
# één release en verdwijnt daarna (zie #577).
#
# Waarom hij nu nog nodig is: de checkouts op UAT/PROD draaien v1.14.0, en het
# deploy-script DAAR doet na `git checkout --detach <tag>` een `exec "$0" "$@"`
# (#162). Bestaat deze bestandsnaam niet in de nieuwe tag, dan faalt die exec
# nadat de checkout al gebeurd is — midden in een productie-deploy.
echo "LET OP: deploy-hdev.sh is verouderd — gebruik voortaan: ./deploy.sh hdev [tag]" >&2
exec "$(dirname "$0")/deploy.sh" hdev "$@"
