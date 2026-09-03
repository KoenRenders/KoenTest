"""Guard on the hand-maintained module list in `check_imports.py` (#583).

`check_imports.py` imports every module it lists. That list is written by hand,
so a rename or a removal can leave a dead entry behind — which used to surface
only in the Docker build, i.e. at deploy time (#581, `app.ui.settings_ui`).

Two safety nets now cover that: CI runs `check_imports.py` itself in the boot
job, and this test fails fast with a precise message about *which* entry rotted.
Completeness of the list (every module present) is option B of #583 and is not
asserted here.

The file is parsed, never imported: importing it would execute the whole smoke
test at collection time, which needs an app environment pytest does not set up.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CHECK_IMPORTS = BACKEND / "check_imports.py"


def _listed_modules() -> list[str]:
    tree = ast.parse(CHECK_IMPORTS.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == "MODULES" for t in targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"No MODULES list found in {CHECK_IMPORTS}")


def _exists(module: str) -> bool:
    """A dotted name resolves to either a module file or a package directory."""
    base = BACKEND.joinpath(*module.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def test_module_list_is_not_empty():
    modules = _listed_modules()
    assert len(modules) > 20, f"MODULES suspiciously short ({len(modules)} entries)"


def test_no_module_in_the_list_has_disappeared():
    stale = [m for m in _listed_modules() if not _exists(m)]
    assert not stale, (
        "check_imports.py names modules that no longer exist on disk — the Docker "
        "build (and therefore the deploy) will fail on these:\n  "
        + "\n  ".join(stale)
    )


def test_no_duplicate_entries():
    modules = _listed_modules()
    dupes = sorted({m for m in modules if modules.count(m) > 1})
    assert not dupes, "Duplicate entries in MODULES: " + ", ".join(dupes)
