"""Mediabestanden: lezen, uploaden, bijwerken, verwijderen (#635 I).

Deze functies stonden als routerfuncties in `router.py` en werden door beide
UI-modules geïmporteerd — de JSON-router als servicelaag. Ze bevatten wel degelijk
domeinregels: welke soorten er bestaan, dat een activiteitenfoto een bestaande
activiteit nodig heeft, dat sponsors juist géén activiteit hebben, hoeveel
bestanden er in één keer mogen, en waar de volgende `sort_order` vandaan komt.

Fouten komen naar buiten als `MediaFout` (invoer) of `LookupError` (niet
gevonden); de route vertaalt die naar een statuscode.
"""
from typing import Optional, Sequence

from app.domains.media.images import ALLOWED_CONTENT_TYPES, ImageError, process_image
from app.domains.media.pdf import (PDF_CONTENT_TYPE, PNG_CONTENT_TYPE,
                                    first_page_png)
from app.domains.media.svg import SVG_CONTENT_TYPE, process_svg
from app.domains.media.models import MediaAsset
from app.i18n import _

# `tenant_logo` (#258): het logo van de vereniging zelf — één per tenant.
# Eerste afnemer is de vergader-PDF, die het in zijn kop zet in plaats van een
# ingetypt woordmerk. Een mediasoort en geen tenant-instelling: een logo is
# bytes, en die horen waar de andere bytes al staan.
VALID_KINDS = {"sponsor", "activity_photo", "tenant_logo"}
# Files that another component links to from a text — not part of the media
# library screen, which is why they are not in VALID_KINDS (#984).
DOCUMENT_KINDS = {"newsletter_file"}
# The Design Studio (CR-10 §3.11, #1005). `design_image` is the picture that goes
# INTO a poster and is uploaded like any other image — re-encoded, only to 4096 px
# instead of 1600. `design_render` is the rendered poster, produced by the studio
# itself (Inkscape); it never arrives through an upload, and the upload refuses it
# by name so the reason is readable instead of "unknown kind".
DESIGN_IMAGE_KIND = "design_image"
DESIGN_RENDER_KIND = "design_render"
DESIGN_KINDS = {DESIGN_IMAGE_KIND, DESIGN_RENDER_KIND}
# What may come in through the upload endpoint. The library screen still offers
# only VALID_KINDS — a design image belongs to its activity, not to the library.
UPLOADABLE_KINDS = VALID_KINDS | {DESIGN_IMAGE_KIND}
MAX_BATCH = 20


class MediaFout(ValueError):
    """Een invoerfout die het scherm toont. Geen HTTPException: de service kent
    geen HTTP."""


def meta(asset: MediaAsset) -> dict:
    """Lichte metadata-respons (zonder de blobs)."""
    return {
        "id": asset.id,
        "kind": asset.kind,
        "activity_id": asset.activity_id,
        "component_id": asset.component_id,
        "title": asset.title,
        "link_url": asset.link_url,
        "sort_order": asset.sort_order,
        "is_active": asset.is_active,
        # #1057: alleen betekenisvol bij een sponsorlogo — zie het model.
        "show_in_footer": asset.show_in_footer,
        "width": asset.width,
        "height": asset.height,
        "byte_size": asset.byte_size,
        "content_type": asset.content_type,
        "is_pdf": asset.content_type == "application/pdf",
        "url": f"/api/v1/media/{asset.id}",
        "thumb_url": f"/api/v1/media/{asset.id}/thumb",
    }


def activity_photo_covers(db) -> list[dict]:
    """Per activiteit met foto's één cover-thumbnail — in één query.

    Gebruikt door de fotopagina om albumkaartjes met een echte beeld-preview te
    tonen i.p.v. een placeholder-icoon. DISTINCT ON (activity_id) pakt per
    activiteit de eerste foto (laagste sort_order, dan id).
    """
    rijen = (db.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_photo",
                     MediaAsset.is_active.is_(True),
                     MediaAsset.activity_id.isnot(None))
             .order_by(MediaAsset.activity_id, MediaAsset.sort_order.asc(),
                       MediaAsset.id.asc())
             .distinct(MediaAsset.activity_id).all())
    return [{"activity_id": a.activity_id, "thumb_url": f"/api/v1/media/{a.id}/thumb"}
            for a in rijen]


