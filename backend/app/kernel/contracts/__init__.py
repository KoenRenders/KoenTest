"""Contracten — DTO's en event-definities die de grens tussen componenten vormen.

Regels (§9, §12):
- Alleen waarden en frozen dataclasses/Pydantic-DTO's, nooit ORM-objecten.
- Additief wijzigen is vrij; breaking = deprecatie-cyclus (V2 naast V1).
- Elk component declareert in zijn CONTRACT.md welke contracten het publiceert
  en consumeert; dit pakket is de gedeelde vindplaats.
"""
