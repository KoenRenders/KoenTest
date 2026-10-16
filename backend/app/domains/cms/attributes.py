"""The attributes of the `cms` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="cms.cms_page.title",
        columns=("cms.cms_pages.title",),
        label=None,
        name_en="Title",
        help="The title of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.slug",
        columns=("cms.cms_pages.slug",),
        label=None,
        name_en="Slug",
        help="The slug of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.content",
        columns=("cms.cms_pages.content",),
        label=None,
        name_en="Content",
        help="The content of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.is_published",
        columns=("cms.cms_pages.is_published",),
        label=None,
        name_en="Is published",
        help="The is published of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.show_in_nav",
        columns=("cms.cms_pages.show_in_nav",),
        label=None,
        name_en="Show in nav",
        help="The show in nav of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.is_home",
        columns=("cms.cms_pages.is_home",),
        label=None,
        name_en="Is home",
        help="The is home of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.show_in_footer",
        columns=("cms.cms_pages.show_in_footer",),
        label=None,
        name_en="Show in footer",
        help="The show in footer of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.parent_id",
        columns=("cms.cms_pages.parent_id",),
        label="Onder sectie",
        name_en="Section",
        help="The page this page stands under in the site's menu (CR-17 phase 6).",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.sort_order",
        columns=("cms.cms_pages.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.opening",
        columns=("cms.cms_pages.opening",),
        label=None,
        name_en="Opening",
        help="The opening of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page.hero",
        columns=("cms.cms_pages.hero",),
        label=None,
        name_en="Hero",
        help="The hero of the cms page.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page_translation.title",
        columns=("cms.page_translations.title",),
        label=None,
        name_en="Title",
        help="The title of the cms page translation.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page_translation.menu_label",
        columns=("cms.page_translations.menu_label",),
        label="Naam in het menu",
        name_en="Menu label",
        help="The menu label of the cms page translation.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page_translation.draft_json",
        columns=("cms.page_translations.draft_json",),
        label=None,
        name_en="Draft json",
        help="The draft json of the cms page translation.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page_translation.published_json",
        columns=("cms.page_translations.published_json",),
        label=None,
        name_en="Published json",
        help="The published json of the cms page translation.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page_translation.published_at",
        columns=("cms.page_translations.published_at",),
        label=None,
        name_en="Published at",
        help="The published at of the cms page translation.",
        ai_exposure=AiExposure.PUBLIC,  # K4
    ),
    Attribute(
        key="cms.cms_page_translation.published_by",
        columns=("cms.page_translations.published_by",),
        label=None,
        name_en="Published by",
        help="The published by of the cms page translation.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
)
