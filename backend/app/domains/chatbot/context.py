"""System-prompt + context-stuffing.

Klein datavolume (één vereniging) → we stoppen de gepubliceerde CMS-pagina's
gewoon in de system-prompt; geen RAG/embeddings nodig. De persona en de
vangrails staan hier: feitelijk blijven, niets verzinnen, structuurvelden
winnen, en bij twijfel de bezoeker een idee/vraag laten achterlaten.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.cms import CmsPage
from app.services.cms_render import render_cms_content

# Bovengrens op de ingestopte CMS-tekst, zodat de prompt niet ontspoort als er
# ooit veel pagina's bijkomen. Ruim voldoende voor een verenigingssite.
MAX_CMS_CHARS = 12_000

SYSTEM_PERSONA = """\
Je bent 'Raakje', de vriendelijke assistent op de website van Raak Millegem, een
Vlaamse vrijetijdsvereniging. Je helpt bezoekers in het Nederlands (nl-BE),
beknopt en warm.

Wat je doet:
- Bezoekers informeren over de vereniging, de activiteiten en het lidmaatschap.
- Vragen over de agenda beantwoorden via de tool get_upcoming_activities en
  get_activity_detail. Verzin nooit datums, prijzen of locaties: die komen
  altijd uit de tools/structuurgegevens en winnen van eender welke tekst.
- Bij twijfel of als je iets niet zeker weet: verzin niets. Bied aan om de vraag
  of het idee door te geven aan het bestuur via submit_idea (vraag dan naam en
  optioneel e-mail voor een bevestiging).

Wat je NIET doet:
- Je kan niet inschrijven of betalingen regelen; verwijs daarvoor naar de
  inschrijfknop op de website.
- Je hebt geen toegang tot ledengegevens of persoonlijke dossiers.

Houd antwoorden kort en concreet. Antwoord altijd in het Nederlands.\
"""


def _published_pages_block(db: Session) -> str:
    pages = (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)  # noqa: E712
        .order_by(CmsPage.sort_order, CmsPage.id)
        .all()
    )
    chunks: list[str] = []
    used = 0
    for page in pages:
        # Render placeholders ({{membership_price_full}} → "35,00") zoals de
        # publieke site, anders ziet de bot de ruwe codes i.p.v. de waarden (#205).
        body = (render_cms_content(page.content) or "").strip()
        if not body:
            continue
        block = f"## {page.title}\n{body}"
        if used + len(block) > MAX_CMS_CHARS:
            block = block[: max(0, MAX_CMS_CHARS - used)]
        chunks.append(block)
        used += len(block)
        if used >= MAX_CMS_CHARS:
            break
    return "\n\n".join(chunks)


def build_system_prompt(db: Session) -> str:
    """Stel de volledige system-prompt samen: persona + vangrails + CMS-context."""
    cms = _published_pages_block(db)
    if cms:
        return (
            f"{SYSTEM_PERSONA}\n\n"
            "Hieronder staat de actuele inhoud van de website. Gebruik deze als "
            "bron voor je antwoorden:\n\n"
            f"{cms}"
        )
    return SYSTEM_PERSONA
