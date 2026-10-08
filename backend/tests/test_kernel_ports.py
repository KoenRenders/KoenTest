"""`kernel/ports.py` — a synchronous command between domains, with an answer
(`docs/architecture.md` §3.2.1 step 2; CR-13 phase 4c, #1251).

What the mechanism promises, each as its own test: one handler per port, the
outcome comes back, a refusal passes through untouched, and a port nobody
handles is a wiring fault — never a refusal.

Broken on purpose to check these can go red (run, then restored): the
`PortHandledTwice` check removed from `handles` → the second-handler test;
`call` wrapped in `try/except Exception: return None` → the refusal test (and
three recordings of `test_answer_ports_unchanged_1251.py`); `_same_function` made
to answer False → the same-function test; `call` answering None where no handler
is registered → the wiring-fault test.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.kernel import ports
from app.kernel.ports import Port, PortHandledTwice, PortNotHandled, call, handles, has_handler


@dataclass(frozen=True)
class Double(Port):
    number: int


@dataclass(frozen=True)
class Doubled:
    number: int


class TooLarge(ValueError):
    """The refusal of the test port's owner."""


@pytest.fixture(autouse=True)
def _the_registry_as_it_was():
    """These tests register handlers of their own; the app's stay as they were."""
    before = dict(ports._handlers)
    yield
    ports._handlers.clear()
    ports._handlers.update(before)


def _double(port: Double, db) -> Doubled:
    if port.number > 100:
        raise TooLarge("too large to double")
    return Doubled(port.number * 2)


def test_the_one_handler_answers_with_its_outcome():
    handles(Double)(_double)
    assert has_handler(Double)
    assert call(Double(21), db=None) == Doubled(42)


def test_the_handler_gets_the_callers_session():
    seen = []

    @handles(Double)
    def remember(port: Double, db) -> Doubled:
        seen.append(db)
        return Doubled(0)

    session = object()
    call(Double(1), session)
    assert seen == [session], "the handler does not run in the caller's transaction"


def test_a_refusal_passes_through_untouched():
    handles(Double)(_double)
    with pytest.raises(TooLarge, match="too large to double"):
        call(Double(101), db=None)


def test_a_second_handler_for_a_port_is_refused_at_registration():
    handles(Double)(_double)

    def another(port: Double, db) -> Doubled:
        return Doubled(0)

    with pytest.raises(PortHandledTwice, match="_double"):
        handles(Double)(another)
    assert call(Double(2), db=None) == Doubled(4), "the first handler was replaced"


def test_the_same_function_registered_again_is_the_same_handler():
    """A handler module loaded a second time registers its functions again; that
    is the same handler, not a second one."""
    handles(Double)(_double)
    handles(Double)(_double)
    assert call(Double(3), db=None) == Doubled(6)


def test_a_port_nobody_handles_is_a_wiring_fault_not_a_refusal():
    """`PortNotHandled` is a `RuntimeError`: no door may read it as a 4xx. A
    refusal is a `ValueError` or an `HTTPException` of the owner; this is neither."""
    from fastapi import HTTPException

    assert not has_handler(Double)
    with pytest.raises(PortNotHandled) as fault:
        call(Double(1), db=None)
    assert isinstance(fault.value, RuntimeError)
    assert not isinstance(fault.value, (ValueError, LookupError, HTTPException))
    assert "handlers.py" in str(fault.value), "the message does not say where to look"


def test_the_ports_of_forms_are_handled_once_the_app_is_loaded():
    """`app.main` imports every `handlers.py`; a port contract without its
    handler would fail at the first registration with answers, not at start-up."""
    import app.main  # noqa: F401 — registers the handlers
    from app.kernel.contracts.forms import SubmitAttached, UpdateAttached

    assert has_handler(SubmitAttached) and has_handler(UpdateAttached)
    assert ports._handlers[SubmitAttached].__module__ == "app.domains.forms.handlers"
    assert ports._handlers[UpdateAttached].__module__ == "app.domains.forms.handlers"
