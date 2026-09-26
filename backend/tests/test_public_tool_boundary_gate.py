"""The public Raakje reaches no admin tool — not by spec, not by forged call (#1075).

Koen's rule, 20 September 2026: the public Raakje and the back-office one are the
same product, and *the only difference is the security on the public one, which
must be 100% closed: no information about members, payments, registrations or
forms.* That boundary exists — the public toolset is a separate allowlist, and
`test_public_tool_field_contract.py` fixes which fields its results may carry.
This gate is the keystone on top: it proves the boundary in both directions and
through the real caller.

- **The toolsets are disjoint.** Every tool pack in the code base is found by
  scanning for its `TOOL_SPECS` declaration — not from a list typed here, so a
  new pack enters the comparison the day it is written. The public pack's names
  must share nothing with any other pack's, and the public dispatcher must refuse
  every admin name *by the allowlist*, with the tool's name in the refusal. Not
  merely "an error": a pack that gained `run_report` as an unimplemented branch
  also returns an error, and that is exactly the drift this must catch (the
  lesson of #680 — test the reason, not the failure).
- **A public session cannot reach them, forged or not.** A scripted provider,
  wired in through the real `/raakje/vraag` route, asks for every admin tool
  with plausible arguments. Each answer the loop hands back to the model is the
  allowlist refusal, and the admin implementations — spied on — are never
  entered. The route is the caller, so a rewiring of the public loop onto the
  shared dispatcher would fail here even if the allowlist itself stayed intact.

Broken on purpose, restored after: the `run_report` spec appended to the public
`TOOL_SPECS` → the disjointness test fails naming `run_report`, the refusal test
fails because the public dispatcher now answers "niet-geïmplementeerde tool"
instead of the allowlist refusal, and the route test fails on that same answer.
"""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from app.domains.chatbot.providers.base import AssistantMessage, ToolCall
from app.domains.chatbot.tools import ALLOWED_TOOLS as PUBLIC_TOOLS
from app.domains.chatbot.tools import TOOL_SPECS as PUBLIC_SPECS
from app.domains.chatbot.tools import execute_tool as public_dispatch

APP = Path(__file__).resolve().parents[1] / "app"
PUBLIC_MODULE = "app.domains.chatbot.tools"

# Arguments a forger would send: real object keys, so a dispatcher that let the
# call through would actually run a report on members and payments.
FORGED_ARGUMENTS = {
    "run_report": {"objects": ["member", "payment_amount"], "layout": "detail"},
    "list_values": {"object": "payment_status"},
}


def _tool_packs() -> dict[str, set[str]]:
    """Every `TOOL_SPECS` in the code base, by module — found, not listed."""
    packs: dict[str, set[str]] = {}
    for path in APP.rglob("*.py"):
        if not re.search(r"^TOOL_SPECS\b", path.read_text(), re.MULTILINE):
            continue
        module = ".".join(("app",) + path.relative_to(APP).with_suffix("").parts)
        specs = importlib.import_module(module).TOOL_SPECS
        packs[module] = {spec["function"]["name"] for spec in specs}
    assert PUBLIC_MODULE in packs, "the public pack was not found; the scan is wrong"
    assert len(packs) >= 2, (
        "only one tool pack found — the admin pack is missing from the scan, so "
        "this gate would compare the public set with nothing (#678)")
    for module, names in packs.items():
        assert names, f"{module} declares an empty TOOL_SPECS; nothing to compare"
    return packs


def _admin_tools() -> set[str]:
    return set().union(*(names for module, names in _tool_packs().items()
                         if module != PUBLIC_MODULE))


def _refusal(name: str) -> str:
    """The allowlist's own refusal — the reason, not just a failure."""
    return f"Onbekende of niet-toegelaten tool: {name}"


# ── The toolsets are disjoint ────────────────────────────────────────────────

def test_the_public_toolset_holds_no_admin_tool():
    shared = PUBLIC_TOOLS & _admin_tools()
    assert not shared, (
        "these admin tools are in the public Raakje's toolset: "
        f"{sorted(shared)} — the public bot must not be able to look up members, "
        "payments, registrations or forms")
    assert {spec["function"]["name"] for spec in PUBLIC_SPECS} == PUBLIC_TOOLS


def test_the_public_dispatcher_refuses_every_admin_tool_by_name(db_session):
    admin = _admin_tools()
    assert admin >= {"run_report", "list_values"}, "the reporting tools are not in the scan"
    for name in sorted(admin):
        out = json.loads(public_dispatch(name, FORGED_ARGUMENTS.get(name, {}), db_session))
        assert out == {"error": _refusal(name)}, (
            f"{name}: the public dispatcher answered {out!r} instead of the "
            "allowlist refusal — is it in the allowlist, or did the refusal text move?")


# ── A public session cannot reach them, forged or not ───────────────────────

class Forger:
    """A provider that asks for every admin tool, then answers."""

    # A stand-in logs as the `mock` provider: the AI log only takes known codes
    # (CR-12 phase 4), and a fake name would lose the row to the seam's except.
    name = "mock"
    model = "forger-1"

    def __init__(self, names: list[str]):
        self.names = names
        self.calls: list[list[dict]] = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(m) for m in messages])
        if len(self.calls) == 1:
            return AssistantMessage(tool_calls=[
                ToolCall(id=f"forged-{i}", name=name,
                         arguments=FORGED_ARGUMENTS.get(name, {}))
                for i, name in enumerate(self.names)])
        return AssistantMessage(content="klaar", usage={"prompt": 1, "completion": 1})


@pytest.fixture
def spied_admin_tools(monkeypatch):
    """The admin implementations, replaced by spies that record and refuse."""
    from app.domains.reporting import assistant

    reached: list[str] = []

    def _spy(name):
        def _entered(*args, **kwargs):
            reached.append(name)
            raise AssertionError(f"{name} was entered from the public Raakje")
        return _entered

    monkeypatch.setattr(assistant, "run_report", _spy("run_report"))
    monkeypatch.setattr(assistant, "list_values", _spy("list_values"))
    return reached


def test_a_public_session_cannot_reach_an_admin_tool_even_when_forged(
        client, db_session, monkeypatch, spied_admin_tools):
    from app.config import settings
    from app.domains.chatbot import providers

    admin = sorted(_admin_tools())
    forger = Forger(admin)
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(providers, "get_provider", lambda model="": forger)

    answer = client.post("/raakje/vraag",
                         data={"vraag": "Hoeveel lidgeld staat er nog open?"})

    assert answer.status_code == 200, answer.text[:300]
    assert len(forger.calls) == 2, "the loop did not come back after the forged calls"
    # What the loop handed back to the model for each forged call: the refusal,
    # and nothing that a tool could have produced.
    tool_messages = {m["name"]: json.loads(m["content"])
                     for m in forger.calls[1] if m.get("role") == "tool"}
    assert set(tool_messages) == set(admin), sorted(tool_messages)
    for name in admin:
        assert tool_messages[name] == {"error": _refusal(name)}, (
            f"{name}: the public loop handed the model {tool_messages[name]!r}")
    assert spied_admin_tools == [], (
        f"admin tools entered from the public route: {spied_admin_tools}")
    for name in admin:
        assert name not in answer.text, f"the refusal leaked the tool name {name} to the page"
