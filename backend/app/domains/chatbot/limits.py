"""Gebruikslimieten van Raakje (#635 I).

Het dagelijkse tekenbudget stond in `router.py`, en het scherm importeerde het
daar rechtstreeks. Het is gedeelde toestand: de JSON-route en het scherm schrijven
naar dezelfde teller, dus het moet dezelfde instantie zijn — één module die beide
importeren, en geen router die als servicelaag dienstdoet.
"""
from app.config import settings
from app.limiter import DailyCharBudget

# Dagelijks tekenbudget per IP (config-gestuurd). Eén gedeelde instantie zodat de
# teller over requests heen blijft staan.
chat_char_budget = DailyCharBudget(settings.chat_daily_char_budget)
