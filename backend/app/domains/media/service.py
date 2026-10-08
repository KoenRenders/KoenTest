"""Mediabestanden: lezen, uploaden, bijwerken, verwijderen (#635 I).

Deze functies stonden als routerfuncties in `router.py` en werden door beide
UI-modules geïmporteerd — de JSON-router als servicelaag. Ze bevatten wel degelijk
domeinregels: welke soorten er bestaan, dat een activiteitenfoto een bestaande
activiteit nodig heeft, dat sponsors juist géén activiteit hebben, hoeveel
bestanden er in één keer mogen, en waar de volgende `sort_order` vandaan komt.

Fouten komen naar buiten als `MediaFout` (invoer) of `LookupError` (niet
gevonden); de route vertaalt die naar een statuscode.
"""

from dataclasses import dataclass
from typing import NamedTuple, Optional, Sequence

from sqlalchemy import and_

from app.domains.media.images import ALLOWED_CONTENT_TYPES, ImageError, process_image
from app.domains.media.models import (
    MediaAsset,
    MediaAssetTag,
    MediaKind,
    MediaTag,
    as_media_kind,
)
from app.domains.media.pdf import PDF_CONTENT_TYPE, PNG_CONTENT_TYPE, first_page_png
from app.domains.media.svg import SVG_CONTENT_TYPE, process_svg
from app.i18n import _
from app.kernel.codes import code_of

# `tenant_logo` (#258): het logo van de vereniging zelf — één per tenant.
# Eerste afnemer is de vergader-PDF, die het in zijn kop zet in plaats van een
# ingetypt woordmerk. Een mediasoort en geen tenant-instelling: een logo is
# bytes, en die horen waar de andere bytes al staan.
# `page_image` (#1173): an image placed in the text of a CMS page. Koen writes a
# public how-to page — how to join, how to renew, how to check your details — and
# those need screenshots.
#
# Its own kind rather than an activity photo, for two reasons that hang together: it
# belongs to NO activity (so `activity_id` stays empty), and it is stored LOSSLESSLY
# because it is usually a screenshot — lettering, which is exactly the material JPEG
# damages. See `LOSSLESS_KINDS` in images.py for the measurement behind that (#1131).
#
# The name follows the other kinds: owner + thing. "page_media" would not say what
# it is, and the others do.
PAGE_IMAGE_KIND = MediaKind.PAGE_IMAGE
VALID_KINDS = {MediaKind.SPONSOR, MediaKind.ACTIVITY_PHOTO, MediaKind.TENANT_LOGO, PAGE_IMAGE_KIND}
# Files that another component links to from a text — not part of the media
# library screen, which is why they are not in VALID_KINDS (#984).
DOCUMENT_KINDS = {MediaKind.NEWSLETTER_FILE}
# The Design Studio (CR-10 §3.11, #1005). `design_image` is the picture that goes
# INTO a poster and is uploaded like any other image — re-encoded, to the one size
# of 2 400 px every upload has since #1473. `design_render` is the rendered poster,
# produced by the studio itself (Inkscape); it never arrives through an upload, and
# the upload refuses it by name so the reason is readable instead of "unknown kind".
DESIGN_IMAGE_KIND = MediaKind.DESIGN_IMAGE
DESIGN_RENDER_KIND = MediaKind.DESIGN_RENDER
DESIGN_KINDS = {DESIGN_IMAGE_KIND, DESIGN_RENDER_KIND}
# What may come in through the upload endpoint. The library screen still offers
# only VALID_KINDS — a design image belongs to its activity, not to the library.
UPLOADABLE_KINDS = VALID_KINDS | {DESIGN_IMAGE_KIND}
MAX_BATCH = 20


class MediaFout(ValueError):
    """Een invoerfout die het scherm toont. Geen HTTPException: de service kent
    geen HTTP."""


@dataclass(frozen=True)
class MediaUse:
    """One place that shows a picture: what it is called and where to fix it
    (CR-15 §C4.4, #1471). A consumer's `references_to_media` returns these."""

    label: str
    href: str


class MediaInUse(MediaFout):
    """Deleting a picture that something still shows (#1471). Carries the uses,
    so a screen can offer them as links; there is no forced delete."""

    def __init__(self, uses: list[MediaUse]):
        self.uses = uses
        names = ", ".join(use.label for use in uses)
        super().__init__(_("Nog in gebruik in %(waar)s. Pas dat eerst aan.") % {"waar": names})


def uses_by_asset(db, asset_ids) -> dict[int, list[MediaUse]]:
    """Where each of these pictures is used — derived, never stored (§C4.4).

    Each consumer knows what it references, so media asks them through their
    facades: the Design Studio (the picture slots and the logo strip of every
    design) and the CMS (the page texts). A stored table of uses would make every
    consumer write twice, and the two would drift. The newsletter needs no
    facade: a letter references an activity, never a picture.

    Lazy imports: both consumers import media's facade themselves.
    """
    from app.domains.cms.api import references_to_media as pages_using
    from app.domains.designstudio.api import references_to_media as designs_using

    ids = sorted({int(i) for i in asset_ids})
    found: dict[int, list[MediaUse]] = {i: [] for i in ids}
    if not ids:
        return found
    for references in (designs_using(db, ids), pages_using(db, ids)):
        for asset_id, uses in references.items():
            found.setdefault(asset_id, []).extend(uses)
    return found


