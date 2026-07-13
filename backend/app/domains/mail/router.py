from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.auth.api import get_current_admin
from app.database import get_db
from app.domains.mail.models import EmailLog
from app.domains.auth.api import User
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


@router.delete("/email-log/{log_id}", status_code=204)
def delete_email_log(
    log_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Verwijder één gelogde mail (#328). Harde delete: de email_log is een log
    (geen soft-delete), en de bewaartermijn-opschoning verwijdert sowieso hard.
    Admin-only — handig om test-mails op te ruimen of gevoelige inhoud te wissen."""
    row = db.query(EmailLog).filter(EmailLog.id == log_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="E-maillog niet gevonden")
    db.delete(row)
    db.commit()
