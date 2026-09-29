"""#1305 — typing `activities` changes no route: same response model, same OpenAPI.

`disallow_untyped_defs` asks every function in `app.domains.activities` for a
return type. On a FastAPI route that is not only a type: without an explicit
`response_model`, FastAPI takes the return annotation AS the response model, and
then validates and serialises the answer through it. A `-> dict` on a JSON route
changes what the route sends; on a screen it would add validation that was not
there (CR-13 R13: a behaviour change). So the routes get `-> HTMLResponse`,
`-> Response` or an explicit `response_model=None`, and this test proves nothing
moved.

The snapshot, `tests/snapshots/activities_routes.json`, was taken from master
`43ac7e05` before a single annotation was added: per route — the screens that
are not in the schema too — its endpoint, the response model FastAPI settled on,
its response class, and its OpenAPI operation. The test builds the same picture
from the running app and asks for it to be identical. A route that is really
meant to change regenerates the snapshot on purpose:

    python -m tests.test_activities_routes_unchanged

Proven red (29 September 2026), additively, before the screens were annotated:
`-> dict` added to `ui.activiteiten_page` (a screen without `response_model`)
→ "GET /activiteiten: response_model None → <class 'dict'>". FastAPI had taken
the annotation as the response model, which is exactly the change this test is
for. The same route with `-> HTMLResponse` leaves it at None.
"""

import json
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "activities_routes.json"

pytestmark = pytest.mark.ui_agnostisch


def routes() -> dict:
    """Every route an `app.domains.activities` module defines, as FastAPI sees it."""
    from app.main import app

    schema = app.openapi()
    out: dict = {}

    def walk(items, prefix: str = "") -> None:
        for item in items:
            if type(item).__name__ == "_IncludedRouter":
                walk(item.original_router.routes, prefix + (item.include_context.prefix or ""))
                continue
            if hasattr(item, "routes") and not hasattr(item, "endpoint"):
                walk(item.routes, prefix)
                continue
            endpoint = getattr(item, "endpoint", None)
            if endpoint is None or not endpoint.__module__.startswith("app.domains.activities"):
                continue
            path = prefix + item.path
            for method in sorted((item.methods or set()) - {"HEAD", "OPTIONS"}):
                out[f"{method} {path}"] = {
                    "endpoint": f"{endpoint.__module__}.{endpoint.__name__}",
                    "response_model": repr(getattr(item, "response_model", None)),
                    "response_class": getattr(
                        getattr(item, "response_class", None), "__name__", ""
                    ),
                    "openapi": schema.get("paths", {}).get(path, {}).get(method.lower()),
                }

    walk(app.routes)
    return json.loads(json.dumps(out, sort_keys=True, default=str))


def test_the_walk_sees_the_routes():
    found = routes()
    assert len(found) >= 60, f"only {len(found)} activities routes — the walk is blind"
    assert sum(1 for r in found.values() if r["openapi"]) >= 20, "no JSON route in the schema"


def test_every_activities_route_is_what_it_was():
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = routes()

    assert set(now) == set(before), (
        f"routes added {sorted(set(now) - set(before))}, gone {sorted(set(before) - set(now))}"
    )
    changed = {
        key: {
            field: (before[key][field], now[key][field])
            for field in before[key]
            if before[key][field] != now[key][field]
        }
        for key in before
        if before[key] != now[key]
    }
    assert not changed, (
        "a route changed — a return annotation became its response model?\n"
        + (json.dumps(changed, indent=1, ensure_ascii=False)[:4000])
    )


if __name__ == "__main__":
    SNAPSHOT.write_text(
        json.dumps(routes(), indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
