"""Reporting (#851): the report shows one address column instead of three.

Koen: *"Zouden we niet een veld 'adreslijn' (straat huisnummer busnummer) voorzien
in de view [...]? Dat gaat veel gebruikt worden."* He narrowed the scope himself on
10 September 2026: **only the view and the universe**. Nothing in the model,
nothing in the existing screens, and no shared Python function.

**The view already has the column.** `d_address.address_line` was built in
migration 110 and it is already declared in the universe, so this migration adds
no SQL. What is left is the part that is data: the shipped report
"Leden per bestuurslid" picked three separate address columns, and now picks one.

**Why it was three, and why that reason is gone.** #850 split the address because
composed into a single string it sorted wrong — "Straat 10" before "Straat 2". That
was true of the report as it stood then. It stopped being true when the same issue
gave a universe object its own `sort_sql`: the visible column can now be the whole
line while the order comes from the split fields underneath. **The sort key stays
the split fields.** Ordering on the composed text is precisely the fault #850 fixed,
and it would come straight back the day somebody drops `sort_sql` as redundant.

The three separate objects stay in the universe. Whoever wants to group by street
must be able to; this changes one report's presentation, not what can be asked.

**Deliberately not touched: the six other places that compose the same line**
(`mail/service.py`, twice in `audit/changes.py`, `mdm/import_service.py`, and
inline in two templates). Two of them feed the ledenwijzigingen export for Raak
Nationaal (#512), which we do not touch, so this view is knowingly a seventh copy
until the clean-up issue reduces all of them to one. That issue also carries the
real bug found on the way: `mdm/templates/_leden_lijst.html` writes street and
house number **without** the bus number, so bus 1 and bus 3 read as the same
address — left standing here on purpose, because it needs a characterisation test
on that export before anything moves.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "112"
down_revision = "111"
branch_labels = None
depends_on = None


SELECTION = {
    "objects": ["board_member", "address_line", "member_head_name",
                "member_partner_name", "member_total_count"],
    "filters": [{"object": "member_valid_today", "operator": "eq",
                 "values": ["Ja"]}],
    "sort": [{"object": "board_member", "direction": "asc"},
             {"object": "address_line", "direction": "asc"}],
    "layout": "pivot",
    "pivot_column": "",
}


def upgrade() -> None:
    # Only the rows that still carry the three-column shape, so a report a board
    # member has already adjusted is left alone.
    op.get_bind().execute(
        sa.text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
            "WHERE builtin_key = 'members_per_board_member' "
            "  AND selection::text LIKE '%address_street%'"
        ),
        {"s": json.dumps(SELECTION)},
    )


def downgrade() -> None:
    pass
