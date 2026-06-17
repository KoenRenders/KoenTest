"""Tests voor documenttekst-extractie naar chatbot_info (#206).

Bewaakt de invarianten die ertoe doen:
- PDF mét bruikbare tekstlaag → gratis pad, **geen** OCR-call;
- scan-PDF/afbeelding → OCR-pad (mits key + ingeschakeld);
- zonder key geen OCR-kost;
- de tekst komt in een **chatbot_info-rij** gekoppeld aan het asset; opnieuw
  uitlezen (force) raakt override/addition niet;
- de bot krijgt de effectieve tekst (poster + reglement) via get_activity_detail.
"""
import json

from app.config import settings
from app.models.activity import Activity
from app.models.activity_sub_registration import ActivitySubRegistration
from app.models.asset import MediaAsset
from app.models.chatbot_info import ChatbotInfo
from app.domains.chatbot.tools import execute_tool
import app.services.media_extraction as mx


# ── Routing: tekstlaag vs OCR ────────────────────────────────────────────────

def test_pdf_with_text_layer_skips_ocr(monkeypatch):
    monkeypatch.setattr(mx, "_extract_pdf_text_layer", lambda raw: "x" * 200)

    def _boom(*a, **k):
        raise AssertionError("OCR mag niet aangeroepen worden bij een tekstlaag")

    monkeypatch.setattr(mx, "_ocr_via_mistral", _boom)
    assert mx.extract_document_text(b"%PDF", "application/pdf") == "x" * 200


def test_scanned_pdf_falls_back_to_ocr(monkeypatch):
    monkeypatch.setattr(mx, "_extract_pdf_text_layer", lambda raw: "")
    monkeypatch.setattr(settings, "mistral_api_key", "test-key")
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(mx, "_ocr_via_mistral", lambda raw, ct: "OCR-TEKST")
    assert mx.extract_document_text(b"%PDF", "application/pdf") == "OCR-TEKST"


def test_image_without_key_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "mistral_api_key", None)
    assert mx.extract_document_text(b"\x89PNG", "image/png") == ""


# ── update_media_extracted_text → chatbot_info-rij ───────────────────────────

def _poster(db, activity, data=b"posterbytes", content_type="image/png"):
    asset = MediaAsset(
        kind="activity_poster", activity_id=activity.id,
        data=data, content_type=content_type, byte_size=len(data),
    )
    db.add(asset)
    db.flush()
    return asset


def test_extraction_creates_chatbot_info_row_and_skips_unless_force(db_session, monkeypatch):
    a = Activity(name="Lentewandeling")
    db_session.add(a)
    db_session.flush()
    asset = _poster(db_session, a)

    calls = {"n": 0}

    def _fake_extract(raw, ct):
        calls["n"] += 1
        return "Breng stevige schoenen mee."

    monkeypatch.setattr(mx, "extract_document_text", _fake_extract)

    mx.update_media_extracted_text(asset.id, db=db_session)
    row = db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset.id).first()
    assert row is not None
    assert row.extracted_text == "Breng stevige schoenen mee."
    assert row.extracted_at is not None
    assert calls["n"] == 1

    # Tweede keer zonder force → rij heeft al tekst → skip.
    mx.update_media_extracted_text(asset.id, db=db_session)
    assert calls["n"] == 1

    # Met force → opnieuw uitlezen, maar override/addition blijven onaangeroerd.
    row.text_override = "Handmatig gecorrigeerd."
    row.text_addition = "Honden welkom."
    db_session.flush()
    monkeypatch.setattr(mx, "extract_document_text", lambda raw, ct: "Verse OCR.")
    mx.update_media_extracted_text(asset.id, db=db_session, force=True)
    db_session.refresh(row)
    assert row.extracted_text == "Verse OCR."
    assert row.text_override == "Handmatig gecorrigeerd."  # behouden
    assert row.text_addition == "Honden welkom."           # behouden


def test_non_extractable_kind_creates_no_row(db_session, monkeypatch):
    a = Activity(name="Fuif")
    db_session.add(a)
    db_session.flush()
    photo = MediaAsset(
        kind="activity_photo", activity_id=a.id,
        data=b"img", content_type="image/png", byte_size=3,
    )
    db_session.add(photo)
    db_session.flush()
    monkeypatch.setattr(mx, "extract_document_text", lambda raw, ct: "ZOU NIET MOGEN")
    mx.update_media_extracted_text(photo.id, db=db_session)
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == photo.id).first() is None


# ── effective_text: override vervangt, addition vult aan ─────────────────────

def test_effective_text_override_and_addition():
    row = ChatbotInfo(extracted_text="machine", text_addition="extra")
    assert row.effective_text == "machine\n\nextra"
    row.text_override = "correctie"
    assert row.effective_text == "correctie\n\nextra"


# ── Bot-feed: poster + reglement via get_activity_detail ─────────────────────

def test_get_activity_detail_includes_poster_and_component_text(db_session):
    a = Activity(name="Quiz")
    db_session.add(a)
    db_session.flush()
    poster = MediaAsset(
        kind="activity_poster", activity_id=a.id,
        data=b"p", content_type="image/png", byte_size=1,
    )
    db_session.add(poster)
    sub = ActivitySubRegistration(activity_id=a.id, name="Hoofdquiz")
    db_session.add(sub)
    db_session.flush()
    info = MediaAsset(
        kind="component_info", component_id=sub.id,
        data=b"i", content_type="application/pdf", byte_size=1,
    )
    db_session.add(info)
    db_session.flush()
    db_session.add(ChatbotInfo(media_asset_id=poster.id, extracted_text="Inschrijven per ploeg van 4."))
    db_session.add(ChatbotInfo(media_asset_id=info.id, extracted_text="Reglement: max 6 personen per ploeg."))
    db_session.flush()

    out = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    assert out["flyer_text"] == "Inschrijven per ploeg van 4."
    assert out["components"][0]["info_text"] == "Reglement: max 6 personen per ploeg."