def uses_of(db, asset_id: int) -> list[MediaUse]:
    """Where this one picture is used (#1471); empty when nowhere."""
    return uses_by_asset(db, [asset_id])[asset_id]


def meta(asset: MediaAsset) -> dict:
    """Lichte metadata-respons (zonder de blobs)."""
    return {
        "id": asset.id,
        # The code: this dict is what a screen and the JSON API get (CR-12).
        "kind": code_of(asset.kind),
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
    rijen = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == MediaKind.ACTIVITY_PHOTO,
            MediaAsset.is_active.is_(True),
            MediaAsset.activity_id.isnot(None),
        )
        .order_by(MediaAsset.activity_id, MediaAsset.sort_order.asc(), MediaAsset.id.asc())
        .distinct(MediaAsset.activity_id)
        .all()
    )
    return [
        {"activity_id": a.activity_id, "thumb_url": f"/api/v1/media/{a.id}/thumb"} for a in rijen
    ]


def list_activity_photos(db, activity_id: int) -> list[dict]:
    rijen = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == MediaKind.ACTIVITY_PHOTO,
            MediaAsset.activity_id == activity_id,
            MediaAsset.is_active.is_(True),
        )
        .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc())
        .all()
    )
    return [meta(a) for a in rijen]


def list_media(
    db,
    *,
    kind: MediaKind | str | None = None,
    activity_id: Optional[int] = None,
) -> list[dict]:
    """The pictures of a kind, of an activity — or, with `WITHOUT_ACTIVITY`, of
    none (#1527)."""
    query = db.query(MediaAsset)
    if kind:
        soort = as_media_kind(kind)
        if soort is None:
            return []
        query = query.filter(MediaAsset.kind == soort)
    if activity_id == WITHOUT_ACTIVITY:
        query = query.filter(MediaAsset.activity_id.is_(None))
    elif activity_id is not None:
        query = query.filter(MediaAsset.activity_id == activity_id)
    rijen = query.order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc()).all()
    return [meta(a) for a in rijen]


# Schema's die veilig in een `href` op een publieke pagina mogen (#707).
# `javascript:` en `data:` staan hier bewust niet in; die worden uitgevoerd in de
# browser van de bezoeker. Relatieve links (beginnend met `/`) blijven toegestaan.
VEILIGE_SCHEMAS = ("http://", "https://", "mailto:", "tel:")


def controleer_link(url, *, kind: MediaKind | str):
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
    if as_media_kind(kind) is not MediaKind.SPONSOR:
        return None
    if waarde.startswith("/"):
        return waarde
    if not waarde.lower().startswith(VEILIGE_SCHEMAS):
        raise MediaFout(_("Een link moet met http://, https://, mailto:, tel: of / beginnen."))
    return waarde


def update_media(db, asset_id: int, payload: dict) -> dict:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    if "link_url" in payload:
        # #707: dezelfde regel als bij het uploaden. De soort van het bestaande
        # asset beslist, niet wat het formulier meestuurt.
        payload = {**payload, "link_url": controleer_link(payload["link_url"], kind=asset.kind)}
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
    rijen = (
        db.query(MediaThumbsUp.asset_id, func.count(MediaThumbsUp.id))
        .filter(MediaThumbsUp.asset_id.in_(list(asset_ids)))
        .group_by(MediaThumbsUp.asset_id)
        .all()
    )
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
    rijen = (
        db.query(MediaThumbsUp.asset_id)
        .filter(MediaThumbsUp.asset_id.in_(list(asset_ids)), MediaThumbsUp.visitor_token == token)
        .all()
    )
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

    bestaand = (
        db.query(MediaThumbsUp)
        .filter(MediaThumbsUp.asset_id == asset_id, MediaThumbsUp.visitor_token == token)
        .first()
    )
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

    return (
        db.query(func.count(MediaThumbsUp.id)).filter(MediaThumbsUp.asset_id == asset_id).scalar()
        or 0
    )


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
    groep = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == asset.kind,
            MediaAsset.activity_id == asset.activity_id,
            MediaAsset.component_id == asset.component_id,
        )
        .all()
    )
    move_sibling(groep, asset_id, richting)
    db.commit()


def remove_media(db, asset_id: int) -> None:
    """Delete one asset in the caller's transaction — for another domain's service,
    whose door commits (CR-13 phase 4, §B9.3 (c))."""
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    db.delete(asset)
    db.flush()


def delete_media(db, asset_id: int) -> None:
    """Delete one asset and commit — the door of media's own screens and routes.

    Refused while the picture is in use (#1471, §C4.4): a design or a page that
    points at a deleted picture breaks on the site. No forced delete — the uses
    come with the refusal, and each is one click to change. `remove_media`, the
    door for another domain's own products (renders, posters), does not ask.
    """
    uses = uses_of(db, asset_id)
    if uses:
        raise MediaInUse(uses)
    remove_media(db, asset_id)
    db.commit()


