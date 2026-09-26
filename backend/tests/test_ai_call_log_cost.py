"""The AI log carries provider, API, status, duration and cost (#978).

The cost of a department is only as right as every call that writes into the
log, so these tests go through the real paths: the seam around the real Mistral
provider (only its HTTP call replaced), the OCR function, and the dictation
socket. The rows are read back over SQL, because the sink commits in its own
session on purpose.

Broken to see them red (measured, see each test):
- the `_log(... status="error" ...)` line in `GuardedProvider.complete` removed
  → `test_a_failed_call_is_logged_as_an_error` fails on an empty table;
- the `_log_ocr(...)` call in `_ocr_via_mistral` removed → both OCR tests fail;
- the `_log_ai_call(...)` call in the STT route removed → the dictation test
  fails;
- the `created_at < end` bound in `cost_per_period` removed → the period test
  counts the call on the first of the next month.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text as sql_text

from app.database import SessionLocal
from app.domains.chatbot.api import (AiCapability, AiProvider, GuardedProvider, SeamBlocked, admin_rules,
                                     cost_per_period, list_calls, month_period,
                                     sink_for)
from app.domains.chatbot.providers import mistral as mistral_mod
from app.domains.chatbot.providers.mistral import MistralProvider
from app.kernel.tenancy import DEFAULT_TENANT_ID

pytestmark = pytest.mark.ui_agnostisch

TENANT = DEFAULT_TENANT_ID
ANDER = TENANT + 40


@pytest.fixture
def leeg_logboek():
    def wis():
        eigen = SessionLocal()
        try:
            eigen.execute(sql_text("DELETE FROM ai.ai_call_log"))
            eigen.commit()
        finally:
            eigen.close()

    wis()
    yield
    wis()


def _rows(db):
    return db.execute(sql_text(
        "SELECT tenant_id, surface, capability, model, payload, provider, endpoint, "
        "provider_request_id, status, duration_ms, blocked_reason, cost_credits, "
        "cost_amount, cost_currency FROM ai.ai_call_log ORDER BY id"
    )).mappings().all()


class _Antwoord:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("fout", request=None, response=None)

    def json(self):
        return self._data


MISTRAL_ANTWOORD = {
    "id": "cmpl-e2e-1",
    "choices": [{"message": {"content": "klaar"}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
}


def _mistral(monkeypatch, antwoord):
    def post(*_a, **_k):
        if isinstance(antwoord, Exception):
            raise antwoord
        return antwoord

    monkeypatch.setattr(mistral_mod.httpx, "post", post)
    return GuardedProvider(MistralProvider(api_key="test", model="mistral-small-test"),
                           admin_rules(lambda: set(), capability="reporting"),
                           sink_for("bestuur@example.org"))


# ── The seam, around the real provider ───────────────────────────────────────

def test_a_call_that_went_through_names_provider_api_and_duration(
        db_session, leeg_logboek, monkeypatch):
    _mistral(monkeypatch, _Antwoord(MISTRAL_ANTWOORD)).complete(
        [{"role": "user", "content": "hoeveel inschrijvingen?"}])

    [rij] = _rows(db_session)
    assert rij["provider"] == "mistral"
    assert rij["endpoint"] == "chat.completions"
    assert rij["provider_request_id"] == "cmpl-e2e-1"
    assert rij["status"] == "ok"
    assert rij["duration_ms"] is not None and rij["duration_ms"] >= 0


def test_a_blocked_call_is_logged_as_blocked_with_its_provider(
        db_session, leeg_logboek, monkeypatch):
    provider = _mistral(monkeypatch, AssertionError("mag niet vertrekken"))
    with pytest.raises(SeamBlocked):
        provider.complete([{"role": "user", "content": "mail naar a@example.org"}])

    [rij] = _rows(db_session)
    assert (rij["provider"], rij["status"]) == ("mistral", "blocked")
    assert rij["blocked_reason"]


def test_a_failed_call_is_logged_as_an_error(db_session, leeg_logboek, monkeypatch):
    """The payload left, so the call counts — before #978 it left no row at all."""
    provider = _mistral(monkeypatch, httpx.ConnectTimeout("te traag"))
    with pytest.raises(httpx.ConnectTimeout):
        provider.complete([{"role": "user", "content": "hoeveel?"}])

    [rij] = _rows(db_session)
    assert (rij["provider"], rij["status"]) == ("mistral", "error")
    assert rij["duration_ms"] is not None


def test_an_unknown_status_is_refused():
    with pytest.raises(ValueError):
        sink_for()(surface="admin", capability="reporting", model="m", payload="",
                   status="misschien")


