"""Ports: a synchronous command from one domain into another, with an answer
(`docs/architecture.md` §3.2.1 step 2, roadmap R10; CR-13 phase 4c, #1251).

An event reports a fact and waits for nobody. A port is for the other case: the
caller needs something done by another domain **and the outcome to go on** —
"store these answers and tell me their id". Then a call through that domain's
`api.py` couples the two; a port names the request in a contract both sides read.

How it works, on purpose as small as `events.py` beside it:

- A **contract** is a frozen dataclass in `kernel/contracts/<owner>.py` that
  subclasses `Port`. It carries plain values only — ids, text, dates, numbers,
  tuples of other contract dataclasses. No mapped object and no schema of a
  domain crosses a port: that is what lets a port become a network call the day
  a component is extracted.
- **Exactly one handler** per port, registered with `@handles(ThePort)` in the
  owner's `handlers.py`. A second, different handler for the same port raises at
  import; the same function registered again (its module loaded twice) is
  ignored.
- `call(port, db)` runs that handler **in the caller's transaction** and returns
  its outcome. The handler flushes and never commits; the door service that
  called commits.
- A **refusal** is the owner's own exception, raised by its service as before;
  `call` catches nothing. Each contract's docstring names what it refuses.
- No handler registered is not a refusal but a wiring fault: `PortNotHandled`, a
  `RuntimeError`. The module that registers the handler was not imported
  (`app.main` imports every `handlers.py`).

Use:
    @handles(SubmitAttached)
    def submit_attached(port: SubmitAttached, db: Session) -> AttachedSubmission: ...

    outcome = call(SubmitAttached(form_id=7, answers=(...), ...), db)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Port:
    """Base of every port contract; a concrete port is a frozen dataclass in
    `kernel/contracts/`, beside the events of the domain that handles it."""


class PortNotHandled(RuntimeError):
    """A port was called and no handler is registered for it — the module that
    registers it was not imported. A wiring fault, never a refusal: nothing may
    catch it to answer a 4xx."""


class PortHandledTwice(RuntimeError):
    """A second, different handler was registered for a port. A port has one."""


_handlers: dict[type, Callable[..., Any]] = {}


def _same_function(first: Callable, second: Callable) -> bool:
    return (first.__module__, first.__qualname__) == (second.__module__, second.__qualname__)


def handles(port_type: type[Port]) -> Callable[[Callable], Callable]:
    """Register THE handler of a port (decorator)."""

    def decorator(handler: Callable) -> Callable:
        present = _handlers.get(port_type)
        if present is not None and not _same_function(present, handler):
            raise PortHandledTwice(
                f"{port_type.__name__} is handled by {present.__module__}.{present.__qualname__}; "
                f"{handler.__module__}.{handler.__qualname__} cannot handle it too"
            )
        _handlers[port_type] = handler
        return handler

    return decorator


def call(port: Port, db: Session) -> Any:
    """Have the port's one handler do it, in the running transaction, and return
    its outcome. The handler's refusal passes through untouched."""
    handler = _handlers.get(type(port))
    if handler is None:
        raise PortNotHandled(
            f"no handler is registered for {type(port).__name__} — is the owner's "
            f"`handlers.py` imported (through `app.main`)?"
        )
    logger.debug("port %s -> %s", type(port).__name__, handler.__qualname__)
    return handler(port, db)


def has_handler(port_type: type[Port]) -> bool:
    """Whether the port's handler is registered."""
    return port_type in _handlers


def reset_handlers() -> None:
    """For tests only: empty the handler registry."""
    _handlers.clear()