async def upload_media(
    db,
    *,
    files: Sequence,
    kind: MediaKind | str,
    activity_id: Optional[int] = None,
    title: Optional[str] = None,
    link_url: Optional[str] = None,
) -> list[dict]:
    """Store the uploads and commit — the door of media's own screens and routes."""
    stored = await store_uploads(
        db, files=files, kind=kind, activity_id=activity_id, title=title, link_url=link_url
    )
    db.commit()
    return stored


async def store_uploads(
    db,
    *,
    files: Sequence,
    kind: MediaKind | str,
    activity_id: Optional[int] = None,
    title: Optional[str] = None,
    link_url: Optional[str] = None,
) -> list[dict]:
    """Verwerk en bewaar een reeks geüploade afbeeldingen.

    Async omdat een `UploadFile` async gelezen wordt; verder gewone servicecode.
    De regels die hier wonen: alleen bekende soorten, een activiteitenfoto hoort
    bij een bestaande activiteit, een sponsor hangt juist níet aan een activiteit,
    hoogstens MAX_BATCH bestanden per keer, en de nieuwe `sort_order` volgt op wat
    er al in die groep staat.
    """
    from app.domains.activities.api import Activity

    media_kind = as_media_kind(kind)
    if media_kind == DESIGN_RENDER_KIND:
        raise MediaFout(_("Een render wordt door de Design Studio gemaakt en niet opgeladen."))
    if media_kind not in UPLOADABLE_KINDS:
        raise MediaFout("Ongeldige 'kind'")
    # #1005: een design-beeld hangt óók aan een activiteit, maar hoeft het niet —
    # de Design Studio maakt eerst het beeld en koppelt het daarna.
    if media_kind in (MediaKind.ACTIVITY_PHOTO, DESIGN_IMAGE_KIND):
        if activity_id is None and media_kind is MediaKind.ACTIVITY_PHOTO:
            # #696: v1.14 zei "Kies eerst een activiteit." en dat is wat de
            # gebruiker moet doen; "activity_id vereist" is de naam van een
            # kolom. Deze tekst komt in de foutbanner op het uploadscherm.
            raise MediaFout(_("Kies eerst een activiteit."))
        if (
            activity_id is not None
            and not db.query(Activity).filter(Activity.id == activity_id).first()
        ):
            raise LookupError("Activiteit niet gevonden")
    else:
        activity_id = None  # sponsors hangen niet aan een activiteit

    # #707: één plek voor de regel, dus ook op deze ingang. Bij een foto valt de
    # waarde weg; bij een sponsor moet het schema in een href mogen.
    link_url = controleer_link(link_url, kind=media_kind)

    if not files:
        raise MediaFout("Geen bestanden")
    if len(files) > MAX_BATCH:
        raise MediaFout(f"Maximaal {MAX_BATCH} bestanden per keer")

    basis = db.query(MediaAsset).filter(MediaAsset.kind == media_kind)
    if activity_id is not None:
        basis = basis.filter(MediaAsset.activity_id == activity_id)
    volgende = basis.count()

    gemaakt = []
    for index, upload in enumerate(files):
        # #989: SVG only for the association logo, and then cleaned rather than
        # re-encoded (see `media/svg.py`). Every other kind stays raster.
        is_svg = upload.content_type == SVG_CONTENT_TYPE
        if is_svg and media_kind is not MediaKind.TENANT_LOGO:
            raise MediaFout(
                _("%(bestand)s: een SVG kan alleen als logo van de vereniging.")
                % {"bestand": upload.filename}
            )
        if not is_svg and upload.content_type not in ALLOWED_CONTENT_TYPES:
            raise MediaFout(f"Niet-ondersteund bestandstype: {upload.filename}")
        rauw = await upload.read()
        try:
            verwerkt = process_svg(rauw) if is_svg else process_image(rauw, kind=media_kind)
        except ImageError as exc:
            raise MediaFout(f"{upload.filename}: {exc}")

        asset = MediaAsset(
            kind=media_kind,
            activity_id=activity_id,
            title=title or upload.filename,
            link_url=link_url,
            sort_order=volgende + index,
            is_active=True,
            **verwerkt,
        )
        db.add(asset)
        gemaakt.append(asset)

    # A flush, not a commit (CR-13 phase 4): `upload_media` commits for media's own
    # doors; another domain's service stores through here and its door commits.
    db.flush()
    for asset in gemaakt:
        db.refresh(asset)
    return [meta(a) for a in gemaakt]


def add_document(
    db,
    *,
    kind: MediaKind | str,
    filename: str,
    content_type: str,
    data: bytes,
    activity_id: Optional[int] = None,
) -> MediaAsset:
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

    media_kind = as_media_kind(kind)
    toegestane_soorten = DOCUMENT_KINDS | {DESIGN_RENDER_KIND}
    if media_kind not in toegestane_soorten:
        raise MediaFout("Ongeldige 'kind'")
    is_svg = content_type == SVG_CONTENT_TYPE
    if is_svg and media_kind != DESIGN_RENDER_KIND:
        raise MediaFout(_("Een SVG kan hier alleen als render van de Design Studio."))
    if not is_svg and content_type not in DOC_CONTENT_TYPES:
        raise MediaFout(_("Dit bestandstype kan niet: kies een PDF of een afbeelding."))
    try:
        processed = (
            process_svg(data) if is_svg else _process_document(data, content_type, kind=media_kind)
        )
    except ImageError as exc:
        raise MediaFout(f"{filename}: {exc}")
    asset = MediaAsset(
        kind=media_kind,
        title=(filename or "bestand")[:255],
        sort_order=0,
        activity_id=activity_id,
        is_active=True,
        **processed,
    )
    db.add(asset)
    # A flush, not a commit (CR-13 phase 4): every caller is another domain's
    # service, and its door commits.
    db.flush()
    db.refresh(asset)
    return asset


