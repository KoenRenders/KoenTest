"""The meeting screens (CR-09, #258): the list, the document, sending, the circle.

Board-only and desktop-first (§3.2): there is no public counterpart and no plan
for one. Everything sits behind `require_admin_ui` — ADMIN or OPERATOR, the same
door as every other admin screen.

**Agenda and report are one screen.** Preparing and taking minutes differ by a
label, not by a mode: ticking attendance or typing a note *is* entering the
report phase, and every affordance (add a point, add a section, add an
attachment) works identically in both (§3.23). That is why one route, one
template and one view-model serve both.

The paths are Dutch because a board member reads them in the address bar; the
module, the routes and the parameters are English like all new code (CLAUDE.md,
"URL paths follow the audience").
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.domains.meetings.api import (
    ATTENDANCE_EXCUSED,
    ATTENDANCE_PRESENT,
    FILE_SENT_PDF,
    STATUS_AGENDA,
    STATUS_SENT,
    MeetingError,
    add_extra_recipient,
    add_file,
    add_item,
    add_section,
    addable_activities,
    attendance_of,
    create_meeting,
    delete_file,
    delete_item,
    document_of,
    files_of,
    filename_for,
    get_file,
    get_meeting,
    list_meetings,
    previous_meeting,
    long_date,
    member_standing,
    recipients_for,
    remove_extra_recipient,
    render,
    reopen,
    section_label,
    sections_of,
    send_meeting_mail,
    set_attendance,
    update_item,
)
from app.domains.meetings.viewmodels import (
    MeetingCircleView, MeetingDocumentView, MeetingListView, MeetingNewView,
    MeetingSendView,
)
from app.i18n import _
from app.ui import admin_nav, templates

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

NAV = "/admin/vergaderingen"

STATUS_LABELS = {"agenda": "Agenda", "report": "Verslag (bezig)",
                 "sent": "Verslag verstuurd"}
STATUS_TONES = {"agenda": "blue", "report": "yellow", "sent": "green"}

# Attendance cycles present → excused → not ticked. One click per state, in the
# order a secretary uses them.
NEXT_ATTENDANCE = {None: ATTENDANCE_PRESENT, "": ATTENDANCE_PRESENT,
                   ATTENDANCE_PRESENT: ATTENDANCE_EXCUSED,
                   ATTENDANCE_EXCUSED: ""}


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _meeting_or_404(db: Session, meeting_id: int):
    meeting = get_meeting(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=_("Vergadering niet gevonden."))
    return meeting


def _title(meeting) -> str:
    return _("Vergadering — %s") % long_date(meeting.meeting_date)


# ── The list ─────────────────────────────────────────────────────────────────

def _list_view(request: Request, db: Session, error: Optional[str] = None
               ) -> MeetingListView:
    from app.domains.mdm.api import organization_circle

    meetings = list_meetings(db)
    return MeetingListView(
        meetings=meetings,
        status_labels={m.id: _(STATUS_LABELS.get(m.status, m.status)) for m in meetings},
        status_tones={m.id: STATUS_TONES.get(m.status, "gray") for m in meetings},
        dates={m.id: long_date(m.meeting_date) for m in meetings},
        circle_size=len(organization_circle(db)),
        csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


def _new_view(request: Request, db: Session, error: Optional[str] = None
              ) -> MeetingNewView:
    """Het aanmaakscherm, met uur en locatie van de vorige vergadering voorgesteld."""
    previous = previous_meeting(db, date.today() + timedelta(days=365))
    return MeetingNewView(
        suggested_date="",
        suggested_time=(previous.start_time.strftime("%H:%M")
                        if previous is not None and previous.start_time else ""),
        suggested_location=(previous.location or "") if previous is not None else "",
        csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


@router.get("/admin/vergaderingen", response_class=HTMLResponse)
def meeting_list(request: Request, db: Session = Depends(get_db),
                 _email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_vergaderingen.html",
                                      _list_view(request, db).as_context())


@router.get("/admin/vergaderingen/nieuw", response_class=HTMLResponse)
def meeting_new(request: Request, db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui)):
    """Aanmaken op een eigen scherm en niet in een modal (#627, §2.8)."""
    return templates.TemplateResponse(
        request, "admin_vergadering_nieuw.html",
        _new_view(request, db).as_context())


@router.post("/admin/vergaderingen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def meeting_create(request: Request, db: Session = Depends(get_db),
                   _email: str = Depends(require_admin_ui),
                   meeting_date: str = Form(...), start_time: str = Form(""),
                   location: str = Form("")):
    """Create a meeting — its agenda is generated in the same breath (§3.1)."""
    try:
        day = date.fromisoformat(meeting_date)
    except ValueError:
        return templates.TemplateResponse(
            request, "admin_vergadering_nieuw.html",
            _new_view(request, db,
                      error=_("Vul een geldige datum in.")).as_context())
    moment = None
    if start_time:
        try:
            moment = time.fromisoformat(start_time)
        except ValueError:
            moment = None
    meeting = create_meeting(db, meeting_date=day, start_time=moment,
                             location=location.strip() or None)
    doel = f"/admin/vergaderingen/{meeting.id}"
    # De schil draagt hx-boost, dus dit formulier vertrekt als htmx-verzoek. Een
    # 303 laat htmx het antwoord inswappen zonder dat het adres in de balk
    # meeverhuist; `HX-Redirect` laat de browser écht navigeren, zodat de
    # gebruiker op het document staat en een verversing daar blijft. Zonder boost
    # (of vanuit een script) blijft de gewone redirect het juiste antwoord.
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": doel})
    return RedirectResponse(doel, status_code=303)


# ── The circle ───────────────────────────────────────────────────────────────
# Declared before `/{meeting_id}`: FastAPI matches in declaration order, and
# "kring" would otherwise be parsed as a meeting id.

def _circle_view(request: Request, db: Session, query: str = "",
                 error: Optional[str] = None) -> MeetingCircleView:
    from app.domains.mdm.api import list_persons, organization_circle

    circle = organization_circle(db)
    in_circle = {entry.person.id for entry in circle}
    candidates = []
    needle = query.strip().lower()
    if needle:
        # Filtered here and not in mdm: `list_persons` answers "all people of this
        # tenant" and is used by two other screens. A search argument would be a
        # second contract on it for one caller.
        for person in list_persons(db):
            if person.id in in_circle:
                continue
            haystack = f"{person.first_name} {person.last_name}".lower()
            if needle in haystack:
                candidates.append(person)
            if len(candidates) >= 15:
                break
    return MeetingCircleView(circle=circle, candidates=candidates, query=query,
                             csrf_token=_csrf(request), error=error,
                             nav_items=admin_nav(NAV))


@router.get("/admin/vergaderingen/kring", response_class=HTMLResponse)
def circle_screen(request: Request, db: Session = Depends(get_db),
                  _email: str = Depends(require_admin_ui), q: str = ""):
    view = _circle_view(request, db, query=q)
    template = "_vg_kring.html" if request.headers.get("HX-Request") and q else \
        "admin_vergaderkring.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.post("/admin/vergaderingen/kring", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def circle_add(request: Request, db: Session = Depends(get_db),
               _email: str = Depends(require_admin_ui), person_id: int = Form(...)):
    from app.domains.mdm.api import add_to_circle, platform_org

    organization = platform_org(db)
    if organization is None:
        return templates.TemplateResponse(
            request, "_vg_kring.html",
            _circle_view(request, db,
                         error=_("Er is nog geen organisatie ingesteld.")).as_context())
    add_to_circle(db, person_id, organization_id=organization.id)
    return templates.TemplateResponse(request, "_vg_kring.html",
                                      _circle_view(request, db).as_context())


