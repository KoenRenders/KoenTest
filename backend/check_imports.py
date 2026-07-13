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
    "app.domains.analytics.api",
    "app.domains.analytics.ui",
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
    "app.routers.admin",
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
