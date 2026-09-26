"""Public facade of the Design Studio component (CR-10, #1007).

The only door for other components and for the screens. Today nothing else
reads it; the screens are its one caller.
"""
from app.domains.designstudio.brand import COLOURS, DUOS, ENABLED_DUOS, check_template, palette_for  # noqa: F401
from app.domains.designstudio.codes import (  # noqa: F401
    DESIGN_STATUS,
    DRAWING_STYLE,
    GENERATION_STATUS,
    INSET_CORNER,
    LAYOUT,
    PRESET,
    RENDER_VARIANT,
)
from app.domains.designstudio.icons import ICONS  # noqa: F401
from app.domains.designstudio.imaging import STYLES, Budget, ImagingError  # noqa: F401
from app.domains.designstudio.models import (  # noqa: F401
    Design,
    DesignRendition,
    DesignStatus,
    DesignVersion,
    DrawingStyle,
    GenerationStatus,
    ImageGeneration,
    InsetCorner,
    Layout,
    Preset,
    RenderVariant,
)
from app.domains.designstudio.render import RenderError  # noqa: F401
from app.domains.designstudio.service import (  # noqa: F401
    MAX_HIGHLIGHTS,
    MAX_LOGOS,
    MAX_VERSIONS,
    DesignError,
    add_design_image,
    budget,
    check_design,
    content_for,
    create_design,
    delete_design,
    designs_for_activity,
    edited_svg_for,
    facts_for,
    fingerprint,
    get_design,
    image_options,
    is_stale,
    list_designs,
    make_version,
    pick_generation,
    file_slug,
    FILE_LAYOUT_LABELS,
    preview_png,
    PREVIEW_LARGE_PX,
    PREVIEW_PX,
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
    "Budget", "ImagingError", "RenderError", "DesignError", "STYLES",
    "DESIGN_STATUS", "DRAWING_STYLE", "GENERATION_STATUS", "INSET_CORNER",
    "LAYOUT", "PRESET", "RENDER_VARIANT",
    "DesignStatus", "DrawingStyle", "GenerationStatus", "InsetCorner", "Layout",
    "Preset", "RenderVariant",
    "MAX_HIGHLIGHTS", "MAX_LOGOS", "MAX_VERSIONS",
    "PREVIEW_PX", "PREVIEW_LARGE_PX", "file_slug", "FILE_LAYOUT_LABELS",
    "Design", "DesignRendition", "DesignVersion", "ImageGeneration",
    "add_design_image", "budget", "check_design", "content_for", "create_design", "delete_design", "designs_for_activity",
    "edited_svg_for", "facts_for", "fingerprint", "get_design", "image_options", "is_stale", "list_designs",
    "make_version", "pick_generation", "preview_png", "publish", "remove_edited_svg", "rendition",
    "request_images", "save_design", "sponsor_options", "sponsor_usage", "upload_edited_svg", "warnings_for",
]
