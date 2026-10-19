"""The attributes of the `designstudio` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="designstudio.design.activity_id",
        columns=("designstudio.designs.activity_id",),
        label=None,
        name_en="Activity id",
        help="The activity id of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.template_key",
        columns=("designstudio.designs.template_key",),
        label=None,
        name_en="Template key",
        help="The template key of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design.template_version",
        columns=("designstudio.designs.template_version",),
        label=None,
        name_en="Template version",
        help="The template version of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.preset",
        columns=("designstudio.designs.preset",),
        label="Opmaak",
        name_en="Preset",
        help="The preset of the design, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.design.duo_code",
        columns=("designstudio.designs.duo_code",),
        label="Kleurenduo",
        name_en="Duo code",
        help="The duo code of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.status",
        columns=("designstudio.designs.status",),
        label=None,
        name_en="Status",
        help="The status of the design, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.design.poster_title",
        columns=("designstudio.designs.poster_title",),
        label="Titel op de affiche",
        name_en="Poster title",
        help="The poster title of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design.tagline",
        columns=("designstudio.designs.tagline",),
        label="Handgeschreven lijn",
        name_en="Tagline",
        help="The tagline of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design.subtitle",
        columns=("designstudio.designs.subtitle",),
        label="Balk onder de titel",
        name_en="Subtitle",
        help="The subtitle of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design.explanation_md",
        columns=("designstudio.designs.explanation_md",),
        label="Omschrijving anders",
        name_en="Explanation md",
        help="The explanation md of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design.main_image_id",
        columns=("designstudio.designs.main_image_id",),
        label=None,
        name_en="Main image id",
        help="The main image id of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.main_focus_x",
        columns=("designstudio.designs.main_focus_x",),
        label="Brandpunt links–rechts",
        name_en="Main focus x",
        help="The main focus x of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.main_focus_y",
        columns=("designstudio.designs.main_focus_y",),
        label="Brandpunt boven–onder",
        name_en="Main focus y",
        help="The main focus y of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.inset_image_id",
        columns=("designstudio.designs.inset_image_id",),
        label=None,
        name_en="Inset image id",
        help="The inset image id of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.inset_corner",
        columns=("designstudio.designs.inset_corner",),
        label="Polaroid op de foto",
        name_en="Inset corner",
        help="The inset corner of the design, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.design.third_image_id",
        columns=("designstudio.designs.third_image_id",),
        label=None,
        name_en="Third image id",
        help="The third image id of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.published_version_id",
        columns=("designstudio.designs.published_version_id",),
        label=None,
        name_en="Published version id",
        help="The published version id of the design.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design.created_by",
        columns=("designstudio.designs.created_by",),
        label=None,
        name_en="Created by",
        help="The created by of the design.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="designstudio.design_highlight.sort_order",
        columns=("designstudio.design_highlights.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the design highlight.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_highlight.icon_code",
        columns=("designstudio.design_highlights.icon_code",),
        label="Icoon",
        name_en="Icon code",
        help="The icon code of the design highlight.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_highlight.text",
        columns=("designstudio.design_highlights.text",),
        label="Tekst van het kernpunt",
        name_en="Text",
        help="The text of the design highlight.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="designstudio.design_highlight.emphasis",
        columns=("designstudio.design_highlights.emphasis",),
        label=None,
        name_en="Emphasis",
        help="The emphasis of the design highlight.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_logo.media_asset_id",
        columns=("designstudio.design_logos.media_asset_id",),
        label="Logostrook",
        name_en="Media asset id",
        help="The media asset id of the design logo.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_logo.sort_order",
        columns=("designstudio.design_logos.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the design logo.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_rendition.layout_code",
        columns=("designstudio.design_renditions.layout_code",),
        label=None,
        name_en="Layout code",
        help="The layout code of the design rendition, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.design_rendition.variant",
        columns=("designstudio.design_renditions.variant",),
        label=None,
        name_en="Variant",
        help="The variant of the design rendition, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.design_rendition.size_code",
        columns=("designstudio.design_renditions.size_code",),
        label=None,
        name_en="Size code",
        help="The size code of the design rendition.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_rendition.media_asset_id",
        columns=("designstudio.design_renditions.media_asset_id",),
        label=None,
        name_en="Media asset id",
        help="The media asset id of the design rendition.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_rendition.facts_fingerprint",
        columns=("designstudio.design_renditions.facts_fingerprint",),
        label=None,
        name_en="Facts fingerprint",
        help="The facts fingerprint of the design rendition.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design_rendition.min_effective_dpi",
        columns=("designstudio.design_renditions.min_effective_dpi",),
        label=None,
        name_en="Min effective dpi",
        help="The min effective dpi of the design rendition.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_rendition.rendered_at",
        columns=("designstudio.design_renditions.rendered_at",),
        label=None,
        name_en="Rendered at",
        help="The rendered at of the design rendition.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_version.number",
        columns=("designstudio.design_versions.number",),
        label=None,
        name_en="Number",
        help="The number of the design version.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.design_version.facts_fingerprint",
        columns=("designstudio.design_versions.facts_fingerprint",),
        label=None,
        name_en="Facts fingerprint",
        help="The facts fingerprint of the design version.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design_version.sponsor_asset_ids",
        columns=("designstudio.design_versions.sponsor_asset_ids",),
        label=None,
        name_en="Sponsor asset ids",
        help="The sponsor asset ids of the design version.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.design_version.created_by",
        columns=("designstudio.design_versions.created_by",),
        label=None,
        name_en="Created by",
        help="The created by of the design version.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="designstudio.image_generation.request_key",
        columns=("designstudio.image_generations.request_key",),
        label=None,
        name_en="Request key",
        help="The request key of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.image_generation.ai_call_log_id",
        columns=("designstudio.image_generations.ai_call_log_id",),
        label=None,
        name_en="Ai call log id",
        help="The ai call log id of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.seed",
        columns=("designstudio.image_generations.seed",),
        label=None,
        name_en="Seed",
        help="The seed of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.scene",
        columns=("designstudio.image_generations.scene",),
        label=None,
        name_en="Scene",
        help="The scene of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="designstudio.image_generation.style",
        columns=("designstudio.image_generations.style",),
        label=None,
        name_en="Style",
        help="The style of the image generation, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.image_generation.width",
        columns=("designstudio.image_generations.width",),
        label=None,
        name_en="Width",
        help="The width of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.height",
        columns=("designstudio.image_generations.height",),
        label=None,
        name_en="Height",
        help="The height of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.status",
        columns=("designstudio.image_generations.status",),
        label=None,
        name_en="Status",
        help="The status of the image generation, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="designstudio.image_generation.failure_reason",
        columns=("designstudio.image_generations.failure_reason",),
        label=None,
        name_en="Failure reason",
        help="The failure reason of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="designstudio.image_generation.media_asset_id",
        columns=("designstudio.image_generations.media_asset_id",),
        label=None,
        name_en="Media asset id",
        help="The media asset id of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.reserved_cents",
        columns=("designstudio.image_generations.reserved_cents",),
        label=None,
        name_en="Reserved cents",
        help="The reserved cents of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.requested_by",
        columns=("designstudio.image_generations.requested_by",),
        label=None,
        name_en="Requested by",
        help="The requested by of the image generation.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="designstudio.image_generation.requested_at",
        columns=("designstudio.image_generations.requested_at",),
        label=None,
        name_en="Requested at",
        help="The requested at of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="designstudio.image_generation.finished_at",
        columns=("designstudio.image_generations.finished_at",),
        label=None,
        name_en="Finished at",
        help="The finished at of the image generation.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)