# ── Cost: stored, summed, per department ─────────────────────────────────────

def _beeld(tenant_id, **extra):
    velden = dict(surface="designstudio", capability="image", model="flux-2-pro",
                  payload="[prompt]", provider="bfl", endpoint="/v1/flux-2-pro",
                  cost_credits=4.5, cost_amount=0.045, cost_currency="usd",
                  output_megapixels=1.96, tenant_id=tenant_id)
    velden.update(extra)
    sink_for("ontwerper@example.org")(**velden)


def test_a_cost_is_stored_and_summed_for_its_own_department_only(
        db_session, leeg_logboek):
    _beeld(TENANT)
    _beeld(TENANT)
    _beeld(ANDER)

    start, end = month_period(date.today())
    [lijn] = cost_per_period(db_session, tenant_id=TENANT, start=start, end=end)

    assert (lijn.provider, lijn.capability, lijn.calls) == (
        AiProvider.BFL, AiCapability.IMAGE, 2)
    assert lijn.cost_credits == Decimal("9.0")
    assert lijn.cost_amounts == {"USD": Decimal("0.090")}


def test_currencies_are_never_added_together(db_session, leeg_logboek):
    _beeld(TENANT)
    _beeld(TENANT, cost_amount=0.05, cost_currency="EUR")

    start, end = month_period(date.today())
    [lijn] = cost_per_period(db_session, tenant_id=TENANT, start=start, end=end)
    assert lijn.cost_amounts == {"USD": Decimal("0.045"), "EUR": Decimal("0.05")}


def _op(moment: datetime):
    """A call at an exact moment — the sink always writes 'now'."""
    _beeld(TENANT)
    eigen = SessionLocal()
    try:
        eigen.execute(sql_text(
            "UPDATE ai.ai_call_log SET created_at = :t "
            "WHERE id = (SELECT max(id) FROM ai.ai_call_log)"), {"t": moment})
        eigen.commit()
    finally:
        eigen.close()


def test_the_period_counts_nothing_from_before_or_after(db_session, leeg_logboek):
    """The month in Belgian time: 00:30 on 1 October is October, although it is
    still September in UTC."""
    start, end = month_period(date(2026, 10, 15))
    assert start.utcoffset() == timedelta(hours=2)

    _op(start - timedelta(seconds=1))   # 30 September, 23:59:59
    _op(start)                          # 1 October, 00:00 — counts
    _op(start + timedelta(minutes=30))  # 1 October, 00:30 — counts
    _op(end - timedelta(seconds=1))     # 31 October, 23:59:59 — counts
    _op(end)                            # 1 November, 00:00

    [lijn] = cost_per_period(db_session, tenant_id=TENANT, start=start, end=end)
    assert lijn.calls == 3


def test_december_ends_in_the_next_year():
    start, end = month_period(date(2026, 12, 31))
    assert (start.year, start.month, end.year, end.month) == (2026, 12, 2027, 1)


def test_the_list_has_no_payload_and_shows_the_newest_first(db_session, leeg_logboek):
    _beeld(TENANT, model="eerste")
    _beeld(TENANT, model="tweede")
    _beeld(ANDER, model="elders")

    rows, verder = list_calls(db_session, tenant_id=TENANT, per_page=1)
    assert [r.model for r in rows] == ["tweede"] and verder
    assert not hasattr(rows[0], "payload")
    rows, verder = list_calls(db_session, tenant_id=TENANT, page=2, per_page=1)
    assert [r.model for r in rows] == ["eerste"] and not verder


# ── The migration's backfill ─────────────────────────────────────────────────

