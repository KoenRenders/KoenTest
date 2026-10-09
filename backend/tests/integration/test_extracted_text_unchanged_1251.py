"""A document's text reaches the AI context as before, now as a fact (CR-13 phase 4d, #1251).

Media's job read a document and wrote the text into `chatbot_info` itself — a
row of another domain. Since this cut the job reads the document and says what
it read (`DocumentTextExtracted`); the chatbot writes its own row. Whether a
document was read already is a question the job asks the chatbot
(`has_extracted_text`).

Nothing about the row may change. So this records the row, column by column,
after each step of a document's life, and how often the reader was called:
a first reading, a second run (skipped), a forced reading that must leave the
manual override and addition alone, a reading that finds no text, a row that
existed without text, and a kind whose text is never read. Recorded on the code
before the cut; the code after it must leave the same rows.

`extracted_at` is recorded as set or not: it is the moment of the run.
"""

from __future__ import annotations

from pathlib import Path

import app.domains.media.extraction as mx
from app.domains.activities.api import Activity
from app.domains.chatbot.models import ChatbotInfo
from app.domains.media.api import MediaAsset
from tests._snapshot import compare

SNAPSHOTS = Path(__file__).parent / "snapshots" / "extracted_text"
BEFORE = "the chatbot's row for a document, before the text became a fact (#1251)"
COLUMNS = ("title", "extracted_text", "text_override", "text_addition", "is_active", "sort_order")


def _asset(db, activity, kind="activity_poster", title=None) -> MediaAsset:
    asset = MediaAsset(
        kind=kind,
        activity_id=activity.id,
        title=title,
        data=b"bytes",
        content_type="image/png",
        byte_size=5,
    )
    db.add(asset)
    db.flush()
    return asset


def _row(db, asset) -> str:
    db.expire_all()
    rows = db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset.id).all()
    if not rows:
        return "no row"
    assert len(rows) == 1, "more than one row for one document"
    row = rows[0]
    told = [f"{column}={getattr(row, column)!r}" for column in COLUMNS]
    told.append(f"extracted_at={'set' if row.extracted_at else None}")
    return ", ".join(told)


def test_the_row_of_a_document_is_what_it_was(db_session, monkeypatch):
    db = db_session
    activity = Activity(name="Lentewandeling")
    db.add(activity)
    db.flush()
    read = {"calls": 0, "text": "Breng stevige schoenen mee."}

    def reader(raw, content_type, **_more):
        read["calls"] += 1
        return read["text"]

    monkeypatch.setattr(mx, "extract_document_text", reader)
    told: list[str] = []

    def step(name: str, asset) -> None:
        told.append(f"{name}: reader called {read['calls']}x — {_row(db, asset)}")

    poster = _asset(db, activity, title="Affiche lente")
    mx.update_media_extracted_text(poster.id, db=db)
    step("first reading", poster)

    mx.update_media_extracted_text(poster.id, db=db)
    step("second run, not forced", poster)

    row = db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == poster.id).one()
    row.text_override = "Handmatig gecorrigeerd."
    row.text_addition = "Honden welkom."
    db.flush()
    read["text"] = "Verse OCR."
    mx.update_media_extracted_text(poster.id, db=db, force=True)
    step("forced reading, with a manual override and addition", poster)

    read["text"] = ""
    mx.update_media_extracted_text(poster.id, db=db, force=True)
    step("forced reading that finds no text", poster)

    read["text"] = "Nu wel tekst."
    mx.update_media_extracted_text(poster.id, db=db)
    step("a run on a row without text, not forced", poster)

    untitled = _asset(db, activity)
    db.add(ChatbotInfo(media_asset_id=untitled.id, title="Eigen titel", text_addition="Los."))
    db.flush()
    mx.update_media_extracted_text(untitled.id, db=db)
    step("a row that existed without text, with its own title", untitled)

    photo = _asset(db, activity, kind="activity_photo")
    mx.update_media_extracted_text(photo.id, db=db)
    step("a kind whose text is never read", photo)

    mx.update_media_extracted_text(999_999, db=db)
    told.append(f"an asset that is not there: reader called {read['calls']}x")

    compare(SNAPSHOTS, "rows", "\n".join(told) + "\n", BEFORE)
