from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domains.auth.api import get_current_admin
from app.database import get_db
from app.domains.cms.models import CmsPage
from app.domains.mdm.api import GenderCode, RelationTypeCode
from app.domains.auth.api import User
from app.schemas.cms import CmsPageCreate, CmsPageUpdate, CmsPageResponse
from app.domains.cms.render import render_cms_content
from app.i18n import _

router = APIRouter(tags=["cms"])


def _public_page(page: CmsPage) -> CmsPageResponse:
    """Bouw een publieke respons met placeholders ingevuld vanuit config."""
    resp = CmsPageResponse.model_validate(page)
    resp.content = render_cms_content(resp.content)
    return resp


@router.get("/pages", response_model=List[CmsPageResponse])
def list_pages(db: Session = Depends(get_db)):
    pages = (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )
    return [_public_page(p) for p in pages]


@router.get("/pages/{slug}", response_model=CmsPageResponse)
def get_page(slug: str, db: Session = Depends(get_db)):
    page = db.query(CmsPage).filter(CmsPage.slug == slug, CmsPage.is_published == True).first()
    if not page:
        raise HTTPException(status_code=404, detail=_("Page not found"))
    return _public_page(page)


@router.get("/blocks/{slug}", response_model=CmsPageResponse)
def get_block(slug: str, db: Session = Depends(get_db)):
    """Fetch a CMS page as an embedded content block, regardless of published status."""
    page = db.query(CmsPage).filter(CmsPage.slug == slug).first()
    if not page:
        raise HTTPException(status_code=404, detail=_("Block not found"))
    return _public_page(page)


@router.get("/cms/placeholders")
def list_cms_placeholders():
    """Beschikbare codes voor de CMS-editor (code → omschrijving)."""
    from app.domains.cms.render import PLACEHOLDER_LABELS, render_cms_content
    return [
        {
            "code": f"{{{{{code}}}}}",
            "label": label,
            "preview": render_cms_content(f"{{{{{code}}}}}"),
        }
        for code, label in PLACEHOLDER_LABELS.items()
    ]


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
        raise HTTPException(status_code=400, detail=_("Slug already exists"))

    page = CmsPage(
        title=data.title,
        slug=data.slug,
        content=data.content,
        is_published=data.is_published,
        show_in_nav=data.show_in_nav,
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
        raise HTTPException(status_code=404, detail=_("Page not found"))

    if data.slug and data.slug != page.slug:
        existing = db.query(CmsPage).filter(CmsPage.slug == data.slug).first()
        if existing:
            raise HTTPException(status_code=400, detail=_("Slug already exists"))

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
        raise HTTPException(status_code=404, detail=_("Page not found"))
    db.delete(page)
    db.commit()
    return {"detail": "Page deleted"}
