"""The newsletter screens (CR-05, #984): letters, sending, subscribers.

Behind `require_admin_ui`, like every admin screen. The paths are Dutch because
a board member reads them in the address bar; everything else is English.

A draft and a sent letter share one address, `/admin/nieuwsbrieven/{id}`: a
draft opens the composer, a letter that is (being) sent opens its archive. The
status decides, so a bookmark never leads to an editor for something that
already left.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.domains.newsletter import api as nb
from app.domains.newsletter.viewmodels import (
    NewsletterArchiveView,
    NewsletterComposeView,
    NewsletterListView,
    NewsletterPickerView,
    NewsletterSendView,
    NewsletterSettingsView,
    SubscriberImportView,
    SubscriberListView,
)
from app.i18n import _
from app.ui import admin_nav, is_fragment_request, templates

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

NAV = "/admin/nieuwsbrieven"
# The import file stays small: one address per line, about 800 of them. A
# megabyte is a hundred times that, and still refuses a file picked by mistake.
MAX_IMPORT_BYTES = 1_000_000

LETTER_STATUS_LABELS = {nb.LETTER_DRAFT: "Concept", nb.LETTER_SENDING: "Wordt verstuurd",
                        nb.LETTER_SENT: "Verstuurd"}
LETTER_STATUS_TONES = {nb.LETTER_DRAFT: "gray", nb.LETTER_SENDING: "blue", nb.LETTER_SENT: "green"}
AUDIENCE_LABELS = {nb.AUDIENCE_MEMBERS: "Leden", nb.AUDIENCE_NON_MEMBERS: "Niet-leden",
                   nb.AUDIENCE_BOTH: "Allebei"}
DELIVERY_LABELS = {nb.DELIVERY_QUEUED: "In de wachtrij", nb.DELIVERY_SENT: "Verstuurd",
                   nb.DELIVERY_FAILED: "Mislukt", nb.DELIVERY_SKIPPED: "Overgeslagen"}
DELIVERY_TONES = {nb.DELIVERY_QUEUED: "gray", nb.DELIVERY_SENT: "green",
                  nb.DELIVERY_FAILED: "yellow", nb.DELIVERY_SKIPPED: "gray"}
SUBSCRIBER_LABELS = {nb.SUBSCRIBER_CONFIRMED: "Bevestigd",
                     nb.SUBSCRIBER_PENDING: "Wacht op bevestiging",
                     nb.SUBSCRIBER_UNSUBSCRIBED: "Uitgeschreven"}
SUBSCRIBER_TONES = {nb.SUBSCRIBER_CONFIRMED: "green", nb.SUBSCRIBER_PENDING: "yellow",
                    nb.SUBSCRIBER_UNSUBSCRIBED: "gray"}
SOURCE_LABELS = {nb.SOURCE_PUBLIC_FORM: "formulier", nb.SOURCE_IMPORT: "import",
                 nb.SOURCE_ADMIN: "beheer"}


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _base_url(db: Session) -> str:
    from app.kernel.tenant_config import tenant_base_url

    return tenant_base_url(db).rstrip("/")


def _moment(value: Optional[datetime]) -> str:
    """A moment as a board member reads it: 'di 15 sep, 18:00' in Belgian time."""
    if value is None:
        return ""
    from zoneinfo import ZoneInfo

    local = value.astimezone(ZoneInfo("Europe/Brussels"))
    return f"{nb.short_date(local.date())}, {local.strftime('%H:%M')}"


def _go(request: Request, target: str) -> Response:
    """Navigate for real after a POST — the shell is boosted, so a plain 303
    would be swapped in without the address bar following."""
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


def _letter_or_404(db: Session, newsletter_id: int):
    letter = nb.get_newsletter(db, newsletter_id)
    if letter is None:
        raise HTTPException(status_code=404, detail=_("Nieuwsbrief niet gevonden."))
    return letter


def _raakje_enabled(db: Session) -> bool:
    from app.kernel.tenant_config import tenant_admin_chat_enabled

    return tenant_admin_chat_enabled(db)


# ── The list ─────────────────────────────────────────────────────────────────

def _list_view(request: Request, db: Session, q: str = "",
               error: Optional[str] = None) -> NewsletterListView:
    letters = nb.list_newsletters(db, query=q)
    progress = {letter.id: nb.progress_of(db, letter) for letter in letters
                if letter.status != nb.LETTER_DRAFT}
    moments = {}
    for letter in letters:
        if letter.status == nb.LETTER_DRAFT:
            moments[letter.id] = _("laatst bewaard %(m)s") % {"m": _moment(letter.updated_at)}
        elif letter.status == nb.LETTER_SENDING:
            moments[letter.id] = _("gestart %(m)s") % {"m": _moment(letter.send_started_at)}
        else:
            moments[letter.id] = _("verstuurd %(m)s") % {"m": _moment(letter.send_finished_at)}
    return NewsletterListView(
        letters=letters, q=q,
        status_labels={l.id: _(LETTER_STATUS_LABELS[l.status]) for l in letters},
        status_tones={l.id: LETTER_STATUS_TONES[l.status] for l in letters},
        audience_labels={l.id: (_(AUDIENCE_LABELS[l.audience]) if l.audience
                                else _("nog niet gekozen")) for l in letters},
        progress=progress, moments=moments,
        csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


@router.get("/admin/nieuwsbrieven", response_class=HTMLResponse)
def newsletter_list(request: Request, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui), q: str = ""):
    view = _list_view(request, db, q=q)
    template = "_nb_lijst.html" if is_fragment_request(request) else "admin_nieuwsbrieven.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.post("/admin/nieuwsbrieven", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def newsletter_create(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    """A new, empty draft — the composer is its own full page (no modal)."""
    letter = nb.create_newsletter(db, created_by=email)
    return _go(request, f"/admin/nieuwsbrieven/{letter.id}")


# ── Subscribers ──────────────────────────────────────────────────────────────
# Declared before `/{newsletter_id}`; the id also carries an `:int` converter,
# so "abonnees" can never be read as a letter.

def _subscriber_view(request: Request, db: Session, q: str = "", status: str = "",
                     error: Optional[str] = None,
                     notice: Optional[str] = None) -> SubscriberListView:
    rows = nb.list_subscribers(db, query=q, status=status)
    return SubscriberListView(
        subscribers=rows, counts=nb.subscriber_counts(db),
        status_labels={k: _(v) for k, v in SUBSCRIBER_LABELS.items()},
        status_tones=SUBSCRIBER_TONES,
        source_labels={s.id: (_("import %(d)s") % {"d": nb.short_date(s.imported_at.date())}
                              if s.source == nb.SOURCE_IMPORT and s.imported_at
                              else _(SOURCE_LABELS.get(s.source, s.source)))
                       for s in rows},
        moments={s.id: _moment(s.confirmed_at or s.created_at) for s in rows},
        q=q, status=status, csrf_token=_csrf(request), error=error, notice=notice,
        nav_items=admin_nav(NAV))


@router.get("/admin/nieuwsbrieven/abonnees", response_class=HTMLResponse)
def subscriber_list(request: Request, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui), q: str = "",
                    status: str = ""):
    view = _subscriber_view(request, db, q=q, status=status)
    template = "_nb_abonnees.html" if is_fragment_request(request) else "admin_abonnees.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.post("/admin/nieuwsbrieven/abonnees", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def subscriber_add(request: Request, db: Session = Depends(get_db),
                   _email: str = Depends(require_admin_ui),
                   subscriber_email: str = Form(""), first_name: str = Form("")):
    try:
        row = nb.add_by_admin(db, subscriber_email, first_name)
        view = _subscriber_view(request, db, notice=_("%(adres)s staat op de lijst.")
                                % {"adres": row.email})
    except nb.NewsletterError as exc:
        view = _subscriber_view(request, db, error=str(exc))
    return templates.TemplateResponse(request, "_nb_abonnees.html", view.as_context())


@router.post("/admin/nieuwsbrieven/abonnees/{subscriber_id:int}/uitschrijven",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def subscriber_unsubscribe(subscriber_id: int, request: Request,
                           db: Session = Depends(get_db),
                           _email: str = Depends(require_admin_ui)):
    nb.unsubscribe_by_admin(db, subscriber_id)
    return templates.TemplateResponse(request, "_nb_abonnees.html",
                                      _subscriber_view(request, db).as_context())


@router.post("/admin/nieuwsbrieven/abonnees/{subscriber_id:int}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def subscriber_erase(subscriber_id: int, request: Request,
                     db: Session = Depends(get_db),
                     _email: str = Depends(require_admin_ui)):
    """The right to erasure: the address disappears, also from the archive."""
    nb.erase(db, subscriber_id)
    return templates.TemplateResponse(request, "_nb_abonnees.html",
                                      _subscriber_view(request, db).as_context())


def _import_view(request: Request, preview=None, text: str = "",
                 error: Optional[str] = None) -> SubscriberImportView:
    return SubscriberImportView(preview=preview, text=text, csrf_token=_csrf(request),
                                error=error, nav_items=admin_nav(NAV))


@router.get("/admin/nieuwsbrieven/abonnees/import", response_class=HTMLResponse)
def subscriber_import_screen(request: Request, _email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_abonnees_import.html",
                                      _import_view(request).as_context())


@router.post("/admin/nieuwsbrieven/abonnees/import", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def subscriber_import_preview(request: Request, db: Session = Depends(get_db),
                                    _email: str = Depends(require_admin_ui),
                                    file: UploadFile = File(...)):
    """Step 1 → 2: read the file and show what would happen. Nothing is written."""
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        return templates.TemplateResponse(
            request, "_nb_import.html",
            _import_view(request, error=_("Dit bestand is te groot voor een adressenlijst."))
            .as_context())
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    preview = nb.preview_import(db, text)
    return templates.TemplateResponse(request, "_nb_import.html",
                                      _import_view(request, preview=preview,
                                                   text=text).as_context())


@router.post("/admin/nieuwsbrieven/abonnees/import/bevestigen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def subscriber_import_run(request: Request, db: Session = Depends(get_db),
                          _email: str = Depends(require_admin_ui),
                          text: str = Form("")):
    """Step 2 → done. The rules are applied again to the text, not to the
    numbers the preview showed: what is written is what is allowed now."""
    result = nb.run_import(db, text)
    view = _subscriber_view(request, db, notice=_(
        "%(n)s adressen toegevoegd. Gekende en uitgeschreven adressen bleven ongewijzigd.")
        % {"n": len(result.new)})
    if request.headers.get("HX-Request"):
        return Response(status_code=204,
                        headers={"HX-Redirect": "/admin/nieuwsbrieven/abonnees"})
    return templates.TemplateResponse(request, "admin_abonnees.html", view.as_context())


# ── Settings ─────────────────────────────────────────────────────────────────

def _settings_view(request: Request, db: Session, notice: Optional[str] = None,
                   error: Optional[str] = None) -> NewsletterSettingsView:
    from app.kernel.tenant_config import (
        NEWSLETTER_DAILY_CAP_DEFAULT, tenant_newsletter_daily_cap,
        tenant_newsletter_house_style)

    return NewsletterSettingsView(
        house_style=tenant_newsletter_house_style(db),
        daily_cap=tenant_newsletter_daily_cap(db),
        daily_cap_default=NEWSLETTER_DAILY_CAP_DEFAULT,
        csrf_token=_csrf(request), notice=notice, error=error, nav_items=admin_nav(NAV))


@router.get("/admin/nieuwsbrieven/instellingen", response_class=HTMLResponse)
def settings_screen(request: Request, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_nieuwsbrief_instellingen.html",
                                      _settings_view(request, db).as_context())


@router.post("/admin/nieuwsbrieven/instellingen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def settings_save(request: Request, db: Session = Depends(get_db),
                  _email: str = Depends(require_admin_ui),
                  house_style: str = Form(""), daily_cap: str = Form("")):
    try:
        cap = int(daily_cap) if daily_cap.strip() else None
    except ValueError:
        cap = 0
    try:
        nb.save_settings(db, house_style=house_style, daily_cap=cap)
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request, "_nb_instellingen.html",
            _settings_view(request, db, error=str(exc)).as_context())
    return templates.TemplateResponse(
        request, "_nb_instellingen.html",
        _settings_view(request, db, notice=_("Bewaard.")).as_context())


# ── One letter ───────────────────────────────────────────────────────────────

def _compose_view(request: Request, db: Session, letter, error: Optional[str] = None,
                  notice: Optional[str] = None, raakje_error: Optional[str] = None,
                  apply_html: str = "", apply_placement: str = "",
                  apply_range: str = "") -> NewsletterComposeView:
    from app.domains.meetings.api import recent_report_points

    counts = nb.audience_counts(db)
    options = [
        (nb.AUDIENCE_MEMBERS, _("Leden"),
         _("%(n)s adressen · iedereen met een adres in een gezin met lidmaatschap %(j)s")
         % {"n": counts.members, "j": datetime.now().year}),
        (nb.AUDIENCE_NON_MEMBERS, _("Niet-leden"),
         _("%(n)s bevestigde adressen · met uitschrijflink") % {"n": counts.non_members}),
        (nb.AUDIENCE_BOTH, _("Allebei"),
         _("%(n)s adressen · %(d)s dubbele samengevoegd")
         % {"n": counts.both, "d": counts.overlap}),
    ]
    raakje = _raakje_enabled(db)
    chosen = []
    points = []
    messages = nb.messages_of(db, letter) if raakje else []
    if raakje:
        facts = nb.activity_facts(db, letter.draft_activity_ids, base_url=_base_url(db))
        chosen = [facts[i] for i in letter.draft_activity_ids if i in facts]
        points = recent_report_points(db)
    return NewsletterComposeView(
        letter=letter, counts=counts, audience_options=options,
        saved_at=_moment(letter.updated_at),
        raakje_enabled=raakje, chosen_activities=chosen, report_points=points,
        ticked_points=list(letter.draft_meeting_item_ids or []),
        messages=messages,
        proposals={m.id: nb.display_proposal(db, letter, m) for m in messages if m.proposal},
        csrf_token=_csrf(request), error=error, notice=notice, raakje_error=raakje_error,
        apply_html=apply_html, apply_placement=apply_placement, apply_range=apply_range,
        nav_items=admin_nav(NAV))


def _archive_view(request: Request, db: Session, letter, status: str = "",
                  q: str = "", error: Optional[str] = None) -> NewsletterArchiveView:
    progress = nb.progress_of(db, letter)
    deliveries = nb.deliveries_of(db, letter, status=status, query=q)
    return NewsletterArchiveView(
        letter=letter,
        status_label=_(LETTER_STATUS_LABELS[letter.status]),
        status_tone=LETTER_STATUS_TONES[letter.status],
        audience_label=_(AUDIENCE_LABELS.get(letter.audience or "", "")),
        progress=progress,
        expected=_moment(progress.expected_finish) if progress.expected_finish else "",
        started=_moment(letter.send_started_at),
        finished=_moment(letter.send_finished_at),
        deliveries=deliveries,
        delivery_labels={k: _(v) for k, v in DELIVERY_LABELS.items()},
        delivery_tones=DELIVERY_TONES,
        moments={d.id: _moment(d.sent_at) for d in deliveries},
        status_filter=status, q=q, csrf_token=_csrf(request), error=error,
        nav_items=admin_nav(NAV))


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}", response_class=HTMLResponse)
def newsletter_screen(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                      _email: str = Depends(require_admin_ui), status: str = "",
                      q: str = ""):
    letter = _letter_or_404(db, newsletter_id)
    if letter.status == nb.LETTER_DRAFT:
        return templates.TemplateResponse(request, "admin_nieuwsbrief.html",
                                          _compose_view(request, db, letter).as_context())
    view = _archive_view(request, db, letter, status=status, q=q)
    template = ("_nb_afleveringen.html" if is_fragment_request(request)
                else "admin_nieuwsbrief_archief.html")
    return templates.TemplateResponse(request, template, view.as_context())


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/bewaren",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def newsletter_save(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui),
                    subject: str = Form(""), body_html: str = Form(""),
                    audience: str = Form("")):
    """Autosave: the status line comes back, nothing else is swapped — the
    editor must never be replaced under the author's fingers."""
    letter = _letter_or_404(db, newsletter_id)
    error = None
    try:
        nb.update_draft(db, letter, subject=subject, body_html=body_html,
                        audience=audience or None)
    except nb.NewsletterError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request, "_nb_bewaard.html",
        _compose_view(request, db, letter, error=error).as_context())


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/activiteiten",
            response_class=HTMLResponse)
