"""Service-laag voor het indienen/wijzigen van formulier-inzendingen (#327).

Hier zit de *betekenis*-validatie: de antwoorden worden gecontroleerd tegen het
opgeslagen veldschema (required, types, min/max, regex, geldige opties), los van
welke router de service aanroept. De router doet enkel vorm (Pydantic) + HTTP.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List

from fastapi import HTTPException

from app.models.form import Form, FormField, FormSubmissionAnswer
from app.schemas.form import AnswerIn

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
    from app.models.form import FormSubmission

    if form.status != "open":
        raise HTTPException(status_code=403, detail="Dit formulier staat niet open voor inzendingen.")
    if form.max_submissions is not None:
        count = (
            db.query(FormSubmission)
            .filter(FormSubmission.form_id == form.id)
            .count()
        )
        if count >= form.max_submissions:
            raise HTTPException(status_code=403, detail="Dit formulier heeft het maximum aantal inzendingen bereikt.")
