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
#: The workbench is core since #1876 and its tasks are in the reporting
#: universe: every screen under it offers the assistant, as when it was a module.
_WORKBENCH = "/admin/werkbank"

_ACTIVITY = re.compile(r"^/admin/activiteiten/(\d+)(?:/|$)")
_NEWSLETTER = re.compile(r"^/admin/nieuwsbrieven/(\d+)$")
_NEW_ACTIVITY = "/admin/activiteiten/nieuw"


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
    #: #1562 PR 2 — a screen whose conversation is about what stands ON it:
    #: fields of the screen that travel with a question (`hx-include`, and
    #: `hx-vals` as a `js:` expression), and where the turns the server keeps
    #: for this record are loaded from.
    include: str = ""
    vals: str = ""
    history_url: str = ""

    @property
    def can_ask(self) -> bool:
        return self.available and not self.blocked


def module_knows_the_assistant(code: ModuleCode | None, path: str) -> bool:
    """Is the assistant offered on this module's screens? Derived from the
    registry: the module has objects in the reporting universe, or it is
    reporting itself; of the shell's own screens the dashboard and the
    workbench."""
    if code is None:
        stem = path.rstrip("/")
        return stem in (*_GENERAL_PATHS, _WORKBENCH) or stem.startswith(_WORKBENCH + "/")
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


def _activity(db: Session, activity_id: int, *, editing: bool = False) -> AssistantContext | None:
    from app.domains.activities.api import get_activity, proposal_vals, proposer_url

    activity = get_activity(db, activity_id)
    if activity is None:
        return None
    if editing:
        # #1604: while the fiche is being edited, the panel proposes for its
        # form — name, location, description, date and time. A key of its own:
        # the address changes from reading to editing, and the panel swaps only
        # when the key does. Questions about the activity stay in read mode.
        return AssistantContext(
            key=f"activity-edit:{activity_id}",
            available=True,
            label=_("voorstel voor %(name)s") % {"name": activity.name},
            post_url=proposer_url(activity_id),
            suggestions=(
                _("Schrijf een omschrijving."),
                _("Stel een betere naam voor."),
            ),
            # #1659: the form as it stands travels with the request.
            vals=proposal_vals(),
        )
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


#: What the newsletter page sends along with a question: the text as it stands
#: in the editor, the selection and what stands before the cursor — Raakje
#: rewrites the selection or writes for that spot (Koen, 17 September 2026).
_NEWSLETTER_FIELDS = "#nb-inhoud"
_NEWSLETTER_VALS = (
    'js:{selection: window.nbSelectie ? nbSelectie() : "", '
    'selection_range: window.nbBereik ? nbBereik() : "", '
    'before_cursor: window.nbVoorCursor ? nbVoorCursor() : ""}'
)


def _newsletter(db: Session, newsletter_id: int) -> AssistantContext | None:
    """The draft of a newsletter: Raakje writes along (CR-05 §3.15), since #1562
    in this panel. The newsletter's facade says whether there is a draft to
    write for; None for a letter that is sent or does not exist."""
    from app.domains.newsletter.api import draft_subject

    subject = draft_subject(db, newsletter_id)
    if subject is None:
        return None
    base = f"/admin/nieuwsbrieven/{newsletter_id}/raakje"
    return AssistantContext(
        key=f"newsletter:{newsletter_id}",
        available=True,
        label=_("over de nieuwsbrief “%(name)s”") % {"name": subject}
        if subject
        else _("over deze nieuwsbrief"),
        post_url=f"{base}/vraag",
        suggestions=(
            _("Schrijf een voorstel voor de hele brief."),
            _("Maak de geselecteerde tekst korter."),
            _("Schrijf een stuk voor waar mijn cursor staat."),
        ),
        include=_NEWSLETTER_FIELDS,
        vals=_NEWSLETTER_VALS,
        history_url=f"{base}/gesprek",
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
    # A module whose facade offers the assistant a command (§B4.9): the
    # newsletter's proposer, on the draft it writes for. Asked before the
    # rule of the reporting universe, which the newsletter is not in.
    letter = _NEWSLETTER.match(path)
    if letter:
        found = _newsletter(db, int(letter.group(1)))
        if found is not None:
            return found
    if not module_knows_the_assistant(serving_module(path), path):
        return AssistantContext(
            key="unknown",
            available=False,
            label="",
            blocked=_("Raakje kent deze gegevens nog niet."),
        )
    if path == _NEW_ACTIVITY:
        # #1649: the fiche of an activity that does not exist yet. The proposer
        # of #1604 fills its empty form; there is nothing to ask questions about.
        from app.domains.activities.api import NEW_PROPOSER_URL, proposal_vals

        return AssistantContext(
            key="activity-new",
            available=True,
            label=_("voorstel voor een nieuwe activiteit"),
            post_url=NEW_PROPOSER_URL,
            suggestions=(
                _("Schaatsen op zondag 8 november van 10 tot 12 uur in de schaatsbaan."),
                _("Schrijf een omschrijving."),
            ),
            vals=proposal_vals(),
        )
    record = _ACTIVITY.match(path + "/")
    if record:
        # Only the fiche itself has an edit state; a tab of the record (its
        # registrations) reads, whatever its query says.
        on_fiche = path == f"/admin/activiteiten/{record.group(1)}"
        found = _activity(
            db, int(record.group(1)), editing=on_fiche and state.get("bewerken") == "1"
        )
        if found is not None:
            return found
    if path == "/admin/betalingen":
        return _payments(db, state, tenant_id)
    return _general(db, tenant_id)
