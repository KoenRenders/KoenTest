"""Lint-gate taalbeleid (#407-T): nieuwe gebruikersteksten moeten door _().

AST-check: elke HTTPException(..., detail=<string-literal>) en elk
subject=<string-literal> in de mail-service moet een _()-aanroep zijn.
Dynamische details (str(exc), f-strings met louter interpolatie) blijven
toegestaan — het gaat om onvertaalde vaste teksten.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _bare_literal(node) -> bool:
    """Een kale string-literal met letters (geen _()-wrap, geen symbolen-only)."""
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and any(c.isalpha() for c in node.value))


def test_gebruikersteksten_gaan_door_gettext():
    overtredingen = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            naam = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if naam == "HTTPException":
                for kw in node.keywords:
                    if kw.arg == "detail" and _bare_literal(kw.value):
                        overtredingen.append(
                            f"{path.relative_to(APP.parent)}:{kw.value.lineno} "
                            f"detail zonder _(): {kw.value.value[:50]!r}")
            if naam == "_send":
                for kw in node.keywords:
                    if kw.arg == "subject" and _bare_literal(kw.value):
                        overtredingen.append(
                            f"{path.relative_to(APP.parent)}:{kw.value.lineno} "
                            f"mail-subject zonder _(): {kw.value.value[:50]!r}")
    assert not overtredingen, (
        "Onvertaalde gebruikersteksten (wrap in _() uit app.i18n):\n"
        + "\n".join(sorted(overtredingen)))