@router.post("/admin/vergaderingen/kring/{relation_id}/beeindigen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def circle_end(relation_id: int, request: Request, db: Session = Depends(get_db),
               _email: str = Depends(require_admin_ui)):
    from app.domains.mdm.api import end_circle_relation

    end_circle_relation(db, relation_id)
    return templates.TemplateResponse(request, "_vg_kring.html",
                                      _circle_view(request, db).as_context())


# ── The document ─────────────────────────────────────────────────────────────

def _document_view(request: Request, db: Session, meeting,
                   picker_section_id: Optional[int] = None,
                   picker_query: str = "",
                   error: Optional[str] = None) -> MeetingDocumentView:
    from app.domains.mdm.api import organization_circle

    picker_options = []
    if picker_section_id is not None:
        picker_options = addable_activities(db, meeting, picker_query)
    return MeetingDocumentView(
        meeting=meeting, title=_title(meeting),
        status_label=_(STATUS_LABELS.get(meeting.status, meeting.status)),
        status_tone=STATUS_TONES.get(meeting.status, "gray"),
        sections=document_of(db, meeting),
        circle=organization_circle(db, on_day=meeting.meeting_date),
        attendance=attendance_of(db, meeting),
        standing=member_standing(db),
        picker_section_id=picker_section_id, picker_options=picker_options,
        picker_query=picker_query,
        attachments=files_of(db, meeting),
        sent_pdfs=files_of(db, meeting, purpose=FILE_SENT_PDF),
        editable=meeting.status != STATUS_SENT,
        csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


def _document_response(request: Request, db: Session, meeting, **kwargs):
    """Every write re-renders the document fragment — one swap, one truth."""
    return templates.TemplateResponse(
        request, "_vg_document.html",
        _document_view(request, db, meeting, **kwargs).as_context())


@router.get("/admin/vergaderingen/{meeting_id}", response_class=HTMLResponse)
def meeting_document(meeting_id: int, request: Request, db: Session = Depends(get_db),
                     _email: str = Depends(require_admin_ui)):
    meeting = _meeting_or_404(db, meeting_id)
    return templates.TemplateResponse(
        request, "admin_vergadering.html",
        _document_view(request, db, meeting).as_context())


@router.get("/admin/vergaderingen/{meeting_id}/kiezer", response_class=HTMLResponse)
def item_picker(meeting_id: int, request: Request, db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui),
                section_id: int = 0, q: str = ""):
    """Open the picker over the activities this agenda does not carry yet."""
    meeting = _meeting_or_404(db, meeting_id)
    return _document_response(request, db, meeting,
                              picker_section_id=section_id or None, picker_query=q)


@router.post("/admin/vergaderingen/{meeting_id}/punt", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def item_add(meeting_id: int, request: Request, db: Session = Depends(get_db),
             _email: str = Depends(require_admin_ui), section_id: int = Form(...),
             activity_id: str = Form(""), title: str = Form("")):
    meeting = _meeting_or_404(db, meeting_id)
    section = next((s for s in sections_of(db, meeting) if s.id == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail=_("Sectie niet gevonden."))
    try:
        add_item(db, meeting, section,
                 activity_id=int(activity_id) if activity_id else None,
                 title=title.strip() or None)
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.post("/admin/vergaderingen/{meeting_id}/punt/{item_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def item_update(meeting_id: int, item_id: int, request: Request,
                db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui), notes: str = Form(None),
                title: str = Form(None), steward_person_id: str = Form(None)):
    meeting = _meeting_or_404(db, meeting_id)
    try:
        update_item(db, meeting, item_id, notes=notes, title=title,
                    steward_person_id=(int(steward_person_id)
                                       if steward_person_id else None))
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.post("/admin/vergaderingen/{meeting_id}/punt/{item_id}/verwijder",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def item_delete(meeting_id: int, item_id: int, request: Request,
                db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui)):
    meeting = _meeting_or_404(db, meeting_id)
    try:
        delete_item(db, meeting, item_id)
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.post("/admin/vergaderingen/{meeting_id}/sectie", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def section_add(meeting_id: int, request: Request, db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui), title: str = Form("")):
    """A named block for a big topic — always before Varia, which stays last."""
    meeting = _meeting_or_404(db, meeting_id)
    try:
        add_section(db, meeting, title)
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.post("/admin/vergaderingen/{meeting_id}/aanwezigheid",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def attendance_toggle(meeting_id: int, request: Request, db: Session = Depends(get_db),
                      _email: str = Depends(require_admin_ui),
                      person_id: int = Form(...), current: str = Form("")):
    meeting = _meeting_or_404(db, meeting_id)
    nxt = NEXT_ATTENDANCE.get(current or None, ATTENDANCE_PRESENT)
    try:
        set_attendance(db, meeting, person_id, nxt or None)
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.post("/admin/vergaderingen/{meeting_id}/heropen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def meeting_reopen(meeting_id: int, request: Request, db: Session = Depends(get_db),
                   _email: str = Depends(require_admin_ui)):
    """Reopen a sent report for the correction that comes the day after (§3.23)."""
    meeting = _meeting_or_404(db, meeting_id)
    reopen(db, meeting)
    return _document_response(request, db, meeting)


# ── Files ────────────────────────────────────────────────────────────────────

@router.post("/admin/vergaderingen/{meeting_id}/bijlage", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def attachment_add(meeting_id: int, request: Request,
                         db: Session = Depends(get_db),
                         _email: str = Depends(require_admin_ui),
                         file: UploadFile = File(...)):
    meeting = _meeting_or_404(db, meeting_id)
    data = await file.read()
    try:
        add_file(db, meeting, filename=file.filename or "bijlage",
                 content_type=file.content_type or "application/octet-stream",
                 data=data)
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.post("/admin/vergaderingen/{meeting_id}/bijlage/{file_id}/verwijder",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def attachment_delete(meeting_id: int, file_id: int, request: Request,
                      db: Session = Depends(get_db),
                      _email: str = Depends(require_admin_ui)):
    meeting = _meeting_or_404(db, meeting_id)
    try:
        delete_file(db, meeting, file_id)
    except MeetingError as exc:
        return _document_response(request, db, meeting, error=str(exc))
    return _document_response(request, db, meeting)


@router.get("/admin/vergaderingen/{meeting_id}/bestand/{file_id}")
def file_download(meeting_id: int, file_id: int, db: Session = Depends(get_db),
                  _email: str = Depends(require_admin_ui)):
    """Download an attachment or an archived PDF — admin session required.

    This is the whole reason meeting files are not media assets: media serves
    publicly by design, so a board document there would depend forever on a flag
    being set at every upload. Here there is no public path to forget (§4).
    """
    record = get_file(db, meeting_id, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=_("Bestand niet gevonden."))
    return Response(content=record.data, media_type=record.content_type,
                    headers={"Content-Disposition":
                             f'attachment; filename="{record.filename}"'})


# ── The PDF ──────────────────────────────────────────────────────────────────

def _pdf_context(db: Session, meeting, *, kind: str) -> dict:
    """Everything the PDF template needs — the same structure the screen shows."""
    from app.domains.mdm.api import organization_circle

    ticked = attendance_of(db, meeting)
    present, excused = [], []
    for entry in organization_circle(db, on_day=meeting.meeting_date):
        name = f"{entry.person.first_name} {entry.person.last_name}".strip()
        if ticked.get(entry.person.id) == ATTENDANCE_PRESENT:
            present.append(name)
        elif ticked.get(entry.person.id) == ATTENDANCE_EXCUSED:
            excused.append(name)
    return {"meeting": meeting, "kind": kind,
            "kind_label": _("Agenda") if kind == "agenda" else _("Verslag"),
            "date_label": long_date(meeting.meeting_date),
            "sections": document_of(db, meeting),
            "present": present, "excused": excused,
            "location": meeting.location or "",
            "standing": member_standing(db)}


@router.get("/admin/vergaderingen/{meeting_id}/pdf")
def meeting_pdf(meeting_id: int, db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui), kind: str = "verslag"):
    """Download the PDF as the circle will receive it (§3.16).

    The control step is a download and not a preview pane: the secretary checks
    the real artefact, and sending regenerates it — so what was checked is what
    goes out.
    """
    meeting = _meeting_or_404(db, meeting_id)
    internal = "agenda" if kind == "agenda" else "report"
    pdf = render(context=_pdf_context(db, meeting, kind=internal))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{filename_for(meeting, kind=internal)}"'})


# ── Sending ──────────────────────────────────────────────────────────────────

def _default_subject(meeting, kind: str) -> str:
    """The subject the board already uses, so the thread stays recognisable."""
    stem = _("RAAK vergadering %s") % long_date(meeting.meeting_date)
    if meeting.location:
        stem = f"{stem} {meeting.location}"
    return stem if kind == "agenda" else f"Re: {stem} — {_('verslag')}"


def _default_body(meeting, kind: str) -> str:
    if kind == "agenda":
        return _("Hallo allemaal,\n\nIn bijlage de agenda van onze vergadering "
                 "van %s.\n\nAllen warm uitgenodigd!") % long_date(meeting.meeting_date)
    return _("Hoi allemaal,\n\nIn bijlage het verslag van onze vergadering "
             "van %s.") % long_date(meeting.meeting_date)


def _send_view(request: Request, db: Session, meeting, kind: str, email: str,
               subject: str = "", body: str = "",
               error: Optional[str] = None) -> MeetingSendView:
    internal = "agenda" if kind == "agenda" else "report"
    return MeetingSendView(
        meeting=meeting, kind=internal,
        kind_label=_("agenda") if internal == "agenda" else _("verslag"),
        subject=subject or _default_subject(meeting, internal),
        body=body or _default_body(meeting, internal),
        recipients=recipients_for(db, meeting),
        extra_recipients=list(meeting.extra_recipients),
        attachments=[f for f in files_of(db, meeting)
                     if (f.on_agenda_mail if internal == "agenda" else f.on_report_mail)],
        pdf_filename=filename_for(meeting, kind=internal),
        reply_to=email,
        already_sent_at=(meeting.agenda_sent_at if internal == "agenda"
                         else meeting.report_sent_at),
        csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


@router.get("/admin/vergaderingen/{meeting_id}/verstuur", response_class=HTMLResponse)
def send_screen(meeting_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui), kind: str = "verslag"):
    meeting = _meeting_or_404(db, meeting_id)
    return templates.TemplateResponse(
        request, "admin_vergadering_verstuur.html",
        _send_view(request, db, meeting, kind, email).as_context())


@router.post("/admin/vergaderingen/{meeting_id}/ontvanger", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def recipient_add(meeting_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui), kind: str = Form("verslag"),
                  extra_email: str = Form("")):
    """A one-off address for this meeting only — the guest speaker case (§3.15)."""
    meeting = _meeting_or_404(db, meeting_id)
    error = None
    try:
        add_extra_recipient(db, meeting, extra_email)
    except MeetingError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request, "_vg_verstuur.html",
        _send_view(request, db, meeting, kind, email, error=error).as_context())


@router.post("/admin/vergaderingen/{meeting_id}/ontvanger/{recipient_id}/verwijder",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def recipient_remove(meeting_id: int, recipient_id: int, request: Request,
                     db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui),
                     kind: str = Form("verslag")):
    meeting = _meeting_or_404(db, meeting_id)
    remove_extra_recipient(db, meeting, recipient_id)
    return templates.TemplateResponse(
        request, "_vg_verstuur.html",
        _send_view(request, db, meeting, kind, email).as_context())


@router.post("/admin/vergaderingen/{meeting_id}/verstuur", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def send_mail(meeting_id: int, request: Request, db: Session = Depends(get_db),
              email: str = Depends(require_admin_ui), kind: str = Form("verslag"),
              subject: str = Form(""), body: str = Form("")):
    """Send, after a human has read it (§3.12) — never automatically.

    The PDF is regenerated here and archived as it goes out, in the same
    transaction that stamps the sent moment: what was sent and the fact that it
    was sent can never disagree.
    """
    meeting = _meeting_or_404(db, meeting_id)
    internal = "agenda" if kind == "agenda" else "report"
    try:
        pdf = render(context=_pdf_context(db, meeting, kind=internal))
        send_meeting_mail(db, meeting, kind=internal, subject=subject.strip(),
                          body_html=_as_html(body), reply_to=email, pdf=pdf,
                          pdf_filename=filename_for(meeting, kind=internal))
    except MeetingError as exc:
        return templates.TemplateResponse(
            request, "_vg_verstuur.html",
            _send_view(request, db, meeting, kind, email, subject=subject,
                       body=body, error=str(exc)).as_context())
    except Exception:
        logger.exception("Vergadermail versturen mislukt (meeting %s)", meeting_id)
        return templates.TemplateResponse(
            request, "_vg_verstuur.html",
            _send_view(request, db, meeting, kind, email, subject=subject, body=body,
                       error=_("Versturen mislukt. Kijk de e-maillog na.")).as_context())
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/vergaderingen/{meeting.id}"})


def _as_html(body: str) -> str:
    """The typed message as HTML, escaped, with the line breaks kept.

    Escaping here and not in the template: this text goes into a mail, which no
    Jinja autoescape ever sees.
    """
    from html import escape

    return "<br>".join(escape(line) for line in (body or "").splitlines())