def activity_picker(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui), q: str = "",
                    purpose: str = "insert"):
    """The picker: every coming activity. `purpose` says what a click does —
    insert a line in the editor, or give the activity to Raakje."""
    letter = _letter_or_404(db, newsletter_id)
    spans = nb.insertable_activities(db, query=q)
    view = NewsletterPickerView(
        letter=letter, spans=spans, q=q,
        purpose="raakje" if purpose == "raakje" else "insert",
        dates={s.activity.id: nb.short_date(s.start) for s in spans},
        csrf_token=_csrf(request))
    return templates.TemplateResponse(request, "_nb_kiezer.html", view.as_context())


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/invoegen/activiteit/{activity_id:int}",
            response_class=HTMLResponse)
def insert_activity(newsletter_id: int, activity_id: int, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui)):
    """The HTML snippet "Activiteit invoegen" puts at the cursor."""
    _letter_or_404(db, newsletter_id)
    facts = nb.activity_facts(db, [activity_id], base_url=_base_url(db))
    if activity_id not in facts:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden."))
    line = nb.activity_line_html(facts[activity_id])
    return HTMLResponse(f"<div>{line}</div>")


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/invoegen/kalender",
            response_class=HTMLResponse)
def insert_calendar(newsletter_id: int, db: Session = Depends(get_db),
                    _email: str = Depends(require_admin_ui)):
    _letter_or_404(db, newsletter_id)
    return HTMLResponse(nb.calendar_html(db, base_url=_base_url(db)))


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/invoegen/afsluiting",
            response_class=HTMLResponse)
