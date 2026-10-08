from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import User, get_current_admin
from app.domains.cms import service as _service
from app.domains.cms.api import published_html
from app.domains.cms.models import CmsPage
from app.i18n import _
from app.schemas.cms import CmsPageApiUpdate, CmsPageCreate, CmsPageResponse

router = APIRouter(tags=["cms"])


def _public_page(db: Session, page: CmsPage) -> CmsPageResponse:
    """Bouw een publieke respons: vanaf snede 3 het gepubliceerde document,
    zolang er geen is de opgeslagen HTML (snede 3 van #1671 — de lezers
    verhuizen, één bron in `published_html`)."""
    resp = CmsPageResponse.model_validate(page)
    resp.content = published_html(db, page)
    return resp


@router.get("/pages", response_model=List[CmsPageResponse])
def list_pages(db: Session = Depends(get_db)):
    pages = (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )
    return [_public_page(db, p) for p in pages]


@router.get("/pages/{slug}", response_model=CmsPageResponse)
def get_page(slug: str, db: Session = Depends(get_db)):
    page = db.query(CmsPage).filter(CmsPage.slug == slug, CmsPage.is_published == True).first()
    if not page:
        raise HTTPException(status_code=404, detail=_("Page not found"))
    return _public_page(db, page)


@router.get("/blocks/{slug}", response_model=CmsPageResponse)
def get_block(slug: str, db: Session = Depends(get_db)):
    """Fetch a CMS page as an embedded content block, regardless of published status."""
    page = db.query(CmsPage).filter(CmsPage.slug == slug).first()
    if not page:
        raise HTTPException(status_code=404, detail=_("Block not found"))
    return _public_page(db, page)


@router.get("/cms/placeholders")
def list_cms_placeholders():
    """Beschikbare codes voor de CMS-editor (code → omschrijving)."""
    return _service.placeholders()


@router.get("/admin/pages", response_model=List[CmsPageResponse])
def list_all_pages(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return _service.list_pages(db)


@router.post("/pages", response_model=CmsPageResponse)
def create_page(
    data: CmsPageCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        return _service.create_page(db, data)
    except _service.SlugBestaatAl as exc:
        raise HTTPException(status_code=400, detail=_(str(exc)))


@router.put("/pages/{page_id}", response_model=CmsPageResponse)
def update_page(
    page_id: int,
    data: CmsPageApiUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        return _service.update_page(db, page_id, data)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Page not found"))
    except _service.SlugBestaatAl as exc:
        raise HTTPException(status_code=400, detail=_(str(exc)))


@router.delete("/pages/{page_id}")
def delete_page(
    page_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    try:
        _service.delete_page(db, page_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Page not found"))
    return {"detail": "Page deleted"}