def _migratie_130():
    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "130_ai_call_log_provider_and_cost.py")
    spec = importlib.util.spec_from_file_location("migratie_130", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_labels_the_rows_that_were_there(db_session, leeg_logboek):
    """The suite migrates an empty database, so the backfill runs here on rows
    written the way the old code wrote them."""
    eigen = SessionLocal()
    try:
        # The pre-130 shape — '' for provider and capability — is what migration
        # 163 made impossible: its foreign keys refuse ''. This session sets the
        # key triggers aside to write the old rows; the backfill is what is
        # under test here, not the keys.
        eigen.execute(sql_text("SET LOCAL session_replication_role = replica"))
        for model, reden in (("mistral-small-latest", ""),
                             ("mistral-medium-latest", "een e-mailadres"),
                             ("recorder-1", "")):
            eigen.execute(sql_text(
                "INSERT INTO ai.ai_call_log (tenant_id, surface, capability, actor, "
                "model, payload, blocked_reason, provider, endpoint, "
                "provider_request_id, status) VALUES (:t, 'admin', '', '', :m, '', "
                ":r, '', '', '', '')"), {"t": TENANT, "m": model, "r": reden})
        for statement in _migratie_130().BACKFILL_SQL:
            eigen.execute(sql_text(statement))
        eigen.commit()
    finally:
        eigen.close()

    rows = [(r["model"], r["provider"], r["status"]) for r in _rows(db_session)]
    assert rows == [
        ("mistral-small-latest", "mistral", "ok"),
        ("mistral-medium-latest", "mistral", "blocked"),
        ("recorder-1", "", "ok"),
    ]


# ── The paths outside the chat seam ──────────────────────────────────────────

def test_ocr_is_logged_with_its_department(db_session, leeg_logboek, monkeypatch):
    import app.domains.media.extraction as mx

    monkeypatch.setattr(mx.httpx, "post", lambda *a, **k: _Antwoord(
        {"id": "ocr-1", "pages": [{"markdown": "Affiche"}]}))
    assert mx._ocr_via_mistral(b"png-bytes", "image/png", tenant_id=ANDER) == "Affiche"

    [rij] = _rows(db_session)
    assert (rij["tenant_id"], rij["capability"], rij["provider"], rij["endpoint"],
            rij["status"]) == (ANDER, "ocr", "mistral", "ocr", "ok")
    assert rij["provider_request_id"] == "ocr-1"
    assert "png-bytes" not in rij["payload"], "the document itself is not logged"


def test_an_ocr_call_is_logged_with_its_cost(db_session, leeg_logboek, monkeypatch):
    """#1212: Mistral charges OCR per page, and the row must say what it cost.

    Before this, the OCR rows had a count and no amount, so the AI cost screen
    added them up as nothing. The page count comes from the answer
    (`usage_info.pages_processed`), the price from `OCR_PRICE_PER_PAGE_USD`.

    Broken on purpose to check that this test can go red: `cost_amount` left
    out of the call in `_log_ocr` → the row has no amount and the month total
    has no USD line.
    """
    import app.domains.media.extraction as mx
    from app.config import settings

    monkeypatch.setattr(settings, "ocr_price_per_page_usd", 0.004)
    monkeypatch.setattr(mx.httpx, "post", lambda *a, **k: _Antwoord(
        {"id": "ocr-2", "pages": [{"markdown": "Een"}, {"markdown": "Twee"}],
         "usage_info": {"pages_processed": 3, "doc_size_bytes": None}}))
    mx._ocr_via_mistral(b"pdf-bytes", "application/pdf", tenant_id=TENANT)

    [rij] = _rows(db_session)
    assert rij["capability"] == "ocr"
    assert (rij["cost_amount"], rij["cost_currency"]) == (Decimal("0.012000"), "USD")

    start, end = month_period(date.today())
    [lijn] = cost_per_period(db_session, tenant_id=TENANT, start=start, end=end)
    assert lijn.capability is AiCapability.OCR
    assert lijn.cost_amounts == {"USD": Decimal("0.012000")}


def test_a_failed_ocr_is_logged_too(db_session, leeg_logboek, monkeypatch):
    import app.domains.media.extraction as mx

    monkeypatch.setattr(mx.httpx, "post", lambda *a, **k: _Antwoord({}, status=500))
    with pytest.raises(httpx.HTTPStatusError):
        mx._ocr_via_mistral(b"png", "image/png", tenant_id=TENANT)

    [rij] = _rows(db_session)
    assert (rij["capability"], rij["status"]) == ("ocr", "error")
    # #1212: no page count in the answer, so no cost — an estimate would be an
    # invented amount on the cost screen.
    assert rij["cost_amount"] is None and rij["cost_currency"] is None


def test_a_dictation_session_is_logged(client, db_session, leeg_logboek, monkeypatch):
    import json

    from app.config import settings
    from app.domains.stt import router as stt_mod

    monkeypatch.setattr(settings, "stt_mode", "native_first")
    monkeypatch.setattr(settings, "stt_provider", "mock")
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        ws.send_bytes(b"audio-chunk")
        ws.send_text(json.dumps({"type": "stop"}))
        while ws.receive_json()["type"] != "final":
            pass
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()

    [rij] = _rows(db_session)
    assert (rij["surface"], rij["capability"], rij["provider"], rij["status"]) == (
        "public", "dictation", "mock", "ok")
    assert rij["tenant_id"] == TENANT
    assert rij["payload"] == "[audio: 11 bytes, %d Hz]" % settings.stt_sample_rate
