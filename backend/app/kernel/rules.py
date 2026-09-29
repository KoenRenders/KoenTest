"""One home for every rule (CR-13, `docs/change_request_13_oo_foundation.md`).

Two registries the gates read, and the one flush listener that makes an
aggregate's `check()` fire on every ORM write. The rules themselves live on the
entities; this module only knows *where* they are.

**The flush listener (§B4.2).** An aggregate that carries a rule over several of
its own fields defines `check()` and is registered with `@aggregate`. Before
every flush, the listener calls `check()` on each new or changed registered
object. So the object says no on every ORM path — router, UI route, import,
seed, script — without anyone having to remember to call it, which is
requirement R2 of the change request word for word. `check()` must be cheap and
must never touch a session (§B4.1): it runs inside the flush, on what is already
loaded. It signals a broken rule by raising its domain's error.

A soft-deleted object is not checked: deleting a legacy row that breaks today's
rule must stay possible, and a deleted row takes part in nothing.

**The derived-value registry (§B4.3).** A derived value — a total, a balance, a
state — is computed once, by its owner, and only shown elsewhere. The registry
names that owner, today's function and the method it becomes, so the gate
*one owner per derived value* (phase 0c) can find a second computation.

Installed when this module is imported; `app/database.py` imports it, so every
session the application or the tests create carries the listener.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session

T = TypeVar("T", bound=type)

# ── Aggregates and their check() ─────────────────────────────────────────────

_AGGREGATES: set[type] = set()


def aggregate(cls: T) -> T:
    """Register an entity whose `check()` must hold on every flush.

    Refuses a class without a callable `check`: a registered aggregate that has
    nothing to check is a registration that promises what it does not do.
    """
    if not callable(getattr(cls, "check", None)):
        raise TypeError(f"{cls.__name__} is registered as an aggregate but has no check()")
    _AGGREGATES.add(cls)
    return cls


def aggregates() -> frozenset[type]:
    return frozenset(_AGGREGATES)


def unregister_aggregate(cls: type) -> None:
    """For tests that register a temporary aggregate and must leave no trace."""
    _AGGREGATES.discard(cls)


def _check_on_flush(session: Session, flush_context: Any, instances: Any) -> None:
    for obj in (*session.new, *session.dirty):
        if type(obj) not in _AGGREGATES:
            continue
        if getattr(obj, "deleted_at", None) is not None:
            continue
        obj.check()


def install_flush_checks() -> None:
    """Attach the listener to every `Session`. Idempotent."""
    if not event.contains(Session, "before_flush", _check_on_flush):
        event.listen(Session, "before_flush", _check_on_flush)


def uninstall_flush_checks() -> None:
    """For the test that proves the listener is what refuses (§B8 test 1b)."""
    if event.contains(Session, "before_flush", _check_on_flush):
        event.remove(Session, "before_flush", _check_on_flush)


install_flush_checks()


# ── Named exemptions ──────────────────────────────────────────────────────────
#
# A rule on an aggregate holds on every path; where one path may deliberately store
# what the rule refuses, the exemption is written down by name, with its reason, at
# the one place that grants it — never as a flag an entity reads from the request.
# It holds for the transaction the path runs in and is gone after its commit or
# rollback, so it cannot leak into the next request on a pooled session.

_EXEMPTIONS = "cr13_rule_exemptions"


def exempt(session: Session, rule: str, reason: str) -> None:
    """Let `rule` stand aside for this session's current transaction, because `reason`."""
    session.info.setdefault(_EXEMPTIONS, {})[rule] = reason


def exemption(obj: Any, rule: str) -> str | None:
    """The reason `rule` stands aside for the transaction `obj` is written in, if any.

    Reads the object's state, not the database: the session an object belongs to is
    bookkeeping, and asking it for its notes is no query (§B4.1).
    """
    from sqlalchemy import inspect as sa_inspect

    session = sa_inspect(obj).session
    if session is None:
        return None
    return session.info.get(_EXEMPTIONS, {}).get(rule)


def _end_exemptions(session: Session, *_args: Any) -> None:
    session.info.pop(_EXEMPTIONS, None)


for _moment in ("after_commit", "after_rollback"):
    if not event.contains(Session, _moment, _end_exemptions):
        event.listen(Session, _moment, _end_exemptions)


# ── Derived values and their owner ───────────────────────────────────────────


@dataclass(frozen=True)
class DerivedValue:
    """One derived value, the function that computes it today, and its home.

    `today` is a dotted path to the function that owns the computation now;
    `target` is the method it becomes in the phase named, by delegation first and
    moving second (§B4.3). The gate reads `today` until `target` exists.
    """

    name: str
    today: str
    target: str
    phase: int


_DERIVED: dict[str, DerivedValue] = {}


def derived_value(name: str, *, today: str, target: str, phase: int) -> DerivedValue:
    if name in _DERIVED:
        raise ValueError(f"derived value {name!r} registered twice — one owner per value")
    value = DerivedValue(name=name, today=today, target=target, phase=phase)
    _DERIVED[name] = value
    return value


def derived_values() -> dict[str, DerivedValue]:
    return dict(_DERIVED)


# The derived values that exist today (§B4.3). The others the change request
# names — `person.age`, `member.active_membership` — have no single owner yet;
# they are registered in the phase that gives them one.
# Phase 1: `Registration.total()` exists and delegates to this owner; the
# computation stays in `totals.py`, which also prices the quotes made before a
# registration exists (master CLI, 29 September 2026). So `today` stays the owner.
derived_value(
    "registration.total",
    today="app.domains.activities.totals.compute_registration_total",
    target="app.domains.activities.models.Registration.total",
    phase=1,
)
derived_value(
    "registration.state",
    today="app.domains.activities.service.registration_state",
    target="app.domains.activities.models.Registration.state",
    phase=1,
)
derived_value(
    "registration.balance",
    today="app.domains.payment.service.registration_balance",
    target="app.domains.activities.models.Registration.balance",
    phase=2,
)
derived_value(
    "payment_record.state",
    today="app.domains.payment.service.derived_status",
    target="app.domains.payment.models.PaymentRecord.state",
    phase=2,
)
