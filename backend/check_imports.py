"""Import smoke test: can every mounted module be imported at all?

This runs in two places, deliberately (#583):

* the **Docker build** (`backend/Dockerfile`) — a broken import stops the image
  from being produced, so nothing undeployable reaches a server;
* the **CI boot job** (`.github/workflows/backend-tests.yml`) — so the very same
  failure shows up on push instead of at deploy time.

Without that second place CI runs ahead of reality: in #581 `app.ui.settings_ui`
was removed (merged into `app.ui.tenants_ui`) while the list below still named
it. CI was green; only the HDEV deploy failed, in the build. What CI calls green
must be deployable.

MODULES is maintained by hand. `tests/test_check_imports_gate.py` guards against
an entry that no longer exists; deriving the list automatically is option B of
#583.
"""
import importlib
import sys

MODULES = [
    # Domain modules
    "app.domains.membership.api",
    "app.domains.payment.api",
    "app.domains.payment.router",
    "app.domains.payment.ui",
    "app.domains.media.api",
    "app.domains.media.router",
    "app.domains.media.ui",
    "app.domains.chatbot.router",
    "app.domains.chatbot.ui",
    "app.domains.chatbot.info_router",
    "app.domains.stt.router",
    "app.domains.cms.api",
    "app.domains.cms.ui",
    "app.domains.membership.ui",
    "app.domains.cms.router",
    "app.domains.mdm.router",
    "app.domains.forms.router",
    "app.domains.forms.ui",
    "app.domains.forms.admin_ui",
    "app.domains.workflow.ui",
    "app.domains.activities.api",
    "app.domains.activities.router",
    "app.domains.activities.ui",
    "app.domains.activities.admin_ui",
    "app.domains.auth.api",
    "app.domains.auth.router",
    "app.domains.auth.ui",
    "app.domains.auth.admin_ui",
    "app.domains.cms.admin_ui",
    "app.domains.media.admin_ui",
    "app.ui.changes_ui",
    "app.ui.system_ui",
    "app.ui.admin_api",
    "app.ui.tenants_ui",
    "app.domains.audit.api",
    "app.domains.audit.router",
    "app.domains.mdm.import_router",
    "app.domains.mdm.api",
    "app.domains.mdm.ui",
    "app.domains.mail.api",
    "app.domains.mail.router",
    "app.domains.mail.ui",
    # Schemas
    "app.domains.membership.schemas_member",
    "app.domains.membership.schemas_family",
    "app.schemas.activity",
    # Routers
    "app.domains.membership.register_router",
    "app.domains.membership.household_router",
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
