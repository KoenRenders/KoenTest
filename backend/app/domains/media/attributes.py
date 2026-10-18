"""The attributes of the `media` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="media.media_asset.kind",
        columns=("media.media_assets.kind",),
        label="Soort",
        name_en="Kind",
        help="The kind of the media asset, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="media.media_asset.activity_id",
        columns=("media.media_assets.activity_id",),
        label="Activiteit",
        name_en="Activity id",
        help="The activity id of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.component_id",
        columns=("media.media_assets.component_id",),
        label=None,
        name_en="Component id",
        help="The component id of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.data",
        columns=("media.media_assets.data",),
        label=None,
        name_en="Data",
        help="The data of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.content_type",
        columns=("media.media_assets.content_type",),
        label=None,
        name_en="Content type",
        help="The content type of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.thumbnail",
        columns=("media.media_assets.thumbnail",),
        label=None,
        name_en="Thumbnail",
        help="The thumbnail of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.thumb_content_type",
        columns=("media.media_assets.thumb_content_type",),
        label=None,
        name_en="Thumb content type",
        help="The thumb content type of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.byte_size",
        columns=("media.media_assets.byte_size",),
        label=None,
        name_en="Byte size",
        help="The byte size of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.width",
        columns=("media.media_assets.width",),
        label=None,
        name_en="Width",
        help="The width of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.height",
        columns=("media.media_assets.height",),
        label=None,
        name_en="Height",
        help="The height of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.title",
        columns=("media.media_assets.title",),
        label="Titel",
        name_en="Title",
        help="The title of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.link_url",
        columns=("media.media_assets.link_url",),
        label="Link",
        name_en="Link url",
        help="The link url of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.sort_order",
        columns=("media.media_assets.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.is_active",
        columns=("media.media_assets.is_active",),
        label="Actief",
        name_en="Is active",
        help="The is active of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_asset.show_in_footer",
        columns=("media.media_assets.show_in_footer",),
        label="Toon onder de publieke pagina's",
        name_en="Show in footer",
        help="The show in footer of the media asset.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_tag.name",
        columns=("media.tags.name",),
        label=None,
        name_en="Name",
        help="The name of the media tag.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="media.media_thumbs_up.visitor_token",
        columns=("media.media_thumbs_up.visitor_token",),
        label=None,
        name_en="Visitor token",
        help="The visitor token of the media thumbs up.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
)
