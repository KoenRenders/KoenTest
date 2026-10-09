"""What media stores, removes and refuses for another domain — recorded (#1251, the media ports).

Every caller that stores or removes a file in media goes through a port
(`docs/architecture.md` §3.2.1 step 2): `StoreFile`, `RemoveAsset`,
`RemoveFileOf`. Nothing of what media accepts or refuses changes with that. This
test walks every kind another domain stores — an activity's poster, a
component's info document, a render and an image of the Design Studio, a
newsletter's attachment — and compares, case by case, the asset row that results
or the sentence of the refusal with what the code did before the ports.

`EXPECTED` was recorded on the old code (9 October 2026: `store_activity_poster`,
`store_component_info`, `add_document`, `store_uploads`, `remove_media` and the
two `drop_…` functions called directly). The three functions under *The way in*
are the only thing that changed since; the cases and `EXPECTED` did not.
"""

from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import BackgroundTasks, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.domains.media.api import (
    MediaAsset,
    add_document,
    drop_activity_poster,
    drop_component_info,
    remove_media,
    store_activity_poster,
    store_component_info,
    store_uploads,
)
from tests.conftest import seed_activity_with_product
from tests.integration.test_media_pdf_preview import _pdf

pytestmark = pytest.mark.ui_agnostisch

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'


