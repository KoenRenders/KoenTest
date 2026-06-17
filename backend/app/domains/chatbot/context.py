"""System-prompt + context-stuffing.

Klein datavolume (één vereniging) → we stoppen de gepubliceerde CMS-pagina's
gewoon in de system-prompt; geen RAG/embeddings nodig. De persona en de
vangrails staan hier: feitelijk blijven, niets verzinnen, structuurvelden
winnen, en bij twijfel de bezoeker een idee/vraag laten achterlaten.

Alle admin-tekst voor de bot komt uit de ``chatbot_info``-tabel:
- **CMS-rijen** sturen opt-out/override aan: gepubliceerde pagina's gaan standaard
  mee; een actieve rij met ``is_active=false`` zet er één uit, ``text_override``
  vervangt de inhoud, ``text_addition`` vult ze aan.
- **Vrije notities** (rijen zonder FK) worden als extra context toegevoegd.
Daarnaast injecteren we een **membership-blok** uit de config, zodat de bot
prijzen/tarieven altijd correct kent — ook als geen pagina ze vermeldt.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.models.chatbot_info import ChatbotInfo
from app.models.cms import CmsPage
from app.services.cms_render import _format_md, _format_price, render_cms_content
from app.domains.payment_status.service import membership_price_for_date

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


def _membership_block() -> str:
    """Lidmaatschapstarieven uit de config + het nu geldende tarief (#205).

    Opgebouwd uit dezelfde ``settings`` als de publieke placeholders, dus altijd
    in sync. Het 'nu'-tarief komt uit de bestaande prijslogica, zodat de bot geen
    datum-rekenwerk hoeft te doen."""
    full = _format_price(settings.membership_price_full)
    half = _format_price(settings.membership_price_half)
    start = _format_md(settings.membership_half_price_start_md)
    end = _format_md(settings.membership_half_price_end_md)
    nxt = _format_md(settings.membership_next_year_from_md)
    now_price = _format_price(membership_price_for_date(date.today()))
    return (
        "## Lidmaatschap\n"
        f"- Volledig lidgeld: €{full}. Halftarief: €{half} "
        f"(van {start} t/m {end}).\n"
        f"- Vanaf {nxt} dekt de betaling ook heel volgend jaar.\n"
        f"- Op dit moment geldt het tarief van €{now_price}."
    )


def _cms_overrides(db: Session) -> dict[int, ChatbotInfo]:
    rows = (
        db.query(ChatbotInfo)
        .filter(ChatbotInfo.cms_page_id.isnot(None))
        .all()
    )
    return {r.cms_page_id: r for r in rows}


def _published_pages_block(db: Session) -> str:
    """Gepubliceerde CMS-pagina's (opt-out): standaard mee, tenzij een chatbot_info-
    rij ze uitzet/overschrijft/aanvult."""
    overrides = _cms_overrides(db)
    pages = (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)  # noqa: E712
        .order_by(CmsPage.sort_order, CmsPage.id)
        .all()
    )
    chunks: list[str] = []
    used = 0
    for page in pages:
        ci = overrides.get(page.id)
        if ci is not None and not ci.is_active:
            continue  # admin zette deze pagina uit voor de bot
        # Basis = override of de gerenderde pagina-inhoud; + eventuele aanvulling.
        if ci is not None and ci.text_override:
            base = ci.text_override.strip()
        else:
            base = (render_cms_content(page.content) or "").strip()
        if ci is not None and ci.text_addition:
            base = (base + "\n\n" + ci.text_addition.strip()).strip()
        if not base:
            continue
        block = f"## {page.title}\n{base}"
        if used + len(block) > MAX_CMS_CHARS:
            block = block[: max(0, MAX_CMS_CHARS - used)]
        chunks.append(block)
        used += len(block)
        if used >= MAX_CMS_CHARS:
            break
    return "\n\n".join(chunks)


def _free_notes_block(db: Session) -> str:
    """Vrijstaande 'eigen AI-context'-notities (rijen zonder FK, actief)."""
    rows = (
        db.query(ChatbotInfo)
        .filter(
            ChatbotInfo.media_asset_id.is_(None),
            ChatbotInfo.cms_page_id.is_(None),
            ChatbotInfo.is_active == True,  # noqa: E712
        )
        .order_by(ChatbotInfo.sort_order, ChatbotInfo.id)
        .all()
    )
    chunks = []
    for r in rows:
        text = r.effective_text
        if not text:
            continue
        chunks.append(f"## {r.title}\n{text}" if r.title else text)
    return "\n\n".join(chunks)


def build_system_prompt(db: Session) -> str:
    """Stel de volledige system-prompt samen: persona + membership + CMS + notities."""
    sections = [SYSTEM_PERSONA, _membership_block()]
    cms = _published_pages_block(db)
    if cms:
        sections.append(
            "Hieronder staat de actuele inhoud van de website. Gebruik deze als "
            "bron voor je antwoorden:\n\n" + cms
        )
    notes = _free_notes_block(db)
    if notes:
        sections.append("Extra context van het bestuur:\n\n" + notes)
    return "\n\n".join(sections)
