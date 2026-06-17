"""Pydantic-schema's voor het admin-beheer van chatbot_info (#235)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatbotInfoEdit(BaseModel):
    """Bewerkbare velden van een chatbot_info-rij (media-/cms-/notitie-rij)."""
    title: Optional[str] = None
    text_override: Optional[str] = None
    text_addition: Optional[str] = None
    is_active: bool = True
    sort_order: Optional[int] = None


class NoteCreate(BaseModel):
    """Een vrijstaande 'eigen AI-context'-notitie (geen FK)."""
    title: Optional[str] = None
    text_addition: str = Field(min_length=1)
    is_active: bool = True
