"""Tests voor documenttekst-extractie (#206).

Bewaakt de invarianten die ertoe doen:
- PDF mét bruikbare tekstlaag → gratis pad, **geen** OCR-call;
- scan-PDF/afbeelding → OCR-pad (mits key + ingeschakeld);
- zonder key geen OCR-kost;
- de tekst komt op het **media-record**; opnieuw uitlezen vereist force;
- de bot krijgt de tekst (poster + reglement) via get_activity_detail.
"""
import json

from app.config import settings
from app.models.activity import Activity
from app.models.activity_sub_registration import ActivitySubRegistration
from app.models.asset import MediaAsset
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


def test_image_uses_ocr(monkeypatch):
    monkeypatch.setattr(settings, "mistral_api_key", "test-key")
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(mx, "_ocr_via_mistral", lambda raw, ct: "BEELD-OCR")
    assert mx.extract_document_text(b"\x89PNG", "image/png") == "BEELD-OCR"


def test_image_without_key_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "mistral_api_key", None)
    assert mx.extract_document_text(b"\x89PNG", "image/png") == ""


# ── update_media_extracted_text: opslag op het asset-record + skip/force ─────

def _poster(db, activity, data=b"posterbytes", content_type="image/png"):
    asset = MediaAsset(
        kind="activity_poster", activity_id=activity.id,
        data=data, content_type=content_type, byte_size=len(data),
    )
    db.add(asset)
    db.flush()
    return asset


def test_update_stores_on_asset_and_skips_when_present(db_session, monkeypatch):
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
    db_session.refresh(asset)
    assert asset.extracted_text == "Breng stevige schoenen mee."
    assert asset.extracted_at is not None
    assert calls["n"] == 1

    # Tweede keer zonder force → asset heeft al tekst → skip.
    mx.update_media_extracted_text(asset.id, db=db_session)
    assert calls["n"] == 1

    # Met force → opnieuw uitlezen (de 'Opnieuw lezen'-knop).
    mx.update_media_extracted_text(asset.id, db=db_session, force=True)
    assert calls["n"] == 2


def test_non_extractable_kind_is_ignored(db_session, monkeypatch):
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
    db_session.refresh(photo)
    assert photo.extracted_text is None


# ── Bot-feed: poster + reglement via get_activity_detail ─────────────────────

def test_get_activity_detail_includes_poster_and_component_text(db_session):
    a = Activity(name="Quiz")
    db_session.add(a)
    db_session.flush()
    db_session.add(MediaAsset(
        kind="activity_poster", activity_id=a.id,
        data=b"p", content_type="image/png", byte_size=1,
        extracted_text="Inschrijven per ploeg van 4.",
    ))
    sub = ActivitySubRegistration(activity_id=a.id, name="Hoofdquiz")
    db_session.add(sub)
    db_session.flush()
    db_session.add(MediaAsset(
        kind="component_info", component_id=sub.id,
        data=b"i", content_type="application/pdf", byte_size=1,
        extracted_text="Reglement: max 6 personen per ploeg.",
    ))
    db_session.flush()

    out = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    assert out["flyer_text"] == "Inschrijven per ploeg van 4."
    assert out["components"][0]["info_text"] == "Reglement: max 6 personen per ploeg."
