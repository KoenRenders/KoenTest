"""Tenant-provisioning (#546 fase 3) — OPERATOR-only.

Een nieuwe tenant = een UNIT-``Organization`` onder een account, met basis-settings.
Na het aanmaken wordt de tenant_codes-cache gewist (``invalidate_tenant_codes``)
zodat de nieuwe tenant meteen resolvet (pad-prefix ``/<code>/…`` of, na het zetten
van een hostname-mapping in de settings, via de hostnaam). Composer-module: schrijft
via de mdm-/kernel-facades.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    csrf_from_request, get_user_roles, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)


def _require_operator(db: Session, email: str) -> None:
    if "OPERATOR" not in get_user_roles(db, email):
        raise HTTPException(status_code=403,
                            detail=_("Alleen de platformbeheerder (OPERATOR) mag tenants aanmaken."))


def _ctx(request: Request, db: Session) -> dict:
    from app.domains.mdm.api import Organization

    units = (db.query(Organization).filter(Organization.org_type == "UNIT")
             .order_by(Organization.id).all())
    accounts = (db.query(Organization).filter(Organization.org_type == "ACCOUNT")
                .order_by(Organization.id).all())
    return {"nav_items": admin_nav("/admin/tenants"), "units": units,
            "accounts": accounts, "error": None, "opgeslagen": False,
            "csrf_token": csrf_from_request(request)}


@router.get("/admin/tenants", response_class=HTMLResponse)
def tenants(request: Request, db: Session = Depends(get_db),
            email: str = Depends(require_admin_ui)):
    _require_operator(db, email)
    return templates.TemplateResponse(request, "admin_tenants.html", _ctx(request, db))


@router.post("/admin/tenants", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def tenant_aanmaken(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    name: str = Form(""), code: str = Form(""),
                    account_id: str = Form(""), base_url: str = Form("")):
    from app.domains.mdm.api import Organization, invalidate_tenant_codes
    from app.kernel.tenant_config import set_setting

    _require_operator(db, email)
    name, code = name.strip(), code.strip().lower()
    ctx = _ctx(request, db)
    if not name or not re.fullmatch(r"[a-z0-9-]+", code or ""):
        ctx["error"] = _("Naam én een geldige code (kleine letters, cijfers, streepjes) zijn verplicht.")
        return templates.TemplateResponse(request, "admin_tenants.html", ctx)
    if db.query(Organization).filter(Organization.code == code).first():
        ctx["error"] = _("Die code bestaat al.")
        return templates.TemplateResponse(request, "admin_tenants.html", ctx)

    parent = int(account_id) if account_id.isdigit() else None
    org = Organization(org_type="UNIT", code=code, name=name,
                       parent_id=parent, is_active=True)
    db.add(org)
    db.flush()
    # Basis-settings voor de nieuwe tenant (de rest zet de OPERATOR via Instellingen).
    set_setting(db, "display_name", name, tenant_id=org.id)
    if base_url.strip():
        set_setting(db, "base_url", base_url.strip(), tenant_id=org.id)
    db.commit()
    # Cache wissen zodat de nieuwe tenant meteen resolvet (#546).
    invalidate_tenant_codes()

    ctx = _ctx(request, db)
    ctx["opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_tenants.html", ctx)
