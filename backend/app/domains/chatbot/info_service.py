"""AI-context van Raakje: documenten, CMS-pagina's en notities (#635 I).

Deze functies stonden in `info_router.py` en werden door `chatbot/ui.py`
rechtstreeks geïmporteerd — de JSON-router als servicelaag. De routes daar zijn nu
dunne schillen.

Wat hier woont zijn de regels die het scherm niet hoort te kennen: welke bronnen
er in de context zitten (affiches, onderdeel-info, CMS-pagina's, notities), hoe een
document zijn label krijgt, en dat een rij zonder ChatbotInfo als "standaard aan"
telt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.domains.activities.api import Activity, ActivitySubRegistration
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage

# media wordt per functie geïmporteerd: `media/extraction.py` importeert op
# modulniveau `ChatbotInfo` uit chatbot.api, dat op zijn beurt deze module laadt.
# Een module-level import hier zou EXTRACTABLE_KINDS opvragen terwijl
# media/api.py nog aan het initialiseren is.
from app.i18n import _
from app.kernel.codes import code_of
from app.kernel.contracts.media import ReadTextAgain
from app.kernel.ports import call
from app.schemas.chatbot_info import ChatbotInfoEdit, NoteCreate

if TYPE_CHECKING:  # alleen voor de typechecker — geen import bij het draaien
    from app.domains.media.api import MediaAsset


def has_extracted_text(db: Session, asset_id: int) -> bool:
    """Whether the text of this document was read already — the question media's
    reading job asks before it reads again (CR-13 phase 4d, #1251). A read."""
    row = db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).first()
    return bool(row and row.extracted_text)


def keep_extracted_text(
    db: Session, asset_id: int, *, title: Optional[str], text: str, extracted_at
) -> None:
    """The text media read of a document, into the chatbot's own row for it: the
    row is made when there is none (with the document's title), and only the
    extracted text and its moment are written — a manual override, an addition
    and the row's own title stay. No commit: the reading job's transaction."""
    row = db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).first()
    if row is None:
        row = ChatbotInfo(media_asset_id=asset_id, title=title)
        db.add(row)
    row.extracted_text = text or None
    row.extracted_at = extracted_at
    db.flush()


def _row(ci: Optional[ChatbotInfo]) -> Optional[dict]:
    if ci is None:
        return None
    return {
        "id": ci.id,
        "title": ci.title,
        "extracted_text": ci.extracted_text,
        "text_override": ci.text_override,
        "text_addition": ci.text_addition,
        "is_active": ci.is_active,
        "sort_order": ci.sort_order,
        "extracted_at": ci.extracted_at,
        "effective_text": ci.effective_text,
    }


def _document_label(db: Session, asset: "MediaAsset") -> str:
    from app.domains.media.api import MediaKind

    if asset.kind is MediaKind.ACTIVITY_POSTER and asset.activity_id:
        a = db.query(Activity).filter(Activity.id == asset.activity_id).first()
        return f"{a.name} — poster" if a else "poster"
    if asset.kind is MediaKind.COMPONENT_INFO and asset.component_id:
        c = (
            db.query(ActivitySubRegistration)
            .filter(ActivitySubRegistration.id == asset.component_id)
            .first()
        )
        if c:
            an = c.activity.name if c.activity else "activiteit"
            return f"{an} — {c.name} (info)"
        return "reglement"
    return code_of(asset.kind) or ""


def list_chatbot_info(db: Session, _admin=None):
    from app.domains.media.api import EXTRACTABLE_KINDS, MediaAsset

    rows_by_asset = {
        ci.media_asset_id: ci
        for ci in db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id.isnot(None)).all()
    }
    documents = []
    for asset in (
        db.query(MediaAsset)
        .filter(MediaAsset.kind.in_(EXTRACTABLE_KINDS))
        .order_by(MediaAsset.id)
        .all()
    ):
        documents.append(
            {
                "asset_id": asset.id,
                "kind": code_of(asset.kind),
                "is_pdf": asset.content_type == "application/pdf",
                "label": _document_label(db, asset),
                "info": _row(rows_by_asset.get(asset.id)),
            }
        )

    # CMS: gepubliceerde pagina's + hun (optionele) override-rij.
    rows_by_page = {
        ci.cms_page_id: ci
        for ci in db.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id.isnot(None)).all()
    }
    cms = []
    for page in (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)  # noqa: E712
        .order_by(CmsPage.sort_order, CmsPage.id)
        .all()
    ):
        cms.append(
            {
                "page_id": page.id,
                "title": page.title,
                "slug": page.slug,
                "info": _row(rows_by_page.get(page.id)),
            }
        )

    # Vrije notities.
    notes = [
        _row(ci)
        for ci in db.query(ChatbotInfo)
        .filter(ChatbotInfo.media_asset_id.is_(None), ChatbotInfo.cms_page_id.is_(None))
        .order_by(ChatbotInfo.sort_order, ChatbotInfo.id)
        .all()
    ]
    return {"documents": documents, "cms": cms, "notes": notes}


