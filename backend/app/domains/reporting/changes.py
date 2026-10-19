"""Overzicht/export van alle ledendata-wijzigingen sinds een datum (#82).

Raak Nationaal heeft geen API; wijzigingen in dit portaal moeten manueel
overgetypt worden. Dit leest de append-only history-tabellen (recorded_at >=
since) en levert per wijziging een leesbare regel, zodat de admin ze één voor één
kan overnemen. Bevat persoonsdata: admin-only, nooit in de repo.
(verhuisd uit app/services/member_changes.py, #444)
"""

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.domains.activities.api import (
    ActivityDateHistory,
    ActivityHistory,
    ComponentHistory,
    ProductHistory,
    RegistrationHistory,
    RegistrationItemHistory,
)
from app.domains.mdm.api import (
    CONTACT,
    AddressHistory,
    ContactDetailHistory,
    MemberHistory,
    MemberPersonHistory,
    PersonHistory,
    RelationType,
    contact_change,
)
from app.domains.membership.api import MembershipHistory
from app.i18n import _, moment_text
from app.kernel.clock import belgian_day_start
from app.kernel.codes import code_label
from app.kernel.ods import build_ods
from app.kernel.operations import OPERATION

# The three words of the history operation live in the kernel's label table
# since CR-12 phase 4; `code_label()` reads them.


def _fmt(value) -> str:
    return "" if value is None else str(value)


def _addr_text(street, house_number, bus_number) -> str:
    s = f"{_fmt(street)} {_fmt(house_number)}".strip()
    if bus_number:
        s += f" bus {bus_number}"
    return s


