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

#: De Nederlandse woorden komen LETTERLIJK uit `admin_ui.veldtype_labels`, het
#: woordenboek dat de form-builder tot nu toe vulde — §B8.5 vraagt dezelfde
#: woorden als voordien. De cataloog van §B5.3 stelde er andere voor ("Tekst",
#: "Tekstvak", "Keuzerondjes"); die waren afgeleid van de codenamen en niet van
#: het scherm. Het scherm wint, en dat is een bevinding voor het CR.
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
    # `info` stond niet in dat woordenboek — een infoblok is geen keuze in de
    # bouwer — dus hier komt het woord wél uit de cataloog.
    CodeSeed(code="info", nl="Infotekst", en="Info text", sort_order=90),
    CodeSeed(code="phone", nl="Telefoonnummer", en="Phone number", sort_order=100),
)

FIELD_TYPE = CodeList(
    name="field_type", schema="form",
    codes=FieldTypeCode, labels=FieldTypeLabel, enum=FieldType,
    fk_from=("form.form_fields.field_type",),
)
