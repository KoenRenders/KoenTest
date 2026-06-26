"""Export van formulier-inzendingen naar CSV of ODS (#327).

Eén rij per inzending, kolommen = velden. Meervoudige checkbox-antwoorden worden
in één cel samengevoegd. ODS hergebruikt de gedeelde build_ods-helper (#200).
"""
import csv
import io

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
            if ans.value_text is not None:
                per_field[ans.field_id].append(ans.value_text)
            elif ans.value_number is not None:
                per_field[ans.field_id].append(f"{ans.value_number}")
            elif ans.value_option_id is not None:
                per_field[ans.field_id].append(option_label.get(ans.value_option_id, ""))
            elif ans.value_rating is not None:
                per_field[ans.field_id].append(str(ans.value_rating))

        when = sub.submitted_at.strftime("%d/%m/%Y %H:%M") if sub.submitted_at else ""
        row = [when, sub.submitter_name or "", sub.submitter_email or ""]
        for f in form.fields:
            row.append(_MULTI_SEP.join(per_field[f.id]))
        rows.append(row)

    return headers, rows


def export_csv(db, form: Form) -> bytes:
    headers, rows = _build_table(db, form)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def export_ods(db, form: Form) -> bytes:
    headers, rows = _build_table(db, form)
    sheet_name = (form.title or "Formulier")[:31]
    return build_ods(sheet_name, headers, rows)