def _png(size=(60, 40)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


# ── The way in ───────────────────────────────────────────────────────────────


def _upload(filename: str, content_type: str, content: bytes) -> UploadFile:
    return UploadFile(
        file=BytesIO(content), filename=filename, headers=Headers({"content-type": content_type})
    )


def _store(db, world, *, kind, filename, content_type, content, owner=None) -> tuple[int, bool]:
    """Store one file; returns the asset's id and whether a text extraction was
    started for it."""
    upload = _upload(filename, content_type, content)
    tasks = BackgroundTasks()
    if kind == "activity_poster":
        stored = asyncio.run(store_activity_poster(db, world["activity"], upload, tasks))
        return stored["id"], bool(tasks.tasks)
    if kind == "component_info":
        stored = asyncio.run(store_component_info(db, world["component"], upload, tasks))
        return stored["id"], bool(tasks.tasks)
    if kind == "design_image":
        rows = asyncio.run(store_uploads(db, files=[upload], kind=kind, activity_id=owner))
        return rows[0]["id"], False
    asset = add_document(
        db, kind=kind, filename=filename, content_type=content_type, data=content, activity_id=owner
    )
    return asset.id, False


def _remove_asset(db, asset_id: int) -> None:
    remove_media(db, asset_id)


def _remove_file_of(db, world, kind: str) -> None:
    if kind == "activity_poster":
        drop_activity_poster(db, world["activity"])
    else:
        drop_component_info(db, world["component"])


# ── The cases ────────────────────────────────────────────────────────────────

PNG = ("image/png", _png)
PDF = ("application/pdf", _pdf)

STORES = [
    # (label, kind, filename, content type, content, owner)
    ("a poster, an image", "activity_poster", "affiche.png", "image/png", _png, None),
    ("a poster, a PDF", "activity_poster", "affiche.pdf", "application/pdf", _pdf, None),
    ("a component's info, a PDF", "component_info", "reglement.pdf", "application/pdf", _pdf, None),
    ("a render, a PDF", "design_render", "quiz-A4.pdf", "application/pdf", _pdf, None),
    ("a render, an image", "design_render", "quiz-A4.png", "image/png", _png, None),
    (
        "a render, an SVG",
        "design_render",
        "quiz-A4-bewerkt.svg",
        "image/svg+xml",
        lambda: SVG,
        None,
    ),
    ("an attachment of a letter", "newsletter_file", "bijlage.pdf", "application/pdf", _pdf, None),
    ("a design image for an activity", "design_image", "ai-7.png", "image/png", _png, "activity"),
    ("a design image without an activity", "design_image", "foto.png", "image/png", _png, None),
]

REFUSALS = [
    (
        "a poster of a type media does not take",
        "activity_poster",
        "affiche.txt",
        "text/plain",
        lambda: b"x",
        None,
    ),
    (
        "a poster that is empty",
        "activity_poster",
        "affiche.pdf",
        "application/pdf",
        lambda: b"",
        None,
    ),
    (
        "an info document of a type media does not take",
        "component_info",
        "r.txt",
        "text/plain",
        lambda: b"x",
        None,
    ),
    (
        "a render of a type media does not take",
        "design_render",
        "r.txt",
        "text/plain",
        lambda: b"x",
        None,
    ),
    ("a render that is empty", "design_render", "leeg.pdf", "application/pdf", lambda: b"", None),
    ("an SVG as an attachment", "newsletter_file", "b.svg", "image/svg+xml", lambda: SVG, None),
    (
        "an attachment of a type media does not take",
        "newsletter_file",
        "b.txt",
        "text/plain",
        lambda: b"x",
        None,
    ),
    (
        "a design image of a type media does not take",
        "design_image",
        "f.gif",
        "image/gif",
        lambda: b"x",
        None,
    ),
    (
        "a design image that is no image",
        "design_image",
        "f.png",
        "image/png",
        lambda: b"not a png",
        None,
    ),
    (
        "a design image for an activity that is not there",
        "design_image",
        "f.png",
        "image/png",
        _png,
        "nobody",
    ),
]

EXPECTED: dict[str, object] = {
    "a poster, an image": {
        "kind": "activity_poster",
        "title": "Testactiviteit - poster.jpg",
        "content_type": "image/jpeg",
        "activity": "the activity",
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (60, 40),
        "has_bytes": True,
        "picture": "image/jpeg",
        "extraction started": True,
    },
    "a poster, a PDF": {
        "kind": "activity_poster",
        "title": "Testactiviteit - poster.pdf",
        "content_type": "application/pdf",
        "activity": "the activity",
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (None, None),
        "has_bytes": True,
        "picture": "image/png",
        "extraction started": True,
    },
    "a component's info, a PDF": {
        "kind": "component_info",
        "title": "Testactiviteit - Onderdeel - info.pdf",
        "content_type": "application/pdf",
        "activity": None,
        "component": "the component",
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (None, None),
        "has_bytes": True,
        "picture": "image/png",
        "extraction started": True,
    },
    "a render, a PDF": {
        "kind": "design_render",
        "title": "quiz-A4.pdf",
        "content_type": "application/pdf",
        "activity": None,
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (None, None),
        "has_bytes": True,
        "picture": "image/png",
        "extraction started": False,
    },
    "a render, an image": {
        "kind": "design_render",
        "title": "quiz-A4.png",
        "content_type": "image/png",
        "activity": None,
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (60, 40),
        "has_bytes": True,
        "picture": "image/png",
        "extraction started": False,
    },
    "a render, an SVG": {
        "kind": "design_render",
        "title": "quiz-A4-bewerkt.svg",
        "content_type": "image/svg+xml",
        "activity": None,
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (10, 10),
        "has_bytes": True,
        "picture": "image/png",
        "extraction started": False,
    },
    "an attachment of a letter": {
        "kind": "newsletter_file",
        "title": "bijlage.pdf",
        "content_type": "application/pdf",
        "activity": None,
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (None, None),
        "has_bytes": True,
        "picture": "image/png",
        "extraction started": False,
    },
    "a design image for an activity": {
        "kind": "design_image",
        "title": "ai-7.png",
        "content_type": "image/jpeg",
        "activity": "the activity",
        "component": None,
        "sort_order": 0,
        "is_active": True,
        "link_url": None,
        "size": (60, 40),
        "has_bytes": True,
        "picture": "image/jpeg",
        "extraction started": False,
    },
    "a design image without an activity": {
        "kind": "design_image",
        "title": "foto.png",
        "content_type": "image/jpeg",
        "activity": None,
        "component": None,
        "sort_order": 1,
        "is_active": True,
        "link_url": None,
        "size": (60, 40),
        "has_bytes": True,
        "picture": "image/jpeg",
        "extraction started": False,
    },
    "a poster of a type media does not take": "Niet-ondersteund bestandstype: affiche.txt",
    "a poster that is empty": "affiche.pdf: Leeg bestand",
    "an info document of a type media does not take": "Niet-ondersteund bestandstype: r.txt",
    "a render of a type media does not take": "Dit bestandstype kan niet: kies een PDF of een "
    "afbeelding.",
    "a render that is empty": "leeg.pdf: Leeg bestand",
    "an SVG as an attachment": "Een SVG kan hier alleen als render van de Design Studio.",
    "an attachment of a type media does not take": "Dit bestandstype kan niet: kies een PDF of "
    "een afbeelding.",
    "a design image of a type media does not take": "f.gif: Geen geldige afbeelding",
    "a design image that is no image": "f.png: Geen geldige afbeelding",
    "a design image for an activity that is not there": "Activiteit niet gevonden",
    "a second poster takes the first one's place": 1,
    "renders are kept beside each other": 3,
    "the poster and the info document removed": (0, 0),
    "removing a poster that is not there": 0,
    "one render removed": 2,
    "removing an asset that is not there": "Niet gevonden",
}


def _row(db, world, asset_id: int) -> dict:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).one()
    owners = {world["activity"]: "the activity", world["component"]: "the component", None: None}
    return {
        "kind": asset.kind.value,
        "title": asset.title,
        "content_type": asset.content_type,
        "activity": owners[asset.activity_id],
        "component": owners[asset.component_id],
        "sort_order": asset.sort_order,
        "is_active": asset.is_active,
        "link_url": asset.link_url,
        "size": (asset.width, asset.height),
        "has_bytes": bool(asset.byte_size),
        "picture": asset.thumb_content_type,
    }


