"""Import smoke test: can every module under `app/` be imported at all?

This runs in two places, deliberately (#583):

* the **Docker build** (`backend/Dockerfile`) — a broken import stops the image
  from being produced, so nothing undeployable reaches a server;
* the **CI boot job** (`.github/workflows/backend-tests.yml`) — so the very same
  failure shows up on push instead of at deploy time.

Without that second place CI runs ahead of reality: in #581 `app.ui.settings_ui`
was removed (merged into `app.ui.tenants_ui`) while the hand-written module list
still named it. CI was green; only the HDEV deploy failed, in the build. What CI
calls green must be deployable.

The list used to be maintained by hand, which is what made that drift possible
and also left modules silently unchecked. It is now **derived** from the package
itself (option B of #583): every module under `app/` is discovered and imported,
so the check can neither name something that is gone nor miss something new.

`tests/test_check_imports_gate.py` guards the discovery against blind spots.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys

import app

# Modules that must not be imported by this check. Keep empty if at all possible;
# every entry is a blind spot. Document the reason and reference an issue.
SKIP: tuple[str, ...] = ()


def discover() -> list[str]:
    """Every importable module name under `app/`, the package itself included.

    `walk_packages` imports each package it descends into. A package whose
    `__init__` raises would otherwise be skipped silently, so failures during the
    walk are collected and reported as import errors like any other.
    """
    failed: list[str] = []
    names = ["app"]
    for info in pkgutil.walk_packages(app.__path__, prefix="app.", onerror=failed.append):
        names.append(info.name)
    return sorted(set(names + failed) - set(SKIP))


def main() -> int:
    errors: list[str] = []
    for module in discover():
        try:
            importlib.import_module(module)
            print(f"OK: {module}")
        except Exception as exc:  # noqa: BLE001 — report every failure, not just ImportError
            errors.append(f"ERROR: {module}: {exc}")
            print(f"ERROR: {module}: {exc}")

    if errors:
        print(f"\n{len(errors)} import error(s)")
        return 1
    print("\nAll imports OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