def activities_by_kind(db) -> dict[MediaKind, set[int]]:
    """Per kind, the activities with media of that kind — in one query, for the
    library's derived branches (#1470): album photos, and posters apart."""
    out: dict[MediaKind, set[int]] = {}
    for activity_id, kind in (
        db.query(MediaAsset.activity_id, MediaAsset.kind)
        .filter(MediaAsset.activity_id.isnot(None))
        .distinct()
    ):
        out.setdefault(kind, set()).add(activity_id)
    return out


def activity_ids_with_media(db) -> set[int]:
    """De activiteiten die al media hebben — voor de filter-dropdown (#459).

    Bewust een aparte functie: de dropdown toont alleen wat iets oplevert, terwijl
    de upload-keuzelijst juist álle activiteiten toont (#476). Twee lijsten met
    twee bedoelingen.
    """
    return {
        rij[0]
        for rij in db.query(MediaAsset.activity_id)
        .filter(MediaAsset.activity_id.isnot(None))
        .distinct()
    }


# ── Affiches, onderdeel-info en hertekstextractie (#635 I) ───────────────────
# Deze vijf stonden als routerfuncties in `router.py` en werden door de
# beheerschermen geïmporteerd. Ze dragen domeinregels: een affiche vervangt de
# vorige (er is er één per activiteit), verwijderen neemt de geëxtraheerde tekst
# vanzelf mee, en hertekstextractie mag alleen op een leesbaar documenttype.


async def replace_activity_poster(db, activity_id: int, file, background_tasks):
    """Replace an activity's poster and commit — the door of the activity screens
    and media's route. The Design Studio stores through `store_activity_poster`."""
    stored = await store_activity_poster(db, activity_id, file, background_tasks)
    db.commit()
    return stored


async def store_activity_poster(db, activity_id: int, file, background_tasks):
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
        db,
        file,
        kind=MediaKind.ACTIVITY_POSTER,
        activity_id=activity_id,
        title_base=f"{activity.name} - poster",
    )
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return meta(asset)


def delete_activity_poster(db, activity_id: int) -> None:
    """Hard delete: dat neemt de geëxtraheerde tekst vanzelf mee (#206)."""
    drop_activity_poster(db, activity_id)
    db.commit()


def drop_activity_poster(db, activity_id: int) -> None:
    """Remove an activity's poster without committing (#1559: the fiche removes
    it in the transaction of its one save)."""
    for asset in (
        db.query(MediaAsset)
        .filter(MediaAsset.kind == MediaKind.ACTIVITY_POSTER, MediaAsset.activity_id == activity_id)
        .all()
    ):
        db.delete(asset)


def reextract_text(db, asset_id: int, background_tasks) -> dict:
    """De "Opnieuw lezen"-knop (#235).

    Draait op de achtergrond en raakt enkel `extracted_text` aan — een handmatige
    override of aanvulling in de AI-context blijft staan.
    """
    from app.domains.media.extraction import EXTRACTABLE_KINDS, update_media_extracted_text

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None or asset.kind not in EXTRACTABLE_KINDS:
        raise LookupError("Document niet gevonden")
    background_tasks.add_task(update_media_extracted_text, asset_id, None, True)
    return {"status": "bezig", "asset_id": asset_id}


async def replace_component_info(db, component_id: int, file, background_tasks):
    """Replace a component's info document and commit — the door of media's own
    route. The activity fiche stores through `store_component_info` (#1559)."""
    stored = await store_component_info(db, component_id, file, background_tasks)
    db.commit()  # the door of the component screens (CR-13 phase 4)
    return stored


async def store_component_info(db, component_id: int, file, background_tasks):
    """Vervang het info-document van een onderdeel, zonder commit (#1559: the
    fiche saves its attachments in the transaction of its one save).

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
        db,
        file,
        kind=MediaKind.COMPONENT_INFO,
        component_id=component_id,
        title_base=f"{activiteit_naam} - {component.name} - info",
    )
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return meta(asset)


def delete_component_info(db, component_id: int) -> None:
    drop_component_info(db, component_id)
    db.commit()


def drop_component_info(db, component_id: int) -> None:
    """Hard-delete a component's info document, without committing (#1559)."""
    for asset in (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == MediaKind.COMPONENT_INFO, MediaAsset.component_id == component_id
        )
        .all()
    ):
        db.delete(asset)


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
    poster = (
        db.query(MediaAsset)
        .filter(MediaAsset.kind == MediaKind.ACTIVITY_POSTER, MediaAsset.activity_id == activity_id)
        .order_by(MediaAsset.id.desc())
        .first()
    )
    if poster is not None:
        if poster.content_type == PDF_CONTENT_TYPE:
            if poster.thumbnail is None:
                png = first_page_png(poster.data or b"")
                if png:
                    poster.thumbnail = png
                    poster.thumb_content_type = PNG_CONTENT_TYPE
                    # A flush (CR-13 phase 4): the rendering is a cache; the caller's
                    # door keeps it if it commits, and it is made again if not.
                    db.flush()
            return f"/api/v1/media/{poster.id}/thumb" if poster.thumbnail else None
        return f"/api/v1/media/{poster.id}"
    cover = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == MediaKind.ACTIVITY_PHOTO,
            MediaAsset.is_active.is_(True),
            MediaAsset.activity_id == activity_id,
        )
        .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc())
        .first()
    )
    return f"/api/v1/media/{cover.id}/thumb" if cover is not None else None


