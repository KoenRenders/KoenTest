"""Server-side aggregatie van formulier-resultaten (#327).

Berekent per veld de tellingen die de admin-resultaten-tab toont, zodat niet alle
ruwe inzendingen naar de browser hoeven (schaalt beter, minder PII in de client).
"""
from sqlalchemy import func

from app.models.form import (
    Form,
    FormSubmission,
    FormSubmissionAnswer,
    RATING_LABELS,
)


def compute_results(db, form: Form) -> dict:
    submission_count = (
        db.query(func.count(FormSubmission.id))
        .filter(FormSubmission.form_id == form.id)
        .scalar()
        or 0
    )
    last_submission = (
        db.query(func.max(FormSubmission.submitted_at))
        .filter(FormSubmission.form_id == form.id)
        .scalar()
    )

    fields_out = []
    for field in form.fields:
        entry = {
            "field_id": field.id,
            "label": field.label,
            "field_type": field.field_type,
        }
        ftype = field.field_type

        if ftype in ("select", "radio", "checkbox"):
            counts = dict(
                db.query(
                    FormSubmissionAnswer.value_option_id, func.count(FormSubmissionAnswer.id)
                )
                .filter(FormSubmissionAnswer.field_id == field.id)
                .filter(FormSubmissionAnswer.value_option_id.isnot(None))
                .group_by(FormSubmissionAnswer.value_option_id)
                .all()
            )
            entry["options"] = [
                {"option_id": o.id, "label": o.label, "count": int(counts.get(o.id, 0))}
                for o in field.options
            ]
            entry["response_count"] = int(sum(counts.values()))

        elif ftype == "rating":
            rows = (
                db.query(FormSubmissionAnswer.value_rating, func.count(FormSubmissionAnswer.id))
                .filter(FormSubmissionAnswer.field_id == field.id)
                .filter(FormSubmissionAnswer.value_rating.isnot(None))
                .group_by(FormSubmissionAnswer.value_rating)
                .all()
            )
            dist = {int(r): int(c) for r, c in rows}
            total = sum(dist.values())
            weighted = sum(r * c for r, c in dist.items())
            top = field.rating_max or 5
            low, high = field.rating_low_label, field.rating_high_label

            def _label(n: int) -> str:
                # Standaard 5-punts zonder eigen labels → de vaste woord-labels.
                if top == 5 and not low and not high:
                    return RATING_LABELS[n]
                if n == 1 and low:
                    return f"{n} ({low})"
                if n == top and high:
                    return f"{n} ({high})"
                return str(n)

            entry["distribution"] = [
                {"rating": n, "label": _label(n), "count": dist.get(n, 0)}
                for n in range(1, top + 1)
            ]
            entry["response_count"] = total
            entry["average"] = round(weighted / total, 2) if total else None

        elif ftype == "number":
            agg = (
                db.query(
                    func.count(FormSubmissionAnswer.id),
                    func.avg(FormSubmissionAnswer.value_number),
                    func.min(FormSubmissionAnswer.value_number),
                    func.max(FormSubmissionAnswer.value_number),
                )
                .filter(FormSubmissionAnswer.field_id == field.id)
                .filter(FormSubmissionAnswer.value_number.isnot(None))
                .one()
            )
            cnt, avg, mn, mx = agg
            entry["response_count"] = int(cnt or 0)
            entry["average"] = round(float(avg), 2) if avg is not None else None
            entry["min"] = float(mn) if mn is not None else None
            entry["max"] = float(mx) if mx is not None else None

        else:  # text, textarea, email
            texts = (
                db.query(FormSubmissionAnswer.value_text)
                .filter(FormSubmissionAnswer.field_id == field.id)
                .filter(FormSubmissionAnswer.value_text.isnot(None))
                .order_by(FormSubmissionAnswer.id.desc())
                .all()
            )
            values = [t[0] for t in texts]
            entry["response_count"] = len(values)
            entry["answers"] = values

        fields_out.append(entry)

    return {
        "submission_count": int(submission_count),
        "last_submission": last_submission,
        "fields": fields_out,
    }
