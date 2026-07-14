"""Model-discovery-gate (#395 blok H): elk domains/*/models.py moet in
app/models/__init__.py geïmporteerd zijn, anders mist Alembic (en de
tenant-migratie-inventaris) die tabellen — zoals de workflow-modellen
overkwam vóór #406."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def test_alle_domain_models_in_discovery():
    bron = (APP / "models" / "__init__.py").read_text()
    geimporteerd = {
        node.module
        for node in ast.walk(ast.parse(bron))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    ontbrekend = []
    for models_py in sorted(APP.glob("domains/*/models.py")):
        domein = models_py.parent.name
        module = f"app.domains.{domein}.models"
        # cms/media/analytics lopen via hun facade (…api) — ook goed.
        facade = f"app.domains.{domein}.api"
        if module not in geimporteerd and facade not in geimporteerd:
            ontbrekend.append(module)
    assert not ontbrekend, f"Niet in model-discovery: {ontbrekend}"
