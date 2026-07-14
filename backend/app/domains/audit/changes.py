"""Overzicht/export van alle ledendata-wijzigingen sinds een datum (#82).

Raak Nationaal heeft geen API; wijzigingen in dit portaal moeten manueel
overgetypt worden. Dit leest de append-only history-tabellen (recorded_at >=
since) en levert per wijziging een leesbare regel, zodat de admin ze één voor één
kan overnemen. Bevat persoonsdata: admin-only, nooit in de repo.
(verhuisd uit app/services/member_changes.py, #444)
"""
from datetime import date, datetime, time, timezone
from io import BytesIO
from typing import List, Optional

from sqlalchemy.orm import Session

from app.i18n import _
from app.kernel.ods import build_ods

from app.domains.payment.api import PaymentRecordHistory
from app.domains.membership.api import MembershipHistory
from app.domains.activities.api import (
    RegistrationItemHistory,
    ActivityHistory,
    ActivityDateHistory,
    ComponentHistory,
    ProductHistory,
)
from app.domains.mdm.api import (
    PersonHistory,
    MemberHistory,
    MemberPersonHistory,
    AddressHistory,
    ContactDetailHistory,
)

_OPERATION_LABELS = {"insert": "Toegevoegd", "update": "Gewijzigd", "delete": "Verwijderd"}


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
        """"2400 Mol" voor een postcode-id (i.p.v. de nietszeggende id)."""
        if postal_code_id is None:
            return ""
        if postal_code_id not in self._pc:
            from app.domains.mdm.api import PostalCode
            pc = self._q(PostalCode).filter(PostalCode.id == postal_code_id).first()
            self._pc[postal_code_id] = f"{_fmt(pc.postal_code)} {_fmt(pc.municipality)}".strip() if pc else ""
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
            en = (self._q(ExternalNumber)
                  .filter(ExternalNumber.person_id == person_id)
                  .order_by(ExternalNumber.id).first())
            self._ext[person_id] = _fmt(en.external_id) if en else ""
        return self._ext[person_id]

    def _addr_of(self, person_id):
        if person_id is None:
            return ""
        if person_id not in self._addr:
            from app.domains.mdm.api import Address
            from app.domains.mdm.api import PostalCode
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
            mp = (self._q(MemberPerson)
                  .filter(MemberPerson.member_id == member_id,
                          MemberPerson.relation_type == "HOOFDLID").first())
            self._head_of_member[member_id] = mp.person_id if mp else None
        return self._head_of_member[member_id]

    def _person_by_email(self, email):
        """Person-id achter een e-mailadres (gast-inschrijving zonder gekoppeld lid)."""
        if not email:
            return None
        from sqlalchemy import func
        from app.domains.mdm.api import ContactDetail
        cd = (self._q(ContactDetail)
              .filter(func.lower(ContactDetail.value) == email.strip().lower(),
                      ContactDetail.contact_type_code == "EMAIL").first())
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
        return {"person_name": _fmt(reg.contact_name), "person_external_id": "",
                "head_address": "", "head_external_id": ""}

    def from_payment(self, payable_type, payable_id) -> Optional[dict]:
        """Verrijking voor een betaling-wijziging: via de inschrijving of het
        lidmaatschap waar de betaling aan hangt."""
        if payable_type == "registration":
            return self.from_registration(payable_id)
        if payable_type == "membership":
            from app.domains.membership.api import Membership
            ms = self._q(Membership).filter(Membership.id == payable_id).first()
            if ms is not None:
                return self.fields(member_id=ms.member_id)
        return None


_EMPTY_SUBJECT = {
    "person_name": "", "person_external_id": "", "head_address": "", "head_external_id": "",
}


def _row(h, *, entity: str, entity_id: Optional[int], summary: str, group: str = "Leden",
         subject: Optional[dict] = None) -> dict:
    return {
        "recorded_at": h.recorded_at,
        "group": group,
        "entity": entity,
        "entity_id": entity_id,
        "operation": h.operation,
        "operation_label": _(_OPERATION_LABELS.get(h.operation, h.operation)),
        "action": h.action,
        "actor": h.actor,
        "summary": summary,
        **(subject or _EMPTY_SUBJECT),
    }


def member_changes_since(db: Session, since: date) -> List[dict]:
    """Alle ledendata-wijzigingen met recorded_at >= since, nieuw → oud."""
    since_dt = datetime.combine(since, time.min, tzinfo=timezone.utc)
    rows: List[dict] = []
    subj = _SubjectResolver(db)

    for h in db.query(PersonHistory).filter(PersonHistory.recorded_at >= since_dt):
        if h.action == "person_revived":
            # Heractivering bij her-import (#227): de naam staat al in de eigen kolom.
            rows.append(_row(h, entity="Persoon", entity_id=h.person_id,
                             summary="Heractivering", subject=subj.fields(person_id=h.person_id)))
            continue
        if h.action == "lidnr_attached":
            # Identiteitsmatch (#192): lidnummer gehecht aan een bestaand lid (#229).
            rows.append(_row(h, entity="Persoon", entity_id=h.person_id,
                             summary="Lidnummer gekoppeld", subject=subj.fields(person_id=h.person_id)))
            continue
        naam = f"{_fmt(h.first_name)} {_fmt(h.last_name)}".strip() or "—"
        dob = f" (geb. {h.date_of_birth})" if h.date_of_birth else ""
        summary = f"{naam}{dob}"
        if h.operation == "update":
            prev = (db.query(PersonHistory)
                    .filter(PersonHistory.person_id == h.person_id,
                            PersonHistory.recorded_at < h.recorded_at)
                    .order_by(PersonHistory.recorded_at.desc()).first())
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
        rows.append(_row(h, entity="Persoon", entity_id=h.person_id, summary=summary,
                         subject=subj.fields(person_id=h.person_id)))

    for h in db.query(MemberHistory).filter(MemberHistory.recorded_at >= since_dt):
        if h.action == "member_revived":
            summary = "Heractivering gezin"
        elif h.action in ("board_member_assigned", "board_member_imported"):
            # Toon wíé het (nieuwe) verantwoordelijke bestuurslid is i.p.v. enkel "Gezin".
            naam = subj._name_of(h.board_member_id)
            summary = f"Bestuurslid: {naam}" if naam else "Bestuurslid gewijzigd"
        else:
            summary = "Gezin"
        rows.append(_row(h, entity="Gezin", entity_id=h.member_id, summary=summary,
                         subject=subj.fields(member_id=h.member_id)))

    for h in db.query(MemberPersonHistory).filter(MemberPersonHistory.recorded_at >= since_dt):
        rows.append(_row(
            h, entity="Gezinslid", entity_id=h.member_person_id,
            summary=f"In gezin als {_fmt(h.relation_type)}",
            subject=subj.fields(person_id=h.person_id, member_id=h.member_id),
        ))

    for h in db.query(AddressHistory).filter(AddressHistory.recorded_at >= since_dt):
        adres = _addr_text(h.street, h.house_number, h.bus_number)
        body = adres
        if h.operation == "update":
            prev = (db.query(AddressHistory)
                    .filter(AddressHistory.address_id == h.address_id,
                            AddressHistory.recorded_at < h.recorded_at)
                    .order_by(AddressHistory.recorded_at.desc()).first())
            if prev is not None:
                prev_adres = _addr_text(prev.street, prev.house_number, prev.bus_number)
                if prev_adres != adres:
                    body = f"{prev_adres} → {adres}"
        pc = subj.postcode_label(h.postal_code_id)
        summary = f"{body}, {pc}" if pc else body
        rows.append(_row(
            h, entity="Adres", entity_id=h.address_id,
            summary=summary,
            subject=subj.fields(person_id=h.person_id),
        ))

    for h in db.query(ContactDetailHistory).filter(ContactDetailHistory.recorded_at >= since_dt):
        # Bij een wijziging "oud → nieuw" tonen door de vorige snapshot van ditzelfde
        # contact op te zoeken (#188).
        value_part = _fmt(h.value)
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
                value_part = f"{_fmt(prev.value)} → {_fmt(h.value)}"
        rows.append(_row(
            h, entity="Contact", entity_id=h.contact_detail_id,
            summary=f"{_fmt(h.contact_type_code)}: {value_part}",
            subject=subj.fields(person_id=h.person_id),
        ))

    for h in db.query(MembershipHistory).filter(MembershipHistory.recorded_at >= since_dt):
        rows.append(_row(
            h, entity="Lidmaatschap", entity_id=h.membership_id,
            summary=f"jaar {_fmt(h.year)}, actief={_fmt(h.is_active)}, {_fmt(h.valid_from)}–{_fmt(h.valid_to)}",
            subject=subj.fields(member_id=h.member_id),
        ))

    rows.sort(key=lambda r: r["recorded_at"], reverse=True)
    return rows


