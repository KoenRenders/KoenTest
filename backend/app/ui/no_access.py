"""The calm "no access" page (#1583; design-system-end-state §3.18).

A signed-in user who opens an admin screen their role may not see got a bare
JSON body, `{"detail": "Je hebt geen toegang tot deze actie."}`. One handler (`app.main`) hands every
403 to `no_access_page`, which answers with a page **only** for a browser
navigation to a server-rendered admin screen:

- a `GET` that asks for HTML, of a path under `/admin`, without `HX-Request`;
- by someone who is signed in (a visitor without a session is sent to the
  sign-in screen before it comes to a 403, #1458).

Everything else keeps its answer: `/api/v1/…` its JSON, an htmx request the
status its page shows in place, a `POST` its refusal. The status stays 403.

The way back points to a place this user may see. The norm says "Terug naar
<lijst>", but who may not see a record may not see its module's list either;
so the button goes to the page their role enters the back office by
(`auth.back_office_home`: the workbench, for everyone with a back-office role) and, for
whoever has no page there, to where the site lands them (`auth.landing_for`) —
one rule each, no copy of either here.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from app.i18n import _
from app.ui import nav_for, site_context, templates


def _is_admin_navigation(request: Request) -> bool:
    if request.method != HTTPMethod.GET or request.headers.get("HX-Request"):
        return False
    if "text/html" not in request.headers.get("accept", ""):
        return False
    path = request.url.path
    return path == "/admin" or path.startswith("/admin/")


def no_access_page(request: Request) -> Response | None:
    """The page for this refused request, or None when the request keeps the
    plain 403 (an API call, a fragment, a write, a visitor without a session)."""
    if not _is_admin_navigation(request):
        return None
    from app.database import get_db
    from app.domains.auth.api import (
        SESSION_COOKIE,
        back_office_home,
        csrf_from_request,
        landing_for,
        read_session_value,
        rights_of,
    )

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if email is None:
        return None
    # The session the app's own routes get (`get_db`, or what stands in for it):
    # a handler runs outside the dependency system, so it asks for it itself.
    session = request.app.dependency_overrides.get(get_db, get_db)()
    db = next(session)
    try:
        home = back_office_home(db, email)
        in_admin = home is not None and home != request.url.path
        if in_admin:
            label = _("Naar de werkbank")
            target = home
        else:
            label, target = _("Naar de website"), landing_for(db, email)
        context: dict[str, Any] = {"way_out": {"href": target, "label": label}}
        if in_admin:
            # The user's own navigation: only what his rights open. No gate let
            # this request in, so the menu is asked for his rights directly.
            context["nav_items"] = nav_for("", rights_of(db, email))
            context["csrf_token"] = csrf_from_request(request)
            template = "no_access.html"
        else:
            context.update(site_context(db, request))
            template = "no_access_site.html"
        return templates.TemplateResponse(request, template, context, status_code=403)
    finally:
        session.close()
