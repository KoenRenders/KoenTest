from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.idea import Idea
from app.models.user import User
from app.schemas.idea import IdeaCreate, IdeaResponse
from app.services.email import send_idea_acknowledgement

router = APIRouter(tags=["ideas"])


@router.post("/ideas", response_model=IdeaResponse)
def submit_idea(data: IdeaCreate, db: Session = Depends(get_db)):
    idea = Idea(
        submitter_name=data.submitter_name,
        submitter_email=data.submitter_email,
        content=data.content,
    )
    db.add(idea)
    db.commit()
    db.refresh(idea)

    if data.submitter_email:
        try:
            send_idea_acknowledgement(
                to_email=data.submitter_email,
                name=data.submitter_name,
                message=data.content,
            )
        except Exception:
            pass

    return idea


@router.get("/ideas", response_model=List[IdeaResponse])
def list_ideas(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return db.query(Idea).order_by(Idea.submitted_at.desc()).all()


@router.put("/ideas/{idea_id}", response_model=IdeaResponse)
def update_idea(
    idea_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    idea.is_reviewed = True
    db.commit()
    db.refresh(idea)
    return idea