class _SubjectResolver:
    """Leidt per wijziging de betrokken persoon + het hoofdlid van diens gezin af.

    Voor manuele overname in Raak Nationaal wil de admin per wijziging zien om
    wélke persoon het gaat en op welk gezinsadres. Soft-deleted entiteiten worden
    bewust meegenomen (``include_deleted=True``, zoals #190): een wijziging is een
    historisch feit en moet de bewaarde naam/adres blijven tonen.
    """

    def __init__(self, db: Session):
        self.db = db
        self._name: dict = {}
        self._ext: dict = {}
        self._addr: dict = {}
        self._member_of_person: dict = {}
        self._head_of_member: dict = {}
        self._pc: dict = {}

    def _q(self, model):
        return self.db.query(model).execution_options(include_deleted=True)

    def postcode_label(self, postal_code_id) -> str:
        """ "2400 Mol" voor een postcode-id (i.p.v. de nietszeggende id)."""
        if postal_code_id is None:
            return ""
        if postal_code_id not in self._pc:
            from app.domains.mdm.api import PostalCode

            pc = self._q(PostalCode).filter(PostalCode.id == postal_code_id).first()
            self._pc[postal_code_id] = (
                f"{_fmt(pc.postal_code)} {_fmt(pc.municipality)}".strip() if pc else ""
            )
        return self._pc[postal_code_id]

    def _name_of(self, person_id):
        if person_id is None:
            return ""
        if person_id not in self._name:
            from app.domains.mdm.api import Person

            p = self._q(Person).filter(Person.id == person_id).first()
            self._name[person_id] = f"{_fmt(p.first_name)} {_fmt(p.last_name)}".strip() if p else ""
        return self._name[person_id]

    def _ext_of(self, person_id):
        if person_id is None:
            return ""
        if person_id not in self._ext:
            from app.domains.mdm.api import ExternalNumber

            en = (
                self._q(ExternalNumber)
                .filter(ExternalNumber.person_id == person_id)
                .order_by(ExternalNumber.id)
                .first()
            )
            self._ext[person_id] = _fmt(en.external_id) if en else ""
        return self._ext[person_id]

    def _addr_of(self, person_id):
        if person_id is None:
            return ""
        if person_id not in self._addr:
            from app.domains.mdm.api import Address, PostalCode

            a = self._q(Address).filter(Address.person_id == person_id).first()
            if a is None:
                self._addr[person_id] = ""
            else:
                s = f"{_fmt(a.street)} {_fmt(a.house_number)}".strip()
                if a.bus_number:
                    s += f" bus {a.bus_number}"
                pc = self._q(PostalCode).filter(PostalCode.id == a.postal_code_id).first()
                if pc:
                    s += f", {_fmt(pc.postal_code)} {_fmt(pc.municipality)}".rstrip()
                self._addr[person_id] = s
        return self._addr[person_id]

    def _member_of(self, person_id):
        if person_id is None:
            return None
        if person_id not in self._member_of_person:
            from app.domains.mdm.api import MemberPerson

            mp = self._q(MemberPerson).filter(MemberPerson.person_id == person_id).first()
            self._member_of_person[person_id] = mp.member_id if mp else None
        return self._member_of_person[person_id]

    def _head_of(self, member_id):
        if member_id is None:
            return None
        if member_id not in self._head_of_member:
            from app.domains.mdm.api import MemberPerson

            mp = (
                self._q(MemberPerson)
                .filter(
                    MemberPerson.member_id == member_id,
                    MemberPerson.relation_type == RelationType.PRIMARY_MEMBER,
                )
                .first()
            )
            self._head_of_member[member_id] = mp.person_id if mp else None
        return self._head_of_member[member_id]

    def _person_by_email(self, email):
        """Person-id achter een e-mailadres (gast-inschrijving zonder gekoppeld lid)."""
        if not email:
            return None
        from sqlalchemy import func

        from app.domains.mdm.api import ContactDetail

        # `person_id IS NOT NULL` is niet overbodig sinds #945: een organisatie
        # draagt haar e-mailadres nu als rij in dezelfde tabel, met `person_id`
        # leeg. Zonder deze voorwaarde kan deze `.first()` — die geen ordening
        # heeft — de organisatierij pakken en `None` teruggeven, waarna de
        # auditregel stil haar onderwerp verliest.
        cd = (
            self._q(ContactDetail)
            .filter(
                ContactDetail.person_id.isnot(None),
                func.lower(ContactDetail.value) == email.strip().lower(),
                ContactDetail.contact_type_code == CONTACT.EMAIL,
            )
            .first()
        )
        return cd.person_id if cd else None

    def fields(self, *, person_id=None, member_id=None) -> dict:
        """De vier extra kolommen voor één wijziging. Subject = de betrokken
        persoon (of, bij een gezin/lidmaatschap-wijziging, het hoofdlid)."""
        head_member_id = member_id if member_id is not None else self._member_of(person_id)
        subject_person_id = person_id if person_id is not None else self._head_of(head_member_id)
        head_person_id = self._head_of(head_member_id)
        # Geen gezin/hoofdlid gevonden → val terug op de persoon zelf, zodat het
        # adres/extern nummer toch ingevuld raken (bv. een lid zonder gezinskoppeling).
        if head_person_id is None:
            head_person_id = subject_person_id
        return {
            "person_name": self._name_of(subject_person_id),
            "person_external_id": self._ext_of(subject_person_id),
            "head_address": self._addr_of(head_person_id),
            "head_external_id": self._ext_of(head_person_id),
        }

    def from_registration(self, registration_id) -> Optional[dict]:
        """Verrijking voor een wijziging die aan een inschrijving hangt
        (betaling of bestelregel). Gekoppeld lid → persoon + hoofdlid; een gast
        zonder persoon toont enkel de contactnaam."""
        if registration_id is None:
            return None
        from app.domains.activities.api import Registration

        reg = self._q(Registration).filter(Registration.id == registration_id).first()
        if reg is None:
            return None
        if reg.person_id is not None:
            return self.fields(person_id=reg.person_id)
        # Gast-inschrijving: probeer het lid te matchen op het contact-e-mailadres,
        # zodat persoon + hoofdlid-adres tóch ingevuld raken (#221).
        pid = self._person_by_email(reg.contact_email)
        if pid is not None:
            return self.fields(person_id=pid)
        return {
            "person_name": _fmt(reg.contact_name),
            "person_external_id": "",
            "head_address": "",
            "head_external_id": "",
        }

    def from_payment(self, payable_type, payable_id) -> Optional[dict]:
        """Verrijking voor een betaling-wijziging: via wat de betaling betaalt — de
        persoon of het gezin erachter, zoals de describer van die soort het zegt
        (CR-21 phase 0, #1748). Een gast zonder persoon toont enkel de contactnaam."""
        from app.domains.payment.api import describe_one

        what = describe_one(self.db, payable_type, payable_id)
        if what.household_id is not None:
            return self.fields(member_id=what.household_id)
        if what.person_id is not None:
            return self.fields(person_id=what.person_id)
        pid = self._person_by_email(what.contact_email)
        if pid is not None:
            return self.fields(person_id=pid)
        if what.contact_name is None and what.contact_email is None:
            return None
        return {
            "person_name": _fmt(what.contact_name),
            "person_external_id": "",
            "head_address": "",
            "head_external_id": "",
        }


