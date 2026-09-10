"""#821 — a setting you configure per environment must actually reach the container.

The backend service has **no `env_file:`**: every variable is listed explicitly in the
`environment:` block of the compose files. Whatever is not there never gets in, however
neatly it sits in `.env.<env>`.

That went wrong three times, each time with a different name and each time silently:

| # | Variable | Consequence |
|---|---|---|
| #798 | `SEED_OPERATOR_EMAILS` | migration 087 granted OPERATOR to **nobody** |
| #821 | `PLATFORM_HOSTS` | the tenant cookie was set and never read; you silently switched afdeling |
| #821 | `TENANT_HOSTNAMES` | no consequence (yet) — no tenant on its own hostname |

The gate from #798 looked for `SEED_` names in migrations and did not cover the other
two. This one is more general, and above all it is **derived** rather than enumerated.

**The derivation.** A name in `.env.<env>.example` is by definition something you set
per environment — that file is the list somebody keeps next to their server. If that
same name is also a field on `Settings`, then the BACKEND reads it, and it belongs in
the backend service's `environment:` block. If it is not a Settings field
(`DB_PASSWORD`, `UMAMI_APP_SECRET`), it belongs to another service and it is enough
that the compose file knows about it.

So nobody has to maintain a list: document a variable for an environment, and this gate
demands that it actually arrives.

Broken on purpose to check that this test can go red: removed `PLATFORM_HOSTS` from
`docker-compose.prod.yml` → red, naming both the variable and the file.
"""
import ast
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "backend" / "app" / "config.py"
ENVIRONMENTS = ("hdev", "uat", "prod")


def _settings_fields() -> set[str]:
    """The field names of `Settings`, as ENV NAMES (pydantic reads them uppercased)."""
    tree = ast.parse(CONFIG.read_text())
    klass = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.ClassDef) and n.name == "Settings"), None)
    assert klass is not None, "class Settings not found in config.py"
    fields = {n.target.id.upper() for n in klass.body
              if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    assert len(fields) > 30, f"only {len(fields)} settings found — does this gate still read config.py?"
    return fields


def _documented(environment: str) -> set[str]:
    path = ROOT / f".env.{environment}.example"
    assert path.exists(), f"{path.name} is missing"
    names = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", path.read_text(), re.M))
    assert names, f"{path.name} documents no variable at all"
    return names


def _backend_environment(environment: str) -> set[str]:
    config = yaml.safe_load((ROOT / f"docker-compose.{environment}.yml").read_text())
    block = config["services"]["backend"]["environment"]
    return set(block) if isinstance(block, dict) else {r.split("=", 1)[0] for r in block}


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_every_documented_backend_setting_is_passed_through(environment):
    fields = _settings_fields()
    passed_through = _backend_environment(environment)

    missing = sorted(name for name in _documented(environment)
                     if name in fields and name not in passed_through)

    assert not missing, (
        f"these settings are in .env.{environment}.example and are read by the backend, "
        f"but docker-compose.{environment}.yml does not pass them through — so they "
        f"never reach the container: {missing}")


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_a_documented_non_backend_variable_is_used_somewhere(environment):
    """The counterpart, and without it the previous test would be too narrow.

    `DB_PASSWORD` and `UMAMI_APP_SECRET` are not `Settings` fields — they belong to the
    db and umami services. So they should NOT be in the backend block, but they must be
    used somewhere by the compose file. A name you document and nobody reads is a silent
    promise too.
    """
    fields = _settings_fields()
    content = (ROOT / f"docker-compose.{environment}.yml").read_text()

    unused = sorted(name for name in _documented(environment)
                    if name not in fields and name not in content)

    assert not unused, (
        f"these variables are in .env.{environment}.example but do not appear in "
        f"docker-compose.{environment}.yml: {unused}")
