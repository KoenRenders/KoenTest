"""CR-13 phase 4c, M2 (#1251): the fiche's files go through media's ports — what the
screen answers and what media keeps stays.

The one save of an activity's fiche stores or removes the poster and each
component's info document. Until M2 `activities/fiche.py` called four commands of
media for it (`store_activity_poster`, `drop_activity_poster`,
`store_component_info`, `drop_component_info`), with the request's upload object
in hand. It asks media through its ports now — `StoreFile` and `RemoveFileOf`
(`kernel/contracts/media.py`) — with the file as plain values, read once at the
door.

No behaviour changes, so the proof is **the same answer and the same rows on the
same input**: every case below was recorded on the code BEFORE the ports — the
status of the save, the refusal as the screen gets it, and every asset media
keeps (its kind, its owner, its name, its type, its size and a digest of its
bytes) — and the code with the ports must give it again, character for character
(`tests/_snapshot.py`).

**What a refusal is measured at:** the answer is the fiche's own refusal — an
HTML 422 sent to the fiche's message line (`HX-Retarget`), which the screen swaps
in — not a JSON error. Its text is in the recording.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from app.domains.activities.models import (
    Activity,
    ActivityDate,
    ActivityProduct,
    ActivitySubRegistration,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.api import MediaAsset
from tests._fiche import Fiche
from tests._snapshot import compare, fixed_ids, normalise
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "fiche_files_1251"
BEFORE = "the fiche's files went through media's ports (CR-13 phase 4c, M2)"
MODELS = (Activity, ActivityDate, ActivitySubRegistration, ActivityProduct, MediaAsset)
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _png(name: str = "affiche.png"):
    return (name, io.BytesIO(PNG), "image/png")


@pytest.fixture
def world(client, db_session):
    """An activity with one component, and the board member's session."""
    with fixed_ids(db_session, MODELS):
        activity, component, _product = seed_activity_with_product(
            db_session, price="10.00", is_free=False
        )
        db_session.commit()
        value = make_session_value(SEEDED_ADMIN_EMAIL)
        client.cookies.set(SESSION_COOKIE, value)
        yield activity, component, {"X-CSRF-Token": csrf_token_for(value)}


def _assets(db) -> str:
    db.expire_all()
    lines = []
    for asset in db.query(MediaAsset).order_by(MediaAsset.id):
        lines.append(
            f"asset {asset.id}: kind={asset.kind} activity={asset.activity_id} "
            f"component={asset.component_id} title={asset.title!r} type={asset.content_type} "
            f"bytes={asset.byte_size} size={asset.width}x{asset.height} "
            f"digest={hashlib.sha256(asset.data).hexdigest()[:12]} "
            f"thumbnail={'yes' if asset.thumbnail else 'no'}"
        )
    return "\n".join(lines) or "(no assets)"


def _record(name: str, response, db) -> None:
    said = response.text if response.status_code != 200 else "(the fiche, in read mode)"
    got = normalise(f"{response.status_code}\n{said}\n--- media ---\n{_assets(db)}", {}, {})
    compare(SNAPSHOTS, name, got, BEFORE)


def test_a_poster_is_stored_replaced_and_dropped_as_it_was(client, db_session, world):
    activity, _component, headers = world

    stored = Fiche(db_session, activity.id).post(client, headers, files={"file": _png()})
    _record("poster_stored", stored, db_session)

    replaced = Fiche(db_session, activity.id).post(
        client, headers, files={"file": _png("nieuwe-affiche.png")}
    )
    _record("poster_replaced", replaced, db_session)

    fiche = Fiche(db_session, activity.id)
    fiche.data["file_delete"] = "1"
    _record("poster_dropped", fiche.post(client, headers), db_session)


def test_info_documents_are_stored_and_dropped_as_they_were(client, db_session, world):
    """On the component that is there and on one added in the same save — a
    picture and a PDF."""
    activity, component, headers = world

    fiche = Fiche(db_session, activity.id)
    new = fiche.add("c", name="Met reglement")
    stored = fiche.post(
        client,
        headers,
        files={
            f"c.{component.id}.file": _png("info.png"),
            f"c.{new}.file": ("reglement.pdf", io.BytesIO(PDF), "application/pdf"),
        },
    )
    _record("info_stored", stored, db_session)

    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, info_delete="1")
    _record("info_dropped", fiche.post(client, headers), db_session)


@pytest.mark.parametrize(
    "name, place, upload",
    [
        ("refused_type_on_a_component", "component", ("foto.heic", b"x", "image/heic")),
        ("refused_type_as_poster", "poster", ("nota.txt", b"geen afbeelding", "text/plain")),
        ("refused_empty_file", "poster", ("leeg.png", b"", "image/png")),
        ("refused_not_what_it_says", "poster", ("nep.png", b"dit is geen png", "image/png")),
    ],
)
def test_a_refused_file_refuses_the_save_as_it_did(client, db_session, world, name, place, upload):
    activity, component, headers = world
    filename, content, content_type = upload
    field = "file" if place == "poster" else f"c.{component.id}.file"

    fiche = Fiche(db_session, activity.id)
    fiche.set("c", component.id, name="Niet hernoemd")
    response = fiche.post(
        client, headers, files={field: (filename, io.BytesIO(content), content_type)}
    )

    _record(name, response, db_session)
    if response.status_code == 422:
        assert response.headers.get("HX-Retarget") == "#aa-fiche-message"
        db_session.expire_all()
        kept = db_session.get(ActivitySubRegistration, component.id).name
        assert kept == "Onderdeel", "a refused file wrote the rest of the save"