def _sentence(exc: Exception) -> str:
    return str(getattr(exc, "detail", exc))


def test_media_stores_removes_and_refuses_what_it_did(db_session):
    db = db_session
    activity, component, _product = seed_activity_with_product(db)
    world = {"activity": activity.id, "component": component.id}
    owner_of = {"activity": world["activity"], "nobody": 999_999, None: None}
    got: dict[str, object] = {}

    for label, kind, filename, content_type, content, owner in STORES:
        asset_id, extraction = _store(
            db,
            world,
            kind=kind,
            filename=filename,
            content_type=content_type,
            content=content(),
            owner=owner_of[owner],
        )
        got[label] = {**_row(db, world, asset_id), "extraction started": extraction}

    for label, kind, filename, content_type, content, owner in REFUSALS:
        with pytest.raises(Exception) as refused:  # noqa: PT011 — the sentence is what is recorded
            _store(
                db,
                world,
                kind=kind,
                filename=filename,
                content_type=content_type,
                content=content(),
                owner=owner_of[owner],
            )
        got[label] = _sentence(refused.value)

    def count(kind: str) -> int:
        return db.query(MediaAsset).filter(MediaAsset.kind == kind).count()

    # One poster and one info document per owner: a second store replaces the first.
    first, _started = _store(
        db,
        world,
        kind="activity_poster",
        filename="nieuw.png",
        content_type="image/png",
        content=_png(),
    )
    got["a second poster takes the first one's place"] = count("activity_poster")
    # A render and an attachment are kept beside the others.
    got["renders are kept beside each other"] = count("design_render")

    _remove_file_of(db, world, "activity_poster")
    _remove_file_of(db, world, "component_info")
    db.flush()
    got["the poster and the info document removed"] = (
        count("activity_poster"),
        count("component_info"),
    )
    _remove_file_of(db, world, "activity_poster")  # nothing there: no refusal
    db.flush()
    got["removing a poster that is not there"] = count("activity_poster")

    render = db.query(MediaAsset).filter(MediaAsset.kind == "design_render").first().id
    _remove_asset(db, render)
    got["one render removed"] = count("design_render")
    with pytest.raises(Exception) as refused:  # noqa: PT011
        _remove_asset(db, 999_999)
    got["removing an asset that is not there"] = _sentence(refused.value)
    assert first  # the id of the replaced poster was real

    assert got == EXPECTED
