"""Publieke facade van het chatbot-component (fase 4c, #404)."""
from app.domains.chatbot.models import ChatbotInfo  # noqa: F401

# CR-12 phase 4: the four code lists of the AI call log, for every caller that
# writes a row — the design studio, OCR, dictation and the capability packs.
from app.domains.chatbot.codes import (  # noqa: F401
    AI_CAPABILITY,
    AI_PROVIDER,
    AI_STATUS,
    AI_SURFACE,
)
from app.domains.chatbot.models import (  # noqa: F401
    AiCapability,
    AiProvider,
    AiStatus,
    AiSurface,
)

# Het dagbudget is gedeelde toestand tussen de JSON-route en het scherm: beide
# schrijven naar dezelfde teller, dus het moet dezelfde instantie zijn (#635 I).
from app.domains.chatbot.limits import (  # noqa: F401
    admin_chat_char_budget,
    chat_char_budget,
)

# De naad: alles wat een capability-pakket nodig heeft om op de gedeelde lus te
# draaien (CR-07 §4.1). Één export, zodat een pakket de chatbot-internals niet
# hoeft te kennen — en zodat de wachter en het logboek er niet omheen te bouwen
# zijn.
from app.domains.chatbot.logbook import sink_for  # noqa: F401

# #978: what the AI cost a department — one reader for the screen and for CR-10.
from app.domains.chatbot.costs import (  # noqa: F401
    CallRow,
    CostLine,
    cost_per_period,
    list_calls,
    month_period,
)
from app.domains.chatbot.seam import (  # noqa: F401
    REDACTION_PLACEHOLDERS,
    GuardedProvider,
    SeamBlocked,
    admin_rules,
    public_rules,
    redact,
)
from app.domains.chatbot.service import ChatTimeout, run_chat  # noqa: F401
from app.domains.chatbot.providers import get_provider  # noqa: F401


# #975: de leestools van de publieke bot, uitgeleend aan de beheer-assistent. Lazy,
# om dezelfde reden als `run_public_chat`: `tools` haalt `media.api` binnen, dat op
# zijn beurt deze facade importeert.
def read_tool_specs():
    from app.domains.chatbot.tools import read_tool_specs as _impl

    return _impl()


def execute_read_tool(name, arguments, db):
    from app.domains.chatbot.tools import execute_read_tool as _impl

    return _impl(name, arguments, db)


def read_only_tool_names():
    from app.domains.chatbot.tools import READ_ONLY_TOOLS

    return READ_ONLY_TOOLS
from app.domains.chatbot.info_service import (  # noqa: F401
    create_note,
    delete_row,
    get_row,
    list_chatbot_info,
    toggle_row,
    update_row,
)

__all__ = [
    "admin_chat_char_budget", "chat_char_budget",
    "ChatTimeout", "GuardedProvider", "SeamBlocked", "admin_rules",
    "REDACTION_PLACEHOLDERS", "get_provider", "public_rules", "redact", "run_chat", "sink_for",
    "CallRow", "CostLine", "cost_per_period", "list_calls", "month_period",
    "execute_read_tool", "read_only_tool_names", "read_tool_specs", "create_note", "delete_row", "get_row",
    "list_chatbot_info",
    "toggle_row", "update_row","ChatbotInfo"]
