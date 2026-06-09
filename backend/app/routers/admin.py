from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.activity import Activity
from app.models.member import Member, Membership
from app.models.idea import Idea
from app.models.user import User

router = APIRouter(tags=["admin"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    today = date.today()
    return {
        "members": db.query(func.count(Member.id)).scalar(),
        "active_members": db.query(func.count(Membership.id))
            .filter(Membership.year == today.year, Membership.is_active == True)
            .scalar(),
        "upcoming_activities": db.query(func.count(Activity.id))
            .filter(Activity.date >= today)
            .scalar(),
        "open_ideas": db.query(func.count(Idea.id))
            .filter(Idea.is_reviewed == False)
            .scalar(),
    }