_EMPTY_SUBJECT = {
    "person_name": "",
    "person_external_id": "",
    "head_address": "",
    "head_external_id": "",
}


def _row(
    h,
    *,
    entity: str,
    entity_id: Optional[int],
    summary: str,
    group: str = "Leden",
    subject: Optional[dict] = None,
) -> dict:
    return {
        "recorded_at": h.recorded_at,
        "group": group,
        "entity": entity,
        "entity_id": entity_id,
        "operation": h.operation,
        "operation_label": code_label(OPERATION.name, h.operation),
        "action": h.action,
        "actor": h.actor,
        "summary": summary,
        **(subject or _EMPTY_SUBJECT),
    }


# ── #1885 gate 3: every logged column a history row carries is shown ─────────
#
# Each object kind keeps the summary it had (Koen retypes these lines into the
# national programme: #82, #230, #1833); what that summary does not show yet is
# added to an update as "<label>: old → new", from the one declaration of what is
# logged (`kernel.logged`) and with the word of the attribute register (CR-33).
# A long text is not written out: "<label> gewijzigd" — its old and new text stay
# in the history table (Koen, 16 October 2026, "10a").

#: What no row of Wijzigingen shows, with its reason. `tenant_id` and `account_id` for every kind.
NOT_SHOWN_ANYWHERE = {
    "tenant_id": "the screen shows one workspace's changes",
    "account_id": "the account a party belongs to (CR-26): the screen shows one account's",
}

#: Per logged model: the columns its own summary shows (`shown`) and the ones no
#: row shows (`not_shown`, with the reason). Every other logged column is shown
#: by `_more`, under its register label. `tests/test_logged_gate.py` (gate 3)
#: holds every declared model to this table.
SHOWN: dict[str, dict] = {}


def shows(model_name: str, *, shown=(), not_shown=None) -> None:
    SHOWN[model_name] = {"shown": set(shown), "not_shown": dict(not_shown or {})}


def _column_index() -> dict:
    from app.kernel.attributes import load_all_attributes, registry

    load_all_attributes()
    return {column: attr for attr in registry().values() for column in attr.columns}


def label_of(model, column: str):
    """The register's entry of a model column, or None."""
    from sqlalchemy import inspect

    from app.kernel.attributes import column_path

    col = inspect(model).columns[column]
    return _column_index().get(column_path(col))


