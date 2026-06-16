"""Swapbare LLM-provider-laag voor de chatbot.

De enige naad tussen de chatbot-logica en een concrete LLM-leverancier. Wie de
productie-provider wil wisselen (Mistral → Ionos/Infomaniak/self-hosted) raakt
enkel deze map aan; router, tools en widget blijven ongemoeid.
"""
from .base import AssistantMessage, LLMProvider, ToolCall
from .factory import get_provider

__all__ = ["AssistantMessage", "LLMProvider", "ToolCall", "get_provider"]
