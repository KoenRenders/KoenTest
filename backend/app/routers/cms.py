from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.cms import CmsPage
from app.models.codes import GenderCode
from app.models.user import User
from app.schemas.cms import CmsPageCreate, CmsPageUpdate, CmsPageResponse

router = APIRouter(tags=["cms"])


@router.get("/gender-codes")
def list_gender_codes(db: Session = Depends(get_db)):
    rows = (
        db.query(GenderCode)
        .filter(GenderCode.language == "nl")
        .order_by(GenderCode.code)
        .all()
    )
    return [{"code": r.code, "value": r.value} for r in rows]


@router.get("/pages", response_model=List[CmsPageResponse])
def list_pages(db: Session = Depends(get_db)):
    return (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )


@router.get("/pages/{slug}", response_model=CmsPageResponse)
def get_page(slug: str, db: Session = Depends(get_db)):
    page = db.query(CmsPage).filter(CmsPage.slug == slug, CmsPage.is_published == True).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.get("/blocks/{slug}", response_model=CmsPageResponse)
def get_block(slug: str, db: Session = Depends(get_db)):
    """Fetch a CMS page as an embedded content block, regardless of published status."""
    page = db.query(CmsPage).filter(CmsPage.slug == slug).first()
    if not page:
        raise HTTPException(status_code=404, detail="Block not found")
    return page


@router.get("/admin/pages", response_model=List[CmsPageResponse])
def list_all_pages(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return (
        db.query(CmsPage)
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )


@router.post("/pages", response_model=CmsPageResponse)
def create_page(
    data: CmsPageCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    existing = db.query(CmsPage).filter(CmsPage.slug == data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")

    page = CmsPage(
        title=data.title,
        slug=data.slug,
        content=data.content,
        is_published=data.is_published,
        sort_order=data.sort_order,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


@router.put("/pages/{page_id}", response_model=CmsPageResponse)
def update_page(
    page_id: int,
    data: CmsPageUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if data.slug and data.slug != page.slug:
        existing = db.query(CmsPage).filter(CmsPage.slug == data.slug).first()
        if existing:
            raise HTTPException(status_code=400, detail="Slug already exists")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(page, field, value)

    db.commit()
    db.refresh(page)
    return page


@router.delete("/pages/{page_id}")
def delete_page(
    page_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    db.delete(page)
    db.commit()
    return {"detail": "Page deleted"}
