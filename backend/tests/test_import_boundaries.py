"""Import-grens-test (#396) — de "import-linter" als pytest (architectuurdoc §8/§14-F).

Regels (laagmodel §8):
1. De kernel (app.kernel + app.database/app.config) importeert NOOIT uit
   domeinen, routers, services, models of schemas.
2. Domeinen importeren elkaars internals niet: app.domains.X mag uit
   app.domains.Y (X != Y) enkel ``...api`` importeren.
3. De oude wereld (routers/services) die in domein-internals grijpt staat op een
   expliciete, per fase krimpende allowlist — nieuw doodhout faalt de build.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# Reach-ins van vóór de modularisatie. Elke fase van epic #393 verwijdert regels;
# regels TOEVOEGEN mag alleen met een fase-verwijzing.
LEGACY_ALLOWLIST = {
    ("app.routers.chat", "app.domains.chatbot.service"),
    ("app.routers.chatbot_info", "app.domains.chatbot.context"),
    ("app.routers.stt", "app.domains.stt.guards"),
    ("app.routers.stt", "app.domains.stt.providers"),
    ("app.routers.chat", "app.domains.chatbot.context"),
    ("app.routers.chat", "app.domains.chatbot.providers"),
}

# Cross-domain-reach-ins van vóór de modularisatie (zelfde krimp-regel): de
# payments-fase (#401) en chatbot-fase (#404) vervangen deze door facades.
LEGACY_CROSS_DOMAIN = {
    # verhuisd uit de oude wereld met de router mee (4a #402); analytics/audit
    # krijgen hun facade in fase 4c (#404)
    ("app.domains.chatbot.context", "app.domains.payment.api"),
}

KERNEL_FORBIDDEN_PREFIXES = (
    "app.domains", "app.routers", "app.services", "app.models", "app.schemas",
)


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP.parent).with_suffix("")
    return ".".join(rel.parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _domain_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "domains"] and parts[2] != "__init__":
        return parts[2]
    return None


def test_import_boundaries():
    violations = []
    for path in APP.rglob("*.py"):
        module = _module_name(path)
        imports = _imports(path)

        for imp in imports:
            # Regel 1: kernel importeert niets uit de hogere lagen.
            if module.startswith("app.kernel") and imp.startswith(KERNEL_FORBIDDEN_PREFIXES):
                violations.append(f"KERNEL: {module} -> {imp}")

            # Regel 2: cross-domain enkel via de facade (…api).
            src, dst = _domain_of(module), _domain_of(imp)
            if (src and dst and src != dst and not imp.endswith(".api")
                    and (module, imp) not in LEGACY_CROSS_DOMAIN):
                violations.append(f"CROSS-DOMAIN: {module} -> {imp}")

            # Composer-uitzonderingen: main mount routers/ui/handlers,
            # models/__init__ doet model-discovery voor Alembic. Dat zijn de
            # bedoelde compositiepunten, geen reach-in.
            composer = (
                (module == "app.main" and imp.split(".")[-1] in ("router", "ui", "admin_ui", "info_router", "handlers", "workflow", "changes_ui", "system_ui"))
                or (module == "app.models.__init__" and imp.endswith(".models"))
            )

            # Regel 3: oude wereld -> domein-internals enkel via de allowlist.
            if not module.startswith("app.domains") and not module.startswith("app.kernel") and not composer:
                if dst and not imp.endswith(".api") and (module, imp) not in LEGACY_ALLOWLIST:
                    violations.append(f"REACH-IN (niet op allowlist): {module} -> {imp}")

    assert not violations, "Import-grenzen geschonden:\n" + "\n".join(sorted(violations))
