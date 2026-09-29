"""#1305 — every function in `app.domains.activities` is typed, and stays typed.

`disallow_untyped_defs` is on for `app.domains.activities.*` in `pyproject.toml`:
CR-13 phase 1 did the two modules where the Registration aggregate's rules live,
#1305 the other 195 functions. mypy is what enforces it in CI; this gate holds the
two things that could quietly undo it:

- **the setting disappears**, or an override switches it off for one module — then
  mypy stays green and the next untyped function goes in unnoticed;
- **the count**: the gate reads the modules itself and counts the functions
  without a full annotation, and that count must be zero. It is the number the
  setting guards, measured without depending on how mypy is invoked.

A domain's tests are not the application (CR-13 R15) and are not counted.

Proven red (29 September 2026), additively:
- an override `module = "app.domains.activities.service"` with
  `disallow_untyped_defs = false` added to `pyproject.toml` → "switched off";
- `def _zz(x): return x` added to `activities/service.py` → "1 untyped function"
  naming it (mypy failed on it too).
"""

import ast
import fnmatch
import tomllib
from pathlib import Path

import pytest

from tests._bestanden import bestanden

pytestmark = pytest.mark.ui_agnostisch

BACKEND = Path(__file__).resolve().parents[1]
ACTIVITIES = BACKEND / "app" / "domains" / "activities"
PATTERN = "app.domains.activities.*"


def _overrides() -> list[dict]:
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["mypy"].get("overrides", [])


def _modules(override: dict) -> list[str]:
    module = override.get("module", [])
    return [module] if isinstance(module, str) else list(module)


def test_the_setting_is_on_for_all_of_activities():
    on = [o for o in _overrides() if PATTERN in _modules(o) and o.get("disallow_untyped_defs")]
    assert on, f"no mypy override sets disallow_untyped_defs for {PATTERN} (#1305)"


def test_no_override_switches_it_off_for_a_module():
    off = [
        module
        for o in _overrides()
        if o.get("disallow_untyped_defs") is False
        for module in _modules(o)
        if fnmatch.fnmatch(module, PATTERN) or module.startswith("app.domains.activities")
    ]
    assert not off, f"disallow_untyped_defs switched off for {off} (#1305)"


def _untyped(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        params = args.posonlyargs + args.args + args.kwonlyargs
        params += [a for a in (args.vararg, args.kwarg) if a is not None]
        missing = [a.arg for a in params if a.annotation is None and a.arg not in ("self", "cls")]
        if node.returns is None or missing:
            found.append(f"{path.relative_to(BACKEND)}:{node.lineno} {node.name}")
    return found


def test_no_function_in_activities_is_untyped():
    files = bestanden(
        (p for p in ACTIVITIES.rglob("*.py") if "tests" not in p.relative_to(ACTIVITIES).parts),
        wat="the modules of app.domains.activities",
        minstens=8,
    )
    untyped = [entry for path in files for entry in _untyped(path)]
    assert not untyped, f"{len(untyped)} untyped function(s) in activities:\n" + "\n".join(untyped)
