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
from app.domains.payment_status.service import (
    current_membership_counts,
    membership_price_for_date,
    membership_valid_period,
)

# Bovengrens op de ingestopte CMS-tekst, zodat de prompt niet ontspoort als er
# ooit veel pagina's bijkomen. Ruim voldoende voor een verenigingssite.
MAX_CMS_CHARS = 12_000

SYSTEM_PERSONA = """\
Je bent 'Raakje', de vriendelijke assistent op de website van Raak Millegem, een
Vlaamse vrijetijdsvereniging. Je helpt bezoekers in het Nederlands (nl-BE),
beknopt en warm.

Wat je doet:
- Bezoekers informeren over de vereniging, de activiteiten en het lidmaatschap.
- Vragen over activiteiten en de agenda (komend én voorbij) beantwoorden via de
  tools get_activities (zet when='past' voor voorbije activiteiten) en
  get_activity_detail.

STRIKTE REGELS — verzin NOOIT iets:
- Voor ELKE vraag over een activiteit (wat, wanneer, voor wie, programma,
  onderdelen, begeleiding, prijs, locatie): roep eerst get_activities of
  get_activity_detail aan en antwoord UITSLUITEND met wat die teruggeven.
- De tool-/structuurgegevens zijn de enige waarheid en winnen altijd van eender
  welke tekst (ook van de postertekst of de website-inhoud hieronder).
- Staat een veld op 'niet vermeld' of leeg, of ontbreekt het in het
  tool-resultaat, dan is die informatie er niet. Zeg dan eerlijk dat je het niet
  zeker weet. Verzin geen activiteiten, datums, tijden, locaties,
  programma-onderdelen, doelgroepen of begeleiding, en doe geen aannames over wat
  'meestal' bij zo'n activiteit hoort.
- Bied in dat geval aan om de vraag door te geven via submit_idea. Vraag dan
  ALTIJD zowel de naam ALS het e-mailadres — beide zijn verplicht, want zonder
  e-mailadres kan het bestuur niet antwoorden. Roep submit_idea pas aan als je
  beide hebt; ontbreekt er één, vraag het eerst.

Voorbeeld bij ontbrekende info:
- Bezoeker: "Wat kunnen kinderen daar doen?"
- Als get_activity_detail daar niets over bevat: "Daarover staat in onze gegevens
  niets specifieks vermeld. Wil je dat ik je vraag aan het bestuur doorgeef? Dan
  heb ik je naam en e-mailadres nodig."

PERSONEN EN HUN ROL — niets afleiden of combineren (#309):
- Noem de functie of rol van een persoon (voorzitter, penningmeester, secretaris,
  wijkmeester, bestuurslid, ...) ALLEEN als die letterlijk en ondubbelzinnig in de
  context hieronder staat, gekoppeld aan exact die persoon.
- Combineer NOOIT gegevens van verschillende personen, ook niet als ze dezelfde
  achternaam hebben. Leid een rol nooit af en gok nooit.
- Weet je een rol niet zeker, of staat ze niet expliciet vermeld, zeg dan eerlijk
  dat je dat niet in je gegevens hebt; verzin geen functie. Bied aan de vraag door
  te geven via submit_idea (naam én e-mailadres verplicht).

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
    # Duur server-side voorgekauwd (#273): de halfprijs-grens bepaalt enkel de
    # PRIJS, niet de geldigheidsduur. Zo kan de bot 16 sep niet als einddatum
    # verzinnen — een lidmaatschap loopt altijd t/m 31 december van het gedekte jaar.
    _, valid_to = membership_valid_period(date.today())
    valid_to_str = f"{_format_md(f'{valid_to.month:02d}-{valid_to.day:02d}')} {valid_to.year}"
    return (
        "## Lidmaatschap\n"
        f"- Volledig lidgeld: €{full}. Halftarief: €{half} "
        f"(van {start} t/m {end}).\n"
        f"- **Duur:** een lidmaatschap loopt ALTIJD t/m 31 december van het jaar "
        f"waarvoor je betaalt. De periode {start}–{end} bepaalt ALLEEN de prijs "
        f"(halftarief), niet hoe lang je lid bent.\n"
        f"- Wie betaalt vanaf {nxt} is gedekt t/m 31 december van het volgende jaar.\n"
        f"- Wie vandaag lid wordt, is lid t/m {valid_to_str}.\n"
        f"- Op dit moment geldt het tarief van €{now_price}."
    )


def _membership_counts_block(db: Session) -> str:
    """Actueel ledenaantal (#294): vandaag-geldige lidmaatschappen + de eraan
    gekoppelde personen. Bewust enkel **geaggregeerde** aantallen — geen namen of
    persoonsgegevens (de persona heeft geen toegang tot dossiers)."""
    households, persons = current_membership_counts(db)
    gezin = "gezin" if households == 1 else "gezinnen"
    pers = "persoon" if persons == 1 else "personen"
    return (
        "## Ledenaantal\n"
        f"Raak Millegem telt op dit moment {households} aangesloten {gezin} "
        f"(huishoudens) met in totaal {persons} {pers}. Dit zijn de leden met een "
        "vandaag geldig lidmaatschap. Gebruik deze cijfers als iemand vraagt hoeveel "
        "leden, gezinnen of personen de vereniging heeft; verzin geen andere getallen. "
        "Geef nooit namen of persoonlijke gegevens van leden."
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


def _today_block() -> str:
    """Temporeel anker (v1.9.1, #249): zonder 'vandaag' kan het model verleden niet
    van toekomst onderscheiden en verzint het datums (bv. een voorbije datum als
    'eerstvolgende'). We geven de datum mee én verbieden zelf datums te berekenen
    uit terugkerende afspraken."""
    return (
        "## Vandaag\n"
        f"Vandaag is {date.today().isoformat()} (formaat JJJJ-MM-DD). Gebruik deze "
        "datum om te bepalen wat al voorbij is en wat nog komt; presenteer nooit een "
        "datum uit het verleden als 'eerstvolgende'. Bereken zelf geen concrete datums "
        "uit terugkerende regels (zoals 'de eerste donderdag van de maand'): geef dan "
        "de regel zelf weer. Concrete activiteitsdatums komen enkel uit get_activities."
    )


def build_system_prompt(db: Session) -> str:
    """Stel de volledige system-prompt samen: persona + vandaag + membership + CMS + notities."""
    sections = [SYSTEM_PERSONA, _today_block(), _membership_block(), _membership_counts_block(db)]
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
