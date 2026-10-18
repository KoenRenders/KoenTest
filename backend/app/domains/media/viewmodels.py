"""View-models of the media library's screens (#2130)."""

from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class MediaRecordView(ViewModel):
    """`media_record.html`: one picture, read or edited, with where it is used."""

    asset: dict[str, Any]
    title: str
    badges: list[dict[str, str]]
    facts: list[dict[str, str]]
    primary: dict[str, str] | None
    actions: list[dict[str, Any]]
    way_back: dict[str, str]
    editing: bool
    is_sponsor: bool
    #: The picture's tags as their paths ("Jeugd › Kamp"), and as the choice's values.
    tag_labels: list[str]
    tag_ids: list[str]
    tag_options: list[tuple[str, str]]
    uses: list[dict[str, str]]
    #: The list the record was opened from; saving and deleting return to it.
    terug: str
    record_url: str
    csrf_token: str
    nav_items: list[Any] = field(default_factory=list)
