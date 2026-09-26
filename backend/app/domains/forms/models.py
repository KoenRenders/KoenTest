from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    SmallInteger,
    String,
    Text,
    Boolean,
    DateTime,
    Numeric,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import EnumColumn
from app.kernel.tenancy import TenantMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class FieldType(Enum):
    """Welk soort veld dit is; de rendering en de export vertakken erop.

    CR-12 fase 4: was het tupel `FIELD_TYPES` plus de CHECK van migratie 062.
    Die CHECK gaat weg — de foreign key zegt hetzelfde. Bewust geen `date`
    (nog niet nodig).
    """

    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    EMAIL = "email"
    SELECT = "select"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    RATING = "rating"
    INFO = "info"      # louter informatief tekstblok, geen antwoord (#335)
    PHONE = "phone"    # gsm/telefoon met lichte validatie (#344)


class FormStatus(Enum):
    """draft (in opbouw) → open (publiek invulbaar) → closed (dicht)."""

    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


#: Achterwaartse namen voor wie het tupel verwachtte. Ze leiden af uit de enum,
#: zodat er één bron is (CLAUDE.md: twee plaatsen voor één feit is de bug).
FIELD_TYPES = tuple(m.value for m in FieldType)
FORM_STATUSES = tuple(m.value for m in FormStatus)

# Rating is een vast 5-punts Likert: 1 = zeer slecht ... 5 = zeer goed.
RATING_MIN = 1
RATING_MAX = 5
RATING_LABELS = {
    1: "Zeer slecht",
    2: "Slecht",
    3: "Neutraal",
    4: "Goed",
    5: "Zeer goed",
}


class Form(TenantMixin, Base):
    __tablename__ = "forms"
    __table_args__ = {"schema": "form"}

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    # Niet-raadbare deellink-sleutel; de publieke URL is /formulier/<share_token>.
    share_token = Column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[FormStatus] = mapped_column(
        EnumColumn(FormStatus, length=20),
        ForeignKey("form.form_status_codes.code"), nullable=False,
        default=FormStatus.DRAFT)
    requires_login = Column(Boolean, nullable=False, default=False)
    max_submissions = Column(Integer, nullable=True)
    # Bevestigingsmail na inzending (enkel als er een e-mailadres is).
    send_confirmation = Column(Boolean, nullable=False, default=False)
    confirmation_message = Column(Text, nullable=True)
    # Sta wijzigen-na-indienen toe via een edit_token-link.
    allow_edit = Column(Boolean, nullable=False, default=False)
    # Anoniem (#343): geen contactblok, geen bevestigingsmail, geen submitter bewaard.
    is_anonymous = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    fields = relationship(
        "FormField",
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="FormField.position, FormField.id",
    )
    sections = relationship(
        "FormSection",
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="FormSection.position, FormSection.id",
    )
    submissions = relationship(
        "FormSubmission", back_populates="form", cascade="all, delete-orphan"
    )


