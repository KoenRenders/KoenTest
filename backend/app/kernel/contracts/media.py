"""The ports media handles (contract, see media/CONTRACT.md) — `kernel/ports.py`,
`docs/architecture.md` §3.2.1 step 2.

One set for every domain that stores or removes a file in media, named by what
media does and not by who asks. The bytes cross here once: the caller's door
read the upload, its service hands the bytes over. Media commits nothing — the
caller's door does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.kernel.ports import Port


@dataclass(frozen=True)
class AssetStored:
    """The outcome of `StoreFile`: the asset that holds the file, as media named
    and kept it (an image is re-encoded, so the content type may differ)."""

    asset_id: int
    title: Optional[str]
    content_type: str


@dataclass(frozen=True)
class AssetsRemoved:
    """The outcome of both removes: how many assets went."""

    count: int


@dataclass(frozen=True)
class StoreFile(Port):
    """Store one file of a kind, for an owner or for none.

    `kind` is media's stored code. By the kind media decides what happens: an
    activity's poster and a component's info document take the place of the one
    their owner had and get their text read (a job, started when the caller's
    transaction commits); a render and a newsletter's attachment are kept beside
    the others; a design image is re-encoded like every uploaded image.

    Refused with media's `MediaFout`, which carries the sentence for the screen:
    a content type the kind does not take, an empty file, a file over media's
    limit (`MAX_UPLOAD_BYTES`), a file that is not what its type says, a poster
    or an info document without its owner. A design image for an activity that
    does not exist raises `LookupError`, as the upload did.
    """

    kind: str
    filename: str
    content_type: str
    content: bytes
    #: The owner: an activity (a poster, a design image) or a component (its info).
    activity_id: Optional[int] = None
    component_id: Optional[int] = None
    #: A name for the file without its extension — for a poster and an info
    #: document, which are shown by that name; media adds the extension.
    title_base: Optional[str] = None


@dataclass(frozen=True)
class RemoveAsset(Port):
    """Remove one asset by its id. An id that is not there raises `LookupError`."""

    asset_id: int


@dataclass(frozen=True)
class RemoveFileOf(Port):
    """Remove what an owner has of a kind — an activity's poster, a component's
    info document. Nothing there is no refusal: the outcome counts zero."""

    kind: str
    activity_id: Optional[int] = None
    component_id: Optional[int] = None


@dataclass(frozen=True)
class ReadingPlanned:
    """The outcome of `ReadTextAgain`: the document whose text will be read."""

    asset_id: int


@dataclass(frozen=True)
class ReadTextAgain(Port):
    """Read the text of a stored document once more — the "Opnieuw lezen" button
    of the AI context. Media plans the reading as a job that starts when the
    caller's transaction commits; only the extracted text is replaced, a manual
    override or addition stays. An asset that is not there, or of a kind whose
    text is never read, raises `LookupError`."""

    asset_id: int
