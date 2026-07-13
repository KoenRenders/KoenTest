import importlib
import sys

MODULES = [
    # Domain modules
    "app.domains.membership.api",
    "app.domains.payment.api",
    "app.domains.payment.router",
    "app.domains.payment.ui",
    "app.domains.forms.router",
    "app.domains.forms.ui",
    "app.domains.workflow.ui",
    "app.domains.activities.api",
    "app.domains.activities.router",
    "app.domains.auth.api",
    "app.domains.auth.router",
    "app.domains.auth.ui",
    "app.domains.mdm.api",
    "app.domains.mdm.ui",
    "app.domains.mail.api",
    "app.domains.mail.router",
    "app.domains.mail.ui",
    # Schemas
    "app.schemas.member",
    "app.schemas.family",
    "app.schemas.activity",
    # Routers
    "app.routers.members",
    "app.routers.cms",
    "app.routers.admin",
    "app.routers.media",
    # Main app
    "app.main",
]

errors = []
for module in MODULES:
    try:
        importlib.import_module(module)
        print(f"OK: {module}")
    except Exception as e:
        errors.append(f"ERROR: {module}: {e}")
        print(f"ERROR: {module}: {e}")

if errors:
    print(f"\n{len(errors)} import error(s)")
    sys.exit(1)
else:
    print("\nAll imports OK")