class FormSection(TenantMixin, Base):
    __tablename__ = "form_sections"
    __table_args__ = {"schema": "form"}

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(
        Integer, ForeignKey("form.forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(300), nullable=True)
    description = Column(Text, nullable=True)
    position = Column(Integer, nullable=False, default=0)
    # Sectie-navigatie (#336): waar na deze sectie naartoe als geen keuze-optie
    # een sprong forceert. NULL + next_is_end=false = lineair (volgende sectie).
    next_section_id = Column(
        Integer, ForeignKey("form.form_sections.id", ondelete="SET NULL"), nullable=True
    )
    next_is_end = Column(Boolean, nullable=False, default=False, server_default="false")

    form = relationship("Form", back_populates="sections")
    next_section = relationship("FormSection", remote_side=[id])


class FormField(TenantMixin, Base):
    __tablename__ = "form_fields"
    __table_args__ = {"schema": "form"}

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(
        Integer, ForeignKey("form.forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optionele koppeling aan een sectie (#335). NULL = ongegroepeerd.
    section_id = Column(
        Integer, ForeignKey("form.form_sections.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_type: Mapped[FieldType] = mapped_column(
        EnumColumn(FieldType, length=20),
        ForeignKey("form.field_type_codes.code"), nullable=False)
    label = Column(String(300), nullable=False)
    help_text = Column(Text, nullable=True)
    required = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    # Validatie als kolommen (geen JSON).
    min_value = Column(Numeric(12, 2), nullable=True)
    max_value = Column(Numeric(12, 2), nullable=True)
    min_length = Column(Integer, nullable=True)
    max_length = Column(Integer, nullable=True)
    regex_pattern = Column(Text, nullable=True)
    # Configureerbare rating-schaal (#341). Aantal punten (default 5) + optionele
    # eindpunt-labels. Leeg + 5 punten → de standaard "zeer slecht → zeer goed".
    rating_max = Column(Integer, nullable=True)
    rating_low_label = Column(String(100), nullable=True)
    rating_high_label = Column(String(100), nullable=True)

    form = relationship("Form", back_populates="fields")
    section = relationship("FormSection")
    options = relationship(
        "FormFieldOption",
        back_populates="field",
        cascade="all, delete-orphan",
        order_by="FormFieldOption.position, FormFieldOption.id",
    )


class FormFieldOption(TenantMixin, Base):
    __tablename__ = "form_field_options"
    __table_args__ = {"schema": "form"}

    id = Column(Integer, primary_key=True, index=True)
    field_id = Column(
        Integer,
        ForeignKey("form.form_fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(300), nullable=False)
    value = Column(String(300), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    # "Andere…"-optie: bij selectie kan de respondent vrije tekst invullen (#337).
    # Die tekst wordt bewaard als value_text op de antwoordrij naast value_option_id.
    is_other = Column(Boolean, nullable=False, default=False, server_default="false")
    # Branching (#336): bij een radio/select-veld kan een optie de invuller naar een
    # andere sectie sturen, of naar het einde. Enkel voor 'één keuze'/'keuzelijst'.
    skip_to_section_id = Column(
        Integer, ForeignKey("form.form_sections.id", ondelete="SET NULL"), nullable=True
    )
    skip_to_end = Column(Boolean, nullable=False, default=False, server_default="false")

    field = relationship("FormField", back_populates="options")
    skip_to_section = relationship("FormSection")


class FormSubmission(TenantMixin, Base):
    __tablename__ = "form_submissions"
    __table_args__ = {"schema": "form"}

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(
        Integer, ForeignKey("form.forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)
    # Bewust vrije tekst, geen FK naar Person/Member (loose coupling).
    submitter_name = Column(String(200), nullable=True)
    submitter_email = Column(String(255), nullable=True)
    # Niet-raadbare sleutel voor de "wijzig je antwoord"-link (enkel bij allow_edit).
    edit_token = Column(String(64), nullable=True, unique=True, index=True)

    form = relationship("Form", back_populates="submissions")
    answers = relationship(
        "FormSubmissionAnswer",
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class FormSubmissionAnswer(TenantMixin, Base):
    __tablename__ = "form_submission_answers"
    __table_args__ = {"schema": "form"}

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(
        Integer,
        ForeignKey("form.form_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_id = Column(
        Integer,
        ForeignKey("form.form_fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Getypeerde kolommen i.p.v. JSON. Per antwoord is precies één waardekolom
    # gevuld, afhankelijk van het veldtype. Meervoudige checkbox = meerdere rijen.
    value_text = Column(Text, nullable=True)
    value_number = Column(Numeric(12, 2), nullable=True)
    value_option_id = Column(
        Integer, ForeignKey("form.form_field_options.id", ondelete="SET NULL"), nullable=True
    )
    value_rating = Column(SmallInteger, nullable=True)

    submission = relationship("FormSubmission", back_populates="answers")
    field = relationship("FormField")
    option = relationship("FormFieldOption")


class FormStatusCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "form_status_codes"
    __table_args__ = {"schema": "form"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class FormStatusLabel(Base):
    """The word a screen shows for this code, per language (CR-12 phase 4)."""

    __tablename__ = "form_status_labels"
    __table_args__ = {"schema": "form"}

    code = Column(String(20), ForeignKey("form.form_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class FieldTypeCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "field_type_codes"
    __table_args__ = {"schema": "form"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class FieldTypeLabel(Base):
    """The word a screen shows for this code, per language (CR-12 phase 4)."""

    __tablename__ = "field_type_labels"
    __table_args__ = {"schema": "form"}

    code = Column(String(20), ForeignKey("form.field_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)
