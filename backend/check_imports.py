import importlib
import sys

MODULES = [
    # Domain modules
    "app.domains.payment_gateway.models",
    "app.domains.payment_gateway.service",
    "app.domains.payment_gateway.router",
    "app.domains.payment_status.models",
    "app.domains.payment_status.service",
    "app.domains.payment_status.router",
    "app.domains.forms.router",
    "app.domains.forms.ui",
    "app.domains.workflow.ui",
    "app.domains.auth.api",
    "app.domains.auth.router",
    "app.domains.mail.api",
    "app.domains.mail.router",
    # Schemas
    "app.schemas.member",
    "app.schemas.family",
    "app.schemas.activity",
    # Routers
    "app.routers.members",
    "app.routers.activities",
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