def _show(model, column: str, value) -> str:
    """A value as the user reads it: yes/no, a code as its label, else as stored."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return _("ja") if value else _("nee")
    from sqlalchemy import inspect

    col = inspect(model).columns[column]
    for key in col.foreign_keys:
        table = key.column.table.name
        if table.endswith("_codes"):
            return code_label(table.removesuffix("_codes"), value)
    return _fmt(value)


def _is_long_text(model, column: str) -> bool:
    from sqlalchemy import Text, inspect

    return isinstance(inspect(model).columns[column].type, Text)


def _model_of(history: type) -> type:
    from app.kernel.logged import declared

    for entry in declared():
        if entry.history is history:
            return entry.model
    raise LookupError(f"{history.__name__} belongs to no logged model (#1885)")


def _more(db: Session, h) -> List[str]:
    """What an update changed that its kind's own summary does not show."""
    from app.kernel.logged import declaration_of, history_column, logged_columns

    if h.operation != "update":
        return []
    model = _model_of(type(h))
    entry = declaration_of(model)
    rules = SHOWN[model.__name__]
    history = type(h)
    key = getattr(history, entry.key)
    prev = (
        db.query(history)
        .filter(key == getattr(h, entry.key), history.id < h.id)
        .order_by(history.id.desc())
        .first()
    )
    if prev is None:
        return []
    lines: List[str] = []
    for name in logged_columns(entry):
        if name in rules["shown"] or name in rules["not_shown"] or name in NOT_SHOWN_ANYWHERE:
            continue
        stored = history_column(entry, name)
        old, new = getattr(prev, stored), getattr(h, stored)
        if _fmt(old) == _fmt(new):
            continue
        attr = label_of(model, name)
        label = attr.text if attr is not None else name
        if _is_long_text(model, name):
            lines.append(_("%(label)s gewijzigd") % {"label": label})
        else:
            lines.append(f"{label}: {_show(model, name, old)} → {_show(model, name, new)}")
    return lines


REF = "a reference by id, set when the row is made"
_SUBJECT = "the row's subject columns name the person and the household"

shows(
    "Person",
    shown={"first_name", "last_name", "date_of_birth", "gender_code"},
    not_shown={
        "superseded_by_id": "set and cleared by a merge, which the row's action names "
        "(person_merged, person_unmerged)"
    },
)
shows("Member", shown={"board_member_id"})
shows(
    "MemberPerson",
    shown={"relation_type"},
    not_shown={"person_id": _SUBJECT, "member_id": _SUBJECT},
)
shows(
    "Address",
    shown={"street", "house_number", "bus_number", "postal_code_id"},
    not_shown={"person_id": _SUBJECT, "organization_id": "the organisation that owns it: " + REF},
)
shows(
    "ContactDetail",
    shown={"contact_type_code", "value", "is_primary"},
    not_shown={"person_id": _SUBJECT, "organization_id": "the organisation that owns it: " + REF},
)
shows(
    "ExternalNumber",
    shown={"source", "external_id"},
    not_shown={"person_id": _SUBJECT},
)
shows(
    "Membership",
    shown={"year", "is_active", "valid_from", "valid_to"},
    not_shown={"member_id": _SUBJECT},
)
shows(
    "Activity",
    shown={"name"},
    not_shown={"copied_from_id": "the activity a copy was made from: " + REF},
)
shows("ActivityDate", shown={"start_date", "end_date", "activity_id"})
_FIXED = "fixed since v2.0: every component is INDIVIDUAL and free, its products carry the price"
shows(
    "ActivitySubRegistration",
    shown={"name", "activity_id"},
    not_shown={
        "registration_type_code": _FIXED,
        "is_free": _FIXED,
        "member_price": _FIXED,
        "form_id": "the form of its questions: " + REF.replace(", set when the row is made", ""),
    },
)
shows(
    "ActivityProduct",
    shown={"name", "price", "component_id"},
)
shows(
    "Registration",
    shown={"contact_name", "contact_email", "phone", "remarks"},
    not_shown={
        "activity_id": _SUBJECT,
        "person_id": _SUBJECT,
        "component_id": "the component it is for: " + REF,
        "form_submission_id": "the record of its answers; the row's answers show them in words",
    },
)
shows("RegistrationItem", shown={"product_id", "quantity", "registration_id"})
shows(
    "PaymentRecord",
    shown={"type", "amount", "method", "status", "payable_type", "payable_id"},
    not_shown={
        "refund_of_id": "the payment a refund pays back: " + REF,
        "gateway_payment_id": "the provider's payment: " + REF,
    },
)


