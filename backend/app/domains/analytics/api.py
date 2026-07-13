"""Publieke facade van het analytics-component (fase 4c, #404): het
read-model op het rapportageschema (§5.8). Events zijn PII-vrij (afgedwongen
in de service)."""
from app.domains.analytics.models import BusinessEvent  # noqa: F401
from app.domains.analytics.service import log_business_event  # noqa: F401

__all__ = ["BusinessEvent", "log_business_event"]
