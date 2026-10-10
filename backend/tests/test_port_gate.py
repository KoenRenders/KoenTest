"""The gate rules of a port, proven on a small world of their own (#1251).

A port is a synchronous command between two domains (`docs/architecture.md`
§3.2.1 step 2): a contract in `kernel/contracts/<owner>.py`, one handler in the
owner's domain, a caller that goes through `kernel.ports.call`. The rules live in
`test_rules_gate.py` (section 14, and the two places it points at); this file
holds what they hold.

The gate lands before the first port. So nothing here waits for one: every rule
is proven on a tree of a dozen files written into a temporary folder, which the
collectors walk instead of `app/`. Each proof is additive — one file of the small
world is replaced or added, the finding is read by its own words, and the world
without that change is in order (`test_the_small_world_is_in_order`), so a proof
cannot pass because the walk saw nothing.

On the repository itself there is one test, `test_the_ports_of_the_application`:
hard, without a baseline.
"""

from __future__ import annotations

import textwrap

import pytest

from tests import test_rules_gate as gate

pytestmark = pytest.mark.ui_agnostisch

_WORLD = {
    "kernel/ports.py": """
        class Port: ...

        def handles(port): ...

        def call(port, db): ...
    """,
    "kernel/events.py": """
        def subscribe(event): ...
    """,
    "kernel/contracts/forms.py": """
        from dataclasses import dataclass
        from typing import Optional

        from app.kernel.ports import Port

        @dataclass(frozen=True)
        class AttachedAnswer:
            field_id: int
            text: Optional[str] = None
            option_ids: tuple[int, ...] = ()

        @dataclass(frozen=True)
        class AttachedSubmission:
            submission_id: int

        @dataclass(frozen=True)
        class SubmitAttached(Port):
            form_id: int
            answers: tuple[AttachedAnswer, ...]
            submitter_name: str | None = None
    """,
    "kernel/contracts/mdm.py": """
        from dataclasses import dataclass
        from datetime import date
        from decimal import Decimal

        from app.kernel.ports import Port

        @dataclass(frozen=True)
        class HouseholdCreated:
            household_id: int
            person_ids: tuple[int, ...]

        @dataclass(frozen=True)
        class CreateHousehold(Port):
            street: str
            born: date | None
            fee: Decimal
    """,
    "domains/forms/api.py": "from .service import submit_attached\n",
    "domains/forms/service.py": """
        def submit_attached(db, form_id, answers):
            db.add(object())
            return 1
    """,
    "domains/forms/handlers.py": """
        from app.kernel.contracts.forms import AttachedSubmission, SubmitAttached
        from app.kernel.ports import handles

        from . import service

        @handles(SubmitAttached)
        def submit_attached(port: SubmitAttached, db) -> AttachedSubmission:
            return AttachedSubmission(service.submit_attached(db, port.form_id, port.answers))
    """,
    "domains/mdm/api.py": "from .service import create_household\n",
    "domains/mdm/service.py": """
        def create_household(db, street):
            db.add(object())
            return 1
    """,
    "domains/mdm/handlers.py": """
        from app.kernel.contracts.mdm import CreateHousehold, HouseholdCreated
        from app.kernel.ports import handles

        from . import service

        @handles(CreateHousehold)
        def create_household(port: CreateHousehold, db) -> HouseholdCreated:
            return HouseholdCreated(service.create_household(db, port.street), ())
    """,
    "domains/mail/api.py": "from .service import send_note\n",
    "domains/mail/service.py": """
        def send_note(db, text):
            db.add(object())
    """,
    "domains/activities/service.py": """
        from app.kernel import ports
        from app.kernel.contracts.forms import SubmitAttached

        def register(db, form_id):
            return ports.call(SubmitAttached(form_id=form_id, answers=()), db)
    """,
    "domains/membership/service.py": """
        from app.kernel.contracts.mdm import CreateHousehold
        from app.kernel.ports import call

        def sign_up(db, street):
            return call(CreateHousehold(street=street, born=None, fee=0), db)
    """,
}

