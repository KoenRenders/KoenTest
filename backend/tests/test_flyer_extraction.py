"""Tests voor flyertekst-extractie (#206).

Bewaakt de invarianten die ertoe doen:
- PDF mét bruikbare tekstlaag → gratis pad, **geen** OCR-call;
- scan-PDF/afbeelding → OCR-pad (mits key + ingeschakeld);
- zonder key geen OCR-kost;
- (her)extractie is idempotent via de poster-hash;
- de bot krijgt flyer_text via get_activity_detail.
"""
import json

import pytest

from app.config import settings
from app.models.activity import Activity
from app.models.asset import MediaAsset
from app.domains.chatbot.tools import execute_tool
import app.services.flyer_extraction as fx


# ── Routing: tekstlaag vs OCR ────────────────────────────────────────────────

def test_pdf_with_text_layer_skips_ocr(monkeypatch):
    monkeypatch.setattr(fx, "_extract_pdf_text_layer", lambda raw: "x" * 200)

    def _boom(*a, **k):
        raise AssertionError("OCR mag niet aangeroepen worden bij een tekstlaag")

    monkeypatch.setattr(fx, "_ocr_via_mistral", _boom)
    assert fx.extract_flyer_text(b"%PDF", "application/pdf") == "x" * 200


def test_scanned_pdf_falls_back_to_ocr(monkeypatch):
    monkeypatch.setattr(fx, "_extract_pdf_text_layer", lambda raw: "")
    monkeypatch.setattr(settings, "mistral_api_key", "test-key")
    monkeypatch.setattr(settings, "flyer_ocr_enabled", True)
    monkeypatch.setattr(fx, "_ocr_via_mistral", lambda raw, ct: "OCR-TEKST")
    assert fx.extract_flyer_text(b"%PDF", "application/pdf") == "OCR-TEKST"


def test_image_uses_ocr(monkeypatch):
    monkeypatch.setattr(settings, "mistral_api_key", "test-key")
    monkeypatch.setattr(settings, "flyer_ocr_enabled", True)
    monkeypatch.setattr(fx, "_ocr_via_mistral", lambda raw, ct: "BEELD-OCR")
    assert fx.extract_flyer_text(b"\x89PNG", "image/png") == "BEELD-OCR"


def test_image_without_key_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "mistral_api_key", None)
    assert fx.extract_flyer_text(b"\x89PNG", "image/png") == ""


# ── update_activity_flyer_text: opslag + idempotentie ────────────────────────

def _activity_with_poster(db, data=b"posterbytes", content_type="image/png"):
    a = Activity(name="Lentewandeling")
    db.add(a)
    db.flush()
    db.add(
        MediaAsset(
            kind="activity_poster", activity_id=a.id,
            data=data, content_type=content_type, byte_size=len(data),
        )
    )
    db.flush()
    return a


def test_update_stores_and_is_idempotent(db_session, monkeypatch):
    a = _activity_with_poster(db_session)
    calls = {"n": 0}

    def _fake_extract(raw, ct):
        calls["n"] += 1
        return "Breng stevige schoenen mee."

    monkeypatch.setattr(fx, "extract_flyer_text", _fake_extract)

    fx.update_activity_flyer_text(a.id, db=db_session)
    db_session.refresh(a)
    assert a.flyer_text == "Breng stevige schoenen mee."
    assert a.flyer_text_hash  # gezet
    assert calls["n"] == 1

    # Tweede keer met dezelfde poster → hash-skip, geen nieuwe extractie.
    fx.update_activity_flyer_text(a.id, db=db_session)
    assert calls["n"] == 1


def test_update_reextracts_when_poster_changes(db_session, monkeypatch):
    a = _activity_with_poster(db_session, data=b"eerste")
    monkeypatch.setattr(fx, "extract_flyer_text", lambda raw, ct: "v1")
    fx.update_activity_flyer_text(a.id, db=db_session)
    db_session.refresh(a)
    first_hash = a.flyer_text_hash

    # Poster vervangen (andere bytes) → andere hash → opnieuw extraheren.
    asset = db_session.query(MediaAsset).filter(
        MediaAsset.kind == "activity_poster", MediaAsset.activity_id == a.id
    ).first()
    asset.data = b"tweede-versie"
    db_session.flush()
    monkeypatch.setattr(fx, "extract_flyer_text", lambda raw, ct: "v2")
    fx.update_activity_flyer_text(a.id, db=db_session)
    db_session.refresh(a)
    assert a.flyer_text == "v2"
    assert a.flyer_text_hash != first_hash


# ── Bot-feed ─────────────────────────────────────────────────────────────────

def test_get_activity_detail_includes_flyer_text(db_session):
    a = Activity(name="Quiz", flyer_text="Inschrijven per ploeg van 4.")
    db_session.add(a)
    db_session.flush()
    out = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    assert out["flyer_text"] == "Inschrijven per ploeg van 4."
