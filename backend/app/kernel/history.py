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
    return {col.key: getattr(obj, col.key) for col in mapper.column_attrs if col.key not in exclude}


# #713: what stands in `actor` when NOBODY was signed in.
#
# Empty used to mean two things at once — "nobody was signed in" and "we forgot who
# did this" — and a screen shows both as an empty cell. So nobody could read such a
# cell, and the next omission could join it unseen; that is how the four came about
# that #713 put right.
#
# Since then the public roads write this, and empty means **a fault**. No `@`, so it
# is never read as an e-mail address. Rows from before stay empty: they cannot be
# explained in hindsight and are not to be treated as if they could.
PUBLIC_ACTOR = "publiek"
