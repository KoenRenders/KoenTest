"""View-models of the Design Studio screens (CR-10, #1007).

What each screen gets from its route, typed, in one place — so a wrong or
forgotten key is an error in the route instead of an empty box on the screen,
and `tests/test_template_variables_gate.py` can prove statically that the
templates ask for nothing that is not promised here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True)
class DesignRow:
    """One line of the list: the design and the facts around it, flat."""
    id: int
    activity_id: int
    activity_name: str
    preset_label: str
    status_label: str
    status_tone: str
    version_count: int
    published: bool
    stale: bool
    updated: str


@dataclass(frozen=True)
class ImageOption:
    """A picture the unit can put in a slot: an activity photo, an uploaded
    design image or a fetched AI variant."""
    id: int
    thumb_url: str
    label: str
    source: str  # activity_photo | design_image | generated


@dataclass(frozen=True)
class HighlightRow:
    icon: str
    text: str
    emphasis: bool


@dataclass(frozen=True)
class VersionRow:
    id: int
    number: int
    created: str
    published: bool
    stale: bool
    files: list[dict[str, str]]  # label, url


@dataclass(frozen=True)
class GenerationRow:
    id: int
    status: str
    status_label: str
    thumb_url: str
    media_asset_id: Optional[int]
    failure_reason: str
    scene: str
    style: str
    image_url: str


@dataclass(frozen=True, kw_only=True)
class DesignListView(ViewModel):
    """`admin_ontwerpen.html` and its fragment `_ds_lijst.html`."""

    rows: list[DesignRow]
    q: str = ""
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class DesignNewView(ViewModel):
    """`admin_ontwerp_nieuw.html` — creating happens on its own screen, not in
    a modal (design-system §2.8)."""

    activity_options: list[tuple[int, str]]
    activity_id: str
    duo_options: list[tuple[str, str]]
    duo_code: str
    preset_options: list[tuple[str, str]]
    preset: str
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class DesignEditorView(ViewModel):
    """`admin_ontwerp.html` — the editor — and its fragment `_ds_voorbeeld.html`."""

    design_id: int
    activity_id: int
    activity_name: str
    status: str
    status_label: str
    status_tone: str

    # Form values, flat strings as the form posts them.
    preset: str
    preset_options: list[tuple[str, str]]
    duo_code: str
    duo_options: list[tuple[str, str]]
    tagline: str
    subtitle: str
    # "Omschrijving anders": the activity's description unless the design
    # typed its own; `explanation_is_own` says which one the field shows.
    explanation_md: str
    explanation_is_own: bool
    highlights: list[HighlightRow]
    icon_options: list[tuple[str, str]]

    # Images
    main_image_id: Optional[int]
    inset_image_id: Optional[int]
    third_image_id: Optional[int]
    main_focus_x: str
    main_focus_y: str
    inset_corner: str
    corner_options: list[tuple[str, str]]
    image_options: list[ImageOption]
    logo_options: list[ImageOption]
    logo_ids: list[int]

    # Facts shown read-only, from the activity.
    facts: list[tuple[str, str]]
    facts_href: str

    # Preview and checks
    preview_url: str
    #: The same picture at print resolution, for "Groot bekijken" — slow to
    #: render, so it is not what the panel shows inline.
    preview_large_url: str
    layout: str
    layout_options: list[tuple[str, str]]
    violations: list[str]
    warnings: list[str]
    render_error: Optional[str]
    edited_layouts: list[str]
    font_links: list[tuple[str, str]]

    versions: list[VersionRow]
    published_version_id: Optional[int]
    max_versions: int

    # AI images
    ai_enabled: bool
    ai_budget_line: str
    generations: list[GenerationRow]
    ai_prompt: str
    ai_style: str
    style_options: list[tuple[str, str]]
    style_texts: dict[str, str]      # what the model is told per style, shown so nobody guesses
    ai_pending: bool                 # variants still under way → the grid polls

    csrf_token: str
    error: Optional[str] = None
    notice: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)
