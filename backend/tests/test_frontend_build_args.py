"""Regressie (#239): elke NEXT_PUBLIC_-build-arg die de compose-bestanden aan de
frontend doorgeven, moet ook als ``ARG`` in ``frontend/Dockerfile`` staan.

Achtergrond: de chatbot-widget bleef onzichtbaar omdat de compose
``NEXT_PUBLIC_CHATBOT_ENABLED`` meegaf, maar de Dockerfile die ARG niet
declareerde. Docker dropt een niet-gedeclareerde build-arg stil → Next inlinet
``undefined`` → de feature staat de facto uit. CI bouwt de frontend niet
(`tsc --noEmit`), dus deze statische check vangt die hele klasse af.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = sorted(REPO_ROOT.glob("docker-compose.*.yml"))
DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"

# Build-arg-sleutel in compose, bv. "        NEXT_PUBLIC_CHATBOT_ENABLED: ${...}".
_COMPOSE_KEY = re.compile(r"^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*:", re.MULTILINE)
# ARG-declaratie in de Dockerfile, bv. "ARG NEXT_PUBLIC_CHATBOT_ENABLED=false".
_DOCKER_ARG = re.compile(r"^\s*ARG\s+(NEXT_PUBLIC_[A-Z0-9_]+)", re.MULTILINE)


def test_compose_files_exist():
    assert COMPOSE_FILES, "geen docker-compose.*.yml gevonden"
    assert DOCKERFILE.is_file(), f"{DOCKERFILE} ontbreekt"


def test_every_compose_next_public_arg_is_declared_in_dockerfile():
    declared = set(_DOCKER_ARG.findall(DOCKERFILE.read_text(encoding="utf-8")))

    for compose in COMPOSE_FILES:
        passed = set(_COMPOSE_KEY.findall(compose.read_text(encoding="utf-8")))
        missing = passed - declared
        assert not missing, (
            f"{compose.name} geeft build-arg(s) {sorted(missing)} door aan de "
            f"frontend, maar frontend/Dockerfile declareert er geen ARG voor — "
            f"Docker dropt die stil en de waarde bereikt de Next-build nooit."
        )
