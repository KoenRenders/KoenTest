import importlib
import sys

MODULES = [
    "app.domains.payment_gateway.models",
    "app.domains.payment_gateway.service",
    "app.domains.payment_gateway.router",
    "app.domains.payment_status.models",
    "app.domains.payment_status.service",
    "app.domains.payment_status.router",
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
