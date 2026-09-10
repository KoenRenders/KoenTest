"""#820 — HDEV has no Umami, and that is a decision.

Measured on 10 September 2026: the instance on HDEV had recorded its last visit on
**13 July 2026** and used 155.9 MiB. That 13 July is precisely the day HDEV became
server-rendered is no coincidence: the tracking script disappeared with the React exit
(#405) and came back with #808 only for environments that HAVE tenant settings. HDEV
deliberately has none, so that test traffic can never end up in the production figures.

So it was not only measuring nothing — it never will. Koen, 10 September 2026: *"we are
never going to use it."*

**Why a test here and not just a commit.** A removed service comes back the moment
someone copies a compose file from an environment where it does belong. This test does
not say "Umami is bad" but "on HDEV it measures nothing", and the second test says
straight away where it does belong. Without that second one, "removed everywhere" would
be green too, and that is a very different — wrong — outcome. This is explicitly not a
consolidation: that was rejected in #259, UAT and PROD each keep their own instance.

Broken on purpose to check that these tests can go red: put the service back in
`docker-compose.hdev.yml` → the first falls over; removed the service from
`docker-compose.uat.yml` → the second falls over.
"""
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]


def _stack(environment: str) -> dict:
    path = ROOT / f"docker-compose.{environment}.yml"
    assert path.exists(), f"{path.name} does not exist — this test guards nothing (#678)"
    return yaml.safe_load(path.read_text())


def test_hdev_runs_no_umami():
    config = _stack("hdev")

    assert "umami" not in config["services"], (
        "the umami service is back in the HDEV stack; it measures nothing there as long "
        "as HDEV has no tenant settings (#808)")
    ports = [p for service in config["services"].values()
             for p in (service.get("ports") or [])]
    assert not [p for p in ports if str(p).startswith("8082")], (
        "port 8082 is published on HDEV again")


@pytest.mark.parametrize("environment", ["uat", "prod"])
def test_uat_and_prod_keep_their_own_umami(environment):
    """The counterproof. #259 (merging into one instance) was deliberately rejected."""
    services = _stack(environment)["services"]

    assert "umami" in services, (
        f"{environment} no longer has a umami service; #820 is about HDEV and only "
        f"about HDEV")
    assert f"umami_{environment}" in str(services["umami"]), (
        f"{environment} does not point at its own database umami_{environment}")


def test_the_hdev_env_example_asks_for_no_umami_secret():
    """A secret for a service that does not run is one secret too many."""
    example = (ROOT / ".env.hdev.example").read_text()

    for line in example.splitlines():
        bare = line.strip()
        if bare.startswith("#") or "=" not in bare:
            continue
        assert not bare.startswith("UMAMI"), f"{bare.split('=')[0]} is still there"
