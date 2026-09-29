"""Lidmaatschappen (membership-component, fase 4a #402 — §5.4).

Schema ``membership``. ``member_id`` is een soft-ref naar mdm.members (§6/§8):
de FK is in migratie 078 gedropt; de ORM-relatie (via backref op Member) blijft
voor intern gemak, maar de DB legt de koppeling niet meer vast.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import backref, relationship

from app.database import Base
from app.kernel.rules import aggregate
from app.kernel.tenancy import TenantMixin
from app.kernel.validity_period import ValidityPeriod
from app.soft_delete import SoftDeleteMixin


class MembershipError(ValueError):
    """A rule of this component was violated (CR-13 phase 3, §B4.4).

    Not an HTTPException: that belongs to the entrance, not to the rule. English, one
    class for the domain. The #681 error is not this one: that rule is about a
    person in a household and lives on `mdm`'s household link.
    """


@aggregate
class Membership(TenantMixin, SoftDeleteMixin, Base):
    """Annual membership record per member household (CR-13 phase 3, #1250).

    Its rules, each at its address (§B4.2):

    - **several fields, already loaded** — `check()`: a membership cannot end
      before it begins. Both ends are optional (the import writes a membership
      without dates), so the rule speaks only when both are there. It runs on
      every flush through the kernel's listener;
    - **at rest** — `ck_memberships_valid_period`, migration 172;
    - **the question every screen asks** — `valid_on(day)`: active, and the day
      within the period. The member price, the family portal and the member list
      asked it each in their own words (`valid_from <= day <= valid_to`, a loop
      per caller); the object answers it once, through `ValidityPeriod`.
    """

    __tablename__ = "memberships"
    # CR-13 phase 3 (§B5.2): what `check()` says, at rest too — the same rule as
    # migration 172, which is where the environments get it.
    __table_args__ = (
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
            name="ck_memberships_valid_period",
        ),
        {"schema": "membership"},
    )

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("mdm.members.id"), nullable=False)
    year = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Geldigheidsperiode: gezet zodra de betaling bevestigd is.
    # valid_from = betaaldatum; valid_to = 31 dec dit of volgend jaar (zie service).
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    member = relationship("Member", backref=backref("memberships", cascade="all, delete-orphan"))

    def period(self) -> ValidityPeriod | None:
        """The period this membership is valid, or None while it has no dates."""
        if self.valid_from is None or self.valid_to is None:
            return None
        return ValidityPeriod(self.valid_from, self.valid_to)

    def valid_on(self, day: date) -> bool:
        """Active, and `day` within the period (#111) — the member-price question."""
        period = self.period()
        return bool(self.is_active) and period is not None and period.contains(day)

    def check(self) -> None:
        """A membership cannot end before it begins. Reads only its own fields."""
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_to < self.valid_from:
                from app.i18n import _

                raise MembershipError(_("Een lidmaatschap kan niet eindigen voor het begint."))


class HistoryMixin:
    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)
    action = Column(String(40), nullable=False)
    source = Column(String(30), nullable=False)
    actor = Column(String(255), nullable=True)
    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class MembershipHistory(TenantMixin, HistoryMixin, Base):
    __tablename__ = "membership_history"
    __table_args__ = {"schema": "membership"}

    membership_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    year = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