def _apply_edit(ci: ChatbotInfo, data: ChatbotInfoEdit) -> None:
    if data.title is not None:
        ci.title = data.title
    ci.text_override = data.text_override
    ci.text_addition = data.text_addition
    ci.is_active = data.is_active
    if data.sort_order is not None:
        ci.sort_order = data.sort_order


class InfoRefused(ValueError):
    """A refusal of this service, in the words the administrator reads."""


def add_note(db: Session, *, title: str, text: str) -> dict:
    """A note of our own for Raakje: it has a title and a text.

    The screen decided this itself until CR-13 phase 4c (#1251); a rule at one
    door holds for that door only. Both are asked for the note, not for every
    row of this table — a document's or a page's row carries no title."""
    title, text = title.strip(), text.strip()
    if not title or not text:
        raise InfoRefused(_("Titel en tekst zijn verplicht."))
    return create_note(db, NoteCreate(title=title, text_addition=text, is_active=True))


def create_note(db: Session, data: NoteCreate, _admin=None):
    ci = ChatbotInfo(
        title=data.title,
        text_addition=data.text_addition,
        is_active=data.is_active,
    )
    db.add(ci)
    db.commit()
    db.refresh(ci)
    return _row(ci)


def update_row(db: Session, row_id: int, data: ChatbotInfoEdit, _admin=None):
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if not ci:
        raise LookupError("Rij niet gevonden")
    _apply_edit(ci, data)
    db.commit()
    db.refresh(ci)
    return _row(ci)


def delete_row(db: Session, row_id: int, _admin=None):
    """Verwijder een rij. Voor een cms-/media-rij = terug naar standaardgedrag;
    voor een notitie = de notitie wissen. (De machine-extractie van een document
    komt vanzelf terug bij een volgende upload/'Opnieuw lezen'.)"""
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if ci:
        db.delete(ci)
        db.commit()


def toggle_row(db: Session, row_id: int) -> ChatbotInfo:
    """Zet een contextrij aan of uit.

    Stond als drie regels in het scherm, inclusief de query. Wat "aan of uit"
    betekent voor Raakje — of de rij mee de context in gaat — is domeinkennis.
    """
    rij = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if rij is None:
        raise LookupError("Rij niet gevonden")
    rij.is_active = not rij.is_active
    db.commit()
    return rij


def _page_row(db: Session, page_id: int) -> ChatbotInfo:
    """The info row of a page, made at its first use (#1791).

    A page is in what Raakje knows by default and has no row until an
    administrator says something about it: switch it off, replace its text, add
    to it. The screen offered those actions only for a page that had a row, and
    nothing made one — so a new page could not be taken out. The row is made
    here, switched on, and whoever asked for it changes it in the same
    transaction.
    """
    if db.query(CmsPage.id).filter(CmsPage.id == page_id).first() is None:
        raise LookupError("Pagina niet gevonden")
    row = (
        db.query(ChatbotInfo)
        .filter(ChatbotInfo.cms_page_id == page_id)
        .order_by(ChatbotInfo.id.desc())
        .first()
    )
    if row is None:
        row = ChatbotInfo(cms_page_id=page_id, is_active=True)
        db.add(row)
        db.flush()
    return row


def toggle_page(db: Session, page_id: int) -> None:
    """Switch a page off for Raakje, or on again. A page without a row is on, so
    its first switch turns it off."""
    row = _page_row(db, page_id)
    row.is_active = not row.is_active
    db.commit()


def edit_page(db: Session, page_id: int, *, text_override: str, text_addition: str) -> None:
    """The text Raakje reads instead of the page, and the text it reads beside
    it. An empty one is no text: the page itself is read again."""
    row = _page_row(db, page_id)
    row.text_override = text_override.strip() or None
    row.text_addition = text_addition.strip() or None
    db.commit()


def get_row(db: Session, row_id: int) -> ChatbotInfo:
    rij = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if rij is None:
        raise LookupError("Rij niet gevonden")
    return rij


def read_document_again(db: Session, asset_id: int) -> None:
    """The "Opnieuw lezen" button of the AI context: have media read the text of
    this document once more. This service is the door of the button, so the
    commit is here — the reading starts with it. A document that is not there
    raises media's `LookupError`."""
    call(ReadTextAgain(asset_id), db)
    db.commit()