def tenant_logo(db):
    """Het logo van deze vereniging, of None (#258).

    Eén per tenant: de nieuwste wint, zodat een nieuwe upload de oude vervangt
    zonder dat er iets opgeruimd moet worden. Geeft het asset zelf terug en niet
    een URL, want de eerste afnemer is een PDF — die kan niets ophalen en heeft
    de bytes nodig.
    """
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.kind == MediaKind.TENANT_LOGO)
        .order_by(MediaAsset.id.desc())
        .first()
    )


# ── Tags, shown as a tree (CR-15 §C4.2, #1470) ───────────────────────────────
# A picture carries any number of tags; a tag has an optional parent. The
# library shows them as a tree, and a picture appears under every tag it
# carries and under every tag above those. The activity's photos are no tags:
# the screen derives their branch from the activity.

TAG_NAME_MAX = 80


class TagNode(NamedTuple):
    """One tag in the tree, with how many pictures sit under it — its own and
    those of every tag below it, each picture once."""

    id: int
    name: str
    parent_id: Optional[int]
    pictures: int
    children: tuple["TagNode", ...]


def _all_tags(db) -> list[MediaTag]:
    return db.query(MediaTag).order_by(MediaTag.name.asc(), MediaTag.id.asc()).all()


def _children_of(tags: Sequence[MediaTag]) -> dict[Optional[int], list[MediaTag]]:
    children: dict[Optional[int], list[MediaTag]] = {}
    for tag in tags:
        children.setdefault(tag.parent_id, []).append(tag)
    return children


def tag_subtree_ids(db, tag_id: int) -> set[int]:
    """`tag_id` and every tag below it."""
    children = _children_of(_all_tags(db))
    found, todo = set(), [tag_id]
    while todo:
        current = todo.pop()
        if current in found:
            continue
        found.add(current)
        todo.extend(child.id for child in children.get(current, []))
    return found


class TagIndex(NamedTuple):
    """Everything the library needs of the tags, from two queries (#1470): the
    tree, every tag's path for a choice list, and each picture's tags."""

    tree: list[TagNode]
    paths: list[tuple[int, str]]
    per_asset: dict[int, list[int]]


def tag_index(db) -> TagIndex:
    tags = _all_tags(db)
    links = db.query(MediaAssetTag.asset_id, MediaAssetTag.tag_id).all()
    tree = _tree_of(tags, links)
    per_asset: dict[int, list[int]] = {}
    for asset_id, tag_id in links:
        per_asset.setdefault(asset_id, []).append(tag_id)
    return TagIndex(tree, _paths_of(tree), per_asset)


def tag_tree(db) -> list[TagNode]:
    """The tags as a tree, roots first, each level by name."""
    return tag_index(db).tree


def _tree_of(tags: Sequence[MediaTag], links: Sequence) -> list[TagNode]:
    children = _children_of(tags)
    assets_per_tag: dict[int, set[int]] = {}
    for asset_id, tag_id in links:
        assets_per_tag.setdefault(tag_id, set()).add(asset_id)

    def build(tag: MediaTag) -> tuple[TagNode, set[int]]:
        below = [build(child) for child in children.get(tag.id, [])]
        assets = set(assets_per_tag.get(tag.id, set()))
        for _node, child_assets in below:
            assets |= child_assets
        node = TagNode(tag.id, tag.name, tag.parent_id, len(assets), tuple(n for n, _ in below))
        return node, assets

    return [build(root)[0] for root in children.get(None, [])]


def tag_paths(db) -> list[tuple[int, str]]:
    """Every tag as (id, "Parent › Child"), in tree order — for a choice list."""
    return tag_index(db).paths


def _paths_of(tree: Sequence[TagNode]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []

    def walk(nodes: Sequence[TagNode], prefix: str) -> None:
        for node in nodes:
            path = f"{prefix}{node.name}"
            out.append((node.id, path))
            walk(node.children, f"{path} › ")

    walk(tree, "")
    return out


def list_media_with_tag(db, tag_id: int) -> list[dict]:
    """The pictures carrying `tag_id` or any tag below it, each once."""
    ids = tag_subtree_ids(db, tag_id)
    rijen = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.id.in_(
                db.query(MediaAssetTag.asset_id).filter(MediaAssetTag.tag_id.in_(ids))
            )
        )
        .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc())
        .all()
    )
    return [meta(a) for a in rijen]


