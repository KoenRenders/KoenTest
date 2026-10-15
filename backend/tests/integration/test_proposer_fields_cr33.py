"""The activity proposer hands the fiche as fields of the register (CR-33 T7).

The call carries the fiche as the port rendered it — the register's words, a block in place of
the mark — and not as lines the proposer formatted itself; a key the register refuses stops the
call before anything is sent. Each test can go red for its own reason: the proposer formatting
its own `Naam:` line again, the fiche holding a key that is not public, a refusal that lets the
call through.
"""

import json
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.domains.activities import proposer
from app.domains.chatbot.api import FIELDS_MARK, Field, FieldRefused
from app.domains.chatbot.models import AiCapability
from app.domains.chatbot.providers.base import AssistantMessage, LLMProvider
from app.domains.chatbot.seam import GuardedProvider, admin_rules
from app.kernel.attributes import AiExposure, attribute


class Recorder(LLMProvider):
    name = "mock"
    model = "recorder"

    def __init__(self) -> None:
        self.asked: list[list[dict]] = []

    def complete(self, messages, tools=None, tool_choice=None, json_answer=False):
        self.asked.append([dict(m) for m in messages])
        return AssistantMessage(content=json.dumps({"reply": "Klaar."}))


@pytest.fixture
def recorder(monkeypatch):
    inner = Recorder()

    def _provider(db, actor):
        return GuardedProvider(
            inner,
            admin_rules(
                lambda: set(), capability=AiCapability.ACTIVITY_DRAFTING, scan_prompt_names=False
            ),
        )

    monkeypatch.setattr(proposer, "_provider", _provider)
    return inner


def _standing():
    return proposer.Standing(
        name="Herfstwandeling",
        location="Dorpsplein",
        description="Een stevige wandeling.",
        dates=[
            SimpleNamespace(
                start_date=date(2026, 11, 14),
                end_date=None,
                start_time=time(9, 30),
                end_time=None,
            )
        ],
    )


def test_every_key_of_the_fiche_is_public():
    """The fiche is the activity's public face: nothing in it needs a classification
    beyond `public`, and every key resolves in the register."""
    for key in proposer.RECORD_KEYS:
        assert attribute(key).ai_exposure is AiExposure.PUBLIC, key


def test_the_call_carries_the_fiche_as_the_port_rendered_it(db_session, recorder):
    proposer.propose(
        db_session,
        SimpleNamespace(),
        request="Stel een omschrijving voor.",
        actor="s@example.org",
        standing=_standing(),
    )
    sent = json.dumps(recorder.asked[0], ensure_ascii=False)
    assert FIELDS_MARK not in sent, "the mark was sent as it stands"
    assert "Herfstwandeling" in sent and "2026-11-14" in sent and "09:30" in sent
    assert f"{attribute('activities.activity.name').text}: Herfstwandeling" in sent
    assert "Naam: Herfstwandeling" not in sent, "the proposer formatted its own line again"


def test_a_key_the_register_refuses_stops_the_call_before_it_is_sent(
    db_session, recorder, monkeypatch
):
    monkeypatch.setattr(
        proposer,
        "record_fields",
        lambda activity: [Field("activities.activity.board_notes", "intern geheugensteuntje")],
    )
    with pytest.raises(FieldRefused) as refused:
        proposer.propose(
            db_session,
            SimpleNamespace(),
            request="Stel iets voor.",
            actor="s@example.org",
            standing=_standing(),
        )
    assert recorder.asked == [], "the call was made"
    assert "geheugensteuntje" not in str(refused.value), "a refusal never names the value"