def _with_more(summary: str, db: Session, h) -> str:
    more = _more(db, h)
    return "; ".join([summary, *more]) if more else summary


def member_changes_since(db: Session, since: date) -> List[dict]:
    """Alle ledendata-wijzigingen met recorded_at >= since, nieuw → oud."""
    since_dt = belgian_day_start(since)
    rows: List[dict] = []
    subj = _SubjectResolver(db)

    for h in db.query(PersonHistory).filter(PersonHistory.recorded_at >= since_dt):
        if h.action == "person_revived":
            # Heractivering bij her-import (#227): de naam staat al in de eigen kolom.
            rows.append(
                _row(
                    h,
                    entity="Persoon",
                    entity_id=h.person_id,
                    summary="Heractivering",
                    subject=subj.fields(person_id=h.person_id),
                )
            )
            continue
        if h.action == "lidnr_attached":
            # Identiteitsmatch (#192): lidnummer gehecht aan een bestaand lid (#229).
            rows.append(
                _row(
                    h,
                    entity="Persoon",
                    entity_id=h.person_id,
                    summary="Lidnummer gekoppeld",
                    subject=subj.fields(person_id=h.person_id),
                )
            )
            continue
        naam = f"{_fmt(h.first_name)} {_fmt(h.last_name)}".strip() or "—"
        dob = f" (geb. {h.date_of_birth})" if h.date_of_birth else ""
        summary = f"{naam}{dob}"
        if h.operation == "update":
            prev = (
                db.query(PersonHistory)
                .filter(
                    PersonHistory.person_id == h.person_id,
                    PersonHistory.recorded_at < h.recorded_at,
                )
                .order_by(PersonHistory.recorded_at.desc())
                .first()
            )
            if prev is not None:
                # Per gewijzigd veld een "oud → nieuw" tonen (#230), zodat ook een
                # wijziging die de naam niet raakt (geboortedatum/geslacht) zichtbaar is.
                changes: List[str] = []
                prev_naam = f"{_fmt(prev.first_name)} {_fmt(prev.last_name)}".strip() or "—"
                if prev_naam != naam:
                    changes.append(f"{prev_naam} → {naam}")
                if prev.date_of_birth != h.date_of_birth:
                    changes.append(f"geb. {_fmt(prev.date_of_birth)} → {_fmt(h.date_of_birth)}")
                if _fmt(prev.gender_code) != _fmt(h.gender_code):
                    changes.append(f"geslacht {_fmt(prev.gender_code)} → {_fmt(h.gender_code)}")
                if changes:
                    summary = "; ".join(changes)
        rows.append(
            _row(
                h,
                entity="Persoon",
                entity_id=h.person_id,
                summary=_with_more(summary, db, h),
                subject=subj.fields(person_id=h.person_id),
            )
        )

    for h in db.query(MemberHistory).filter(MemberHistory.recorded_at >= since_dt):
        if h.action == "member_revived":
            summary = "Heractivering gezin"
        elif h.action in ("board_member_assigned", "board_member_imported"):
            # Toon wíé het (nieuwe) verantwoordelijke bestuurslid is i.p.v. enkel "Gezin".
            naam = subj._name_of(h.board_member_id)
            summary = f"Bestuurslid: {naam}" if naam else "Bestuurslid gewijzigd"
        else:
            summary = "Gezin"
        rows.append(
            _row(
                h,
                entity="Gezin",
                entity_id=h.member_id,
                summary=_with_more(summary, db, h),
                subject=subj.fields(member_id=h.member_id),
            )
        )

    for h in db.query(MemberPersonHistory).filter(MemberPersonHistory.recorded_at >= since_dt):
        summary = f"In gezin als {_fmt(h.relation_type)}"
        if h.operation == "update":
            # #1833: a changed relation says what it was — the board retypes this
            # list into the national programme.
            prev = (
                db.query(MemberPersonHistory)
                .filter(
                    MemberPersonHistory.member_person_id == h.member_person_id,
                    MemberPersonHistory.id < h.id,
                )
                .order_by(MemberPersonHistory.id.desc())
                .first()
            )
            if prev is not None and prev.relation_type != h.relation_type:
                summary = f"relatie {_fmt(prev.relation_type)} → {_fmt(h.relation_type)}"
        rows.append(
            _row(
                h,
                entity="Gezinslid",
                entity_id=h.member_person_id,
                summary=_with_more(summary, db, h),
                subject=subj.fields(person_id=h.person_id, member_id=h.member_id),
            )
        )

    for h in db.query(AddressHistory).filter(AddressHistory.recorded_at >= since_dt):
        adres = _addr_text(h.street, h.house_number, h.bus_number)
        body = adres
        if h.operation == "update":
            prev = (
                db.query(AddressHistory)
                .filter(
                    AddressHistory.address_id == h.address_id,
                    AddressHistory.recorded_at < h.recorded_at,
                )
                .order_by(AddressHistory.recorded_at.desc())
                .first()
            )
            if prev is not None:
                prev_adres = _addr_text(prev.street, prev.house_number, prev.bus_number)
                if prev_adres != adres:
                    body = f"{prev_adres} → {adres}"
        pc = subj.postcode_label(h.postal_code_id)
        summary = f"{body}, {pc}" if pc else body
        rows.append(
            _row(
                h,
                entity="Adres",
                entity_id=h.address_id,
                summary=_with_more(summary, db, h),
                subject=subj.fields(person_id=h.person_id),
            )
        )

    for h in db.query(ContactDetailHistory).filter(ContactDetailHistory.recorded_at >= since_dt):
        # Bij een wijziging "oud → nieuw" tonen door de vorige snapshot van ditzelfde
        # contact op te zoeken (#188).
        # #1687: the one presentation of a contact change (`mdm.change_lines`),
        # as the member import's check shows it: the code table's label instead
        # of the stored code ("Mobiel", not "MOBILE"), a number in groups, and
        # "old → new" where the row before this one holds another value.
        # `before` stays None for a new contact and for a row whose value did
        # not change: then the value alone is shown.
        before: Optional[str] = None
        # #1174: een verandering van de HOOFDADRES-markering moet hier te lezen
        # zijn, en niet alleen als "Gewijzigd".
        #
        # Deze regels bestaan om met de hand overgetypt te worden in het
        # Raak Nationaal-programma. Het hoofdadres is precies wat dat programma
        # bijhoudt, en sinds #1174 mag zowel het bestuur als het lid zelf een
        # ander adres aanduiden. Zonder deze zin staat er dan `EMAIL: jan@…` met
        # label "Gewijzigd" en een waarde die niet veranderd is — wie overtypt
        # ziet dát er iets gebeurde maar niet wát, en de lus staat open zonder
        # dat iemand het merkt.
        # De BEDOELING staat in de actie, en dat is betrouwbaarder dan ze achteraf
        # afleiden: `make_email_primary` schrijft `email_promoted` en
        # `email_demoted`. Afleiden kan alleen door de vorige snapshot van
        # dezelfde rij op te zoeken, en die bestaat niet altijd — een rij die
        # buiten een geauditeerd pad ontstond heeft er geen, en dan bleef de
        # markering stil weg. Gemeten bij het bouwen van #1174.
        markering = ""
        if h.action == "email_promoted":
            markering = " — is nu het hoofdadres"
        elif h.action == "email_demoted":
            markering = " — is niet meer het hoofdadres"
        if h.operation == "update":
            prev = (
                db.query(ContactDetailHistory)
                .filter(
                    ContactDetailHistory.contact_detail_id == h.contact_detail_id,
                    ContactDetailHistory.recorded_at < h.recorded_at,
                )
                .order_by(ContactDetailHistory.recorded_at.desc())
                .first()
            )
            if prev is not None and prev.value != h.value:
                before = _fmt(prev.value)
            # Terugval voor paden die de bedoeling niet benoemen — de ledenimport
            # schrijft `contacts_imported` voor élke wijziging.
            if not markering and prev is not None and bool(prev.is_primary) != bool(h.is_primary):
                markering = (
                    " — is nu het hoofdadres" if h.is_primary else " — is niet meer het hoofdadres"
                )
        elif h.operation == "insert" and h.is_primary:
            markering = " — hoofdadres"
        elif h.operation == "delete" and h.is_primary:
            markering = " — was het hoofdadres"
        if h.operation == "delete":
            shown = contact_change(h.contact_type_code, _fmt(h.value), "")
        else:
            shown = contact_change(h.contact_type_code, before, _fmt(h.value))
        rows.append(
            _row(
                h,
                entity="Contact",
                entity_id=h.contact_detail_id,
                summary=_with_more(f"{shown.text()}{markering}", db, h),
                subject=subj.fields(person_id=h.person_id),
            )
        )

    for h in db.query(MembershipHistory).filter(MembershipHistory.recorded_at >= since_dt):
        rows.append(
            _row(
                h,
                entity="Lidmaatschap",
                entity_id=h.membership_id,
                summary=_with_more(
                    f"jaar {_fmt(h.year)}, actief={_fmt(h.is_active)}, "
                    f"{_fmt(h.valid_from)}–{_fmt(h.valid_to)}",
                    db,
                    h,
                ),
                subject=subj.fields(member_id=h.member_id),
            )
        )

    rows.sort(key=lambda r: r["recorded_at"], reverse=True)
    return rows


