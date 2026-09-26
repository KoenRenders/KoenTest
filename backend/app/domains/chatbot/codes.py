"""The code lists of the AI call log (CR-12 phase 4).

Four columns of `ai.ai_call_log` that held free strings: where a call came
from, what it was for, how it went and who answered it. The Dutch words are
taken literally from the dictionaries `chatbot/admin_ui.py` used until now
(§B8.5: the same words as before); the codes that had no word there — the
design studio, translation, image and the providers — get theirs here.

The tones are those of `STATUS_TONES`: a refusal is a warning, not a failure.
"""
from app.domains.chatbot.models import (
    AiCapability,
    AiCapabilityCode,
    AiCapabilityLabel,
    AiProvider,
    AiProviderCode,
    AiProviderLabel,
    AiStatus,
    AiStatusCode,
    AiStatusLabel,
    AiSurface,
    AiSurfaceCode,
    AiSurfaceLabel,
)
from app.kernel.codes import CodeList, CodeSeed

AI_SURFACE_CODES = (
    CodeSeed(code="public", nl="Publiek", en="Public", sort_order=10),
    CodeSeed(code="admin", nl="Beheer", en="Back office", sort_order=20),
    CodeSeed(code="designstudio", nl="Ontwerpstudio", en="Design studio",
             sort_order=30),
)

AI_SURFACE = CodeList(
    name="ai_surface", schema="ai",
    codes=AiSurfaceCode, labels=AiSurfaceLabel, enum=AiSurface,
    fk_from=("ai.ai_call_log.surface",),
)

AI_CAPABILITY_CODES = (
    CodeSeed(code="chat", nl="Chat", en="Chat", sort_order=10),
    CodeSeed(code="reporting", nl="Rapporten", en="Reports", sort_order=20),
    CodeSeed(code="newsletter_drafting", nl="Nieuwsbrief", en="Newsletter",
             sort_order=30),
    CodeSeed(code="ocr", nl="Documenten lezen", en="Reading documents",
             sort_order=40),
    CodeSeed(code="dictation", nl="Dicteren", en="Dictation", sort_order=50),
    CodeSeed(code="translate", nl="Vertalen", en="Translation", sort_order=60),
    CodeSeed(code="image", nl="Beeld", en="Image", sort_order=70),
)

AI_CAPABILITY = CodeList(
    name="ai_capability", schema="ai",
    codes=AiCapabilityCode, labels=AiCapabilityLabel, enum=AiCapability,
    fk_from=("ai.ai_call_log.capability",),
)

AI_STATUS_CODES = (
    CodeSeed(code="ok", nl="Gelukt", en="Succeeded", sort_order=10),
    CodeSeed(code="blocked", nl="Tegengehouden", en="Held back", sort_order=20),
    CodeSeed(code="error", nl="Mislukt", en="Failed", sort_order=30),
    CodeSeed(code="moderated", nl="Geweigerd door de provider",
             en="Refused by the provider", sort_order=40),
)

AI_STATUS = CodeList(
    name="ai_status", schema="ai",
    codes=AiStatusCode, labels=AiStatusLabel, enum=AiStatus,
    fk_from=("ai.ai_call_log.status",),
)

AI_PROVIDER_CODES = (
    CodeSeed(code="mistral", nl="Mistral", en="Mistral", sort_order=10),
    CodeSeed(code="bfl", nl="Black Forest Labs", en="Black Forest Labs",
             sort_order=20),
    CodeSeed(code="mock", nl="mock", en="mock", sort_order=30),
)

AI_PROVIDER = CodeList(
    name="ai_provider", schema="ai",
    codes=AiProviderCode, labels=AiProviderLabel, enum=AiProvider,
    fk_from=("ai.ai_call_log.provider",),
)
