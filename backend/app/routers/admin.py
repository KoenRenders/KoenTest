from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin, get_password_hash
from app.database import get_db
from app.models.activity import Activity
from app.models.member import Member, Membership
from app.models.idea import Idea
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse

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
            .filter(Activity.date >= today, Activity.is_archived == False)
            .scalar(),
        "open_ideas": db.query(func.count(Idea.id))
            .filter(Idea.is_reviewed == False)
            .scalar(),
    }


@router.post("/seed-admin")
def seed_admin(db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == "admin@raakmillegem.be").first()
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")
    user = User(
        email="admin@raakmillegem.be",
        password_hash=get_password_hash("changeme"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role = UserRole(user_id=user.id, role_code="ADMIN")
    db.add(role)
    db.commit()
    return {"detail": "Admin created with email=admin@raakmillegem.be password=changeme — change immediately!"}
