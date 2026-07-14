"""Regressie op #449: de deploy-/seed-scripts mogen niet naar het verdwenen
`app.models.*`-namespace verwijzen.

Achtergrond: bij de v2.0-refactor (#393) verhuisden de modellen naar
`app.domains.<domein>.*`, maar `startup.sh` en enkele seed-scripts bleven op de
oude `app.models.*`-paden staan. Dat brak de backend-start (ModuleNotFoundError)
terwijl `check_imports.py` (dekt enkel `app.main`) en de pytest-suite groen
bleven — de inline `python -c`-imports in `startup.sh` worden door geen van beide
uitgevoerd. Deze test dekt precies dat gat.
"""
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# De scripts die tijdens een deploy buiten check_imports.py om Python-imports doen.
DEPLOY_SCRIPTS = [
    "startup.sh",
    "seed_postal_codes.py",
    "seed_activities.py",
    "seed_pages.py",
    "seed_sponsors.py",
]


@pytest.mark.parametrize("script", DEPLOY_SCRIPTS)
def test_no_stale_app_models_reference(script):
    """Geen enkel deploy-/seed-script mag nog `app.models.` importeren."""
    text = (BACKEND / script).read_text()
    assert "app.models." not in text, (
        f"{script} verwijst nog naar het verwijderde 'app.models.'-namespace; "
        "gebruik de domein-facade (bv. app.domains.mdm.api)."
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
