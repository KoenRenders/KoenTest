"""History-patroon (§5.8): per component een eigen ``*_history``-tabel in het
eigen schema — géén centrale audit-component. Deze module levert de gedeelde
snapshot-hulp; de bestaande audit-tabellen (address_history, product_history, …)
migreren per component naar dit patroon tijdens hun fase."""
from __future__ import annotations

from typing import Any

from sqlalchemy import inspect


def snapshot_row(obj: Any, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """Platte dict van alle kolomwaarden van een ORM-object — de payload voor
    een history-rij (wie/wat/wanneer voegt het component zelf toe)."""
    mapper = inspect(obj).mapper
    return {
        col.key: getattr(obj, col.key)
        for col in mapper.column_attrs
        if col.key not in exclude
    }
