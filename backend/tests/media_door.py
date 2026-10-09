"""The media tests' way to the media library, in process (CR-13 phase 4b, #1251).

Ten JSON routes of the media domain had no caller but tests and are gone: the
admin list, upload, edit and delete, the poster of an activity, the info sheet of
a component, the re-read of a document, the photos of an activity and the list of
sponsors. Nine were a door over one function of `media.service`, which the media
screens and the activity screens call as well; the tests keep handing their files
and their fields to those functions and read the answer as the routes gave it —
an `Answer` with the status code and the body, 400 for a refusal with its words,
404 for what is not there, 409 for an asset that is still shown somewhere.

A file is given as the test client took it: `(name, bytes, content type)`.
The two routes that SERVE a file (`/api/v1/media/{id}` and its thumbnail) stay.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

from fastapi import BackgroundTasks, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from starlette.datastructures import Headers

from app.domains.media import service
from app.domains.media.models import MediaAsset
from app.kernel.contracts.media import RemoveFileOf, StoreFile
from app.kernel.ports import call as call_port
from tests.forms_door import Answer, _db


def _upload(spec: tuple[str, bytes, str]) -> UploadFile:
    name, data, content_type = spec
    return UploadFile(
        file=BytesIO(data), filename=name, headers=Headers({"content-type": content_type})
    )


def _files(files: Any, field: str) -> list[UploadFile]:
    """The files of one form field, from the shapes the test client takes: a
    mapping `{field: spec}` or a list of `(field, spec)` pairs."""
    pairs = files.items() if isinstance(files, dict) else files
    return [_upload(spec) for name, spec in pairs if name == field]


def _answer(call, *, done: int = 200) -> Answer:
    try:
        return Answer(done, jsonable_encoder(call()))
    except HTTPException as exc:
        return Answer(exc.status_code, {"detail": exc.detail})
    except service.MediaInUse as exc:
        return Answer(409, {"detail": {"message": str(exc), "uses": [vars(u) for u in exc.uses]}})
    except service.MediaFout as exc:
        return Answer(400, {"detail": str(exc)})
    except LookupError as exc:
        return Answer(404, {"detail": str(exc)})


def _after(tasks: BackgroundTasks) -> None:
    """Run what the request would have run after its response."""
    asyncio.run(tasks())


def listing(client, *, kind: str | None = None, activity_id: int | None = None) -> Answer:
    return _answer(lambda: service.list_media(_db(client), kind=kind, activity_id=activity_id))


def photos(client, activity_id: int) -> Answer:
    return _answer(lambda: service.list_activity_photos(_db(client), activity_id))


def upload(client, files: Any, data: dict | None = None) -> Answer:
    """Upload one or more files of a kind: `data` holds `kind` and, as the form
    did, `activity_id`, `title` and `link_url`."""
    data = dict(data or {})
    activity_id = data.get("activity_id")
    return _answer(
        lambda: asyncio.run(
            service.upload_media(
                _db(client),
                files=_files(files, "files"),
                kind=data["kind"],
                activity_id=int(activity_id) if activity_id not in (None, "") else None,
                title=data.get("title"),
                link_url=data.get("link_url"),
            )
        )
    )


def _values(files: Any) -> dict:
    """The one file of the field `file`, as the values the service takes."""
    pairs = files.items() if isinstance(files, dict) else files
    name, data, content_type = next(spec for field, spec in pairs if field == "file")
    return {"filename": name, "content_type": content_type, "content": data}


def _store(client, port: StoreFile) -> Answer:
    """Store through media's port and commit, as a door of the application does;
    the answer is the stored asset as media describes it."""
    db = _db(client)

    def stored() -> dict:
        outcome = call_port(port, db)
        db.commit()
        return service.meta(db.get(MediaAsset, outcome.asset_id))

    return _answer(stored)


def set_poster(
    client, activity_id: int, files: Any, *, title_base: str = "Activiteit - poster"
) -> Answer:
    """An activity's poster, through `StoreFile` — the caller names the file, as
    the activity fiche does."""
    return _store(
        client,
        StoreFile(
            kind="activity_poster", activity_id=activity_id, title_base=title_base, **_values(files)
        ),
    )


def drop_poster(client, activity_id: int) -> Answer:
    db = _db(client)

    def dropped() -> None:
        call_port(RemoveFileOf(kind="activity_poster", activity_id=activity_id), db)
        db.commit()

    return _answer(dropped, done=204)


def set_component_info(
    client, component_id: int, files: Any, *, title_base: str = "Activiteit - Onderdeel - info"
) -> Answer:
    """A component's info document, through `StoreFile`."""
    return _store(
        client,
        StoreFile(
            kind="component_info",
            component_id=component_id,
            title_base=title_base,
            **_values(files),
        ),
    )


def update(client, asset_id: int, payload: dict) -> Answer:
    return _answer(lambda: service.update_media(_db(client), asset_id, payload))


def delete(client, asset_id: int) -> Answer:
    def call():
        service.delete_media(_db(client), asset_id)
        return {"detail": "Verwijderd"}

    return _answer(call)
