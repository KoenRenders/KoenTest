"""Export van formulier-inzendingen naar ODS (#327).

Eén rij per inzending, kolommen = velden. Meervoudige checkbox-antwoorden worden
in één cel samengevoegd. ODS hergebruikt de gedeelde build_ods-helper (#200); elke
cel is daar `valuetype="string"`, wat meteen de bescherming is tegen formule-injectie
(#288). Er is bewust geen CSV-export (nooit gevraagd + injectie-gevoelig, #371).
"""
from app.models.form import Form, FormSubmission
from app.services.ods_export import build_ods

_MULTI_SEP = "; "


def _build_table(db, form: Form):
    """Geeft (headers, rows) terug. rows = lijst van lijsten (strings/getallen)."""
    option_label = {}
    for field in form.fields:
        for o in field.options:
            option_label[o.id] = o.label

    headers = ["Ingediend op", "Naam", "E-mail"] + [f.label for f in form.fields]

    submissions = (
        db.query(FormSubmission)
        .filter(FormSubmission.form_id == form.id)
        .order_by(FormSubmission.submitted_at.asc())
        .all()
    )

    rows = []
    for sub in submissions:
        # Verzamel per veld de waarde(n).
        per_field: dict = {f.id: [] for f in form.fields}
        for ans in sub.answers:
            if ans.field_id not in per_field:
                continue
            if ans.value_option_id is not None:
                label = option_label.get(ans.value_option_id, "")
                # "Andere…"-optie: toon "label: vrije tekst".
                if ans.value_text:
                    label = f"{label}: {ans.value_text}" if label else ans.value_text
                per_field[ans.field_id].append(label)
            elif ans.value_text is not None:
                per_field[ans.field_id].append(ans.value_text)
            elif ans.value_number is not None:
                per_field[ans.field_id].append(f"{ans.value_number}")
            elif ans.value_rating is not None:
                per_field[ans.field_id].append(str(ans.value_rating))

        when = sub.submitted_at.strftime("%d/%m/%Y %H:%M") if sub.submitted_at else ""
        row = [when, sub.submitter_name or "", sub.submitter_email or ""]
        for f in form.fields:
            row.append(_MULTI_SEP.join(per_field[f.id]))
        rows.append(row)

    return headers, rows


def build_submissions_view(db, form: Form) -> dict:
    """Per-inzending overzicht voor de admin (#356): veldlabels + per inzending
    de antwoorden (leesbaar) met het inzending-id (voor verwijderen)."""
    option_label = {}
    for field in form.fields:
        for o in field.options:
            option_label[o.id] = o.label
    view_fields = [f for f in form.fields if f.field_type != "info"]

    submissions = (
        db.query(FormSubmission)
        .filter(FormSubmission.form_id == form.id)
        .order_by(FormSubmission.submitted_at.desc())
        .all()
    )
    out = []
    for sub in submissions:
        per_field: dict = {f.id: [] for f in view_fields}
        for ans in sub.answers:
            if ans.field_id not in per_field:
                continue
            if ans.value_text is not None:
                per_field[ans.field_id].append(ans.value_text)
            elif ans.value_number is not None:
                per_field[ans.field_id].append(f"{ans.value_number}")
            elif ans.value_option_id is not None:
                per_field[ans.field_id].append(option_label.get(ans.value_option_id, ""))
            elif ans.value_rating is not None:
                per_field[ans.field_id].append(str(ans.value_rating))
        out.append({
            "id": sub.id,
            "submitted_at": sub.submitted_at,
            "submitter_name": sub.submitter_name,
            "submitter_email": sub.submitter_email,
            "values": [_MULTI_SEP.join(per_field[f.id]) for f in view_fields],
        })
    return {"fields": [f.label for f in view_fields], "submissions": out}


def export_ods(db, form: Form) -> bytes:
    headers, rows = _build_table(db, form)
    sheet_name = (form.title or "Formulier")[:31]
    return build_ods(sheet_name, headers, rows)
