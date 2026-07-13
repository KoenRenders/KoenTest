"""Snapshot-helpers die een momentopname van een bron-rij in de bijbehorende
history-tabel wegschrijven.

Elke helper doet enkel ``db.add(...)`` en GEEN commit: de history-rij commit mee
in dezelfde transactie als de wijziging zelf (atomair — of allebei, of geen van
beide). Roep de helper dus aan vóór de ``db.commit()`` van de caller, en bij een
verwijdering vóór de ``db.delete(...)`` zodat de bron nog uitleesbaar is.
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.domains.payment.api import PaymentRecordHistory
from app.models.history import (
    MembershipHistory,
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


def snapshot_person(db: Session, person, *, operation: str, action: str,
                    source: str, actor: Optional[str] = None) -> None:
    db.add(PersonHistory(
        person_id=person.id,
        last_name=person.last_name,
        first_name=person.first_name,
        date_of_birth=person.date_of_birth,
        gender_code=person.gender_code,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_member(db: Session, member, *, operation: str, action: str,
                    source: str, actor: Optional[str] = None) -> None:
    db.add(MemberHistory(
        member_id=member.id,
        board_member_id=member.board_member_id,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_member_person(db: Session, mp, *, operation: str, action: str,
                           source: str, actor: Optional[str] = None) -> None:
    db.add(MemberPersonHistory(
        member_person_id=mp.id,
        member_id=mp.member_id,
        person_id=mp.person_id,
        relation_type=mp.relation_type,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_membership(db: Session, membership, *, operation: str, action: str,
                        source: str, actor: Optional[str] = None) -> None:
    db.add(MembershipHistory(
        membership_id=membership.id,
        member_id=membership.member_id,
        year=membership.year,
        is_active=membership.is_active,
        valid_from=membership.valid_from,
        valid_to=membership.valid_to,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_address(db: Session, address, *, operation: str, action: str,
                     source: str, actor: Optional[str] = None) -> None:
    db.add(AddressHistory(
        address_id=address.id,
        person_id=address.person_id,
        street=address.street,
        house_number=address.house_number,
        bus_number=address.bus_number,
        postal_code_id=address.postal_code_id,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_contact_detail(db: Session, contact, *, operation: str, action: str,
                            source: str, actor: Optional[str] = None) -> None:
    db.add(ContactDetailHistory(
        contact_detail_id=contact.id,
        person_id=contact.person_id,
        contact_type_code=contact.contact_type_code,
        value=contact.value,
        is_primary=contact.is_primary,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_registration_item(db: Session, item, *, operation: str, action: str,
                               source: str, actor: Optional[str] = None) -> None:
    db.add(RegistrationItemHistory(
        registration_item_id=item.id,
        registration_id=item.registration_id,
        product_id=item.product_id,
        quantity=item.quantity,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_payment_record(db: Session, record, *, operation: str, action: str,
                            source: str, actor: Optional[str] = None) -> None:
    db.add(PaymentRecordHistory(
        payment_record_id=record.id,
        payable_type=record.payable_type,
        payable_id=record.payable_id,
        amount=record.amount,
        amount_paid=record.amount_paid,
        method=record.method,
        status=record.status,
        type=record.type,
        refund_of_id=record.refund_of_id,
        gateway_payment_id=record.gateway_payment_id,
        note=record.note,
        paid_at=record.paid_at,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_activity(db: Session, activity, *, operation: str, action: str,
                      source: str, actor: Optional[str] = None) -> None:
    db.add(ActivityHistory(
        activity_id=activity.id,
        name=activity.name,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_activity_date(db: Session, ad, *, operation: str, action: str,
                           source: str, actor: Optional[str] = None) -> None:
    db.add(ActivityDateHistory(
        activity_date_id=ad.id,
        activity_id=ad.activity_id,
        start_date=ad.start_date,
        end_date=ad.end_date,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_component(db: Session, comp, *, operation: str, action: str,
                       source: str, actor: Optional[str] = None) -> None:
    db.add(ComponentHistory(
        component_id=comp.id,
        activity_id=comp.activity_id,
        name=comp.name,
        price=comp.price,
        member_price=comp.member_price,
        operation=operation, action=action, source=source, actor=actor,
    ))


def snapshot_product(db: Session, product, *, operation: str, action: str,
                     source: str, actor: Optional[str] = None) -> None:
    db.add(ProductHistory(
        product_id=product.id,
        component_id=product.component_id,
        name=product.name,
        price=product.price,
        member_price=product.member_price,
        operation=operation, action=action, source=source, actor=actor,
    ))
