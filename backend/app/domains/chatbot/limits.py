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

# Het budget van de backoffice-assistent, apart van het publieke (#917). Twee
# tellers en niet één: een beheerder die een middag rapporteert, mag de bezoeker op
# de site niet buitensluiten — en omgekeerd. Deze telt per aangemelde beheerder,
# niet per IP.
admin_chat_char_budget = DailyCharBudget(settings.admin_chat_daily_char_budget)