def insert_closing(newsletter_id: int, db: Session = Depends(get_db),
                   _email: str = Depends(require_admin_ui)):
    _letter_or_404(db, newsletter_id)
    return HTMLResponse(nb.closing_html(db))


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/testmail",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def newsletter_test_mail(newsletter_id: int, request: Request,
                         db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui)):
    letter = _letter_or_404(db, newsletter_id)
    try:
        outcome = nb.send_test(db, letter, to_email=email, base_url=_base_url(db))
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request, "_nb_bewaard.html",
            _compose_view(request, db, letter, error=str(exc)).as_context())
    notice = (_("Testmail verstuurd naar %(adres)s.") % {"adres": email}
              if outcome in ("sent", "logged")
              else _("De testmail kon niet vertrekken. Kijk in de e-maillog waarom."))
    return templates.TemplateResponse(
        request, "_nb_bewaard.html",
        _compose_view(request, db, letter, notice=notice).as_context())


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/kopieren",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def newsletter_copy(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    letter = _letter_or_404(db, newsletter_id)
    copy = nb.copy_newsletter(db, letter, created_by=email)
    return _go(request, f"/admin/nieuwsbrieven/{copy.id}")


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def newsletter_delete(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                      _email: str = Depends(require_admin_ui)):
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.delete_draft(db, letter)
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request, "_nb_lijst.html", _list_view(request, db, error=str(exc)).as_context())
    return _go(request, "/admin/nieuwsbrieven")