def tags_of_assets(db, asset_ids: Sequence[int]) -> dict[int, list[int]]:
    """Per picture, the ids of the tags it carries — one query for a page of cards."""
    out: dict[int, list[int]] = {asset_id: [] for asset_id in asset_ids}
    if not asset_ids:
        return out
    for asset_id, tag_id in db.query(MediaAssetTag.asset_id, MediaAssetTag.tag_id).filter(
        MediaAssetTag.asset_id.in_(list(asset_ids))
    ):
        out.setdefault(asset_id, []).append(tag_id)
    return out


def _tag_or_404(db, tag_id: int) -> MediaTag:
    tag = db.query(MediaTag).filter(MediaTag.id == tag_id).first()
    if tag is None:
        raise LookupError(_("Tag niet gevonden"))
    return tag


def _clean_tag_name(name: str) -> str:
    naam = (name or "").strip()
    if not naam:
        raise MediaFout(_("Geef de tag een naam."))
    if len(naam) > TAG_NAME_MAX:
        raise MediaFout(_("Een tagnaam is hoogstens %(n)s tekens.") % {"n": TAG_NAME_MAX})
    return naam


def _refuse_twin(db, name: str, parent_id: Optional[int], *, own_id: Optional[int] = None):
    """The database key refuses it too; this names it before it gets there."""
    twin = db.query(MediaTag).filter(
        MediaTag.name == name,
        MediaTag.parent_id.is_(None) if parent_id is None else MediaTag.parent_id == parent_id,
    )
    if own_id is not None:
        twin = twin.filter(MediaTag.id != own_id)
    if twin.first() is not None:
        raise MediaFout(_("Er bestaat hier al een tag '%(naam)s'.") % {"naam": name})


def create_tag(db, name: str, parent_id: Optional[int] = None) -> MediaTag:
    naam = _clean_tag_name(name)
    if parent_id is not None:
        _tag_or_404(db, parent_id)
    _refuse_twin(db, naam, parent_id)
    tag = MediaTag(name=naam, parent_id=parent_id)
    db.add(tag)
    db.commit()
    return tag


def rename_tag(db, tag_id: int, name: str) -> MediaTag:
    tag = _tag_or_404(db, tag_id)
    naam = _clean_tag_name(name)
    _refuse_twin(db, naam, tag.parent_id, own_id=tag.id)
    tag.name = naam
    db.commit()
    return tag


def move_tag(db, tag_id: int, parent_id: Optional[int]) -> MediaTag:
    """Hang a tag under another one, or at the top (`parent_id` None). Never under
    itself or one of its own descendants: the tree would close into a ring."""
    tag = _tag_or_404(db, tag_id)
    if parent_id is not None:
        _tag_or_404(db, parent_id)
        if parent_id in tag_subtree_ids(db, tag.id):
            raise MediaFout(_("Een tag kan niet onder zichzelf of een eigen ondertag hangen."))
    _refuse_twin(db, tag.name, parent_id, own_id=tag.id)
    tag.parent_id = parent_id
    db.commit()
    return tag


def delete_tag(db, tag_id: int) -> None:
    """Delete a tag that carries nothing: no tag below it and no picture on it.
    The refusal says which and how many, so the board knows what to undo."""
    tag = _tag_or_404(db, tag_id)
    kinderen = db.query(MediaTag).filter(MediaTag.parent_id == tag.id).count()
    if kinderen:
        raise MediaFout(
            _("De tag '%(naam)s' heeft nog %(n)s ondertag(s); verplaats of verwijder die eerst.")
            % {"naam": tag.name, "n": kinderen}
        )
    gebruik = db.query(MediaAssetTag).filter(MediaAssetTag.tag_id == tag.id).count()
    if gebruik:
        raise MediaFout(
            _("De tag '%(naam)s' hangt nog aan %(n)s foto('s); haal hem daar eerst weg.")
            % {"naam": tag.name, "n": gebruik}
        )
    db.delete(tag)
    db.commit()


def _asset_or_404(db, asset_id: int) -> MediaAsset:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError(_("Niet gevonden"))
    return asset


def tag_asset(db, asset_id: int, tag_id: int) -> None:
    """Give a picture a tag. Already there: nothing changes — the key refuses a
    second row, and asking twice is not an error the board can act on."""
    _asset_or_404(db, asset_id)
    _tag_or_404(db, tag_id)
    exists = (
        db.query(MediaAssetTag)
        .filter(MediaAssetTag.asset_id == asset_id, MediaAssetTag.tag_id == tag_id)
        .first()
    )
    if exists is None:
        db.add(MediaAssetTag(asset_id=asset_id, tag_id=tag_id))
    db.commit()


def untag_asset(db, asset_id: int, tag_id: int) -> None:
    db.query(MediaAssetTag).filter(
        MediaAssetTag.asset_id == asset_id, MediaAssetTag.tag_id == tag_id
    ).delete(synchronize_session=False)
    db.commit()


