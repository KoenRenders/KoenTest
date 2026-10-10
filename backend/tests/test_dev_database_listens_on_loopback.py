"""#1889 — the development database listens on the loopback only.

`docker-compose.dev.yml` published the database as `"5432:5432"`. Docker reads
a mapping without an address as every address of the machine (measured on the
development machine on 10 October 2026: `0.0.0.0:5432` and `[::]:5432`), so
the shared development database answered on the local network — with the
compose file's well-known defaults for the user and the password. Nothing
needs that door: the backend and the helper containers of the local scripts
reach the database as `db:5432` inside the compose network, and what runs on
the host uses `localhost:5432`.

The gate reads the file, not a running container: a published database port
in `docker-compose.dev.yml` names a loopback address.

Proven red by adding (an addition, nothing existing was broken): a second
mapping `"5433:5432"` under the `db` service's `ports` — the test failed and
named `db: 5433:5432`; the added line was removed again.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PORT = "5432"
LOOPBACK = ("127.0.0.1:", "[::1]:")


def test_a_published_database_port_names_the_loopback():
    path = ROOT / "docker-compose.dev.yml"
    assert path.exists(), f"{path.name} does not exist — this gate guards nothing (#678)"
    services = yaml.safe_load(path.read_text())["services"]
    # A gate that looks nowhere is green for ever: the service and its ports.
    assert "db" in services, "no `db` service in docker-compose.dev.yml — this gate guards nothing"
    assert services["db"].get("ports"), (
        "the `db` service publishes no port — this gate guards nothing"
    )

    open_mappings = [
        f"{name}: {mapping}"
        for name, service in services.items()
        for mapping in map(str, service.get("ports") or [])
        if mapping.split("/")[0].rsplit(":", 1)[-1] == DATABASE_PORT
        and not mapping.startswith(LOOPBACK)
    ]
    assert not open_mappings, (
        "A database port is published on every address of the machine; "
        'publish it on the loopback ("127.0.0.1:5432:5432"):\n  ' + "\n  ".join(open_mappings)
    )
