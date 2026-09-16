"""The newsletter's background job (CR-05 §3.7, #984).

``newsletter.send`` works through one letter's queue a few mails at a time and
schedules itself again until the queue is empty, or until the day's cap or
Gmail's own quota says to stop — then it schedules itself for when there is
room again. A restart simply picks up the next pending job.

A job runs outside any request, so there is no active tenant. The payload
carries the tenant id, and the handler sets it for the duration of the run:
without it the tenant filter is off and the mail settings would be read for
the default tenant.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.domains.newsletter.service import SEND_JOB, send_batch
from app.kernel.jobs import job
from app.kernel.tenancy import current_tenant_id

logger = logging.getLogger(__name__)


@job(SEND_JOB)
def send_newsletter(db: Session, payload: dict) -> None:
    tenant = payload.get("tenant_id")
    token = current_tenant_id.set(tenant) if tenant else None
    try:
        outcome = send_batch(db, int(payload["newsletter_id"]))
        logger.info("newsletter.send #%s: %s", payload.get("newsletter_id"), outcome)
    finally:
        if token is not None:
            current_tenant_id.reset(token)