def list_activity_photos(db, activity_id: int) -> list[dict]:
    rijen = (db.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_photo",
                     MediaAsset.activity_id == activity_id,
                     MediaAsset.is_active.is_(True))
             .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc()).all())
    return [meta(a) for a in rijen]


def list_media(db, *, kind: Optional[str] = None,
               activity_id: Optional[int] = None) -> list[dict]:
    query = db.query(MediaAsset)
    if kind:
        query = query.filter(MediaAsset.kind == kind)
    if activity_id is not None:
        query = query.filter(MediaAsset.activity_id == activity_id)
    rijen = query.order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc()).all()
    return [meta(a) for a in rijen]


# Schema's die veilig in een `href` op een publieke pagina mogen (#707).
# `javascript:` en `data:` staan hier bewust niet in; die worden uitgevoerd in de
# browser van de bezoeker. Relatieve links (beginnend met `/`) blijven toegestaan.
VEILIGE_SCHEMAS = ("http://", "https://", "mailto:", "tel:")


def controleer_link(url, *, kind: str):
    """De doorklik van een sponsorlogo — of None (#707).

    Twee regels, en allebei horen ze HIER en niet in het scherm: er zijn twee
    ingangen (het uploadscherm en de JSON-route), en een regel in het scherm wordt
    langs de andere omzeild.

    1. **Alleen bij een sponsor.** `link_url` wordt op precies één plek gerenderd:
       de sponsorstrook. Bij een activiteitenfoto wordt de waarde bewaard en nooit
       gebruikt — dan is ze geen instelling maar rommel die later iemand verwart.
       Een meegestuurde waarde wordt server-side genegeerd; vertrouwen op een
       verborgen veld zou de andere ingang openlaten.
    2. **Alleen een schema dat in een href mag.** De waarde gaat rechtstreeks in een
       `href` op een publieke pagina, dus een `javascript:`-URL is klikbaar. Alleen
       een beheerder kan het zetten, dus de ernst is beperkt — maar er stond
       nergens een controle, en dat is geen bewuste keuze geweest.
    """
    from app.i18n import _

    waarde = (url or "").strip()
    if not waarde:
        return None
    if kind != "sponsor":
        return None
    if waarde.startswith("/"):
        return waarde
    if not waarde.lower().startswith(VEILIGE_SCHEMAS):
        raise MediaFout(_(
            "Een link moet met http://, https://, mailto:, tel: of / beginnen."))
    return waarde


def update_media(db, asset_id: int, payload: dict) -> dict:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    if "link_url" in payload:
        # #707: dezelfde regel als bij het uploaden. De soort van het bestaande
        # asset beslist, niet wat het formulier meestuurt.
        payload = {**payload, "link_url": controleer_link(payload["link_url"],
                                                          kind=asset.kind)}
    for veld in ("title", "link_url", "sort_order", "is_active", "show_in_footer"):
        if veld in payload:
            setattr(asset, veld, payload[veld])
    db.commit()
    db.refresh(asset)
    return meta(asset)


def thumb_counts(db, asset_ids) -> dict[int, int]:
    """Aantal duimpjes per foto (#883). Eén query voor de hele pagina."""
    from sqlalchemy import func

    from app.domains.media.models import MediaThumbsUp

    if not asset_ids:
        return {}
    rijen = (db.query(MediaThumbsUp.asset_id, func.count(MediaThumbsUp.id))
             .filter(MediaThumbsUp.asset_id.in_(list(asset_ids)))
             .group_by(MediaThumbsUp.asset_id).all())
    return {asset_id: aantal for asset_id, aantal in rijen}


