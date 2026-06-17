"""Chatbot-domein ('Raakje', #205).

Een publieke website-chatbot die bezoekers informeert over de vereniging,
activiteiten en lidmaatschap, en hen via de bestaande IdeaBox een vraag of idee
laat achterlaten. De LLM-aanroep zit achter een dun, swapbaar laagje
(``providers``) zodat de productie-provider (Mistral, EU) inschuift zonder de
router/tools/widget te raken. POC draait op Mistral Small 4, met een
``MockProvider`` als afhankelijkheidsvrije fallback voor CI/lokaal.
"""
