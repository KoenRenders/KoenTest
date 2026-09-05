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


# ── Opzoeken (#635 I) ────────────────────────────────────────────────────────
# Kleine queries, maar wél met de vraag "welk formulier is dit?" erin. Het scherm
# hoort die vraag te stellen, niet te beantwoorden.

def get_form_by_slug(db, slug: str):
    return db.query(Form).filter(Form.slug == slug).first()


def get_form_by_share_token(db, share_token: str):
    return db.query(Form).filter(Form.share_token == share_token).first()


def get_submission_by_edit_token(db, edit_token: str):
    from app.domains.forms.models import FormSubmission

    return (db.query(FormSubmission)
            .filter(FormSubmission.edit_token == edit_token).first())


# ── Form-builder: secties, velden en opties (#635 D/I) ───────────────────────
# Deze bewerkingen stonden volledig in `admin_ui.py`, inclusief de regels die
# bepalen wat een geldig formulier ís: een sprong moet vooruit gaan, opties horen
# alleen bij keuzevelden, een vertakking alleen bij "één keuze"/"keuzelijst", en
# elk veld heeft een vraag nodig. Die regels golden alleen zolang dít scherm ze
# onthield — een tweede ingang (JSON-import, API) kende ze niet.


class FormulierFout(ValueError):
    """Een invoerfout in de builder. Geen HTTPException: de service kent geen
    HTTP; de route bepaalt de statuscode."""


def get_form(db, form_id: int) -> Form:
    form = db.query(Form).filter(Form.id == form_id).first()
    if form is None:
        raise LookupError("Formulier niet gevonden")
    return form


def _hernummer(items) -> None:
    for index, item in enumerate(sorted(items, key=lambda x: x.position)):
        item.position = index


# ── Secties ──────────────────────────────────────────────────────────────────

def add_section(db, form: Form, *, title: str = "") -> None:
    form.sections.append(FormSection(title=(title or "").strip() or None,
                                     position=len(form.sections)))
    db.commit()


def update_section(db, form: Form, section_id: int, *, title: str = "",
                   description: str = "", next_section_id: str = "",
                   next_is_end: bool = False) -> None:
    """Titel, omschrijving en de sprong naar een volgende sectie.

    Een sprong moet vooruit: een sectie die naar zichzelf of naar een eerdere
    sectie wijst, maakt een lus waar de invuller nooit uit komt.
    """
    section = next((s for s in form.sections if s.id == section_id), None)
    if section is None:
        raise LookupError("Sectie niet gevonden")

    section.title = (title or "").strip() or None
    section.description = (description or "").strip() or None

    doel_id = int(next_section_id) if str(next_section_id).strip().isdigit() else None
    if doel_id is not None:
        doel = next((s for s in form.sections if s.id == doel_id), None)
        if doel is None or doel.position <= section.position:
            raise FormulierFout("Een sectie-sprong moet naar een latere sectie gaan.")
    section.next_section_id = doel_id
    section.next_is_end = bool(next_is_end)
    db.commit()


def move_section(db, form: Form, section_id: int, richting: str) -> None:
    from app.kernel.ordering import move_sibling

    if not any(s.id == section_id for s in form.sections):
        raise LookupError("Sectie niet gevonden")
    move_sibling(form.sections, section_id, richting, attr="position")
    db.commit()


def delete_section(db, form: Form, section_id: int) -> None:
    section = next((s for s in form.sections if s.id == section_id), None)
    if section is not None:
        form.sections.remove(section)
        _hernummer(form.sections)
    db.commit()


# ── Velden ───────────────────────────────────────────────────────────────────

def add_field(db, form: Form, *, label: str, field_type: str = "text",
              section_id: str = "") -> None:
    if field_type not in FIELD_TYPES:
        raise FormulierFout(f"Ongeldig veldtype: {field_type}")
    if not (label or "").strip():
        raise FormulierFout("Elk veld heeft een vraag/label nodig.")
    sid = int(section_id) if str(section_id).strip().isdigit() else None
    broers = [f for f in form.fields if f.section_id == sid]
    form.fields.append(FormField(label=label.strip(), field_type=field_type,
                                 section_id=sid, position=len(broers)))
    db.commit()


def update_field(db, form: Form, field_id: int, **waarden) -> None:
    """De eigenschappen van één veld. Lege tekstwaarden betekenen "niet ingesteld"."""
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None:
        raise LookupError("Veld niet gevonden")
    label = (waarden.get("label") or "").strip()
    if not label:
        raise FormulierFout("Elk veld heeft een vraag/label nodig.")

    def _getal(naam):
        rauw = str(waarden.get(naam) or "").strip()
        return int(rauw) if rauw.isdigit() else None

    veld.label = label
    veld.help_text = (waarden.get("help_text") or "").strip() or None
    veld.required = bool(waarden.get("required"))
    veld.min_length = _getal("min_length")
    veld.max_length = _getal("max_length")
    veld.min_value = (waarden.get("min_value") or "").strip() or None
    veld.max_value = (waarden.get("max_value") or "").strip() or None
    veld.rating_max = _getal("rating_max")
    veld.rating_low_label = (waarden.get("rating_low_label") or "").strip() or None
    veld.rating_high_label = (waarden.get("rating_high_label") or "").strip() or None
    db.commit()