def thumbs_of_visitor(db, asset_ids, token: str | None) -> set[int]:
    """Op welke van deze foto's heeft déze bezoeker geduimd? (#883)

    Enkel om de knop de juiste stand te geven. Er wordt nooit een token of een lijst
    van bezoekers naar buiten gegeven — alleen een aantal, en per foto of jíj geduimd
    hebt.
    """
    from app.domains.media.models import MediaThumbsUp

    if not token or not asset_ids:
        return set()
    rijen = (db.query(MediaThumbsUp.asset_id)
             .filter(MediaThumbsUp.asset_id.in_(list(asset_ids)),
                     MediaThumbsUp.visitor_token == token).all())
    return {rij[0] for rij in rijen}


def toggle_thumb(db, asset_id: int, token: str) -> tuple[int, bool]:
    """Duimpje aan of uit voor deze bezoeker; geeft (aantal, staat het aan) terug (#883).

    Schakelen en niet enkel toevoegen, en dat is meer dan gemak: het maakt de
    cookie-aanpak eerlijk. Wie zijn cookies wist, verliest zijn duimpjes in plaats van
    ze te kunnen verdubbelen.

    De uniciteit ligt in de databank (`uq_thumb_per_visitor`, migratie 113). Deze
    functie vangt de IntegrityError op die twee gelijktijdige kliks opleveren: dan heeft
    de andere het al gezet en is er niets te doen. Zonder die grendel zouden beide
    kliks "bestaat er al een rij?" met nee beantwoorden vóór er één geland is.
    """
    from sqlalchemy.exc import IntegrityError

    from app.domains.media.models import MediaAsset, MediaThumbsUp

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")

    bestaand = (db.query(MediaThumbsUp)
                .filter(MediaThumbsUp.asset_id == asset_id,
                        MediaThumbsUp.visitor_token == token).first())
    if bestaand is not None:
        db.delete(bestaand)
        db.commit()
        return _thumb_total(db, asset_id), False

    db.add(MediaThumbsUp(asset_id=asset_id, visitor_token=token))
    try:
        db.commit()
    except IntegrityError:
        # De andere klik was eerst. Dat is geen fout: de gewenste toestand is bereikt.
        db.rollback()
    return _thumb_total(db, asset_id), True


def _thumb_total(db, asset_id: int) -> int:
    from sqlalchemy import func

    from app.domains.media.models import MediaThumbsUp

    return (db.query(func.count(MediaThumbsUp.id))
            .filter(MediaThumbsUp.asset_id == asset_id).scalar() or 0)


def move_media(db, asset_id: int, richting: str) -> None:
    """Verschuif één asset één plaats binnen ZIJN EIGEN groep (#882).

    v1.14 had hiervoor pijltjes (`moveAsset`) die na elke wissel `sort_order`
    hernummerden naar de positie — zelfherstellend, en het nummer was onzichtbaar. Bij
    de React-exit werd dat een kaal nummerveld, en dat bewaakt niets: twee foto's kunnen
    hetzelfde nummer krijgen (dan beslist het id, wat niemand kan zien), er kunnen gaten
    vallen, en om één foto vooraan te zetten moet je alle andere zelf herzien.

    **De groep is de groep van het asset zelf**, niet de lijst op het scherm: dezelfde
    `kind`, dezelfde `activity_id` en dezelfde `component_id`. Zonder die grens zou het
    herschikken van één album de sponsorlogo's hernummeren — en het scherm toont
    ongefilterd de foto's van álle activiteiten door elkaar.

    `move_sibling` normaliseert eerst naar 0..n en wisselt dan, dus bestaande gaten en
    duplicaten herstellen zich bij de eerste verschuiving. Buiten bereik (bovenste
    omhoog, onderste omlaag) is een no-op en geen fout.
    """
    from app.kernel.ordering import move_sibling

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    # `== None` wordt door SQLAlchemy een IS NULL, dus dit dekt ook een sponsor
    # (activity_id en component_id leeg) zonder aparte tak.
    groep = (db.query(MediaAsset)
             .filter(MediaAsset.kind == asset.kind,
                     MediaAsset.activity_id == asset.activity_id,
                     MediaAsset.component_id == asset.component_id)
             .all())
    move_sibling(groep, asset_id, richting)
    db.commit()


