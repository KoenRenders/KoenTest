"""What audit's service still holds: the name of the actor when nobody was signed in.

The snapshot helpers that stood here write a row of a history table, and a
history table is its component's (`docs/architecture.md` §5.8): each of them
lives with its owner now, in `<domain>/history.py` (CR-13 phase 4c, #1251).
"""

# #713: wat er in `actor` staat wanneer er níemand aangemeld was.
#
# Leeg betekende twee dingen tegelijk — "er was niemand aangemeld" én "we zijn
# vergeten wie dit deed" — en het scherm toont allebei als een lege cel. Daardoor kon
# niemand zo'n cel lezen, en kon een volgende vergetelheid er ongemerkt bij komen; zo
# zijn de vier ontstaan die dit issue rechtzet.
#
# Vanaf nu schrijven de publieke wegen dit, en betekent leeg **fout**. Geen `@`, dus
# niet te verwarren met een e-mailadres. Bestaande rijen blijven leeg: die kunnen we
# niet met terugwerkende kracht duiden en horen we ook niet zo te behandelen.
PUBLIEKE_ACTOR = "publiek"
