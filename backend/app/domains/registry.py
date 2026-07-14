"""Canonieke model-registry-loader (#449).

SQLAlchemy configureert mappers **lui**: pas bij de eerste query/inspect worden
alle mapped classes met elkaar verbonden. Cross-domein-relaties (bv.
``Registration.relationship("Person")`` van activities → membership) vereisen
daarom dat *elke* mapped class al geïmporteerd is vóór dat moment.

Dit is de ENE plek die alle domein- en kernel-modellen laadt. ``app.main`` laadt
ze al impliciet via zijn router-imports, maar smalle contexten — de seed-stappen
in ``startup.sh`` en ``alembic/env.py`` — importeren maar één facade en zouden
anders op een halve registry query'en. Die roepen daarom :func:`load_all_models`
aan zodat de registry compleet is.

Bewust dynamisch: elk domein met een ``models``-module wordt automatisch
meegenomen, zodat een nieuw domein niet vergeten kan worden.
"""
import importlib
import importlib.util
import pkgutil

import app.domains

# Kernel-modellen die niet onder app.domains vallen.
_KERNEL_MODEL_MODULES = (
    "app.kernel.tenant_config",
    "app.kernel.jobs",
)


def load_all_models() -> None:
    """Importeer alle mapped classes zodat SQLAlchemy's registry compleet is.

    Idempotent: herhaalde imports zijn no-ops (modulecache).
    """
    for module in _KERNEL_MODEL_MODULES:
        importlib.import_module(module)

    for info in pkgutil.iter_modules(app.domains.__path__, prefix="app.domains."):
        if not info.ispkg:
            continue
        models_module = f"{info.name}.models"
        # find_spec i.p.v. try/except ModuleNotFoundError: een domein zónder
        # models-module (bv. stt/audit) slaan we over, maar een échte import-fout
        # binnen een bestaande models-module laten we wél doorslaan.
        if importlib.util.find_spec(models_module) is not None:
            importlib.import_module(models_module)