# ── Sending ──────────────────────────────────────────────────────────────────

def _send_view(request: Request, db: Session, letter, email: str,
               error: Optional[str] = None) -> NewsletterSendView:
    from app.kernel.tenant_config import tenant_newsletter_daily_cap

    count = len(nb.recipients_for(db, letter.audience)) if letter.audience else 0
    return NewsletterSendView(
        letter=letter,
        audience_label=_(AUDIENCE_LABELS.get(letter.audience or "", "")),
        recipient_count=count, days=nb.expected_days(db, count) if count else 0,
        daily_cap=tenant_newsletter_daily_cap(db), reply_to_sender=email,
        csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/versturen",
            response_class=HTMLResponse)
def send_screen(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    letter = _letter_or_404(db, newsletter_id)
    if letter.status != nb.LETTER_DRAFT:
        return RedirectResponse(f"/admin/nieuwsbrieven/{letter.id}", status_code=303)
    error = None
    if not letter.audience:
        error = _("Kies eerst voor wie deze nieuwsbrief is.")
    return templates.TemplateResponse(request, "admin_nieuwsbrief_versturen.html",
                                      _send_view(request, db, letter, email,
                                                 error=error).as_context())


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/versturen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def send_letter(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui),
                reply_to: str = Form(nb.REPLY_TO_ASSOCIATION)):
    """After a human read it (CR-05 §3.9) — never automatically."""
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.start_sending(db, letter, sent_by=email, reply_to_mode=reply_to,
                         base_url=_base_url(db))
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request, "_nb_versturen.html",
            _send_view(request, db, letter, email, error=str(exc)).as_context())
    return _go(request, f"/admin/nieuwsbrieven/{letter.id}")