#: What the small world's `api.py` files export that writes — `api_commands()` of
#: the gate derives this from the real tree and holds a floor of ten domains.
_COMMANDS = {
    ("forms", "submit_attached"): "domains/forms/service.py:3",
    ("mdm", "create_household"): "domains/mdm/service.py:3",
    ("mail", "send_note"): "domains/mail/service.py:3",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Build the small world and point the gate's walk at it. Call it with the
    files to add or replace; `None` takes a file away."""

    def build(**changes: str | None):
        files = {
            **_WORLD,
            **{name.replace("__", "/") + ".py": text for name, text in changes.items()},
        }
        app = tmp_path / "app"
        for name, text in files.items():
            if text is None:
                continue
            path = app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text), encoding="utf-8")
        monkeypatch.setattr(gate, "BACKEND", tmp_path)
        monkeypatch.setattr(gate, "APP", app)
        monkeypatch.setattr(gate, "DOMAINS", app / "domains")
        monkeypatch.setattr(gate, "_python_files", lambda: sorted(app.rglob("*.py")))
        monkeypatch.setattr(gate, "api_commands", lambda: _COMMANDS)

    return build


def _command_calls() -> dict[str, str]:
    # The collector is cached per process for the real tree; the small world asks
    # the function underneath.
    return gate.collect_command_calls_outside_handlers.__wrapped__()


def _one(findings, *words: str) -> str:
    """The one finding that carries every word — and that there is exactly one."""
    hits = [f for f in findings if all(word in f for word in words)]
    assert len(hits) == 1, (words, list(findings))
    return hits[0]


# ── The world without a fault ────────────────────────────────────────────────


def test_the_small_world_is_in_order(world):
    """Two ports, each with its handler at home, two callers through `call`: no
    finding of any of the four collectors. Every proof below changes one file of
    this world — so what it finds, it finds because of that file."""
    world()
    assert gate.collect_port_findings() == []
    assert _command_calls() == {}
    assert gate.collect_commit_in_handler() == {}
    assert gate.collect_network_in_handler() == {}
    # The walk saw the handlers it had nothing to say about.
    assert sorted(h.name for _p, _t, h in gate._event_handlers()) == [
        "create_household",
        "submit_attached",
    ]


# ── Rules 1 and 7: through the port is green, past it is red ─────────────────


def test_proof_a_command_past_the_port_stays_red(world):
    """Membership creating a household through `mdm.api` directly is a command
    call; the same through the port (the world as it stands) is none."""
    world(
        domains__membership__service="""
            from app.domains.mdm import api as mdm_api

            def sign_up(db, street):
                return mdm_api.create_household(db, street)
        """
    )
    found = _command_calls()
    assert list(found) == ["domains/membership/service.py::sign_up → mdm.api.create_household"]


# ── Rule 2: exactly one handler, in the owner's domain ───────────────────────


def test_proof_a_second_handler_is_red(world):
    world(
        domains__activities__handlers="""
            from app.kernel.contracts.forms import AttachedSubmission, SubmitAttached
            from app.kernel.ports import handles

            @handles(SubmitAttached)
            def also_submit(port: SubmitAttached, db) -> AttachedSubmission:
                return AttachedSubmission(1)
        """
    )
    findings = gate.collect_port_findings()
    _one(findings, "`SubmitAttached` has 2 handlers", "a port has exactly one")
    _one(findings, "domains/activities/handlers.py::also_submit", "the owner's domain")
    assert len(findings) == 2, findings


def test_proof_a_port_without_a_handler_is_red(world):
    world(domains__mdm__handlers=None)
    findings = gate.collect_port_findings()
    _one(findings, "port `CreateHousehold`", "has no handler", "domains/mdm/handlers.py")
    assert len(findings) == 1, findings


def test_proof_a_handler_of_what_is_no_port_is_red(world):
    """`@handles` on a class that is no `Port` of `kernel/contracts/` — an outcome,
    or a class of the domain itself."""
    world(
        domains__mail__handlers="""
            from app.kernel.contracts.forms import AttachedSubmission
            from app.kernel.ports import handles

            @handles(AttachedSubmission)
            def nothing(port, db) -> AttachedSubmission:
                return port
        """
    )
    findings = gate.collect_port_findings()
    _one(findings, "domains/mail/handlers.py::nothing", "is no `Port`")
    assert len(findings) == 1, findings


# ── Rule 3: a port handler does not commit and reaches no network ────────────


def test_proof_a_port_handler_that_commits_is_red(world):
    world(
        domains__forms__handlers="""
            from app.kernel.contracts.forms import AttachedSubmission, SubmitAttached
            from app.kernel.ports import handles

            @handles(SubmitAttached)
            def submit_attached(port: SubmitAttached, db) -> AttachedSubmission:
                db.commit()
                return AttachedSubmission(1)
        """
    )
    assert list(gate.collect_commit_in_handler()) == ["domains/forms/handlers.py::submit_attached"]


def test_proof_a_port_handler_that_reaches_the_network_is_red(world):
    """Through the service it calls, as the walk follows an event handler."""
    world(
        domains__forms__service="""
            import httpx

            def submit_attached(db, form_id, answers):
                httpx.post("https://example.org")
                return 1
        """
    )
    assert list(gate.collect_network_in_handler()) == ["domains/forms/handlers.py::submit_attached"]


# ── Rule 4: a port handler is no licence ─────────────────────────────────────

_INTO_A_THIRD_DOMAIN = """
    from app.domains.mail.api import send_note
    from app.kernel.contracts.forms import AttachedSubmission, SubmitAttached
    from app.kernel.{module} import {decorator}

    @{decorator}(SubmitAttached)
    def submit_attached(port: SubmitAttached, db) -> AttachedSubmission:
        send_note(db, "received")
        return AttachedSubmission(1)
"""


def test_proof_a_port_handler_that_commands_a_third_domain_is_red(world):
    world(domains__forms__handlers=_INTO_A_THIRD_DOMAIN.format(module="ports", decorator="handles"))
    assert list(_command_calls()) == [
        "domains/forms/handlers.py::submit_attached → mail.api.send_note"
    ]


def test_the_same_call_from_an_event_handler_is_free(world):
    """The asymmetry, held: the one word that differs from the proof above is the
    decorator. An event handler reacts to a fact; a port handler is a command from
    outside (the reason stands at the collector's exemption)."""
    world(
        domains__forms__handlers=_INTO_A_THIRD_DOMAIN.format(module="events", decorator="subscribe")
    )
    assert _command_calls() == {}


# ── Rule 5: a contract carries plain values ──────────────────────────────────

_CONTRACT = """
    from dataclasses import dataclass

    from app.domains.forms.models import Form
    from app.kernel.ports import Port

    @dataclass(frozen=True)
    class AttachedAnswer:
        field_id: int
        {inner}

    @dataclass(frozen=True)
    class AttachedSubmission:
        submission_id: int

    @dataclass(frozen=True)
    class SubmitAttached(Port):
        form_id: int
        answers: tuple[AttachedAnswer, ...]
        {field}
"""


@pytest.mark.parametrize(
    ("field", "offence"),
    [
        ("form: Form", "`Form`"),
        ("forms: tuple[Form, ...]", "`Form`"),
        ("form: Form | None = None", "`Form`"),
        ("form: 'Form'", "`Form`"),
        ("ids: list[int] = None", "`list`"),
        ("extra: dict = None", "`dict`"),
        ("anything = None", ""),
    ],
)
def test_proof_a_contract_that_carries_more_than_plain_values_is_red(world, field, offence):
    world(kernel__contracts__forms=_CONTRACT.format(field=field, inner="text: str"))
    findings = gate.collect_port_findings()
    if offence:
        _one(findings, "`SubmitAttached.", f"carries {offence}", "plain values")
    # An unannotated name is no field of a dataclass: nothing to judge, nothing found.
    assert len(findings) == (1 if offence else 0), findings


def test_proof_what_a_port_holds_is_judged_too(world):
    """The dataclass inside the tuple is part of the contract."""
    world(kernel__contracts__forms=_CONTRACT.format(field="note: str", inner="form: Form"))
    findings = gate.collect_port_findings()
    _one(findings, "`AttachedAnswer.form`", "carries `Form`")
    assert len(findings) == 1, findings


def test_proof_a_contract_with_a_method_is_red(world):
    """A contract is data only (master CLI, 9 October 2026): a `classmethod` that
    converts `Any` into the contract would let anything cross the port unseen."""
    converter = (
        "text: str\n\n        @classmethod\n        def of(cls, answer): return cls(1, answer.text)"
    )
    world(kernel__contracts__forms=_CONTRACT.format(field="note: str", inner=converter))
    findings = gate.collect_port_findings()
    _one(findings, "`AttachedAnswer.of` is a method", "data only")
    assert len(findings) == 1, findings


def test_proof_an_outcome_that_is_no_contract_is_red(world):
    world(
        domains__forms__handlers="""
            from app.kernel.contracts.forms import SubmitAttached
            from app.kernel.ports import handles

            @handles(SubmitAttached)
            def submit_attached(port: SubmitAttached, db) -> int:
                return 1
        """
    )
    findings = gate.collect_port_findings()
    _one(findings, "submit_attached returns `int`", "a dataclass of `kernel/contracts/`")
    assert len(findings) == 1, findings


# ── Rule 6: called from a service or a handler, never from a door ────────────


@pytest.mark.parametrize("door", ["admin_ui", "ui", "router", "register_router"])
@pytest.mark.parametrize(
    "the_import", ["from app.kernel.ports import call", "from app.kernel import ports"]
)
def test_proof_a_door_that_calls_a_port_is_red(world, door, the_import):
    world(
        **{
            f"domains__activities__{door}": f"""
                {the_import}

                def screen(db):
                    return None
            """
        }
    )
    findings = gate.collect_port_findings()
    _one(
        findings,
        f"domains/activities/{door}.py:2",
        "imports `kernel.ports`",
        "a router or a screen",
    )
    assert len(findings) == 1, findings


# ── A repository without a port ──────────────────────────────────────────────

_NO_PORT = {
    "kernel__contracts__forms": "class Submitted: ...\n",
    "kernel__contracts__mdm": "class Created: ...\n",
    "domains__forms__handlers": None,
    "domains__mdm__handlers": None,
    "domains__activities__service": "def register(db): ...\n",
    "domains__membership__service": "def sign_up(db): ...\n",
}


def test_a_world_without_a_port_is_in_order(world):
    world(**_NO_PORT)
    assert gate.collect_port_findings() == []


def test_proof_no_port_found_while_one_is_called_is_red(world):
    """ "Found nothing" is in order only when nothing asks for a port: a caller with
    no `Port` in `kernel/contracts/` means the walk lost the contracts."""
    world(**{**_NO_PORT, "domains__membership__service": _WORLD["domains/membership/service.py"]})
    findings = gate.collect_port_findings()
    _one(findings, "`kernel.ports` is imported", "defines no `Port`")
    assert len(findings) == 1, findings


# ── The repository itself ────────────────────────────────────────────────────


def test_the_ports_of_the_application():
    """Hard, without a baseline: every port has its one handler at home, a contract
    carries plain values, no door calls a port."""
    findings = gate.collect_port_findings()
    assert not findings, "\n".join(findings)