def delete_media(db, asset_id: int) -> None:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    db.delete(asset)
    db.commit()


async def upload_media(db, *, files: Sequence, kind: str,
                       activity_id: Optional[int] = None,
                       title: Optional[str] = None,
                       link_url: Optional[str] = None) -> list[dict]:
    """Verwerk en bewaar een reeks geüploade afbeeldingen.

    Async omdat een `UploadFile` async gelezen wordt; verder gewone servicecode.
    De regels die hier wonen: alleen bekende soorten, een activiteitenfoto hoort
    bij een bestaande activiteit, een sponsor hangt juist níet aan een activiteit,
    hoogstens MAX_BATCH bestanden per keer, en de nieuwe `sort_order` volgt op wat
    er al in die groep staat.
    """
    from app.domains.activities.api import Activity

    if kind == DESIGN_RENDER_KIND:
        raise MediaFout(_("Een render wordt door de Design Studio gemaakt en "
                          "niet opgeladen."))
    if kind not in UPLOADABLE_KINDS:
        raise MediaFout("Ongeldige 'kind'")
    # #1005: een design-beeld hangt óók aan een activiteit, maar hoeft het niet —
    # de Design Studio maakt eerst het beeld en koppelt het daarna.
    if kind in ("activity_photo", DESIGN_IMAGE_KIND):
        if activity_id is None and kind == "activity_photo":
            # #696: v1.14 zei "Kies eerst een activiteit." en dat is wat de
            # gebruiker moet doen; "activity_id vereist" is de naam van een
            # kolom. Deze tekst komt in de foutbanner op het uploadscherm.
            raise MediaFout(_("Kies eerst een activiteit."))
        if (activity_id is not None
                and not db.query(Activity).filter(Activity.id == activity_id).first()):
            raise LookupError("Activiteit niet gevonden")
    else:
        activity_id = None      # sponsors hangen niet aan een activiteit

    # #707: één plek voor de regel, dus ook op deze ingang. Bij een foto valt de
    # waarde weg; bij een sponsor moet het schema in een href mogen.
    link_url = controleer_link(link_url, kind=kind)

    if not files:
        raise MediaFout("Geen bestanden")
    if len(files) > MAX_BATCH:
        raise MediaFout(f"Maximaal {MAX_BATCH} bestanden per keer")

    basis = db.query(MediaAsset).filter(MediaAsset.kind == kind)
    if activity_id is not None:
        basis = basis.filter(MediaAsset.activity_id == activity_id)
    volgende = basis.count()

    gemaakt = []
    for index, upload in enumerate(files):
        # #989: SVG only for the association logo, and then cleaned rather than
        # re-encoded (see `media/svg.py`). Every other kind stays raster.
        is_svg = upload.content_type == SVG_CONTENT_TYPE
        if is_svg and kind != "tenant_logo":
            raise MediaFout(_("%(bestand)s: een SVG kan alleen als logo van de "
                              "vereniging.") % {"bestand": upload.filename})
        if not is_svg and upload.content_type not in ALLOWED_CONTENT_TYPES:
            raise MediaFout(f"Niet-ondersteund bestandstype: {upload.filename}")
        rauw = await upload.read()
        try:
            verwerkt = process_svg(rauw) if is_svg else process_image(rauw, kind=kind)
        except ImageError as exc:
            raise MediaFout(f"{upload.filename}: {exc}")

        asset = MediaAsset(kind=kind, activity_id=activity_id,
                           title=title or upload.filename, link_url=link_url,
                           sort_order=volgende + index, is_active=True, **verwerkt)
        db.add(asset)
        gemaakt.append(asset)

    db.commit()
    for asset in gemaakt:
        db.refresh(asset)
    return [meta(a) for a in gemaakt]


