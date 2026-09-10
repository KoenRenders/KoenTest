"""The reporting domain's screens — phase 1 has only downloads (#832).

No screen and no menu item yet: that is phase 2 (#833). What phase 1 does ship is
one download route per fact, so the datasets are usable in LibreOffice Calc before
the panel exists.

The path is Dutch because a board member reads it in the address bar and gets it
in a link; the route function, the module and the fact keys are English like all
new code (CLAUDE.md, "URL paths follow the audience").
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import require_admin_ui
from app.domains.reporting.api import (
    SelectionError,
    build_dataset_ods,
    dataset_filename,
)
from app.kernel.tenancy import current_tenant_id, DEFAULT_TENANT_ID

router = APIRouter(include_in_schema=False)

ODS_MEDIA_TYPE = "application/vnd.oasis.opendocument.spreadsheet"


def _tenant(request: Request) -> int:
    """The tenant this request belongs to.

    Read from the context variable the resolution middleware sets, not from
    anything the caller sent: a tenant a user could name is a tenant a user could
    change.
    """
    return current_tenant_id.get() or DEFAULT_TENANT_ID


@router.get("/admin/rapporten/dataset/{fact_key}.ods",
            dependencies=[Depends(require_admin_ui)])
def dataset_export(fact_key: str, request: Request,
                   db: Session = Depends(get_db)):
    """One fact, flat, as a spreadsheet.

    The door is `require_admin_ui` — ADMIN or OPERATOR, the same door as every
    other admin screen. v2.3.0 adds no new security surface (#832, decision of
    10 September 2026): a FINANCE-only user does not reach reporting at all, and
    the roles the universe declares per object are not enforced here. Half a fence
    would suggest a protection that is not there.
    """
    try:
        dataset, content = build_dataset_ods(
            db, fact_key, tenant_id=_tenant(request))
    except SelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = dataset_filename(dataset)
    return Response(
        content=content,
        media_type=ODS_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
