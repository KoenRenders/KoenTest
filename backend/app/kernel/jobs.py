"""Achtergrondwerk-primitief (§5.8): één Postgres-jobtabel + scheduler-loop.

Retentie-vegen, mail-retries, respijttermijnen, reconciliaties — componenten
déclareren hun werk hier; geen losse cronjobs. Eigenschappen:
- Jobs zijn transactioneel met de data (enqueue in dezelfde transactie als de
  businessmutatie — commit of geen van beide).
- Uitvoering per job in een eigen transactie; retry met exponentiële backoff.
- ``FOR UPDATE SKIP LOCKED``: meerdere lopers kunnen nooit dezelfde job pakken.
- Herhaald falen wordt luid gelogd (ERROR) en blijft als ``failed`` zichtbaar —
  in fase 4b wordt dat een werkbank-taak (§20.5).

Gebruik:
    @job("mail.retry")
    def retry_mail(db: Session, payload: dict) -> None: ...

    enqueue(db, "mail.retry", {"email_log_id": 7})           # nu
    enqueue(db, "sweep", run_at=..., )                        # gepland
Periodiek werk = de handler her-enqueuet zichzelf met een nieuwe run_at.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal

logger = logging.getLogger(__name__)

_handlers: dict[str, Callable[[Session, dict], None]] = {}


class KernelJob(Base):
    __tablename__ = "kernel_jobs"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    # pending | running | done | failed
    status = Column(String(10), nullable=False, default="pending", index=True)
    run_at = Column(DateTime(timezone=True), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))


def job(name: str) -> Callable[[Callable], Callable]:
    """Registreer de handler voor een job-naam (decorator)."""

    def decorator(handler: Callable[[Session, dict], None]) -> Callable:
        if name in _handlers:
            raise ValueError(f"job-handler '{name}' is al geregistreerd")
        _handlers[name] = handler
        return handler

    return decorator


def enqueue(db: Session, name: str, payload: Optional[dict] = None,
            run_at: Optional[datetime] = None, max_attempts: int = 5) -> KernelJob:
    """Plan een job — in de lopende transactie (commit van de bron = commit van de job)."""
    entry = KernelJob(
        name=name,
        payload=payload or {},
        run_at=run_at or datetime.now(timezone.utc),
        max_attempts=max_attempts,
    )
    db.add(entry)
    return entry


def run_due_jobs(db: Session, batch: int = 10) -> int:
    """Voer vervallen jobs uit; elke job in zijn eigen (sub)transactie. Geeft het
    aantal verwerkte jobs terug. Wordt door de scheduler-loop aangeroepen maar is
    ook los bruikbaar (tests, eenmalige runs)."""
    now = datetime.now(timezone.utc)
    processed = 0
    while processed < batch:
        entry = (
            db.query(KernelJob)
            .filter(KernelJob.status == "pending", KernelJob.run_at <= now)
            .order_by(KernelJob.run_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if entry is None:
            break
        entry.status = "running"
        entry.attempts += 1
        db.commit()

        handler = _handlers.get(entry.name)
        # Savepoint (expliciet, geen contextmanager): een falende handler rolt
        # enkel zijn EIGEN writes terug, nooit de job-administratie of de rest
        # van de sessie.
        savepoint = db.begin_nested()
        try:
            if handler is None:
                raise LookupError(f"geen handler geregistreerd voor job '{entry.name}'")
            handler(db, dict(entry.payload or {}))
            if savepoint.is_active:
                savepoint.commit()
            entry.status = "done"
            entry.last_error = None
            db.commit()
        except Exception as exc:  # noqa: BLE001 — falen hoort bij het primitief
            if savepoint.is_active:
                savepoint.rollback()
            entry.last_error = f"{type(exc).__name__}: {exc}"
            if entry.attempts >= entry.max_attempts:
                entry.status = "failed"
                logger.error("job %s (#%s) definitief GEFAALD na %d pogingen: %s",
                             entry.name, entry.id, entry.attempts, entry.last_error)
            else:
                entry.status = "pending"
                backoff = timedelta(seconds=30 * (2 ** (entry.attempts - 1)))
                entry.run_at = datetime.now(timezone.utc) + backoff
                logger.warning("job %s (#%s) faalde (poging %d/%d), retry over %s: %s",
                               entry.name, entry.id, entry.attempts,
                               entry.max_attempts, backoff, entry.last_error)
            db.commit()
        processed += 1
    return processed


_scheduler_started = False


def start_scheduler(interval_seconds: int = 30) -> None:
    """Start de scheduler-loop (daemon-thread). Idempotent; wordt aangeroepen
    vanuit de applicatie-start en bewust NIET in tests (zie settings.jobs_enabled)."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def loop() -> None:
        logger.info("kernel-jobs scheduler gestart (interval %ss)", interval_seconds)
        while True:
            time.sleep(interval_seconds)
            try:
                db = SessionLocal()
                try:
                    run_due_jobs(db)
                finally:
                    db.close()
            except Exception:  # noqa: BLE001 — de loop mag nooit sterven
                logger.exception("kernel-jobs scheduler-tick faalde")

    threading.Thread(target=loop, name="kernel-jobs", daemon=True).start()
