"""Server-rendered "Word lid"-formulier (React-exit #405, §21).

Meerdere gezinsleden via htmx (rij-fragment per index — geen client-side
state), postcode altijd een dropdown (vaste UI-beslissing), betaalwijze met
Mollie-redirect via HX-Redirect. Hergebruikt register_family integraal
(dedup, prijsregels, mail, audit).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import registration_limiter
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)


def _codes(db: Session) -> dict:
    from app.domains.mdm.api import GenderCode, PostalCode, RelationTypeCode

    def _uniq(rows):
        seen, out = set(), []
        for r in rows:
            if r.code not in seen:
                seen.add(r.code)
                out.append(r)
        return out

    return {
        "gender_codes": _uniq(db.query(GenderCode).order_by(GenderCode.code).all()),
        "relation_types": _uniq(db.query(RelationTypeCode).order_by(RelationTypeCode.code).all()),
        "postal_codes": db.query(PostalCode).order_by(PostalCode.postal_code).all(),
    }


@router.get("/lid-worden", response_class=HTMLResponse)
def lid_worden(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "lid_worden.html", {
        **site_context(db), **_codes(db), "error": None, "values": {}})


@router.get("/lid-worden/persoon-rij", response_class=HTMLResponse)
def persoon_rij(request: Request, db: Session = Depends(get_db)):
    try:
        index = max(1, int(request.query_params.get("index", "1")))
    except ValueError:
        index = 1
    return templates.TemplateResponse(request, "_lid_persoon_rij.html", {
        **_codes(db), "i": index, "values": {}})


def _parse_members(form) -> list[dict]:
    members: list[dict] = []
    index = 0
    while f"m{index}_first_name" in form or f"m{index}_last_name" in form:
        m = {k: (form.get(f"m{index}_{k}") or "").strip() for k in
             ("first_name", "last_name", "date_of_birth", "gender_code",
              "email", "phone", "mobile", "relation_type")}
        if m["first_name"] or m["last_name"]:
            members.append(m)
        index += 1
    return members


@router.post("/lid-worden", response_class=HTMLResponse,
             dependencies=[Depends(registration_limiter)])
async def lid_worden_submit(request: Request, background_tasks: BackgroundTasks,
                            db: Session = Depends(get_db)):
    from pydantic import ValidationError

    from app.routers.members import register_family
    from app.schemas.family import FamilyCreate, FamilyMemberCreate

    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    ctx = {**site_context(db), **_codes(db), "values": values}

    members = _parse_members(form)
    if not members:
        ctx["error"] = "Vul minstens het hoofdlid in."
        return templates.TemplateResponse(request, "lid_worden.html", ctx)
    if not (values.get("postal_code") or "").strip():
        ctx["error"] = "Selecteer een geldige postcode uit de lijst."
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    try:
        data = FamilyCreate(
            street=(values.get("street") or "").strip(),
            house_number=(values.get("house_number") or "").strip(),
            bus_number=(values.get("bus_number") or "").strip() or None,
            postal_code=(values.get("postal_code") or "").strip(),
            payment_method=(values.get("payment_method") or "online").strip(),
            members=[FamilyMemberCreate(
                first_name=m["first_name"], last_name=m["last_name"],
                date_of_birth=m["date_of_birth"] or None,
                gender_code=m["gender_code"] or None,
                email=m["email"] or None, phone=m["phone"] or None,
                mobile=m["mobile"] or None,
                relation_type=m["relation_type"] or ("HOOFDLID" if not members.index(m) else "PARTNER"),
            ) for m in members],
        )
    except ValidationError as exc:
        eerste = exc.errors()[0]
        ctx["error"] = str(eerste.get("msg", "Ongeldige invoer."))
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    try:
        result = register_family(data, background_tasks, db=db)
    except HTTPException as exc:
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    checkout_url = getattr(result, "checkout_url", None)
    response = templates.TemplateResponse(request, "lid_worden_klaar.html", {
        **site_context(db), "checkout": bool(checkout_url),
        "amount": getattr(result, "amount", None)})
    if checkout_url:
        response.headers["HX-Redirect"] = checkout_url
    return response
