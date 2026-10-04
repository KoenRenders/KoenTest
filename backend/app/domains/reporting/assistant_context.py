"""What the Assistent panel knows about the screen it was opened on (CR-11 K8, #1562).

Block 10 (Koen, 4 October 2026; `docs/design-system-end-state.md` §3.15): the
panel has no selectors. **The screen owns its selection and the panel reads
it** — from the screen's address, never from a field of the panel:

- a record ("over Herfstwandeling met soep");
- a list with its filter and the size of the selection ("over 8 openstaande
  betalingen (filter Openstaand)");
- otherwise the tenant ("over Raak Millegem").

Where a number comes from (measured before building, 4 October 2026): the
reporting tools carry a list's filter to the model as forced filters and a
description, but they compute no count — every figure is the model's own
`run_report`. The size of the selection is the screen's knowledge, so it is
asked of the screen's domain (`payment.api.selection_count`), over the same
filter the scope carries. The unit is **bookings**, the rows the model counts —
not the registration groups the toolbar counts — and the line names it.

**Availability by rule, derived and not typed** (§B4.9): a module's screens
offer the assistant when its objects are in the reporting universe — the module
registry already says so (`Module.reporting_folders`). Reporting itself and the
dashboard are about those objects too. Elsewhere the trigger is dimmed and the
panel says "Raakje kent deze gegevens nog niet". There are no command tools
yet (CR-16); when a module's facade exposes them, it joins here.

A list state that cannot be carried over exactly (a search term, a context per
year) is **refused, not dropped**: the line names the list without a count,
the panel says which filter stands in the way, and asking is off until it is
gone (`ScopeNietOverdraagbaar`, #1060).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy.orm import Session

from app.i18n import _
from app.kernel.modules import REGISTRY, ModuleCode, serving_module

#: Where the three kinds of conversation are asked (the routes of `admin_ui`).
ASK = "/admin/rapporten/raakje"

#: Screens of the shell that are about the reporting universe as a whole.
_GENERAL_PATHS = ("/admin", "/admin/dashboard")

_ACTIVITY = re.compile(r"^/admin/activiteiten/(\d+)(?:/|$)")


@dataclass(frozen=True)
class AssistantContext:
    """The panel's context for one screen.

    `key` names the context: when it changes, the conversation starts anew and
    an answer still on its way to the previous one is not shown. `blocked` is
    the reason asking is off ("" when it is not)."""

    key: str
    available: bool
    label: str
    post_url: str = ""
    suggestions: tuple[str, ...] = ()
    blocked: str = ""

    @property
    def can_ask(self) -> bool:
        return self.available and not self.blocked


def module_knows_the_assistant(code: ModuleCode | None, path: str) -> bool:
    """Is the assistant offered on this module's screens? Derived from the
    registry: the module has objects in the reporting universe, or it is
    reporting itself; of the shell's own screens only the dashboard."""
    if code is None:
        return path.rstrip("/") in _GENERAL_PATHS
    return code is ModuleCode.REPORTING or bool(REGISTRY[code].reporting_folders)


def _general(db: Session, tenant_id: int) -> AssistantContext:
    from app.kernel.tenant_config import tenant_display_name

    return AssistantContext(
        key="tenant",
        available=True,
        label=_("over %(name)s") % {"name": tenant_display_name(db, tenant_id=tenant_id)},
        post_url=ASK,
        suggestions=(
            _("Hoeveel gezinnen zijn er per gemeente?"),
            _("Wat staat er nog open aan lidgeld?"),
            _("Welke activiteiten komen eraan?"),
        ),
    )


def _activity(db: Session, activity_id: int) -> AssistantContext | None:
    from app.domains.activities.api import get_activity

    activity = get_activity(db, activity_id)
    if activity is None:
        return None
    return AssistantContext(
        key=f"activity:{activity_id}",
        available=True,
        label=_("over %(name)s") % {"name": activity.name},
        post_url=f"{ASK}/activiteit/{activity_id}",
        suggestions=(
            _("Hoeveel inschrijvingen zijn er?"),
            _("Hoeveel staat er nog open?"),
            _("Wie heeft nog niet betaald?"),
        ),
    )


def _payments(db: Session, state: dict[str, str], tenant_id: int) -> AssistantContext:
    from app.domains.payment.api import selection_count
    from app.domains.reporting.assistant import ScopeNietOverdraagbaar, scope_for_payments

    post_url = f"{ASK}/scherm/betalingen"
    try:
        # The same builder the question will go through: what it refuses here,
        # it refuses there.
        scope_for_payments(state, db, tenant_id=tenant_id)
    except ScopeNietOverdraagbaar as why:
        return AssistantContext(
            key="payments:blocked",
            available=True,
            label=_("over de betalingen op dit scherm"),
            post_url=post_url,
            blocked=_(
                "Raakje kan deze selectie niet overnemen: %(what)s valt buiten wat de "
                "rapportering kent. Neem dat filter weg om een vraag te stellen."
            )
            % {"what": str(why)},
        )
    view = (state.get("zicht") or "alle").strip()
    view = view if view in ("alle", "openstaand") else "alle"
    context = (state.get("context") or "all").strip()
    activity = (state.get("activiteit") or "").strip()
    activity_id = int(activity) if activity.isdigit() else None
    count = selection_count(db, context=context, view=view, activity_id=activity_id)
    filters = []
    if view == "openstaand":
        filters.append(_("filter Openstaand"))
    if context == "membership":
        filters.append(_("alleen lidgeld"))
    if activity_id is not None:
        from app.domains.activities.api import get_activity

        found = get_activity(db, activity_id)
        filters.append(found.name if found is not None else _("één activiteit"))
    if view == "openstaand":
        what = (
            _("over %(n)s openstaande betaling")
            if count == 1
            else _("over %(n)s openstaande betalingen")
        )
    else:
        what = _("over %(n)s betaling") if count == 1 else _("over %(n)s betalingen")
    label = what % {"n": count} + (f" ({', '.join(filters)})" if filters else "")
    return AssistantContext(
        # The filter is part of the context: another selection is another
        # conversation. The count is not — a confirmation changes it, the
        # subject stays.
        key=f"payments:{view}:{context}:{activity_id or ''}",
        available=True,
        label=label,
        post_url=post_url,
        suggestions=(
            _("Hoeveel staat er nog open?"),
            _("Wie heeft nog niet betaald?"),
            _("Hoe verdeelt dit zich over lidgeld en activiteiten?"),
        ),
    )


def context_for(db: Session, url: str, *, tenant_id: int) -> AssistantContext:
    """The context of the screen at `url` — the address the browser shows
    (`HX-Current-URL`), so a list's state is the state on the screen."""
    parts = urlsplit(url or "")
    path = parts.path.rstrip("/") or "/admin"
    state = dict(parse_qsl(parts.query, keep_blank_values=True))
    if not module_knows_the_assistant(serving_module(path), path):
        return AssistantContext(
            key="unknown",
            available=False,
            label="",
            blocked=_("Raakje kent deze gegevens nog niet."),
        )
    record = _ACTIVITY.match(path + "/")
    if record:
        found = _activity(db, int(record.group(1)))
        if found is not None:
            return found
    if path == "/admin/betalingen":
        return _payments(db, state, tenant_id)
    return _general(db, tenant_id)
