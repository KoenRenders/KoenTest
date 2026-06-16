"""Soft delete: markeer rijen met ``deleted_at`` i.p.v. ze hard te verwijderen,
en filter ze globaal uit ALLE ORM-reads (#166).

Geldt voor elk model dat van ``SoftDeleteMixin`` erft — bewust alles behalve
CMS-pagina's en media. Reactivatie van een lid/gezin gebeurt later via het
upload-programma (#74); er is bewust GEEN admin-undelete. Tot #74 bestaat, is een
verwijderd record dus verborgen maar niet herstelbaar.

De globale filter gebruikt het canonieke SQLAlchemy-recept (``with_loader_criteria``
op een ``do_orm_execute``-event): zo hoeft geen enkele afzonderlijke query
aangepast te worden en kan verwijderde data niet "per ongeluk" lekken. Een query
die toch verwijderde rijen nodig heeft (bv. straks het upload-programma) zet
``.execution_options(include_deleted=True)``.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, event
from sqlalchemy.orm import Session, with_loader_criteria


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SoftDeleteMixin:
    """Geeft een model een ``deleted_at`` en brengt het onder de globale filter."""
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)


def soft_delete(obj) -> None:
    """Markeer één object als verwijderd (idempotent — een al verwijderd object
    wordt niet opnieuw gestempeld)."""
    if getattr(obj, "deleted_at", None) is None:
        obj.deleted_at = _utcnow()


@event.listens_for(Session, "do_orm_execute")
def _filter_soft_deleted(execute_state):
    # Bewust óók op relationship-loads (lazy loads van bv. activity.registrations of
    # reg.items): anders lekken soft-deleted rijen in aantallen/saldo-berekeningen die
    # via een relatie lui inladen (#194). Column-loads/refreshes blijven uitgesloten.
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.execution_options.get("include_deleted", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )
