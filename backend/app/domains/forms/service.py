"""Service-laag van het forms-component.

Twee lagen domeinlogica:

1. **Inzendingen** (#327): de *betekenis*-validatie van antwoorden tegen het
   opgeslagen veldschema (required, types, min/max, regex, geldige opties), los
   van welke router de service aanroept. De router doet enkel vorm (Pydantic) +
   HTTP.
2. **De formulierdefinitie zelf** (#635 D). Die regels stonden in `router.py`,
   deels als **private** helpers die `admin_ui.py` er dan toch uit importeerde
   (`_apply_fields`, `_validate_form_payload`) — waarmee de JSON-router de facto
   de servicelaag was. Erger: de twee ingangen deden niet hetzelfde. `update_form`
   schreef tien instellingen, `json_import` maar drie, dus een JSON-import verloor
   stilzwijgend `slug`, `requires_login`, `max_submissions`, `send_confirmation`,
   `confirmation_message`, `allow_edit` en `is_anonymous`.

   En de inzendervalidatie stond drie keer: in de router (met de docstring
   "servicelaag-invariant, zodat élke ingang 'm afdwingt") en tóch nog eens inline
   in de twee publieke schermen — terwijl de API-ingang `submit_bericht` hem
   helemaal niet aanriep.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List

from fastapi import HTTPException

from app.domains.forms.models import (FIELD_TYPES, FORM_STATUSES, Form, FormField,
                                      FormFieldOption, FormSection,
                                      FormSubmissionAnswer)
from app.domains.forms.schemas import AnswerIn
from app.i18n import _

# Eenvoudige e-mailcheck (vorm, niet bestaan). Bewust soepel.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _fail(field: FormField, msg: str) -> "HTTPException":
    return HTTPException(status_code=422, detail=f"'{field.label}': {msg}")


def _answers_by_field(payload_answers: List[AnswerIn]) -> Dict[int, AnswerIn]:
    by_field: Dict[int, AnswerIn] = {}
    for a in payload_answers:
        by_field[a.field_id] = a
    return by_field


def _traversed_field_ids(form: Form, by_field: Dict[int, AnswerIn]) -> set:
    """Bepaal server-side welke velden effectief doorlopen zijn, rekening houdend
    met branching (#336). Overgeslagen secties leveren geen verplichting en geen
    antwoord op. Zonder secties → alle velden (ongewijzigd gedrag)."""
    if not form.sections:
        return {f.id for f in form.fields}

    sections_sorted = sorted(form.sections, key=lambda s: (s.position, s.id))
    order = [s.id for s in sections_sorted]
    pos_index = {sid: i for i, sid in enumerate(order)}
    section_by_id = {s.id: s for s in sections_sorted}

    fields_by_section: Dict[int, list] = {}
    ungrouped_ids = set()
    for f in sorted(form.fields, key=lambda x: (x.position, x.id)):
        if f.section_id is None:
            ungrouped_ids.add(f.id)
        else:
            fields_by_section.setdefault(f.section_id, []).append(f)

    opt = {o.id: o for f in form.fields for o in f.options}

    traversed = set(ungrouped_ids)
    i = 0
    guard = 0
    while i < len(order) and guard <= len(order):
        guard += 1
        sid = order[i]
        jump = None  # "end" of een sectie-id
        for f in fields_by_section.get(sid, []):
            traversed.add(f.id)
            if f.field_type not in ("radio", "select"):
                continue
            ans = by_field.get(f.id)
            if not ans or not ans.option_ids:
                continue
            chosen = opt.get(ans.option_ids[0])
            if not chosen:
                continue
            if chosen.skip_to_end:
                jump = "end"
                break
            if chosen.skip_to_section_id is not None:
                jump = chosen.skip_to_section_id
                break
        # Geen keuze-sprong? Val terug op de sectie-navigatie (#336).
        if jump is None:
            sec = section_by_id.get(sid)
            if sec is not None and sec.next_is_end:
                jump = "end"
            elif sec is not None and sec.next_section_id is not None:
                jump = sec.next_section_id
        if jump == "end":
            break
        if isinstance(jump, int) and pos_index.get(jump, -1) > i:
            i = pos_index[jump]
        else:
            i += 1
    return traversed


def build_answers(form: Form, payload_answers: List[AnswerIn]) -> List[FormSubmissionAnswer]:
    """Valideer de antwoorden tegen het veldschema en bouw (losse, niet-gepersisteerde)
    FormSubmissionAnswer-rijen. Gooit HTTPException(422) bij een schending."""
    by_field = _answers_by_field(payload_answers)
    traversed = _traversed_field_ids(form, by_field)
    rows: List[FormSubmissionAnswer] = []

    for field in form.fields:
        # 'info'-velden zijn louter tekst: nooit verplicht, nooit een antwoord.
        if field.field_type == "info":
            continue
        # Overgeslagen (niet-doorlopen) secties: geen verplichting, geen antwoord.
        if field.id not in traversed:
            continue

        ans = by_field.get(field.id)
        option_ids_valid = {o.id for o in field.options}
        other_option_ids = {o.id for o in field.options if o.is_other}
        other_text = (ans.other_text or "").strip() if (ans and ans.other_text) else ""

        text = (ans.text or "").strip() if (ans and ans.text is not None) else ""
        number = ans.number if ans else None
        option_ids = [oid for oid in (ans.option_ids if ans else [])]
        rating = ans.rating if ans else None

        has_value = bool(text) or number is not None or bool(option_ids) or rating is not None

        if field.required and not has_value:
            raise _fail(field, "dit veld is verplicht.")

        if not has_value:
            continue  # optioneel en leeg → geen rij

        ftype = field.field_type

        if ftype in ("text", "textarea", "email", "phone"):
            if field.min_length is not None and len(text) < field.min_length:
                raise _fail(field, f"minstens {field.min_length} tekens.")
            if field.max_length is not None and len(text) > field.max_length:
                raise _fail(field, f"hoogstens {field.max_length} tekens.")
            if ftype == "email" and not _EMAIL_RE.match(text):
                raise _fail(field, "geen geldig e-mailadres.")
            if ftype == "phone":
                digits = re.sub(r"\D", "", text)
                if not (8 <= len(digits) <= 15):
                    raise _fail(field, "geen geldig telefoonnummer.")
            if field.regex_pattern:
                try:
                    if not re.match(field.regex_pattern, text):
                        raise _fail(field, "ongeldig formaat.")
                except re.error:
                    pass  # ongeldige regex in config → niet blokkeren
            rows.append(FormSubmissionAnswer(field_id=field.id, value_text=text))

        elif ftype == "number":
            try:
                num = Decimal(str(number))
            except (InvalidOperation, TypeError):
                raise _fail(field, "geen geldig getal.")
            if field.min_value is not None and num < field.min_value:
                raise _fail(field, f"minimaal {field.min_value}.")
            if field.max_value is not None and num > field.max_value:
                raise _fail(field, f"maximaal {field.max_value}.")
            rows.append(FormSubmissionAnswer(field_id=field.id, value_number=num))

        elif ftype in ("select", "radio"):
            if len(option_ids) > 1:
                raise _fail(field, "kies hoogstens één optie.")
            oid = option_ids[0]
            if oid not in option_ids_valid:
                raise _fail(field, "ongeldige keuze.")
            txt = other_text if oid in other_option_ids and other_text else None
            rows.append(FormSubmissionAnswer(field_id=field.id, value_option_id=oid, value_text=txt))

        elif ftype == "checkbox":
            for oid in option_ids:
                if oid not in option_ids_valid:
                    raise _fail(field, "ongeldige keuze.")
            # Eén rij per aangevinkte optie; "Andere…"-optie krijgt de vrije tekst.
            for oid in option_ids:
                txt = other_text if oid in other_option_ids and other_text else None
                rows.append(FormSubmissionAnswer(field_id=field.id, value_option_id=oid, value_text=txt))

        elif ftype == "rating":
            if rating is None:
                raise _fail(field, "ongeldige beoordeling.")
            try:
                r = int(rating)
            except (TypeError, ValueError):
                raise _fail(field, "ongeldige beoordeling.")
            top = field.rating_max or 5
            if r < 1 or r > top:
                raise _fail(field, f"beoordeling moet tussen 1 en {top} liggen.")
            rows.append(FormSubmissionAnswer(field_id=field.id, value_rating=r))

    return rows


def assert_open_for_submission(db, form: Form) -> None:
    """Bewaak dat het formulier nog open staat én de inzendingslimiet niet bereikt
    is. Gooit HTTPException als indienen niet (meer) mag."""
    from app.domains.forms.models import FormSubmission

    if form.status != "open":
        raise HTTPException(status_code=403, detail=_("Dit formulier staat niet open voor inzendingen."))
    if form.max_submissions is not None:
        count = (
            db.query(FormSubmission)
            .filter(FormSubmission.form_id == form.id)
            .count()
        )
        if count >= form.max_submissions:
            raise HTTPException(status_code=403, detail=_("Dit formulier heeft het maximum aantal inzendingen bereikt."))


# ── De formulierdefinitie (#635 D) ───────────────────────────────────────────

def update_settings(form: Form, data) -> None:
    """Schrijf de formulierinstellingen uit de payload naar het formulier.

    Alle velden die `FormUpdate` draagt, in één keer — dat is precies wat
    `json_import` niet deed. Ontbreekt een veld in de payload, dan is dat een
    bewuste leegmaking: `FormUpdate` heeft defaults, dus de aanroeper bepaalt de
    payload en niet deze functie.
    """
    for veld in ("title", "slug", "description", "status", "requires_login",
                 "max_submissions", "send_confirmation", "confirmation_message",
                 "allow_edit", "is_anonymous"):
        if hasattr(data, veld):
            setattr(form, veld, getattr(data, veld))


def validate_definition(data) -> None:
    if data.status not in FORM_STATUSES:
        raise HTTPException(status_code=422, detail=_("Ongeldige status: %(status)s") % {"status": data.status})
    sections = getattr(data, "sections", []) or []
    n_sections = len(sections)
    # Sectie-navigatie moet vooruit springen (geen lus).
    for i, s in enumerate(sections):
        if s.next_section_index is not None:
            if not (0 <= s.next_section_index < n_sections):
                raise HTTPException(status_code=422, detail=_("Ongeldige doelsectie."))
            if s.next_section_index <= i:
                raise HTTPException(
                    status_code=422,
                    detail=_("Een sectie-sprong moet naar een latere sectie gaan."),
                )
    for f in data.fields:
        if f.field_type not in FIELD_TYPES:
            raise HTTPException(status_code=422, detail=_("Ongeldig veldtype: %(field_type)s") % {"field_type": f.field_type})
        # Vraag/label is verplicht (#340).
        if not (f.label or "").strip():
            raise HTTPException(status_code=422, detail=_("Elk veld heeft een vraag/label nodig."))
        for o in f.options:
            has_skip = o.skip_to_section_index is not None or o.skip_to_end
            if has_skip and f.field_type not in ("radio", "select"):
                raise HTTPException(
                    status_code=422,
                    detail=_("Vertakking kan enkel bij 'één keuze' of 'keuzelijst'."),
                )
            # Vooruit-sprong afdwingen (geen lus): doelsectie moet ná de sectie van
            # het veld komen. Secties zijn geordend volgens hun index in de payload.
            if o.skip_to_section_index is not None:
                if not (0 <= o.skip_to_section_index < n_sections):
                    raise HTTPException(status_code=422, detail=_("Ongeldige doelsectie voor vertakking."))
                if f.section_index is not None and o.skip_to_section_index <= f.section_index:
                    raise HTTPException(
                        status_code=422,
                        detail=_("Een vertakking moet naar een latere sectie springen."),
                    )


def apply_definition(form: Form, data) -> None:
    """Verzoen de secties/velden/opties van het formulier met de payload.

    Bestaande rijen worden **hergebruikt op basis van hun id** (indien meegestuurd)
    i.p.v. gewist-en-heraangemaakt. Zo behouden velden hun id en blijven de
    eraan gekoppelde inzendings-antwoorden intact wanneer de admin het formulier
    bewerkt (bv. een vraag toevoegt). Velden/opties/secties die niet meer in de
    payload staan, worden verwijderd. Velden verwijzen via `section_index` naar
    de secties in payload-volgorde (branching #336).
    """
    existing_sections = {s.id: s for s in form.sections}
    existing_fields = {f.id: f for f in form.fields}

    # ── Secties: hergebruik-op-id, in payload-volgorde ──────────────────────────
    payload_sections = getattr(data, "sections", []) or []
    result_sections = []
    for si in payload_sections:
        section = existing_sections.get(si.id) if si.id is not None else None
        if section is None:
            section = FormSection()
            form.sections.append(section)
        section.title = si.title
        section.description = si.description
        section.position = si.position
        section.next_is_end = si.next_is_end
        section.next_section = None  # onder resolven
        result_sections.append(section)
    # Verwijder secties die niet meer voorkomen.
    keep_sections = set(result_sections)
    for section in list(form.sections):
        if section not in keep_sections:
            form.sections.remove(section)
    # Sectie-navigatie koppelen (index → sectie-object in payload-volgorde).
    for si, section in zip(payload_sections, result_sections):
        nidx = si.next_section_index
        if nidx is not None and 0 <= nidx < len(result_sections):
            section.next_section = result_sections[nidx]

    # ── Velden: hergebruik-op-id ────────────────────────────────────────────────
    result_fields = []
    for fi in data.fields:
        field = existing_fields.get(fi.id) if fi.id is not None else None
        if field is None:
            field = FormField()
            form.fields.append(field)
        field.field_type = fi.field_type
        field.label = fi.label
        field.help_text = fi.help_text
        field.required = fi.required
        field.position = fi.position
        field.min_value = fi.min_value
        field.max_value = fi.max_value
        field.min_length = fi.min_length
        field.max_length = fi.max_length
        field.regex_pattern = fi.regex_pattern
        field.rating_max = fi.rating_max
        field.rating_low_label = fi.rating_low_label
        field.rating_high_label = fi.rating_high_label
        idx = fi.section_index
        field.section = (
            result_sections[idx] if idx is not None and 0 <= idx < len(result_sections) else None
        )

        # Opties: hergebruik-op-id binnen dit veld.
        existing_options = {o.id: o for o in field.options}
        result_options = []
        for oi in fi.options:
            option = existing_options.get(oi.id) if oi.id is not None else None
            if option is None:
                option = FormFieldOption()
                field.options.append(option)
            option.label = oi.label
            option.value = oi.value
            option.position = oi.position
            option.is_other = oi.is_other
            option.skip_to_end = oi.skip_to_end
            sidx = oi.skip_to_section_index
            option.skip_to_section = (
                result_sections[sidx] if sidx is not None and 0 <= sidx < len(result_sections) else None
            )
            result_options.append(option)
        keep_options = set(result_options)
        for option in list(field.options):
            if option not in keep_options:
                field.options.remove(option)

        result_fields.append(field)

    # Verwijder velden die niet meer voorkomen (hun antwoorden vallen mee weg).
    keep_fields = set(result_fields)
    for field in list(form.fields):
        if field not in keep_fields:
            form.fields.remove(field)


def assert_submitter(form, name, email, *, message=None, require_message=False):
    """Niet-anoniem formulier → naam én een geldig e-mailadres verplicht (#501).

    Eén invariant voor élke ingang: publiek scherm, edit-scherm, JSON-API en het
    berichtenformulier. Voorheen stond deze regel drie keer — hier, en inline in
    de twee publieke schermen — terwijl `submit_bericht` hem helemaal niet
    aanriep. Drie kopieën van één regel, waarvan er één ontbrak.

    `require_message` bestaat voor het berichtenformulier: daar is een leeg
    bericht net zo zinloos als een ontbrekende naam, en die eis stond eerder
    alleen in het scherm.
    """
    if not getattr(form, "is_anonymous", False):
        if not (name or "").strip() or "@" not in (email or ""):
            raise HTTPException(
                status_code=422,
                detail=_("Vul je naam en een geldig e-mailadres in."))
    if require_message and not (message or "").strip():
        raise HTTPException(status_code=422, detail=_("Schrijf een bericht."))