# ── Raakje ───────────────────────────────────────────────────────────────────
# Every route here answers with the Raakje panel only; the editor is never
# replaced from the server. Off — and 404 — when Raakje in the back office is
# off for this tenant or this environment.

def _raakje_letter(db: Session, newsletter_id: int):
    if not _raakje_enabled(db):
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    return _letter_or_404(db, newsletter_id)


def _panel(request: Request, db: Session, letter, **extra) -> HTMLResponse:
    return templates.TemplateResponse(request, "_nb_raakje.html",
                                      _compose_view(request, db, letter, **extra).as_context())


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/activiteit",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def raakje_add_activity(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                        _email: str = Depends(require_admin_ui),
                        activity_id: int = Form(...)):
    letter = _raakje_letter(db, newsletter_id)
    nb.set_draft_sources(db, letter,
                         activity_ids=[*letter.draft_activity_ids, activity_id],
                         meeting_item_ids=letter.draft_meeting_item_ids)
    return _panel(request, db, letter)


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/activiteit/{activity_id:int}/weg",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def raakje_remove_activity(newsletter_id: int, activity_id: int, request: Request,
                           db: Session = Depends(get_db),
                           _email: str = Depends(require_admin_ui)):
    letter = _raakje_letter(db, newsletter_id)
    nb.set_draft_sources(db, letter,
                         activity_ids=[i for i in letter.draft_activity_ids if i != activity_id],
                         meeting_item_ids=letter.draft_meeting_item_ids)
    return _panel(request, db, letter)


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/punten",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def raakje_points(newsletter_id: int, request: Request, db: Session = Depends(get_db),
                        _email: str = Depends(require_admin_ui)):
    """The ticked meeting points — the input gate (CR-05 §3.11)."""
    letter = _raakje_letter(db, newsletter_id)
    form = await request.form()
    ticked = [int(str(v)) for v in form.getlist("point_id") if str(v).isdigit()]
    nb.set_draft_sources(db, letter, activity_ids=letter.draft_activity_ids,
                         meeting_item_ids=ticked)
    return _panel(request, db, letter)


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/vraag",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def raakje_ask(newsletter_id: int, request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui),
               instruction: str = Form(""), body_html: str = Form(""),
               selection: str = Form(""), selection_range: str = Form(""),
               before_cursor: str = Form("")):
    """One turn with Raakje. The current text is saved first, so the proposal
    works on what the author sees."""
    from app.domains.chatbot.api import ChatTimeout, SeamBlocked, admin_chat_char_budget

    letter = _raakje_letter(db, newsletter_id)
    try:
        nb.update_draft(db, letter, subject=letter.subject, body_html=body_html,
                        audience=letter.audience)
    except nb.NewsletterError as exc:
        return _panel(request, db, letter, raakje_error=str(exc))
    admin_chat_char_budget.charge(request, max(len(instruction), 1), key=email)
    try:
        turn = nb.ask_raakje(db, letter, instruction=instruction, actor=email,
                             base_url=_base_url(db), selection=selection,
                             selection_range=selection_range, before_cursor=before_cursor)
    except (nb.DraftingError, SeamBlocked, ChatTimeout) as exc:
        nb.record_turn(db, letter, author_text=instruction, error=str(exc))
        return _panel(request, db, letter, raakje_error=str(exc))
    except Exception:
        logger.exception("Raakje kon geen nieuwsbriefvoorstel maken (brief %s)", letter.id)
        message = _("Sorry, dat lukte niet. Probeer het opnieuw of zeg het anders.")
        nb.record_turn(db, letter, author_text=instruction, error=message)
        return _panel(request, db, letter, raakje_error=message)
    nb.record_turn(db, letter, author_text=instruction, turn=turn)
    return _panel(request, db, letter)


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/{message_id:int}/toepassen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def raakje_apply(newsletter_id: int, message_id: int, request: Request,
                       db: Session = Depends(get_db),
                       _email: str = Depends(require_admin_ui)):
    """Apply a proposal. A marked sentence stays out unless it was ticked
    "klopt, behouden" (CR-05 §3.16)."""
    letter = _raakje_letter(db, newsletter_id)
    message = nb.get_drafting_message(db, letter, message_id)
    if message is None or not message.proposal:
        raise HTTPException(status_code=404, detail=_("Voorstel niet gevonden."))
    form = await request.form()
    keep = {int(str(v)) for v in form.getlist("keep") if str(v).isdigit()}
    placement = str(form.get("placement") or "replace")
    try:
        applied = nb.apply_proposal(db, letter, message, keep=keep,
                                    body_html=str(form.get("body_html") or ""),
                                    base_url=_base_url(db), placement=placement)
    except nb.DraftingError as exc:
        return _panel(request, db, letter, raakje_error=str(exc))
    return _panel(request, db, letter, apply_html=applied.html,
                  apply_placement=applied.placement,
                  apply_range=",".join(str(n) for n in applied.range or []))


@router.post("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/{message_id:int}/weigeren",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def raakje_dismiss(newsletter_id: int, message_id: int, request: Request,
                   db: Session = Depends(get_db),
                   _email: str = Depends(require_admin_ui)):
    letter = _raakje_letter(db, newsletter_id)
    message = nb.get_drafting_message(db, letter, message_id)
    if message is not None:
        nb.dismiss_proposal(db, message)
    return _panel(request, db, letter)