def add_document(db, *, kind: str, filename: str, content_type: str,
                 data: bytes, activity_id: Optional[int] = None) -> MediaAsset:
    """Store one file another component links to or produced, and return it.

    Public like every media asset: it is served at `/api/v1/media/{id}` under its
    own file name, so a newsletter can link to it instead of attaching it to
    hundreds of mails (#984).

    Since #1011 this is also the way in for a `design_render`: the PDF, the PNG
    and the editable SVG of one poster version. Widened here instead of a second
    `add_design_render` next to it, because the two would differ in exactly one
    line — the list of accepted types — and a copy of a storage function is the
    kind of duplication that drifts (CLAUDE.md). SVG is accepted only for a
    render; nothing else has a reason to store one through this door.

    **Media cleans the SVG itself, always** (#1011). Not because the Design
    Studio would forget it, but because the day a second caller uses this
    function without cleaning, nothing may break. Trusting the caller is a rule
    that holds until someone new reads the signature and not the history.
    """
    from app.domains.media.router import DOC_CONTENT_TYPES, _process_document

    toegestane_soorten = DOCUMENT_KINDS | {DESIGN_RENDER_KIND}
    if kind not in toegestane_soorten:
        raise MediaFout("Ongeldige 'kind'")
    is_svg = content_type == SVG_CONTENT_TYPE
    if is_svg and kind != DESIGN_RENDER_KIND:
        raise MediaFout(_("Een SVG kan hier alleen als render van de Design Studio."))
    if not is_svg and content_type not in DOC_CONTENT_TYPES:
        raise MediaFout(_("Dit bestandstype kan niet: kies een PDF of een afbeelding."))
    try:
        processed = (process_svg(data) if is_svg
                     else _process_document(data, content_type, kind=kind))
    except ImageError as exc:
        raise MediaFout(f"{filename}: {exc}")
    asset = MediaAsset(kind=kind, title=(filename or "bestand")[:255], sort_order=0,
                       activity_id=activity_id, is_active=True, **processed)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def activity_ids_with_media(db) -> set[int]:
    """De activiteiten die al media hebben — voor de filter-dropdown (#459).

    Bewust een aparte functie: de dropdown toont alleen wat iets oplevert, terwijl
    de upload-keuzelijst juist álle activiteiten toont (#476). Twee lijsten met
    twee bedoelingen.
    """
    return {rij[0] for rij in db.query(MediaAsset.activity_id)
            .filter(MediaAsset.activity_id.isnot(None)).distinct()}


# ── Affiches, onderdeel-info en hertekstextractie (#635 I) ───────────────────
# Deze vijf stonden als routerfuncties in `router.py` en werden door de
# beheerschermen geïmporteerd. Ze dragen domeinregels: een affiche vervangt de
# vorige (er is er één per activiteit), verwijderen neemt de geëxtraheerde tekst
# vanzelf mee, en hertekstextractie mag alleen op een leesbaar documenttype.

async def replace_activity_poster(db, activity_id: int, file, background_tasks):
    """Vervang de affiche van een activiteit.

    De tekstextractie loopt op de achtergrond (#206): de upload slaagt meteen, de
    (mogelijk betalende) OCR raakt de respons niet. De tekst komt op het
    media-record, niet op de activiteit.
    """
    from app.domains.activities.api import get_activity
    from app.domains.media.extraction import update_media_extracted_text
    from app.domains.media.router import _replace_single_asset

    activity = get_activity(db, activity_id)
    if activity is None:
        raise LookupError("Activiteit niet gevonden")
    asset = await _replace_single_asset(
        db, file, kind="activity_poster", activity_id=activity_id,
        title_base=f"{activity.name} - poster")
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return meta(asset)


