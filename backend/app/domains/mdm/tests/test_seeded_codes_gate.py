"""Refuses a tenant code in the repository that equals a route's first segment · hard · since #1951.

A tenant's code is a path prefix that wins over the route (`resolve_request`).
Creating such a code is refused at run time (`mdm.tenant_service._check_code`);
this gate covers the codes the repository itself brings along, which never pass
that check on their way in:

- the fallback code map (`kernel.tenancy.TENANT_CODES`);
- the organisations the migrations seed (read from the migrated test database);
- the codes `seed_e2e.py` creates.

It cannot see a tenant an operator creates on an environment — the run-time
refusal guards that, and the startup report covers a route added later.

The gate counts before it judges: it must find the seeded codes, or its sources
broke and it would pass anything.

Broken on purpose (15 October 2026, by adding a line, put back):
`code="admin"` added to a `create_tenant` call in `seed_e2e.py` → the gate
failed naming `admin`.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4]

#: The code argument of a tenant created in the e2e seed.
_SEEDED = re.compile(r"""\bcode\s*=\s*["']([a-z0-9-]+)["']""")


def _seed_e2e_codes() -> set[str]:
    text = (BACKEND / "seed_e2e.py").read_text(encoding="utf-8")
    return set(_SEEDED.findall(text))


def test_no_code_the_repository_seeds_equals_a_route(db_session):
    import app.main  # noqa: F401  registers the route table
    from app.domains.mdm.models import Organization
    from app.kernel.route_table import colliding
    from app.kernel.tenancy import TENANT_CODES

    migrated = {code for (code,) in db_session.query(Organization.code).all() if code}
    seeded = _seed_e2e_codes()
    assert set(TENANT_CODES) <= migrated, (
        f"the migrations do not seed the fallback codes {sorted(TENANT_CODES)}: "
        "the gate's sources are broken"
    )
    assert seeded, "the gate finds no code in seed_e2e.py — its pattern is broken"

    found = colliding(set(TENANT_CODES) | migrated | seeded)
    assert not found, (
        f"a tenant code the repository seeds equals a route's first segment: {found} — "
        "that tenant would take the route away from every tenant (#1951)"
    )
