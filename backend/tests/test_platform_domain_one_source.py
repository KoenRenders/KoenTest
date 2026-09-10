"""#866 — one place for "this domain is the platform".

On PROD the platform domain came out on the tenant Raak Millegem instead of on the
landing page. Measured on the server: `.env.caddy` named the **subdomain** while
`PLATFORM_HOSTS` in `.env.prod` named the **apex** domain. Caddy served the one, the app
recognised the other, the request fell through the last line of `resolve_request` and
landed on the default tenant. On UAT the two were equal and it worked — which was the
proof that this was configuration and not code.

Two storage places for one fact drift apart; the only question is when. Same shape as
#860, and the same choice: **make it impossible instead of checking it.** The app variable
is the source and the proxy derives from it — that direction, because one shared Caddy
serves two environments with their own platform domain, so the value belongs per
environment, which is where it already lives.

Broken on purpose to check that these tests can go red: emptied `PLATFORM_HOSTS` in a
throwaway `.env.prod` → the derivation stops with a message naming the environment and the
file, and a caller under `set -e` aborts with exit code 1 instead of handing Caddy an empty
site address; and renamed the variable in `caddy/parts/sites-prod.caddy` → the gate below
falls over, because such a site address expands to nothing and takes the whole config down
with it.

The gate also produced a **false finding** on its first run, and the fix is in the code
rather than in this sentence: it flagged `PLATFORM_WWW_DOMAIN`, which exists only inside a
comment explaining that the block using it was removed. Comments are stripped before
scanning now — a finding about prose is not a finding about configuration.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "caddy" / "platform-domains.sh"
ENVIRONMENTS = ("uat", "prod")


def _derive(tmp_path, values: dict[str, str | None]):
    """Run the real script against throwaway checkouts and report what it exported."""
    for environment, value in values.items():
        checkout = tmp_path / environment
        checkout.mkdir()
        if value is not None:
            (checkout / f".env.{environment}").write_text(
                f"SECRET_KEY=x\nPLATFORM_HOSTS={value}\nDEBUG=false\n")

    env = dict(os.environ)
    env["UAT_CHECKOUT_DIR"] = str(tmp_path / "uat")
    env["PROD_CHECKOUT_DIR"] = str(tmp_path / "prod")
    return subprocess.run(
        ["bash", "-c", f'. "{SCRIPT}" && echo "UAT=$PLATFORM_UAT_DOMAIN" '
                       f'&& echo "PROD=$PLATFORM_PROD_DOMAIN"'],
        env=env, capture_output=True, text=True, timeout=60)


def test_the_proxy_domain_is_the_app_value(tmp_path):
    """The whole point: there is nothing to keep in sync, because it is one value."""
    done = _derive(tmp_path, {"uat": "platform.uat.example.test",
                              "prod": "platform.example.test"})

    assert done.returncode == 0, done.stderr
    assert "UAT=platform.uat.example.test" in done.stdout
    assert "PROD=platform.example.test" in done.stdout


def test_a_list_becomes_a_caddy_site_address(tmp_path):
    """`PLATFORM_HOSTS` is comma-separated; a Caddy site address separates hosts with a
    space. Both forms already exist, so this translates rather than inventing a third."""
    done = _derive(tmp_path, {"uat": "a.example.test,b.example.test",
                              "prod": "platform.example.test"})

    assert "UAT=a.example.test b.example.test" in done.stdout, done.stdout


def test_an_empty_value_stops_the_deploy_naming_the_environment(tmp_path):
    """Empty is more dangerous than wrong: an empty site address makes the WHOLE Caddy
    config invalid, so the proxy does not start and PROD goes down with it.

    The message has to say which environment and which file, or you are left guessing on a
    server at the moment the site is offline.
    """
    done = _derive(tmp_path, {"uat": "platform.uat.example.test", "prod": ""})

    assert done.returncode != 0
    assert "prod" in done.stderr and ".env.prod" in done.stderr, done.stderr
    assert "PROD=" not in done.stdout


def test_a_missing_env_file_stops_the_deploy_too(tmp_path):
    """The other way it goes missing: a checkout that is not where we looked."""
    done = _derive(tmp_path, {"uat": "platform.uat.example.test", "prod": None})

    assert done.returncode != 0
    assert ".env.prod" in done.stderr


def test_the_site_blocks_use_exactly_what_the_script_exports():
    """A derived gate over the files themselves.

    Rename the variable on one side and a site block expands to an empty address — which
    takes the entire config down, not just that block. This is the check that cannot be
    forgotten, because it reads both sides instead of trusting them.
    """
    exported = set(re.findall(r"^export (PLATFORM_\w+)", SCRIPT.read_text(), re.M))
    exported |= set(re.findall(r"^export ([\w ]+)$", SCRIPT.read_text(), re.M))
    exported = {n for blok in exported for n in blok.split() if n.startswith("PLATFORM_")}
    assert exported, "the script exports nothing — this gate would guard nothing (#678)"

    used = set()
    for environment in ENVIRONMENTS:
        parts = ROOT / "caddy" / "parts" / f"sites-{environment}.caddy"
        assert parts.exists(), f"{parts.name} is missing"
        # Comments out first. The first version of this gate flagged
        # `PLATFORM_WWW_DOMAIN`, which exists only in a sentence explaining that the
        # block using it was removed — a finding about prose, not about config.
        levend = "\n".join(r for r in parts.read_text().splitlines()
                            if not r.lstrip().startswith("#"))
        used |= set(re.findall(r"\{\$(PLATFORM_\w+)\}", levend))
    assert used, "no site block references a platform domain at all"

    assert used <= exported, (
        f"these site blocks use a variable the derivation does not export: "
        f"{sorted(used - exported)} — that site address expands to nothing and makes the "
        f"whole config invalid")


def test_the_compose_file_passes_them_into_the_container():
    """Exporting in the shell is not enough: Caddy reads its own container environment,
    so compose has to hand the values over — the same class of omission as #798 and #821,
    where a variable sat neatly in a file and never reached the container.
    """
    config = yaml.safe_load((ROOT / "docker-compose.caddy.yml").read_text())
    block = config["services"]["caddy"].get("environment") or {}
    names = set(block) if isinstance(block, dict) else {r.split("=", 1)[0] for r in block}

    for environment in ENVIRONMENTS:
        assert f"PLATFORM_{environment.upper()}_DOMAIN" in names, (
            f"the caddy service does not receive PLATFORM_{environment.upper()}_DOMAIN")


def test_the_example_env_no_longer_offers_a_second_place():
    """A second place to type it in is a second place for it to drift. The example file is
    what somebody copies when setting up an environment."""
    example = (ROOT / ".env.caddy.example").read_text()

    for line in example.splitlines():
        bare = line.strip()
        if bare.startswith("#") or "=" not in bare:
            continue
        assert not bare.startswith("PLATFORM_"), f"{bare.split('=')[0]} is still offered here"
