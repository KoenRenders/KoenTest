"""The text of a stored document is read by a job (#1251, the media ports).

A poster and a component's info document get their text read for Raakje (#206).
Until the ports that was a background task of the request: it ran after the
response whether or not the save was committed. It is a job now, enqueued by
media in the caller's transaction — so a save that is rolled back reads nothing,
and no port handler reaches the OCR provider.

Proven red (9 October 2026): `start_extraction` taken out of `store_file` → no
job, and the first test finds no text.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401 — the handlers of the ports and the job are loaded through the app
from app.domains.chatbot.api import ChatbotInfo
from app.domains.media import extraction as mx
from app.domains.media.service import EXTRACT_JOB
from app.kernel.contracts.media import StoreFile
from app.kernel.jobs import KernelJob, run_due_jobs
from app.kernel.ports import call
from tests.conftest import seed_activity_with_product
from tests.integration.test_media_pdf_preview import _pdf

pytestmark = pytest.mark.ui_agnostisch


def _store(db, *, kind: str, activity_id=None, component_id=None) -> int:
    return call(
        StoreFile(
            kind=kind,
            filename="document.pdf",
            content_type="application/pdf",
            content=_pdf(),
            activity_id=activity_id,
            component_id=component_id,
            title_base="Zomerbar - document",
        ),
        db,
    ).asset_id


def _jobs(db) -> list[KernelJob]:
    db.flush()
    return db.query(KernelJob).filter(KernelJob.name == EXTRACT_JOB).all()


@pytest.mark.parametrize("kind", ["activity_poster", "component_info"])
def test_a_stored_document_gets_its_text_read_by_the_job(db_session, monkeypatch, kind):
    monkeypatch.setattr(mx, "extract_document_text", lambda raw, ct, **_k: "Zomerbar op 1 juli.")
    activity, component, _product = seed_activity_with_product(db_session)
    asset_id = _store(db_session, kind=kind, activity_id=activity.id, component_id=component.id)

    # Stored, and nothing read yet: the port's handler only planned the reading.
    assert [job.payload for job in _jobs(db_session)] == [{"asset_id": asset_id, "force": False}]
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).count() == 0

    db_session.commit()
    run_due_jobs(db_session)
    row = db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).one()
    assert row.extracted_text == "Zomerbar op 1 juli."


def test_a_save_that_is_rolled_back_reads_nothing(db_session, monkeypatch):
    read = []
    monkeypatch.setattr(mx, "extract_document_text", lambda raw, ct, **_k: read.append(1) or "x")
    activity, _component, _product = seed_activity_with_product(db_session)
    db_session.commit()

    _store(db_session, kind="activity_poster", activity_id=activity.id)
    db_session.rollback()

    assert _jobs(db_session) == []
    assert run_due_jobs(db_session) == 0
    assert read == []


@pytest.mark.parametrize("kind", ["design_render", "newsletter_file"])
def test_a_file_that_is_no_document_for_raakje_starts_no_reading(db_session, kind):
    """A render and a letter's attachment were never read, and are not now."""
    _store(db_session, kind=kind)
    assert _jobs(db_session) == []
