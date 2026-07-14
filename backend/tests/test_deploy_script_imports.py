"""Regressie op #449: de deploy-/seed-/tooling-scripts moeten in een *smalle*
context (schone interpreter, één facade-import) de volledige SQLAlchemy-registry
kunnen configureren.

Achtergrond. Bij de v2.0-refactor (#393) verhuisden de modellen naar
`app.domains.<domein>.*`. Twee gevolgen die CI groen lieten maar de start braken:
1. `startup.sh` + enkele seed-scripts bleven op het oude `app.models.*`-pad staan
   → `ModuleNotFoundError`. `check_imports.py` (enkel `app.main`) en pytest draaien
   die inline `python -c`-imports niet.
2. De seed-stappen importeren maar één facade en query'en dan; dat triggert
   mapper-config terwijl cross-domein-relaties (bv. `Registration → Person`) niet
   resolven omdat het andere domein niet geladen is. `load_all_models()` lost dit
   op; deze test bewaakt beide gaten.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Scripts die tijdens deploy/tooling buiten check_imports.py om Python-imports doen.
DEPLOY_SCRIPTS = [
    "startup.sh",
    "seed_postal_codes.py",
    "seed_activities.py",
    "seed_pages.py",
    "seed_sponsors.py",
    "alembic/env.py",
]


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS)
def test_no_stale_app_models_reference(script):
    """Geen enkel deploy-/seed-/tooling-script mag nog `app.models.` importeren."""
    text = (BACKEND / script).read_text()
    assert "app.models." not in text, (
        f"{script} verwijst nog naar het verwijderde 'app.models.'-namespace; "
        "gebruik de domein-facade of app.domains.registry.load_all_models()."
    )


def test_seed_symbols_importable_from_facades():
    """De symbolen die startup.sh/seeds nodig hebben, bestaan op hun nieuwe pad."""
    from app.domains.mdm.api import PostalCode  # noqa: F401
    from app.domains.activities.api import (  # noqa: F401
        Activity,
        ActivityDate,
        Registration,
        ActivitySubRegistration,
    )
    from app.domains.cms.api import CmsPage  # noqa: F401


def test_registry_configures_all_mappers_in_isolation():
    """In een SCHONE interpreter (zoals startup.sh's `python -c`) moet de registry
    de volledige mapper-graaf configureren — vangt niet-resolvebare cross-domein-
    relationships (de `Person`-fout uit #449). Bewust een subprocess: in-proces zou
    de conftest `app.main` al geladen kunnen hebben, waardoor de smalle seed-context
    niet gereproduceerd wordt.
    """
    code = (
        "from app.domains.registry import load_all_models\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "load_all_models()\n"
        "configure_mappers()\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "load_all_models() + configure_mappers() faalde in een schone interpreter:\n"
        + result.stderr
    )
