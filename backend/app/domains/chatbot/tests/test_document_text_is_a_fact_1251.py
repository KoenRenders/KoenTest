"""The chatbot keeps the text media read of a document, and answers whether it has it
(CR-13 phase 4d, #1251).

Two things the chatbot offers media's reading job since the cut: a read
(`has_extracted_text`) and a subscription to the fact `DocumentTextExtracted`.
The job's whole road is recorded in
`tests/integration/test_extracted_text_unchanged_1251.py`; these hold the two
halves on their own, with the fact published the way the job publishes it.

Red proofs, one replacement each, the tree as before afterwards — the counts
stand in the pull request.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domains.chatbot.api import has_extracted_text
from app.domains.chatbot.models import ChatbotInfo
from app.kernel.contracts.media import DocumentTextExtracted
from app.kernel.events import has_subscribers, publish

MOMENT = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
#: No asset stands behind these ids: the row's link to media is a plain number
#: for the chatbot, which is the point of the cut.
ASSET = 880_001


def _row(db, asset_id=ASSET):
    return db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).one_or_none()


def _extracted(db, text: str, *, title="Affiche", asset_id=ASSET) -> None:
    fact = DocumentTextExtracted(asset_id=asset_id, title=title, text=text, extracted_at=MOMENT)
    publish(fact, db)


def test_the_application_listens_for_the_fact():
    """The job refuses to publish into silence; this is what it asks."""
    assert has_subscribers(DocumentTextExtracted)


def test_a_document_read_for_the_first_time_gets_its_row(db_session):
    assert has_extracted_text(db_session, ASSET) is False

    _extracted(db_session, "Breng stevige schoenen mee.")

    row = _row(db_session)
    assert (row.title, row.extracted_text) == ("Affiche", "Breng stevige schoenen mee.")
    assert row.extracted_at == MOMENT
    assert has_extracted_text(db_session, ASSET) is True


def test_a_second_reading_replaces_the_text_and_nothing_else(db_session):
    _extracted(db_session, "Eerste lezing.")
    row = _row(db_session)
    row.title = "Eigen titel"
    row.text_override = "Handmatig gecorrigeerd."
    row.text_addition = "Honden welkom."
    row.is_active = False
    db_session.flush()

    _extracted(db_session, "Tweede lezing.", title="Andere titel")

    db_session.expire_all()
    row = _row(db_session)
    assert row.extracted_text == "Tweede lezing."
    assert (row.title, row.text_override, row.text_addition, row.is_active) == (
        "Eigen titel",
        "Handmatig gecorrigeerd.",
        "Honden welkom.",
        False,
    )
    assert db_session.query(ChatbotInfo).filter_by(media_asset_id=ASSET).count() == 1


def test_a_reading_that_found_nothing_leaves_no_text(db_session):
    _extracted(db_session, "Eerste lezing.")

    _extracted(db_session, "")

    db_session.expire_all()
    assert _row(db_session).extracted_text is None
    assert has_extracted_text(db_session, ASSET) is False


def test_a_row_without_text_is_not_read_yet(db_session):
    db_session.add(ChatbotInfo(media_asset_id=ASSET, title="Eigen titel", text_addition="Los."))
    db_session.flush()

    assert has_extracted_text(db_session, ASSET) is False


def test_each_document_has_its_own_row(db_session):
    _extracted(db_session, "Een.", asset_id=ASSET)
    _extracted(db_session, "Twee.", asset_id=ASSET + 1)

    assert _row(db_session, ASSET).extracted_text == "Een."
    assert _row(db_session, ASSET + 1).extracted_text == "Twee."
    assert has_extracted_text(db_session, ASSET + 2) is False