def set_asset_tags(db, asset_id: int, tag_ids: Sequence[int]) -> None:
    """The picture carries exactly these tags afterwards — the card's ticks."""
    _asset_or_404(db, asset_id)
    wanted = {int(t) for t in tag_ids}
    for tag_id in wanted:
        _tag_or_404(db, tag_id)
    have = {
        row[0] for row in db.query(MediaAssetTag.tag_id).filter(MediaAssetTag.asset_id == asset_id)
    }
    for tag_id in wanted - have:
        db.add(MediaAssetTag(asset_id=asset_id, tag_id=tag_id))
    if have - wanted:
        db.query(MediaAssetTag).filter(
            MediaAssetTag.asset_id == asset_id, MediaAssetTag.tag_id.in_(have - wanted)
        ).delete(synchronize_session=False)
    db.commit()


# ── The picker's offer (CR-15 §C4.3, #1472) ──────────────────────────────────
# One chooser, from the kit, on every screen that offers a picture: the design
# editor and the CMS modal. What it offers, and in which order, is decided here.

#: What a picker offers. A poster only under its own branch (Affiches); never a
#: render (a product of a design) or a newsletter file. Sponsor and association
#: logos too (#1473): everything in the library that is a picture can be chosen.
PICKABLE_KINDS = (
    MediaKind.ACTIVITY_PHOTO,
    MediaKind.DESIGN_IMAGE,
    MediaKind.PAGE_IMAGE,
    MediaKind.SPONSOR,
    MediaKind.TENANT_LOGO,
)
#: The tree's branches for the kinds that hang off no activity, so the activity
#: branches never reach them (#1473, #1527): per branch a key and its kinds. ONE
#: source for the library and the picker — both trees read it, through `_tree`.
KIND_GROUPS: tuple[tuple[str, tuple[MediaKind, ...]], ...] = (
    ("logos", (MediaKind.SPONSOR, MediaKind.TENANT_LOGO)),
    ("pages", (MediaKind.PAGE_IMAGE,)),
)
#: Design pictures are a branch per activity, like posters (Koen, #1527):
#: Ontwerpbeelden › year › activity, and this "activity" for the ones of none —
#: "Zonder activiteit". No activity has id 0.
WITHOUT_ACTIVITY = 0
#: Every kind with a branch of its own, derived from `KIND_GROUPS`.
KIND_BRANCHES = tuple(kind for _key, kinds in KIND_GROUPS for kind in kinds)
PICK_PAGE_SIZE = 60


def media_url_prefix() -> str:
    """The address every picture is served under, without her id — the one
    place that knows the shape, like `media_url`. The document editor builds
    her figure's preview from this prefix plus the media id (CR-17 #1671),
    so the browser carries no URL shape of her own: storing bytes
    elsewhere (architecture R8) is a change inside media, not in the editor.
    """
    return "/api/v1/media/"


def media_url(asset_id: int, *, base_url: str = "", thumb: bool = False) -> str:
    """The address a picture is served at — the one place that knows its shape
    (CR-15 §C4.6, #1473). Every module asks here instead of writing
    `/api/v1/media/<id>`, so that storing bytes elsewhere (architecture R8) is a
    change inside media. `base_url` for a mail, which needs an absolute address.
    """
    return f"{base_url}{media_url_prefix()}{asset_id}" + ("/thumb" if thumb else "")


def asset_bytes(db, asset_id: int) -> Optional[bytes]:
    """The stored bytes of a picture or file, or None (CR-15 §C4.6, #1473).

    The one door to `MediaAsset.data` for every other module: a poster render
    needs its images, a meeting PDF its logo. With bytes read only here, storing
    them elsewhere (architecture R8) is a change inside media.
    """
    row = db.query(MediaAsset.data).filter(MediaAsset.id == asset_id).first()
    return bytes(row.data) if row is not None and row.data is not None else None


def _offered():
    """What the picker offers, as one condition (#1473): the pickable kinds and a
    poster in its own branch, and only as an image — a poster may be a PDF. The
    one source for `offered_by_picker` (what may be stored) and `pick_options`
    (what is shown), so the two cannot drift apart."""
    return and_(
        MediaAsset.kind.in_((*PICKABLE_KINDS, MediaKind.ACTIVITY_POSTER)),
        MediaAsset.content_type.like("image/%"),
    )


def offered_by_picker(db, asset_id: int) -> bool:
    """Would the picker offer this picture to this tenant? (#1473)

    `_offered`, for one id. Same tenant by the ORM's tenant filter: another
    tenant's picture is not found. A screen that stores a choice asks this,
    because a form field can carry any id.
    """
    return db.query(MediaAsset.id).filter(MediaAsset.id == asset_id, _offered()).first() is not None


class PickItem(NamedTuple):
    id: int
    title: str
    thumb_url: str
    #: "<activity> (<year>)" for a picture of an activity, else "".
    origin: str
    #: The picture itself and its size (#1474): the CMS places it in a page.
    url: str = ""
    width: Optional[int] = None
    height: Optional[int] = None


class PickGroup(NamedTuple):
    #: "Van <activity> (<year>)" for the copy chain's group, "" for the rest.
    label: str
    items: tuple[PickItem, ...]


class PickOptions(NamedTuple):
    groups: tuple[PickGroup, ...]
    total: int
    page: int
    pages: int


def _activity_lookup(db) -> dict[int, tuple[str, Optional[int]]]:
    """Per activity id: its name and the year of its first date."""
    from app.domains.activities.api import activity_options

    return {
        o.id: (o.name, o.first_date.year if o.first_date else None) for o in activity_options(db)
    }


