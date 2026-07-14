"""Admin-endpoints van het audit-domein: wijzigingen-feeds (#82, #189).

(verhuisd uit app/routers/admin.py, #444)
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import User, get_current_admin

router = APIRouter(tags=["admin"])


# ── Ledendata-wijzigingen sinds datum (#82) ───────────────────────────────────

@router.get("/member-changes")
def list_member_changes(
    since: date = Query(..., description="Toon wijzigingen vanaf deze datum (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Alle ledendata-wijzigingen sinds `since`, voor manuele overname in Raak
    Nationaal. Admin-only; bevat persoonsdata."""
    from app.domains.audit.changes import member_changes_since
    return member_changes_since(db, since)


@router.get("/member-changes/export")
def export_member_changes(
    since: date = Query(..., description="Toon wijzigingen vanaf deze datum (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Dezelfde wijzigingen als .ods-download (OpenDocument)."""
    from app.domains.audit.changes import member_changes_since, build_member_changes_ods
    content = build_member_changes_ods(member_changes_since(db, since))
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="ledenwijzigingen-vanaf-{since}.ods"'},
    )


# ── Uniforme Wijzigingen/audit-feed (#189) ────────────────────────────────────

@router.get("/changes")
def list_all_changes(
    since: date = Query(..., description="Toon wijzigingen vanaf deze datum (YYYY-MM-DD)"),
    group: Optional[str] = Query(None, description="Filter op objectgroep"),
    actor: Optional[str] = Query(None, description="Filter op actor (e-mail)"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Uniforme audit-feed: alle wijzigingen (leden, activiteiten, inschrijvingen,
    betalingen) sinds `since`, optioneel gefilterd op objectgroep en/of actor.
    Admin-only; bevat persoonsdata."""
    from app.domains.audit.changes import all_changes_since, GROUPS
    return {"groups": GROUPS, "rows": all_changes_since(db, since, group=group, actor=actor)}