def move_field(db, form: Form, field_id: int, richting: str) -> None:
    from app.kernel.ordering import move_sibling

    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None:
        raise LookupError("Veld niet gevonden")
    broers = [f for f in form.fields if f.section_id == veld.section_id]
    move_sibling(broers, field_id, richting, attr="position")
    db.commit()


def delete_field(db, form: Form, field_id: int) -> None:
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is not None:
        form.fields.remove(veld)
    db.commit()


# ── Opties ───────────────────────────────────────────────────────────────────

KEUZEVELDEN = ("select", "radio", "checkbox")
VERTAKBARE_VELDEN = ("radio", "select")


def add_option(db, form: Form, field_id: int, *, label: str,
               is_other: bool = False) -> None:
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None or veld.field_type not in KEUZEVELDEN:
        raise FormulierFout("Opties kunnen enkel bij keuzevelden.")
    veld.options.append(FormFieldOption(label=(label or "").strip(),
                                        position=len(veld.options),
                                        is_other=bool(is_other)))
    db.commit()


def update_option(db, form: Form, option_id: int, *, label: str = "",
                  is_other: bool = False, skip_to_section_id: str = "",
                  skip_to_end: bool = False) -> None:
    """Een keuze-optie, eventueel met een vertakking.

    Twee regels: vertakken kan alleen bij "één keuze" en "keuzelijst" (bij
    aankruisvakjes zijn er meerdere antwoorden tegelijk, dus één bestemming is
    betekenisloos), en de sprong moet vooruit gaan — anders komt de invuller in
    een lus.
    """
    optie = next((o for f in form.fields for o in f.options if o.id == option_id), None)
    if optie is None:
        raise LookupError("Optie niet gevonden")

    veld = optie.field
    doel_id = (int(skip_to_section_id)
               if str(skip_to_section_id).strip().isdigit() else None)
    if (bool(skip_to_end) or doel_id is not None) and veld.field_type not in VERTAKBARE_VELDEN:
        raise FormulierFout("Vertakking kan enkel bij 'één keuze' of 'keuzelijst'.")
    if doel_id is not None:
        doel = next((s for s in form.sections if s.id == doel_id), None)
        eigen = next((s for s in form.sections if s.id == veld.section_id), None)
        if doel is None or (eigen is not None and doel.position <= eigen.position):
            raise FormulierFout("Een vertakking moet naar een latere sectie springen.")

    optie.label = (label or "").strip() or optie.label
    optie.is_other = bool(is_other)
    optie.skip_to_section_id = doel_id
    optie.skip_to_end = bool(skip_to_end)
    db.commit()


def delete_option(db, form: Form, option_id: int) -> None:
    optie = next((o for f in form.fields for o in f.options if o.id == option_id), None)
    if optie is not None:
        optie.field.options.remove(optie)
    db.commit()


# ── Formulier en inzendingen ─────────────────────────────────────────────────

def create_form(db, *, title: str, share_token: str, status: str = "draft") -> Form:
    form = Form(title=title.strip(), share_token=share_token, status=status)
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


def delete_form(db, form_id: int) -> None:
    form = db.query(Form).filter(Form.id == form_id).first()
    if form is None:
        raise LookupError("Formulier niet gevonden")
    db.delete(form)
    db.commit()


def delete_submission(db, form_id: int, submission_id: int) -> None:
    from app.domains.forms.models import FormSubmission

    inzending = (db.query(FormSubmission)
                 .filter(FormSubmission.id == submission_id,
                         FormSubmission.form_id == form_id).first())
    if inzending is not None:
        db.delete(inzending)
        db.commit()


def import_definition(db, form: Form, data) -> None:
    """Een volledige definitie inlezen (JSON-import).

    Valideert, schrijft **alle** instellingen (dat deed json_import niet, #635-3)
    en verzoent daarna secties/velden/opties. Faalt er iets, dan rolt de hele
    import terug: een half ingelezen formulier is erger dan geen.
    """
    try:
        validate_definition(data)
        update_settings(form, data)
        apply_definition(form, data)
        db.commit()
    except Exception:
        db.rollback()
        raise


def submission_count(db, form_id: int) -> int:
    from app.domains.forms.models import FormSubmission

    return (db.query(FormSubmission)
            .filter(FormSubmission.form_id == form_id).count())


def list_submissions(db, form_id: int):
    """De inzendingen van één formulier, nieuwste eerst."""
    from app.domains.forms.models import FormSubmission

    return (db.query(FormSubmission).filter(FormSubmission.form_id == form_id)
            .order_by(FormSubmission.id.desc()).all())


def list_forms(db, *, q: str = "", status: str = ""):
    """De formulierenlijst met zoekterm en statusfilter.

    Een onbekende status filtert niet: een gemanipuleerde querystring hoort een
    lege lijst noch een 500 op te leveren, gewoon 'alles'.
    """
    query = db.query(Form)
    if (q or "").strip():
        query = query.filter(Form.title.ilike(f"%{q.strip()}%"))
    if status in FORM_STATUSES:
        query = query.filter(Form.status == status)
    return query.order_by(Form.id.desc()).all()


def update_form_settings(db, form: Form, **waarden) -> None:
    """De instellingen uit het builder-scherm.

    Ontbrekende checkboxes betekenen "uit" — een niet-aangevinkt vakje wordt door
    de browser niet meegestuurd. Dat is precies de val van #629: een formulier dat
    op een ándere tab werd opgeslagen, zette `requires_login` stil uit.
    """
    for veld, waarde in waarden.items():
        setattr(form, veld, waarde)
    db.commit()
