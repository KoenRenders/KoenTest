"""The attributes of the `chatbot` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="chatbot.ai_call_log.surface",
        columns=("ai.ai_call_log.surface",),
        label=None,
        name_en="Surface",
        help="The surface of the ai call log, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="chatbot.ai_call_log.capability",
        columns=("ai.ai_call_log.capability",),
        label=None,
        name_en="Capability",
        help="The capability of the ai call log, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="chatbot.ai_call_log.actor",
        columns=("ai.ai_call_log.actor",),
        label=None,
        name_en="Actor",
        help="The actor of the ai call log.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="chatbot.ai_call_log.model",
        columns=("ai.ai_call_log.model",),
        label=None,
        name_en="Model",
        help="The model of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="chatbot.ai_call_log.payload",
        columns=("ai.ai_call_log.payload",),
        label=None,
        name_en="Payload",
        help="The payload of the ai call log.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="chatbot.ai_call_log.tokens_prompt",
        columns=("ai.ai_call_log.tokens_prompt",),
        label=None,
        name_en="Tokens prompt",
        help="The tokens prompt of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="chatbot.ai_call_log.tokens_completion",
        columns=("ai.ai_call_log.tokens_completion",),
        label=None,
        name_en="Tokens completion",
        help="The tokens completion of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.ai_call_log.blocked_reason",
        columns=("ai.ai_call_log.blocked_reason",),
        label=None,
        name_en="Blocked reason",
        help="The blocked reason of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="chatbot.ai_call_log.provider",
        columns=("ai.ai_call_log.provider",),
        label=None,
        name_en="Provider",
        help="The provider of the ai call log, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="chatbot.ai_call_log.endpoint",
        columns=("ai.ai_call_log.endpoint",),
        label=None,
        name_en="Endpoint",
        help="The endpoint of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="chatbot.ai_call_log.provider_request_id",
        columns=("ai.ai_call_log.provider_request_id",),
        label=None,
        name_en="Provider request id",
        help="The provider request id of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="chatbot.ai_call_log.status",
        columns=("ai.ai_call_log.status",),
        label=None,
        name_en="Status",
        help="The status of the ai call log, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="chatbot.ai_call_log.duration_ms",
        columns=("ai.ai_call_log.duration_ms",),
        label=None,
        name_en="Duration ms",
        help="The duration ms of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.ai_call_log.cost_credits",
        columns=("ai.ai_call_log.cost_credits",),
        label=None,
        name_en="Cost credits",
        help="The cost credits of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.ai_call_log.cost_amount",
        columns=("ai.ai_call_log.cost_amount",),
        label=None,
        name_en="Cost amount",
        help="The cost amount of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.ai_call_log.cost_currency",
        columns=("ai.ai_call_log.cost_currency",),
        label=None,
        name_en="Cost currency",
        help="The cost currency of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="chatbot.ai_call_log.output_megapixels",
        columns=("ai.ai_call_log.output_megapixels",),
        label=None,
        name_en="Output megapixels",
        help="The output megapixels of the ai call log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.chatbot_info.media_asset_id",
        columns=("ai.chatbot_info.media_asset_id",),
        label=None,
        name_en="Media asset id",
        help="The media asset id of the chatbot info.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.chatbot_info.cms_page_id",
        columns=("ai.chatbot_info.cms_page_id",),
        label=None,
        name_en="Cms page id",
        help="The cms page id of the chatbot info.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.chatbot_info.title",
        columns=("ai.chatbot_info.title",),
        label=None,
        name_en="Title",
        help="The title of the chatbot info.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="chatbot.chatbot_info.extracted_text",
        columns=("ai.chatbot_info.extracted_text",),
        label=None,
        name_en="Extracted text",
        help="The extracted text of the chatbot info.",
        ai_exposure=AiExposure.PUBLIC,  # K5 — the public bot reads the poster text (#206)
    ),
    Attribute(
        key="chatbot.chatbot_info.text_override",
        columns=("ai.chatbot_info.text_override",),
        label=None,
        name_en="Text override",
        help="The text override of the chatbot info.",
        ai_exposure=AiExposure.PUBLIC,  # K5 — the public bot reads the poster text (#206)
    ),
    Attribute(
        key="chatbot.chatbot_info.text_addition",
        columns=("ai.chatbot_info.text_addition",),
        label=None,
        name_en="Text addition",
        help="The text addition of the chatbot info.",
        ai_exposure=AiExposure.PUBLIC,  # K5 — the public bot reads the poster text (#206)
    ),
    Attribute(
        key="chatbot.chatbot_info.extracted_at",
        columns=("ai.chatbot_info.extracted_at",),
        label=None,
        name_en="Extracted at",
        help="The extracted at of the chatbot info.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.chatbot_info.is_active",
        columns=("ai.chatbot_info.is_active",),
        label=None,
        name_en="Is active",
        help="The is active of the chatbot info.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="chatbot.chatbot_info.sort_order",
        columns=("ai.chatbot_info.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the chatbot info.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)
