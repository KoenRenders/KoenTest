"""Publieke facade van het chatbot-component (fase 4c, #404)."""
from app.domains.chatbot.models import ChatbotInfo  # noqa: F401

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
from app.domains.chatbot.seam import (  # noqa: F401
    GuardedProvider,
    SeamBlocked,
    admin_rules,
    public_rules,
)
from app.domains.chatbot.service import ChatTimeout, run_chat  # noqa: F401
from app.domains.chatbot.providers import get_provider  # noqa: F401
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
    "get_provider", "public_rules", "run_chat", "sink_for", "create_note", "delete_row", "get_row",
    "list_chatbot_info",
    "toggle_row", "update_row","ChatbotInfo"]
