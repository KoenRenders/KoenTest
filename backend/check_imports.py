"""Quick sanity check: import every app module and report failures."""
import sys
import importlib

MODULES = [
    "app.config",
    "app.database",
    "app.auth",
    "app.limiter",
    "app.models",
    "app.schemas.activity",
    "app.schemas.auth",
    "app.schemas.cms",
    "app.schemas.family",
    "app.schemas.idea",
    "app.schemas.member",
    "app.routers.auth",
    "app.routers.activities",
    "app.routers.members",
    "app.routers.ideas",
    "app.routers.cms",
    "app.routers.admin",
    "app.main",
]

errors = []
for mod in MODULES:
    try:
        importlib.import_module(mod)
        print(f"  OK  {mod}")
    except Exception as e:
        print(f"  FAIL {mod}: {e}")
        errors.append(mod)

if errors:
    print(f"\n{len(errors)} module(s) failed to import.")
    sys.exit(1)
else:
    print("\nAll modules imported successfully.")
