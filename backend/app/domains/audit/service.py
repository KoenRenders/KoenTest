"""Snapshot-helpers die een momentopname van een bron-rij in de bijbehorende
history-tabel wegschrijven.

Elke helper doet enkel ``db.add(...)`` en GEEN commit: de history-rij commit mee
in dezelfde transactie als de wijziging zelf (atomair — of allebei, of geen van
beide). Roep de helper dus aan vóór de ``db.commit()`` van de caller, en bij een
verwijdering vóór de ``db.delete(...)`` zodat de bron nog uitleesbaar is.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.membership.api import MembershipHistory

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


def snapshot_membership(
    db: Session,
    membership,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    db.add(
        MembershipHistory(
            membership_id=membership.id,
            member_id=membership.member_id,
            year=membership.year,
            is_active=membership.is_active,
            valid_from=membership.valid_from,
            valid_to=membership.valid_to,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )
