"""Public facade of the Design Studio component (CR-10, #1007).

The only door for other components and for the screens. Today nothing else
reads it; the screens are its one caller.
"""
from app.domains.designstudio.brand import COLOURS, DUOS, ENABLED_DUOS, check_template, palette_for  # noqa: F401
from app.domains.designstudio.icons import ICONS  # noqa: F401
from app.domains.designstudio.imaging import STYLE_LABELS, STYLES, Budget, ImagingError  # noqa: F401
from app.domains.designstudio.models import (  # noqa: F401
    GENERATION_STATES,
    LAYOUT_FEED,
    LAYOUT_PRINT,
    LAYOUTS,
    PRESETS,
    STATUS_DRAFT,
    STATUS_FINAL,
    Design,
    DesignRendition,
    DesignVersion,
    ImageGeneration,
)
from app.domains.designstudio.render import RenderError  # noqa: F401
from app.domains.designstudio.service import (  # noqa: F401
    LAYOUT_LABELS,
    MAX_HIGHLIGHTS,
    MAX_LOGOS,
    MAX_VERSIONS,
    PRESET_LABELS,
    STATUS_LABELS,
    STATUS_TONES,
    DesignError,
    add_design_image,
    budget,
    check_design,
    content_for,
    create_design,
    delete_design,
    edited_svg_for,
    facts_for,
    fingerprint,
    get_design,
    image_options,
    is_stale,
    list_designs,
    make_version,
    pick_generation,
    preview_png,
    publish,
    remove_edited_svg,
    rendition,
    request_images,
    save_design,
    sponsor_options,
    sponsor_usage,
    upload_edited_svg,
    warnings_for,
)

__all__ = [
    "COLOURS", "DUOS", "ENABLED_DUOS", "check_template", "palette_for", "ICONS",
    "Budget", "ImagingError", "RenderError", "DesignError", "STYLE_LABELS", "STYLES",
    "GENERATION_STATES", "LAYOUT_FEED", "LAYOUT_PRINT", "LAYOUTS", "PRESETS", "STATUS_DRAFT", "STATUS_FINAL",
    "LAYOUT_LABELS", "MAX_HIGHLIGHTS", "MAX_LOGOS", "MAX_VERSIONS", "PRESET_LABELS", "STATUS_LABELS", "STATUS_TONES",
    "Design", "DesignRendition", "DesignVersion", "ImageGeneration",
    "add_design_image", "budget", "check_design", "content_for", "create_design", "delete_design",
    "edited_svg_for", "facts_for", "fingerprint", "get_design", "image_options", "is_stale", "list_designs",
    "make_version", "pick_generation", "preview_png", "publish", "remove_edited_svg", "rendition",
    "request_images", "save_design", "sponsor_options", "sponsor_usage", "upload_edited_svg", "warnings_for",
]
