"""Design Studio service: designs, content, versions, publishing (CR-10 §3.14).

The rules that live here and nowhere else:

- **Facts come from the activity at render time.** The title, dates, place,
  deadline, organisers and the association's contact lines are read through
  the facades when a poster is built, never stored on the design. Each version
  keeps a fingerprint of what it used; :func:`is_stale` compares.
- **A version is all-or-nothing.** Every layout is merged, checked with
  Inkscape as the authority and exported; one violation and nothing is
  written. At most :data:`MAX_VERSIONS` per design — the oldest unpublished one
  goes when a fourth is made.
- **Publishing is a copy.** The version's A3 PDF is handed to
  ``media.replace_activity_poster`` exactly like a hand-made upload; the
  activity never learns the Design Studio exists.
- **An uploaded SVG is the unit's.** Cleaned by media's one allowlist
  (#1011 — this component carries no cleaner), kept per layout, used instead
  of the merge for that layout's exports, and named "handmatig bewerkt" until
  it is removed. Its brand check only warns.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import Optional

from sqlalchemy.orm import Session
from starlette.datastructures import Headers, UploadFile

from app.domains.designstudio import brand, imaging, render
from app.domains.designstudio.content import Contact, Highlight, ImageBytes, PosterContent
from app.domains.designstudio.icons import ICONS
from app.domains.designstudio.models import (
    INSET_CORNERS,
    GEN_DISCARDED,
    GEN_PICKED,
    GEN_REQUESTED,
    LAYOUT_FEED,
    LAYOUT_PRINT,
    LAYOUTS,
    PRESETS,
    STATUS_DRAFT,
    STATUS_FINAL,
    VARIANT_PDF,
    VARIANT_PNG,
    VARIANT_SVG,
    VARIANT_SVG_EDITED,
    Design,
    DesignHighlight,
    DesignLogo,
    DesignRendition,
    DesignVersion,
    ImageGeneration,
)
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id


def _tenant() -> int:
    return current_tenant_id.get() or DEFAULT_TENANT_ID

logger = logging.getLogger(__name__)

MAX_VERSIONS = 3
MAX_HIGHLIGHTS = 4          # the unit's own rows (Koen, 20 September 2026: six in total is calmer)
MAX_HIGHLIGHT_ROWS = 6      # plus date/time and place, which come by themselves
MAX_LOGOS = 2
MAX_DATES = 12
IMAGE_SLOTS = ("main_image_id", "inset_image_id", "third_image_id")

MONTHS_NL = ("JANUARI", "FEBRUARI", "MAART", "APRIL", "MEI", "JUNI", "JULI", "AUGUSTUS",
             "SEPTEMBER", "OKTOBER", "NOVEMBER", "DECEMBER")
WEEKDAYS_NL = ("MAANDAG", "DINSDAG", "WOENSDAG", "DONDERDAG", "VRIJDAG", "ZATERDAG", "ZONDAG")

PRESET_LABELS = {"eenvoudig": "Eenvoudig — één grote foto en de tekst van de activiteit over de volle breedte",
                 "beeld": "Met beeld — foto of tekening rechts, kernpunten links, omschrijving eronder",
                 "tekst": "Tekst — geen beeld, kernpunten links, omschrijving rechts"}
STATUS_LABELS = {STATUS_DRAFT: "Ontwerp", STATUS_FINAL: "Definitief"}
STATUS_TONES = {STATUS_DRAFT: "yellow", STATUS_FINAL: "green"}
LAYOUT_LABELS = {LAYOUT_PRINT: "Print (A3/A4)", LAYOUT_FEED: "Instagram (4:5)"}

#: What a version renders per layout: (variant, size code, export kind, page mm, png width).
RENDITIONS = {
    LAYOUT_PRINT: (
        (VARIANT_PDF, "a3", "pdf", None, None),
        (VARIANT_PDF, "a4", "pdf", (210, 297), None),
        (VARIANT_PNG, "a3", "png", None, 1754),
        (VARIANT_SVG, "a3", None, None, None),
    ),
    LAYOUT_FEED: (
        (VARIANT_PNG, "feed", "png", None, 1080),
        (VARIANT_SVG, "feed", None, None, None),
    ),
}


class DesignError(ValueError):
    """An input error the screen shows. Several messages at once are allowed:
    the overflow check names every box that fails, not just the first."""

    def __init__(self, *messages: str):
        super().__init__(" ".join(messages))
        self.messages = list(messages)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Designs ─────────────────────────────────────────────────────────────────

def list_designs(db: Session) -> list[Design]:
    return db.query(Design).order_by(Design.updated_at.desc(), Design.id.desc()).all()


def designs_for_activity(db: Session, activity_id: int) -> list[Design]:
    """The designs of one activity, newest first — for the activity screen's
    jump to the Design Studio (Koen, 20 September 2026)."""
    return (db.query(Design).filter(Design.activity_id == activity_id)
            .order_by(Design.updated_at.desc(), Design.id.desc()).all())


def get_design(db: Session, design_id: int) -> Optional[Design]:
    return db.query(Design).filter(Design.id == design_id).first()


def create_design(db: Session, *, activity_id: int, duo_code: str, preset: str = "beeld",
                  created_by: str = "") -> Design:
    from app.domains.activities.api import get_activity

    if get_activity(db, activity_id) is None:
        raise DesignError("Activiteit niet gevonden.")
    brand.split_duo(duo_code)  # raises on an unknown or forbidden duo
    if duo_code not in brand.ENABLED_DUOS:
        raise DesignError("Dit kleurenduo staat niet aan.")
    if preset not in PRESETS:
        raise DesignError("Onbekende opmaak.")
    design = Design(activity_id=activity_id, duo_code=duo_code, preset=preset, created_by=created_by)
    db.add(design)
    db.commit()
    return design


def save_design(db: Session, design: Design, form: dict, *, highlights: list[tuple[str, str, bool]],
                logo_ids: list[int]) -> None:
    """Store the editor form. Facts are not in ``form``; they cannot be.

    Every refusal comes before the first mutation, so a refused save leaves
    the design exactly as it was and the screen can show what was typed."""
    if form.get("duo_code") not in brand.ENABLED_DUOS:
        raise DesignError("Dit kleurenduo staat niet aan.")
    if form.get("preset") not in PRESETS:
        raise DesignError("Onbekende opmaak.")
    if len(highlights) > MAX_HIGHLIGHTS:
        raise DesignError(f"Ten hoogste {MAX_HIGHLIGHTS} kernpunten.")
    if len(logo_ids) > MAX_LOGOS:
        raise DesignError(f"Ten hoogste {MAX_LOGOS} logo's op de logostrook.")
    kept = [(icon, line, emphasis) for icon, line, emphasis in highlights if (line or "").strip()]
    for icon, _line, _emphasis in kept:
        if icon not in ICONS:
            raise DesignError(f"Onbekend icoon: {icon}")
    if "inset_corner" in form and form["inset_corner"] not in INSET_CORNERS:
        raise DesignError("Onbekende hoek voor de polaroid.")
    # Choices keep their last value when the form leaves them empty; free text
    # becomes NULL so "empty" and "not filled in" stay the same thing.
    for key in ("duo_code", "preset", "inset_corner"):
        if (form.get(key) or "").strip():
            setattr(design, key, form[key].strip())
    for key in ("tagline", "subtitle"):
        if key in form:
            setattr(design, key, (form[key] or "").strip() or None)
    if "explanation_md" in form:
        # "Omschrijving anders": the field shows the activity's description;
        # unchanged (or emptied) means "use the activity's", stored as NULL so
        # it stays live.
        typed = (form["explanation_md"] or "").strip()
        own = facts_for(db, design)["description"]
        design.explanation_md = typed if typed and typed != own else None
    for key in ("main_image_id", "inset_image_id", "third_image_id"):
        if key in form:
            raw = (form[key] or "").strip()
            setattr(design, key, int(raw) if raw.isdigit() else None)
    for key in ("main_focus_x", "main_focus_y"):
        if key in form:
            try:
                setattr(design, key, min(1.0, max(0.0, float(form[key]))))
            except (TypeError, ValueError):
                pass

    # Replace, not merge — and flush the removal before the new rows go in:
    # the unit of work inserts before it deletes, so the same `sort_order`
    # would collide on `uq_design_highlight_order` / `uq_design_logo_order`
    # (HDEV, 19 September 2026: every second save failed with a 500).
    design.highlights.clear()
    design.logos.clear()
    db.flush()
    for i, (icon, line, emphasis) in enumerate(kept):
        design.highlights.append(DesignHighlight(sort_order=i, icon_code=icon, text=line.strip()[:90],
                                                 emphasis=bool(emphasis)))
    for i, asset_id in enumerate(logo_ids):
        design.logos.append(DesignLogo(media_asset_id=asset_id, sort_order=i))
    design.status = STATUS_DRAFT
    design.updated_at = _now()
    db.commit()


def delete_design(db: Session, design: Design) -> None:
    db.delete(design)
    db.commit()


# ── Facts ───────────────────────────────────────────────────────────────────

def _organisers(db: Session, activity_id: int) -> list[Contact]:
    """The organisers ticked as contact (#1004), with the e-mail and gsm the
    activity publishes (override or the person's own). Nobody ticked → the
    poster shows the association's own lines."""
    from app.domains.activities.api import organisers_for

    return [Contact(name=row.name, mobile=row.mobile or "", email=row.email or "")
            for row in organisers_for(db, activity_id) if row.is_contact]


def _association(db: Session) -> dict[str, str]:
    from app.domains.mdm.api import organization_details

    details = organization_details(db, _tenant())
    website = (details.get("website") or "").strip()
    for prefix in ("https://", "http://"):
        if website.startswith(prefix):
            website = website[len(prefix):]
    return {"website": website.rstrip("/"), "email": (details.get("email") or "").strip(),
            "mobile": (details.get("mobile") or details.get("phone") or "").strip(),
            "name": (details.get("name") or "").strip()}


def day_label(day: date, *, weekday: bool = False) -> str:
    text = f"{day.day} {MONTHS_NL[day.month - 1]}"
    return f"{WEEKDAYS_NL[day.weekday()]} {text}" if weekday else text


def time_label(moment) -> str:
    if moment is None:
        return ""
    return f"OM {moment.hour}U" + (f"{moment.minute:02d}" if moment.minute else "")


def _shared_deadline(activity) -> str:
    """The one deadline that holds for every component, as an ISO date or ""."""
    from app.domains.activities.api import shared_deadline

    datum = shared_deadline(activity)
    return datum.isoformat() if datum else ""


def facts_for(db: Session, design: Design) -> dict:
    """Everything the poster takes from outside the design, as plain values.
    This is what the fingerprint hashes, so every key must be JSON-plain."""
    from app.domains.activities.api import get_activity

    activity = get_activity(db, design.activity_id)
    if activity is None:
        raise DesignError("Activiteit niet gevonden.")
    dates = sorted((d for d in activity.dates if getattr(d, "deleted_at", None) is None),
                   key=lambda d: (d.start_date, d.start_time or datetime.min.time()))
    assoc = _association(db)
    return {
        "activity_id": activity.id,
        "title": activity.name or "",
        "location": activity.location or "",
        "dates": [{"date": d.start_date.isoformat(),
                   "time": d.start_time.strftime("%H:%M") if d.start_time else ""} for d in dates],
        # #1053: the deadline moved to the component. A poster speaks for the
        # whole activity, so it only carries a date when every component has the
        # same one; differing dates belong on the page, not on one printed line.
        "deadline": _shared_deadline(activity),
        # #1016: the public description — the poster's explanation unless the
        # design types its own (then the screen names the difference).
        "description": (activity.description or "").strip(),
        "cancelled": bool(activity.is_cancelled),
        # What the QR points at: the activity's own page (slug or id), so
        # "scan voor meer info" really shows this activity (CR-10 §3.7).
        "key": activity.slug or str(activity.id),
        "members_only": bool(activity.members_only),
        "organisers": [{"name": c.name, "mobile": c.mobile, "email": c.email}
                       for c in _organisers(db, activity.id)],
        "website": assoc["website"], "email": assoc["email"], "mobile": assoc["mobile"],
        "association": assoc["name"],
    }


def fingerprint(facts: dict) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def is_stale(db: Session, version: DesignVersion) -> bool:
    return version.facts_fingerprint != fingerprint(facts_for(db, version.design))


# ── Content ─────────────────────────────────────────────────────────────────

def _image(db: Session, asset_id: Optional[int], focus=(0.5, 0.5)) -> Optional[ImageBytes]:
    from app.domains.media.api import MediaAsset

    if not asset_id:
        return None
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None or not asset.content_type.startswith("image/") or asset.content_type == "image/svg+xml":
        return None
    return ImageBytes(bytes(asset.data), asset.content_type, float(focus[0]), float(focus[1]),
                      int(asset.width or 0), int(asset.height or 0))


def _title_lines(title: str) -> tuple[tuple[str, ...], str]:
    """One or two title lines and the joiner: a title with " en " becomes
    two lines around an EN badge; a long title splits at the middle word; a
    short one stays whole."""
    text = (title or "").strip()
    words = text.split()
    if len(words) == 3 and words[1].lower() in ("en", "&"):
        return (words[0].upper(), words[2].upper()), "EN"
    if len(words) >= 2 and len(text) > 14:
        half = len(words) // 2
        return (" ".join(words[:half]).upper(), " ".join(words[half:]).upper()), ""
    return (text.upper(),), ""


def content_for(db: Session, design: Design, facts: Optional[dict] = None) -> PosterContent:
    facts = facts or facts_for(db, design)
    title_lines, joiner = _title_lines(facts["title"])

    highlights: list[Highlight] = []
    dates = facts["dates"]
    date_line = ""
    if len(dates) == 1:
        day = date.fromisoformat(dates[0]["date"])
        date_line = day_label(day, weekday=True)
        if dates[0]["time"]:
            date_line += f" {time_label(datetime.strptime(dates[0]['time'], '%H:%M').time())}"
        highlights.append(Highlight("calendar", date_line, True))
    if facts["location"]:
        highlights.append(Highlight("map-pin", facts["location"].upper()))
    for hl in design.highlights:
        highlights.append(Highlight(hl.icon_code, hl.text.upper()))
    highlights = highlights[:MAX_HIGHLIGHT_ROWS]

    grid = tuple(day_label(date.fromisoformat(d["date"])) for d in dates[:MAX_DATES]) if len(dates) > 1 else ()
    year = date.fromisoformat(dates[0]["date"]).year if dates else date.today().year

    contacts = tuple(Contact(**c) for c in facts["organisers"])

    return PosterContent(
        duo_code=design.duo_code, preset=design.preset,
        title_lines=title_lines, title_joiner=joiner,
        bar_text=(design.subtitle or "").upper(),
        tagline=design.tagline or "",
        highlights=tuple(highlights),
        date_line=date_line, location=(facts["location"] or "").upper(),
        deadline_text=deadline_line(facts["deadline"]),
        more_info_label="Meer info en inschrijven:",
        members_only=bool(facts["members_only"]),
        dates_heading=f"DATA IN {year}",
        dates=grid,
        explanation_md=design.explanation_md or facts["description"],
        main_image=_image(db, design.main_image_id, (design.main_focus_x, design.main_focus_y)),
        inset_image=_image(db, design.inset_image_id), inset_corner=design.inset_corner or "bottom_right",
        third_image=_image(db, design.third_image_id),
        website=facts["website"], email=facts["email"], association_mobile=facts["mobile"], contacts=contacts,
        logos=tuple(img for img in (_image(db, lg.media_asset_id) for lg in design.logos) if img),
        seed=design.id or 1,
    )


def deadline_line(iso: str) -> str:
    """"Inschrijven tot 8 november", or "" when there is no single deadline
    for the whole activity (#1053: it lives per component)."""
    if not iso:
        return ""
    day = date.fromisoformat(iso)
    return f"Inschrijven tot {day.day} {MONTHS_NL[day.month - 1].lower()}"


def qr_url(db: Session, key: str = "") -> str:
    from app.kernel.tenant_config import tenant_home_url

    url = tenant_home_url(db).rstrip("/")
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
    return f"{url}/activiteiten/{key}" if key else url


# ── Preview and check ───────────────────────────────────────────────────────

def edited_svg_for(db: Session, design: Design, layout: str) -> Optional[DesignRendition]:
    return (db.query(DesignRendition)
            .filter(DesignRendition.design_id == design.id, DesignRendition.version_id.is_(None),
                    DesignRendition.layout_code == layout, DesignRendition.variant == VARIANT_SVG_EDITED)
            .first())


def _asset_bytes(db: Session, asset_id: int) -> bytes:
    from app.domains.media.api import MediaAsset

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise DesignError("Bestand niet gevonden in media.")
    return bytes(asset.data)


def merged_for(db: Session, design: Design, layout: str, *, facts: Optional[dict] = None,
               content: Optional[PosterContent] = None) -> render.Merged:
    """The SVG for one layout: the hand-edited one when there is one, else the
    merge. An edited SVG has no boxes to check — the unit took over."""
    edited = edited_svg_for(db, design, layout)
    if edited is not None:
        svg = _asset_bytes(db, edited.media_asset_id).decode("utf-8")
        spec = render.contract(design.template_key)["layouts"][layout]
        return render.Merged(svg=svg, boxes={}, violations=(), width_mm=spec["width_mm"], height_mm=spec["height_mm"])
    content = content or content_for(db, design, facts)
    return render.merge(content, layout=layout, template_key=design.template_key,
                        title=facts["title"] if facts else "Affiche",
                        qr_url=qr_url(db, facts.get("key", "") if facts else ""))


def preview_png(db: Session, design: Design, layout: str, *, width_px: int = 700) -> tuple[bytes, list[str]]:
    """The editor's preview: quick check (no Inkscape measurement), then a PNG."""
    facts = facts_for(db, design)
    merged = merged_for(db, design, layout, facts=facts)
    problems = render.check(merged, authority=False)
    return render.export(merged.svg, "png", png_width_px=width_px), problems


def check_design(db: Session, design: Design) -> dict[str, list[str]]:
    facts = facts_for(db, design)
    content = content_for(db, design, facts)
    return {layout: render.check(merged_for(db, design, layout, facts=facts, content=content), authority=False)
            for layout in LAYOUTS}


# ── Versions ────────────────────────────────────────────────────────────────

def _store_render(db: Session, *, filename: str, content_type: str, data: bytes) -> int:
    from app.domains.media.api import add_document

    asset = add_document(db, kind="design_render", filename=filename, content_type=content_type, data=data)
    return asset.id


def make_version(db: Session, design: Design, *, created_by: str = "") -> DesignVersion:
    """Render every layout, with Inkscape as the authority, and write one
    numbered version — or nothing."""
    facts = facts_for(db, design)
    if facts["cancelled"]:
        raise DesignError("Deze activiteit is geannuleerd; er komt geen affiche van.")
    content = content_for(db, design, facts)
    merged = {layout: merged_for(db, design, layout, facts=facts, content=content) for layout in LAYOUTS}
    problems: list[str] = []
    for layout, m in merged.items():
        problems += [f"{LAYOUT_LABELS[layout]}: {p}" for p in render.check(m, authority=True)]
    if problems:
        raise DesignError(*problems)

    files: list[tuple[str, str, str, str, bytes]] = []  # layout, variant, size, content type, bytes
    slug = f"ontwerp-{design.id}"
    for layout, plan in RENDITIONS.items():
        svg = merged[layout].svg
        for variant, size, kind, page, png_w in plan:
            if kind is None:
                files.append((layout, variant, size, "image/svg+xml", svg.encode("utf-8")))
                continue
            source = render.resize_page(svg, *page) if page else svg
            data = render.export(source, kind, png_width_px=png_w)
            files.append((layout, variant, size, "application/pdf" if kind == "pdf" else "image/png", data))

    number = (max((v.number for v in design.versions), default=0)) + 1
    version = DesignVersion(design=design, number=number, facts_fingerprint=fingerprint(facts),
                            sponsor_asset_ids=",".join(str(lg.media_asset_id) for lg in design.logos),
                            created_by=created_by)
    db.add(version)
    db.flush()
    ext = {"application/pdf": "pdf", "image/png": "png", "image/svg+xml": "svg"}
    for layout, variant, size, ctype, data in files:
        asset_id = _store_render(db, filename=f"{slug}-v{number}-{layout}-{size}.{ext[ctype]}",
                                 content_type=ctype, data=data)
        edited = edited_svg_for(db, design, layout)
        db.add(DesignRendition(design_id=design.id, version_id=version.id, layout_code=layout, variant=variant,
                               size_code=size, media_asset_id=asset_id,
                               facts_fingerprint=edited.facts_fingerprint if edited else None))
    design.status = STATUS_FINAL
    design.updated_at = _now()
    _prune_versions(db, design)
    db.commit()
    return version


def _prune_versions(db: Session, design: Design) -> None:
    """Keep the newest MAX_VERSIONS; the published one is never pruned."""
    from app.domains.media.api import delete_media

    versions = sorted(design.versions, key=lambda v: v.number)
    while len(versions) > MAX_VERSIONS:
        victim = next((v for v in versions if v.id != design.published_version_id), None)
        if victim is None:
            break
        asset_ids = [r.media_asset_id for r in victim.renditions]
        versions.remove(victim)
        # The collection cascades delete-orphan: removing the version is the
        # delete; its renditions go with it. The media files go afterwards —
        # `delete_media` commits, so it must not run mid-flush.
        design.versions.remove(victim)
        db.flush()
        for asset_id in asset_ids:
            try:
                delete_media(db, asset_id)
            except Exception:  # noqa: BLE001 - a missing file must not block the new version
                logger.warning("designstudio: render %s already gone", asset_id)


def rendition(version: DesignVersion, layout: str, variant: str, size: str = "") -> Optional[DesignRendition]:
    for r in version.renditions:
        if r.layout_code == layout and r.variant == variant and (not size or r.size_code == size):
            return r
    return None


async def publish(db: Session, design: Design, version: DesignVersion, background_tasks) -> None:
    """Copy the A3 PDF onto the activity as its poster — through the same door
    a hand-made poster takes. The confirmation is the screen's job."""
    from app.domains.media.api import replace_activity_poster

    pdf = rendition(version, LAYOUT_PRINT, VARIANT_PDF, "a3")
    if pdf is None:
        raise DesignError("Deze versie heeft geen A3-pdf.")
    data = _asset_bytes(db, pdf.media_asset_id)
    upload = UploadFile(file=BytesIO(data), filename=f"affiche-{design.activity_id}-v{version.number}.pdf",
                        headers=Headers({"content-type": "application/pdf"}))
    await replace_activity_poster(db, design.activity_id, upload, background_tasks)
    design.published_version_id = version.id
    design.updated_at = _now()
    db.commit()


# ── Hand-edited SVG ─────────────────────────────────────────────────────────

def upload_edited_svg(db: Session, design: Design, layout: str, raw: bytes) -> list[str]:
    """Store through media — which cleans the file with the platform's one
    allowlist (#1011) — check the page size on what came back, replace for
    this layout. Returns the brand warnings — warnings only (§3.6a): a
    hand-made poster may break the guide, knowingly."""
    from app.domains.media.api import MediaFout, add_document, delete_media

    if layout not in LAYOUTS:
        raise DesignError("Onbekende opmaak.")
    if not raw:
        raise DesignError("Leeg bestand.")
    try:
        asset = add_document(db, kind="design_render", filename=f"ontwerp-{design.id}-{layout}-bewerkt.svg",
                             content_type="image/svg+xml", data=raw)
    except MediaFout as exc:
        raise DesignError(str(exc)) from exc
    cleaned = bytes(asset.data).decode("utf-8")
    spec = render.contract(design.template_key)["layouts"][layout]
    w, h = render.page_size_mm(cleaned)
    if abs(w - spec["width_mm"]) > 1 or abs(h - spec["height_mm"]) > 1:
        delete_media(db, asset.id)
        raise DesignError(f"Het paginaformaat klopt niet: {w:.0f} × {h:.0f} mm in plaats van "
                          f"{spec['width_mm']:.0f} × {spec['height_mm']:.0f} mm.")
    warnings = brand.check_template(cleaned)
    remove_edited_svg(db, design, layout)
    db.add(DesignRendition(design_id=design.id, version_id=None, layout_code=layout, variant=VARIANT_SVG_EDITED,
                           size_code="", media_asset_id=asset.id, facts_fingerprint=fingerprint(facts_for(db, design))))
    design.status = STATUS_DRAFT
    db.commit()
    return warnings


def remove_edited_svg(db: Session, design: Design, layout: str) -> None:
    from app.domains.media.api import delete_media

    existing = edited_svg_for(db, design, layout)
    if existing is not None:
        try:
            delete_media(db, existing.media_asset_id)
        except Exception:  # noqa: BLE001
            logger.warning("designstudio: edited svg %s already gone", existing.media_asset_id)
        db.delete(existing)
        db.commit()


# ── Images ──────────────────────────────────────────────────────────────────

async def add_design_image(db: Session, design: Design, upload, *, slot: str = "") -> int:
    """Store one uploaded picture as a design image and, with ``slot``, put it
    in that place of the design right away."""
    from app.domains.media.api import MediaFout, upload_media

    if slot and slot not in IMAGE_SLOTS:
        raise DesignError("Onbekende plaats voor het beeld.")
    try:
        rows = await upload_media(db, files=[upload], kind="design_image", activity_id=design.activity_id)
    except MediaFout as exc:
        raise DesignError(str(exc)) from exc
    asset_id = rows[0]["id"]
    if slot:
        setattr(design, slot, asset_id)
        design.status = STATUS_DRAFT
        design.updated_at = _now()
    db.commit()
    return asset_id


def image_options(db: Session, design: Design) -> list[dict]:
    """Activity photos, design images of this activity and fetched AI variants."""
    from app.domains.media.api import list_activity_photos, list_media

    out = [dict(m, source="activity_photo") for m in list_activity_photos(db, design.activity_id)]
    out += [dict(m, source="design_image") for m in list_media(db, kind="design_image", activity_id=design.activity_id)]
    return out


def sponsor_options(db: Session) -> list[dict]:
    from app.domains.media.api import list_media

    return [m for m in list_media(db, kind="sponsor") if m.get("is_active", True)]


# ── AI images ───────────────────────────────────────────────────────────────

def spent_this_month(db: Session, *, tenant_id: Optional[int] = None, all_tenants: bool = False) -> Decimal:
    """What the AI log says this unit (or the platform) spent on images this
    month, in EUR. USD lines are converted with the configured rate."""
    from app.domains.chatbot.api import cost_per_period

    start, end = imaging.month_bounds_now()
    tenants = [tenant_id or _tenant()]
    if all_tenants:
        from app.domains.mdm.api import organization_options

        tenants = [o["id"] for o in organization_options(db)] or tenants
    total = Decimal("0")
    for tid in tenants:
        for line in cost_per_period(db, tenant_id=tid, start=start, end=end):
            if line.provider != imaging.PROVIDER:
                continue
            for currency, amount in (line.cost_amounts or {}).items():
                total += imaging.usd_to_eur(amount) if currency == "USD" else amount
    return total


def reserved_cents(db: Session) -> int:
    from sqlalchemy import func

    value = (db.query(func.coalesce(func.sum(ImageGeneration.reserved_cents), 0))
             .filter(ImageGeneration.status == GEN_REQUESTED).scalar())
    return int(value or 0)


def budget(db: Session) -> imaging.Budget:
    return imaging.budget_for(db, tenant_id=_tenant(), spent_eur=spent_this_month(db),
                              reserved_cents=reserved_cents(db))


def request_images(db: Session, design: Design, scene: str, *, requested_by: str = "",
                   reference_asset_id: Optional[int] = None, style: str = "lijn", change: str = "") -> str:
    """One click: budget check, four reservations, four jobs. Returns the
    request key the screen polls on. A second click while the first is still
    running is refused — a double click must not cost twice. With a
    reference image (a variant the unit liked) and ``change`` ("wat wil je
    anders?") the new variants build on that image."""
    from app.kernel.jobs import enqueue

    english, _translated = imaging.translate_scene(scene, actor=requested_by)
    english_change, _c = imaging.translate_scene(change, actor=requested_by)
    prompt = imaging.build_prompt(english, style, english_change)
    scene = scene.strip() or change.strip()   # kept as typed, so the redo shows Dutch to a Dutch speaker
    if any(g.status == GEN_REQUESTED for g in design.generations):
        raise DesignError("Er loopt al een aanvraag voor dit ontwerp; wacht tot die klaar is.")
    with_reference = bool(reference_asset_id)
    per_image = imaging.expected_cost_eur(with_reference=with_reference)
    imaging.check_budget(budget(db), platform_spent_eur=spent_this_month(db, all_tenants=True),
                         cost_eur=per_image * imaging.VARIANTS_PER_CLICK)
    key = imaging.new_request_key()
    rnd = random.Random()
    for _ in range(imaging.VARIANTS_PER_CLICK):
        row = ImageGeneration(design_id=design.id, request_key=key, seed=rnd.randint(1, 2**31 - 1),
                              scene=scene.strip()[:600], style=style,
                              width=1440, height=1248, status=GEN_REQUESTED,
                              reserved_cents=int((per_image * 100).to_integral_value()),
                              requested_by=requested_by)
        db.add(row)
        db.flush()
        enqueue(db, "designstudio.generate", {"generation_id": row.id, "prompt": prompt,
                                              "reference_asset_id": reference_asset_id,
                                              "tenant_id": _tenant()}, max_attempts=1)
    db.commit()
    return key


def sponsor_usage(db: Session, asset_id: int, year: int) -> int:
    """How many designs carried this sponsor logo on a published version in
    ``year`` — the Mona agreement allows five posters a year (CR-10 R11)."""
    from sqlalchemy import extract

    rows = (db.query(DesignVersion.sponsor_asset_ids)
            .join(Design, Design.published_version_id == DesignVersion.id)
            .filter(extract("year", DesignVersion.created_at) == year)
            .filter(DesignVersion.sponsor_asset_ids != "").all())
    return sum(1 for (ids,) in rows if str(asset_id) in ids.split(","))


def warnings_for(design: Design, facts: dict) -> list[str]:
    """What the unit should know but may do anyway: design text that shadows
    a fact (CR-10 §3.7). Never blocks a version."""
    out = []
    if design.explanation_md and facts.get("description") and \
            design.explanation_md.strip() != facts["description"].strip():
        out.append("De omschrijving op de affiche wijkt af van die van de activiteit.")
    return out


def pick_generation(db: Session, design: Design, generation_id: int, *, slot: str = "main_image_id") -> None:
    gen = next((g for g in design.generations if g.id == generation_id), None)
    if gen is None or gen.media_asset_id is None:
        raise DesignError("Dit beeld is er (nog) niet.")
    if slot not in IMAGE_SLOTS:
        raise DesignError("Onbekende plaats voor het beeld.")
    setattr(design, slot, gen.media_asset_id)
    gen.status = GEN_PICKED
    for sibling in design.generations:
        if sibling.request_key == gen.request_key and sibling.id != gen.id and sibling.status == "fetched":
            sibling.status = GEN_DISCARDED
    design.status = STATUS_DRAFT
    design.updated_at = _now()
    db.commit()
