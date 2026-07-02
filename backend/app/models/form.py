from datetime import datetime, timezone

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
from sqlalchemy.orm import relationship

from app.database import Base


# Toegestane veldtypes — houd in sync met de CHECK in migratie 062 en met de
# rendering op de frontend. Bewust geen 'date' (nog niet nodig).
FIELD_TYPES = (
    "text",
    "textarea",
    "number",
    "email",
    "select",
    "radio",
    "checkbox",
    "rating",
    "info",  # louter informatief tekstblok, geen antwoord (#335)
    "phone",  # gsm/telefoon met lichte validatie (#344)
)

# Een formulier doorloopt: draft (in opbouw) -> open (publiek invulbaar) ->
# closed (geen nieuwe/gewijzigde inzendingen meer).
FORM_STATUSES = ("draft", "open", "closed")

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


class Form(Base):
    __tablename__ = "forms"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    # Niet-raadbare deellink-sleutel; de publieke URL is /formulier/<share_token>.
    share_token = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="draft")
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
        order_by="FormField.position",
    )
    sections = relationship(
        "FormSection",
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="FormSection.position",
    )
    submissions = relationship(
        "FormSubmission", back_populates="form", cascade="all, delete-orphan"
    )


class FormSection(Base):
    __tablename__ = "form_sections"

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(
        Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(300), nullable=True)
    description = Column(Text, nullable=True)
    position = Column(Integer, nullable=False, default=0)
    # Sectie-navigatie (#336): waar na deze sectie naartoe als geen keuze-optie
    # een sprong forceert. NULL + next_is_end=false = lineair (volgende sectie).
    next_section_id = Column(
        Integer, ForeignKey("form_sections.id", ondelete="SET NULL"), nullable=True
    )
    next_is_end = Column(Boolean, nullable=False, default=False, server_default="false")

    form = relationship("Form", back_populates="sections")
    next_section = relationship("FormSection", remote_side=[id])


class FormField(Base):
    __tablename__ = "form_fields"

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(
        Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optionele koppeling aan een sectie (#335). NULL = ongegroepeerd.
    section_id = Column(
        Integer, ForeignKey("form_sections.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_type = Column(String(20), nullable=False)
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
        order_by="FormFieldOption.position",
    )


class FormFieldOption(Base):
    __tablename__ = "form_field_options"

    id = Column(Integer, primary_key=True, index=True)
    field_id = Column(
        Integer,
        ForeignKey("form_fields.id", ondelete="CASCADE"),
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
        Integer, ForeignKey("form_sections.id", ondelete="SET NULL"), nullable=True
    )
    skip_to_end = Column(Boolean, nullable=False, default=False, server_default="false")

    field = relationship("FormField", back_populates="options")
    skip_to_section = relationship("FormSection")


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(
        Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True
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


class FormSubmissionAnswer(Base):
    __tablename__ = "form_submission_answers"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(
        Integer,
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_id = Column(
        Integer,
        ForeignKey("form_fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Getypeerde kolommen i.p.v. JSON. Per antwoord is precies één waardekolom
    # gevuld, afhankelijk van het veldtype. Meervoudige checkbox = meerdere rijen.
    value_text = Column(Text, nullable=True)
    value_number = Column(Numeric(12, 2), nullable=True)
    value_option_id = Column(
        Integer, ForeignKey("form_field_options.id", ondelete="SET NULL"), nullable=True
    )
    value_rating = Column(SmallInteger, nullable=True)

    submission = relationship("FormSubmission", back_populates="answers")
    field = relationship("FormField")
    option = relationship("FormFieldOption")