def delete_activity_poster(db, activity_id: int) -> None:
    """Hard delete: dat neemt de geëxtraheerde tekst vanzelf mee (#206)."""
    for asset in (db.query(MediaAsset)
                  .filter(MediaAsset.kind == "activity_poster",
                          MediaAsset.activity_id == activity_id).all()):
        db.delete(asset)
    db.commit()


def reextract_text(db, asset_id: int, background_tasks) -> dict:
    """De "Opnieuw lezen"-knop (#235).

    Draait op de achtergrond en raakt enkel `extracted_text` aan — een handmatige
    override of aanvulling in de AI-context blijft staan.
    """
    from app.domains.media.extraction import (EXTRACTABLE_KINDS,
                                              update_media_extracted_text)

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None or asset.kind not in EXTRACTABLE_KINDS:
        raise LookupError("Document niet gevonden")
    background_tasks.add_task(update_media_extracted_text, asset_id, None, True)
    return {"status": "bezig", "asset_id": asset_id}


async def replace_component_info(db, component_id: int, file, background_tasks):
    """Vervang het info-document van een onderdeel.

    Ook info-PDF's leveren context voor Raakje, dus de tekstextractie loopt hier
    net zo goed op de achtergrond (#206).
    """
    from app.domains.activities.api import get_component
    from app.domains.media.extraction import update_media_extracted_text
    from app.domains.media.router import _replace_single_asset

    component = get_component(db, component_id)
    if component is None:
        raise LookupError("Onderdeel niet gevonden")
    activiteit_naam = component.activity.name if component.activity else "activiteit"
    asset = await _replace_single_asset(
        db, file, kind="component_info", component_id=component_id,
        title_base=f"{activiteit_naam} - {component.name} - info")
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return meta(asset)


def delete_component_info(db, component_id: int) -> None:
    for asset in (db.query(MediaAsset)
                  .filter(MediaAsset.kind == "component_info",
                          MediaAsset.component_id == component_id).all()):
        db.delete(asset)
    db.commit()


def activity_image_path(db, activity_id: int) -> Optional[str]:
    """The picture that represents this activity in a mail, or None (#984).

    The order is Koen's (19 September 2026): **the poster first** — for an
    activity that still has to happen it is the only picture there is, since
    photos come from the album and that exists only afterwards — then the album
    cover of a past one.

    A PDF poster answers with its rendering (#1019) and only when that rendering
    exists: without it ``/thumb`` would serve the PDF itself, and a mail would
    show a broken image. Media decides this, not the newsletter: whether a file
    has a usable picture is knowledge of this domain.
    """
    poster = (db.query(MediaAsset)
              .filter(MediaAsset.kind == "activity_poster",
                      MediaAsset.activity_id == activity_id)
              .order_by(MediaAsset.id.desc()).first())
    if poster is not None:
        if poster.content_type == PDF_CONTENT_TYPE:
            if poster.thumbnail is None:
                png = first_page_png(poster.data or b"")
                if png:
                    poster.thumbnail = png
                    poster.thumb_content_type = PNG_CONTENT_TYPE
                    db.commit()
            return f"/api/v1/media/{poster.id}/thumb" if poster.thumbnail else None
        return f"/api/v1/media/{poster.id}"
    cover = (db.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_photo",
                     MediaAsset.is_active.is_(True),
                     MediaAsset.activity_id == activity_id)
             .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc()).first())
    return f"/api/v1/media/{cover.id}/thumb" if cover is not None else None


def tenant_logo(db):
    """Het logo van deze vereniging, of None (#258).

    Eén per tenant: de nieuwste wint, zodat een nieuwe upload de oude vervangt
    zonder dat er iets opgeruimd moet worden. Geeft het asset zelf terug en niet
    een URL, want de eerste afnemer is een PDF — die kan niets ophalen en heeft
    de bytes nodig.
    """
    return (db.query(MediaAsset)
            .filter(MediaAsset.kind == "tenant_logo")
            .order_by(MediaAsset.id.desc())
            .first())
