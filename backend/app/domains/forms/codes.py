"""The code lists the forms domain owns (CR-12 phase 4).

Two lists that were module tuples in `models.py`, each with a `CHECK` beside
it. The field type's check comes from migration 062 and says exactly what the
new foreign key says, so it goes; the status never had one.

**The rating scale is not here, on purpose** (§B4.10). `RATING_LABELS` maps
1..5 to *Zeer slecht* … *Zeer goed*: a Likert scale, not a vocabulary. It is
copy and stays behind `_()`.
"""
from app.domains.forms.models import (
    FieldType,
    FieldTypeCode,
    FieldTypeLabel,
    FormStatus,
    FormStatusCode,
    FormStatusLabel,
)
from app.kernel.codes import CodeList, CodeSeed

FORM_STATUS_CODES = (
    CodeSeed(code="draft", nl="Concept", en="Draft", sort_order=10),
    CodeSeed(code="open", nl="Open", en="Open", sort_order=20),
    CodeSeed(code="closed", nl="Gesloten", en="Closed", sort_order=30),
)

FORM_STATUS = CodeList(
    name="form_status", schema="form",
    codes=FormStatusCode, labels=FormStatusLabel, enum=FormStatus,
    fk_from=("form.forms.status",),
)

#: The Dutch words come LITERALLY from `admin_ui.veldtype_labels`, the
#: dictionary that filled the form builder until now — §B8.5 asks for the same
#: words as before. The catalogue of §B5.3 proposed others ("Tekst",
#: "Tekstvak", "Keuzerondjes"); those were derived from the code names, not
#: from the screen. The screen wins, and that is a finding for the CR.
FIELD_TYPE_CODES = (
    CodeSeed(code="text", nl="Korte tekst", en="Short text", sort_order=10),
    CodeSeed(code="textarea", nl="Lange tekst", en="Long text", sort_order=20),
    CodeSeed(code="number", nl="Getal", en="Number", sort_order=30),
    CodeSeed(code="email", nl="E-mailadres", en="E-mail address", sort_order=40),
    CodeSeed(code="select", nl="Keuzelijst", en="Dropdown", sort_order=50),
    CodeSeed(code="radio", nl="Eén keuze", en="One choice", sort_order=60),
    CodeSeed(code="checkbox", nl="Meerdere keuzes", en="Several choices",
             sort_order=70),
    CodeSeed(code="rating", nl="Score", en="Score", sort_order=80),
    # `info` was not in that dictionary — an info block is not a choice in the
    # builder — so here the word does come from the catalogue.
    CodeSeed(code="info", nl="Infotekst", en="Info text", sort_order=90),
    CodeSeed(code="phone", nl="Telefoonnummer", en="Phone number", sort_order=100),
)

FIELD_TYPE = CodeList(
    name="field_type", schema="form",
    codes=FieldTypeCode, labels=FieldTypeLabel, enum=FieldType,
    fk_from=("form.form_fields.field_type",),
)
