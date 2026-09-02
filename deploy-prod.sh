#!/usr/bin/env bash
# Wrapper voor terugwaartse compatibiliteit — het echte werk staat in deploy.sh.
# Behouden omdat de release-checklist (#454), de /release-skill en het
# spiekbriefje deze namen gebruiken; ze breken vlak voor de v2.0.0-cutover zou
# risico op de verkeerde plek leggen.
exec "$(dirname "$0")/deploy.sh" prod "$@"
