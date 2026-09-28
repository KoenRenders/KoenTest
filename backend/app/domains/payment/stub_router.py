"""The stub provider's side of the chain: a pretend checkout page and a webhook (#1274).

What Mollie does for a real payment, played here without money: a page with one
button, where the e2e test "pays", and a webhook the page then calls — the way
Mollie's server calls ours. The webhook is the same code as Mollie's
(`gateway_router.process_webhook`): it takes only the id and re-fetches the
status from the provider, so the chain runs through the real security rule.

**These routes do not exist outside development and the tests.** Not a 404 and
not a refusal — they are never registered: `include_stub_routes` adds them only
when `settings.payment_stub_allowed`. A pretend payment page on PROD would be a
page that marks registrations paid without money.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db

from .gateway_router import process_webhook
from .providers import stub

page_router = APIRouter()
webhook_router = APIRouter(prefix="/payment-gateway", tags=["payment-gateway"])


def _path(url: str) -> str:
    """Path and query only: the test server is not at the public URL the
    payment was created with, so the page stays on the host it was opened on."""
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


@page_router.get(stub.CHECKOUT_PATH + "/{payment_id}", response_class=HTMLResponse)
def checkout_page(payment_id: str):
    payment = stub.PAYMENTS.get(payment_id)
    if payment is None:
        raise HTTPException(status_code=404)
    pay_path = f"{stub.CHECKOUT_PATH}/{escape(payment_id)}/betaal"
    webhook_path = escape(_path(payment.webhook_url))
    redirect_path = escape(_path(payment.redirect_url) or "/")
    return f"""<!doctype html><html lang="nl-BE"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Testbetaling</title></head><body>
<main><h1>Testbetaling — geen echt geld</h1>
<p>Bedrag: € {payment.amount}</p>
<button type="button" id="stub-betaal">Betaal</button></main>
<script>
document.getElementById("stub-betaal").addEventListener("click", async () => {{
  await fetch("{pay_path}", {{method: "POST"}});
  await fetch("{webhook_path}", {{method: "POST",
    body: new URLSearchParams({{id: "{escape(payment_id)}"}})}});
  window.location.href = "{redirect_path}";
}});
</script></body></html>"""


@page_router.post(stub.CHECKOUT_PATH + "/{payment_id}/betaal")
def checkout_pay(payment_id: str):
    if payment_id not in stub.PAYMENTS:
        raise HTTPException(status_code=404)
    stub.pay(payment_id)
    return {"status": "paid"}


@webhook_router.post("/webhooks/stub", status_code=200)
def stub_webhook(id: str = Form(...), db: Session = Depends(get_db)):
    """The stub's webhook: Mollie's code path, with the stub's id."""
    return process_webhook(db, id)


def include_stub_routes(app: FastAPI, *, allowed: bool) -> bool:
    """Register the stub's page and webhook — only where the stub may exist.

    Takes `allowed` rather than reading the settings itself, so a test can hand
    it a fresh app and a PROD answer without rebuilding the real one.
    """
    if not allowed:
        return False
    app.include_router(page_router)
    app.include_router(webhook_router, prefix="/api/v1")
    return True