# Objectgroepen voor de filter op de Wijzigingen-pagina (#189).
GROUPS = ["Leden", "Activiteiten", "Inschrijvingen", "Betalingen"]


def all_changes_since(
    db: Session, since: date, *, group: Optional[str] = None, actor: Optional[str] = None
) -> List[dict]:
    """Unified audit-feed (#189): alle history-tabellen sinds ``since``, met een
    objectgroep per rij; optioneel gefilterd op groep en/of actor. Nieuw → oud."""
    # Imported here and not at the top (#781): `payment.service` reaches
    # `audit.api` at load time through the domains it imports, as long as those
    # call audit's snapshot helpers, so a top-level `payment.api` import here closes
    # a cycle that only held because of the order the imports stood in.
    from app.domains.payment.api import PaymentRecordHistory

    since_dt = belgian_day_start(since)
    rows: List[dict] = list(member_changes_since(db, since))  # groep "Leden"
    subj = _SubjectResolver(db)

    for h in db.query(ActivityHistory).filter(ActivityHistory.recorded_at >= since_dt):
        rows.append(
            _row(
                h,
                entity="Activiteit",
                entity_id=h.activity_id,
                summary=_with_more(_fmt(h.name) or f"activiteit #{_fmt(h.activity_id)}", db, h),
                group="Activiteiten",
            )
        )
    for h in db.query(ActivityDateHistory).filter(ActivityDateHistory.recorded_at >= since_dt):
        rows.append(
            _row(
                h,
                entity="Datum",
                entity_id=h.activity_date_id,
                summary=_with_more(
                    f"{_fmt(h.start_date)}–{_fmt(h.end_date)} (activiteit #{_fmt(h.activity_id)})",
                    db,
                    h,
                ),
                group="Activiteiten",
            )
        )
    for h in db.query(ComponentHistory).filter(ComponentHistory.recorded_at >= since_dt):
        rows.append(
            _row(
                h,
                entity="Onderdeel",
                entity_id=h.component_id,
                summary=_with_more(f"{_fmt(h.name)} (activiteit #{_fmt(h.activity_id)})", db, h),
                group="Activiteiten",
            )
        )
    for h in db.query(ProductHistory).filter(ProductHistory.recorded_at >= since_dt):
        rows.append(
            _row(
                h,
                entity="Product",
                entity_id=h.product_id,
                summary=_with_more(
                    f"{_fmt(h.name)} €{_fmt(h.price)} (onderdeel #{_fmt(h.component_id)})", db, h
                ),
                group="Activiteiten",
            )
        )
    for h in db.query(RegistrationHistory).filter(RegistrationHistory.recorded_at >= since_dt):
        # Per gewijzigd veld een "oud → nieuw" (#624), zoals bij een persoon: een
        # stille correctie op iemands contactgegevens moet verklaarbaar zijn.
        summary = _fmt(h.contact_name) or "—"
        if h.operation == "update":
            prev = (
                db.query(RegistrationHistory)
                .filter(
                    RegistrationHistory.registration_id == h.registration_id,
                    RegistrationHistory.recorded_at < h.recorded_at,
                )
                .order_by(RegistrationHistory.recorded_at.desc())
                .first()
            )
            if prev is not None:
                changes: List[str] = []
                for label, oud, nieuw in (
                    ("naam", prev.contact_name, h.contact_name),
                    ("e-mail", prev.contact_email, h.contact_email),
                    ("mobiel", prev.phone, h.phone),
                    ("opmerking", prev.remarks, h.remarks),
                ):
                    if (oud or "") != (nieuw or ""):
                        changes.append(f"{label}: {_fmt(oud) or '—'} → {_fmt(nieuw) or '—'}")
                if changes:
                    summary = "; ".join(changes)
        rows.append(
            _row(
                h,
                entity="Inschrijving",
                entity_id=h.registration_id,
                summary=_with_more(summary, db, h),
                group="Inschrijvingen",
                subject=subj.from_registration(h.registration_id),
            )
        )
    for h in db.query(RegistrationItemHistory).filter(
        RegistrationItemHistory.recorded_at >= since_dt
    ):
        rows.append(
            _row(
                h,
                entity="Bestelregel",
                entity_id=h.registration_item_id,
                summary=_with_more(
                    f"product #{_fmt(h.product_id)} ×{_fmt(h.quantity)} "
                    f"(inschrijving #{_fmt(h.registration_id)})",
                    db,
                    h,
                ),
                group="Inschrijvingen",
                subject=subj.from_registration(h.registration_id),
            )
        )
    for h in db.query(PaymentRecordHistory).filter(PaymentRecordHistory.recorded_at >= since_dt):
        rows.append(
            _row(
                h,
                entity="Betaling",
                entity_id=None,
                summary=_with_more(
                    f"{_fmt(h.type)} €{_fmt(h.amount)} {_fmt(h.method)}/{_fmt(h.status)} "
                    f"({_fmt(h.payable_type)} #{_fmt(h.payable_id)})",
                    db,
                    h,
                ),
                group="Betalingen",
                subject=subj.from_payment(h.payable_type, h.payable_id),
            )
        )

    if group:
        rows = [r for r in rows if r["group"] == group]
    if actor:
        rows = [r for r in rows if (r["actor"] or "") == actor]
    rows.sort(key=lambda r: r["recorded_at"], reverse=True)
    return rows


def build_member_changes_ods(rows: List[dict]) -> bytes:
    headers = [
        _("Tijdstip"),
        _("Wat"),
        _("Type"),
        _("ID"),
        _("Naam persoon"),
        _("Adres hoofdlid"),
        _("Externe ID persoon"),
        _("Externe ID hoofdlid"),
        _("Actie"),
        _("Door"),
        _("Details"),
    ]
    data = []
    for r in rows:
        ts = r["recorded_at"]
        ts_str = moment_text(ts, "%Y-%m-%d %H:%M")
        data.append(
            [
                ts_str,
                r["operation_label"],
                r["entity"],
                "" if r["entity_id"] is None else str(r["entity_id"]),
                r.get("person_name", ""),
                r.get("head_address", ""),
                r.get("person_external_id", ""),
                r.get("head_external_id", ""),
                r["action"],
                r["actor"] or "",
                r["summary"],
            ]
        )
    return build_ods(
        "Ledenwijzigingen",
        headers,
        data,
        col_widths=[4.0, 3.0, 3.5, 2.0, 7.0, 12.0, 4.5, 4.5, 6.5, 6.5, 14.0],
    )
