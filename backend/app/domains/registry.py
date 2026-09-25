"""Canonieke model-registry-loader (#449).

SQLAlchemy configureert mappers **lui**: pas bij de eerste query/inspect worden
alle mapped classes met elkaar verbonden. Cross-domein-relaties (bv.
``Registration`` → ``Person``, ``ChatbotInfo`` → ``MediaAsset``) vereisen daarom
dat *elke* mapped class al geïmporteerd is vóór dat moment.

Dit is de ENE canonieke plek die alle domein- + kernel-modellen laadt. ``app.main``
(via ``app.models``, dat hierheen shimt), ``alembic/env.py`` en de seed-/startup-
stappen roepen :func:`load_all_models` aan zodat de registry compleet is.

Discovery via de **filesystem-glob** i.p.v. ``pkgutil``: namespace-packages zonder
``__init__.py`` (zoals ``app/domains/media``) worden door ``pkgutil.iter_modules``
NIET opgesomd, maar wél door de glob — zo kan geen enkel domein-model gemist
worden (dat gebeurde met media: MediaAsset bleef ongeregistreerd, #449).
"""
import importlib
from pathlib import Path

# Kernel-modellen die niet onder app/domains/ vallen.
_KERNEL_MODEL_MODULES = (
    "app.kernel.tenant_config",
    "app.kernel.jobs",
)

_DOMAINS_DIR = Path(__file__).resolve().parent


def load_all_models() -> None:
    """Importeer alle mapped classes zodat SQLAlchemy's registry compleet is.

    Idempotent: herhaalde imports zijn no-ops (modulecache).
    """
    for module in _KERNEL_MODEL_MODULES:
        importlib.import_module(module)

    for models_file in sorted(_DOMAINS_DIR.glob("*/models.py")):
        importlib.import_module(f"app.domains.{models_file.parent.name}.models")

    # CR-12: de codelijsten horen bij dezelfde lading. De gates itereren over de
    # registry, dus een lijst die nergens geïmporteerd wordt is een lijst die
    # nergens gecontroleerd wordt — en dat zou precies de stille vorm zijn die
    # deze change request wegneemt. Na de modellen, want een declaratie noemt de
    # twee ORM-klassen van haar tabellen.
    from app.kernel.codes import load_all_code_lists

    load_all_code_lists()
