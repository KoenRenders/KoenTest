from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.email_log import EmailLog
from app.models.user import User
from app.schemas.email_log import EmailLogPage

router = APIRouter(tags=["email-log"])


@router.get("/email-log", response_model=EmailLogPage)
def list_email_log(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
    email_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    recipient: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Overzicht van verstuurde mails (#328). Admin-only — bevat persoonsgegevens
    (adressen + volledige inhoud). Filterbaar op type/status/ontvanger."""
    q = db.query(EmailLog)
    if email_type:
        q = q.filter(EmailLog.email_type == email_type)
    if status:
        q = q.filter(EmailLog.status == status)
    if recipient:
        q = q.filter(EmailLog.recipient.ilike(f"%{recipient}%"))

    total = q.with_entities(func.count(EmailLog.id)).scalar() or 0
    items = (
        q.order_by(EmailLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {"items": items, "total": total, "page": page, "per_page": per_page}
