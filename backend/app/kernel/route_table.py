"""The first path segments the application answers on — read from its own route table (#1951).

A request's tenant is resolved from its path first (`tenancy.resolve_request`):
when the first segment equals a tenant's code, that tenant is taken and the
segment is stripped, on every host. So a tenant whose code equals the first
segment of one of the application's routes takes that route away from every
tenant — `admin` the back office, `api` the payment provider's webhook — at once
and without an error.

The reserved words are derived from the route table at the moment they are
asked for, never kept as a list beside it: a route added later is reserved by
existing. A path parameter as the first segment (the CMS's `/{slug}`) reserves
nothing here — what it would reserve is data, not a route.

The kernel does not import `app.main`; `app.main` registers its application here
once, after the last route. Asking before that is refused: an empty set would
read as "nothing collides".
"""

from __future__ import annotations

from typing import Any, Iterable

_app: Any = None


def register(app: Any) -> None:
    """Called once by `app.main`, after the last route and mount."""
    global _app
    _app = app


def _paths(items, prefix: str = ""):
    """Every route's and mount's full path. FastAPI 0.137 keeps an included
    router as an `_IncludedRouter` with its own routes and prefix, and no path
    of its own — the same walk `tests/test_rules_gate.py` makes."""
    for item in items:
        if type(item).__name__ == "_IncludedRouter":
            yield from _paths(
                item.original_router.routes, prefix + (item.include_context.prefix or "")
            )
            continue
        path = getattr(item, "path", None)
        if path is None and hasattr(item, "routes"):
            yield from _paths(item.routes, prefix)
            continue
        yield prefix + (path or "")


def reserved_segments() -> frozenset[str]:
    """The first segment of every route and mount, lower case."""
    if _app is None:
        raise RuntimeError("the route table is not registered; import app.main first (#1951)")
    found = set()
    for path in _paths(_app.routes):
        first = path.lstrip("/").split("/", 1)[0].lower()
        if first and not first.startswith("{"):
            found.add(first)
    return frozenset(found)


def colliding(codes: Iterable[str]) -> list[str]:
    """The codes, of those given, that equal a reserved segment — sorted."""
    reserved = reserved_segments()
    return sorted({code.lower() for code in codes if code and code.lower() in reserved})