def pick_options(
    db,
    *,
    for_activity_id: Optional[int] = None,
    q: str = "",
    year: Optional[int] = None,
    tag_id: Optional[int] = None,
    photos_of: Optional[int] = None,
    posters_of: Optional[int] = None,
    designs_of: Optional[int] = None,
    kind: Optional[MediaKind] = None,
    page: int = 1,
) -> PickOptions:
    """The library as a picker offers it (CR-15 §C4.3, C6 tests 3 and 4).

    - **Last year first.** For a record of a copied activity (`for_activity_id`),
      the photos of the activities it was copied from (#1397) come first, as one
      group per predecessor, "Van <name> (<year>)". They were what the board
      re-uploaded because the old offer showed only the activity's own photos.
    - **A branch of the tree:** `photos_of` an activity (its album photos and
      design images), `posters_of` an activity (Affiches — the only place a
      poster is offered), a `kind` of `KIND_BRANCHES` (Logo's, Paginabeelden, Ontwerpbeelden), or a tag with
      the tags below it. A poster that is a PDF is never offered (`_offered`).
    - **Search** matches the title, the activity's name and a tag's name; the
      **year** keeps the pictures of activities dated in that year. They combine.
    - **Pages of 60**, counted over the groups as one list.

    Reads columns only, never the bytes: a picker lists hundreds of pictures.
    """
    activities = _activity_lookup(db)
    index = tag_index(db)
    names_of_tag = dict(index.paths)

    kinds: tuple[MediaKind, ...] = PICKABLE_KINDS
    if posters_of is not None:
        kinds = (MediaKind.ACTIVITY_POSTER,)
    elif designs_of is not None:
        kinds = (MediaKind.DESIGN_IMAGE,)
    elif kind in KIND_BRANCHES:
        kinds = (kind,)
    rows = (
        db.query(
            MediaAsset.id,
            MediaAsset.kind,
            MediaAsset.activity_id,
            MediaAsset.title,
            MediaAsset.width,
            MediaAsset.height,
        )
        .filter(_offered(), MediaAsset.kind.in_(kinds))
        .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc())
        .all()
    )
    if posters_of is not None:
        rows = [r for r in rows if r.activity_id == posters_of]
    elif designs_of is not None:
        # #1527: Ontwerpbeelden › an activity, or "Zonder activiteit".
        wanted = None if designs_of == WITHOUT_ACTIVITY else designs_of
        rows = [r for r in rows if r.activity_id == wanted]
    elif photos_of is not None:
        rows = [
            r
            for r in rows
            if r.activity_id == photos_of
            and r.kind in (MediaKind.ACTIVITY_PHOTO, MediaKind.DESIGN_IMAGE)
        ]
    elif tag_id is not None:
        under = tag_subtree_ids(db, tag_id)
        rows = [r for r in rows if set(index.per_asset.get(r.id, ())) & under]

    term = (q or "").strip().lower()
    if term:

        def matches(r) -> bool:
            name = activities.get(r.activity_id, ("", None))[0] if r.activity_id else ""
            tags = (names_of_tag.get(t, "") for t in index.per_asset.get(r.id, ()))
            return any(term in (text or "").lower() for text in (r.title, name, *tags))

        rows = [r for r in rows if matches(r)]
    if year is not None:
        rows = [
            r
            for r in rows
            if r.activity_id and activities.get(r.activity_id, ("", None))[1] == year
        ]

    def item(r) -> PickItem:
        origin = ""
        if r.activity_id in activities:
            name, jaar = activities[r.activity_id]
            origin = f"{name} ({jaar})" if jaar else name
        return PickItem(
            r.id,
            r.title or "",
            media_url(r.id, thumb=True),
            origin,
            url=media_url(r.id),
            width=r.width,
            height=r.height,
        )

    ordered: list[tuple[str, PickItem]] = []
    taken: set[int] = set()
    branch_chosen = (
        posters_of is not None
        or photos_of is not None
        or designs_of is not None
        or tag_id is not None
        or kind is not None
    )
    if for_activity_id is not None and not branch_chosen:
        from app.domains.activities.api import predecessors_of

        for earlier in predecessors_of(db, for_activity_id):
            label = (
                _("Van %(naam)s (%(jaar)s)") % {"naam": earlier.name, "jaar": earlier.year}
                if earlier.year
                else _("Van %(naam)s") % {"naam": earlier.name}
            )
            for r in rows:
                if r.activity_id == earlier.id and r.id not in taken:
                    ordered.append((label, item(r)))
                    taken.add(r.id)
    ordered += [("", item(r)) for r in rows if r.id not in taken]

    total = len(ordered)
    pages = max(1, -(-total // PICK_PAGE_SIZE))
    page = min(max(1, page), pages)
    window = ordered[(page - 1) * PICK_PAGE_SIZE : page * PICK_PAGE_SIZE]
    groups: list[PickGroup] = []
    for label, it in window:
        if groups and groups[-1].label == label:
            groups[-1] = PickGroup(label, groups[-1].items + (it,))
        else:
            groups.append(PickGroup(label, (it,)))
    return PickOptions(tuple(groups), total, page, pages)