# Objectgroepen voor de filter op de Wijzigingen-pagina (#189).
GROUPS = ["Leden", "Activiteiten", "Inschrijvingen", "Betalingen"]


def all_changes_since(
    db: Session, since: date, *, group: Optional[str] = None, actor: Optional[str] = None
) -> List[dict]:
    """Unified audit-feed (#189): alle history-tabellen sinds ``since``, met een
    objectgroep per rij; optioneel gefilterd op groep en/of actor. Nieuw → oud."""
    since_dt = datetime.combine(since, time.min, tzinfo=timezone.utc)
    rows: List[dict] = list(member_changes_since(db, since))  # groep "Leden"
    subj = _SubjectResolver(db)

    for h in db.query(ActivityHistory).filter(ActivityHistory.recorded_at >= since_dt):
        rows.append(_row(h, entity="Activiteit", entity_id=h.activity_id,
                         summary=_fmt(h.name) or f"activiteit #{_fmt(h.activity_id)}",
                         group="Activiteiten"))
    for h in db.query(ActivityDateHistory).filter(ActivityDateHistory.recorded_at >= since_dt):
        rows.append(_row(h, entity="Datum", entity_id=h.activity_date_id,
                         summary=f"{_fmt(h.start_date)}–{_fmt(h.end_date)} (activiteit #{_fmt(h.activity_id)})",
                         group="Activiteiten"))
    for h in db.query(ComponentHistory).filter(ComponentHistory.recorded_at >= since_dt):
        rows.append(_row(h, entity="Onderdeel", entity_id=h.component_id,
                         summary=f"{_fmt(h.name)} (activiteit #{_fmt(h.activity_id)})",
                         group="Activiteiten"))
    for h in db.query(ProductHistory).filter(ProductHistory.recorded_at >= since_dt):
        rows.append(_row(h, entity="Product", entity_id=h.product_id,
                         summary=f"{_fmt(h.name)} €{_fmt(h.price)} (onderdeel #{_fmt(h.component_id)})",
                         group="Activiteiten"))
    for h in db.query(RegistrationItemHistory).filter(RegistrationItemHistory.recorded_at >= since_dt):
        rows.append(_row(h, entity="Bestelregel", entity_id=h.registration_item_id,
                         summary=f"product #{_fmt(h.product_id)} ×{_fmt(h.quantity)} (inschrijving #{_fmt(h.registration_id)})",
                         group="Inschrijvingen",
                         subject=subj.from_registration(h.registration_id)))
    for h in db.query(PaymentRecordHistory).filter(PaymentRecordHistory.recorded_at >= since_dt):
        rows.append(_row(h, entity="Betaling", entity_id=None,
                         summary=f"{_fmt(h.type)} €{_fmt(h.amount)} {_fmt(h.method)}/{_fmt(h.status)} ({_fmt(h.payable_type)} #{_fmt(h.payable_id)})",
                         group="Betalingen",
                         subject=subj.from_payment(h.payable_type, h.payable_id)))

    if group:
        rows = [r for r in rows if r["group"] == group]
    if actor:
        rows = [r for r in rows if (r["actor"] or "") == actor]
    rows.sort(key=lambda r: r["recorded_at"], reverse=True)
    return rows


def build_member_changes_ods(rows: List[dict]) -> bytes:
    headers = [
        _("Tijdstip"), _("Wat"), _("Type"), _("ID"), _("Naam persoon"), _("Adres hoofdlid"),
        _("Externe ID persoon"), _("Externe ID hoofdlid"), _("Actie"), _("Door"), _("Details"),
    ]
    data = []
    for r in rows:
        ts = r["recorded_at"]
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else ""
        data.append([
            ts_str, r["operation_label"], r["entity"],
            "" if r["entity_id"] is None else str(r["entity_id"]),
            r.get("person_name", ""), r.get("head_address", ""),
            r.get("person_external_id", ""), r.get("head_external_id", ""),
            r["action"], r["actor"] or "", r["summary"],
        ])
    return build_ods("Ledenwijzigingen", headers, data,
                     col_widths=[4.0, 3.0, 3.5, 2.0, 7.0, 12.0, 4.5, 4.5, 6.5, 6.5, 14.0])
