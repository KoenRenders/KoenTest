"""Facade van het forms-component (#397) — het enige publieke oppervlak (§1).

Buitenstaanders (schermen, andere componenten) gebruiken uitsluitend deze
functies; models/service/router zijn intern. Contract in CONTRACT.md.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.domains.forms.codes import FIELD_TYPE, FORM_STATUS  # noqa: F401
from app.domains.forms.models import (  # noqa: F401
    FieldType,
    Form,
    FormField,
    FormStatus,
    FormSubmission,
)

# CR-12 phase 4: a field as a screen renders it — the design-system page draws
# its examples through the same adapter as the public form.
from app.domains.forms.screenfields import screen_fields  # noqa: F401
from app.i18n import short_datetime

logger = logging.getLogger(__name__)


def get_form_by_slug(db: Session, slug: str) -> Form | None:
    """Publiek raadpleegbaar formulier (of None). DTO-verfijning volgt zodra de
    eerste externe consument (berichten/workflow, #398) zich aandient."""
    from app.domains.forms.service import get_form_by_slug as _impl

    return _impl(db, slug)


def submission_count(db: Session, form_id: int) -> int:
    from app.domains.forms.service import submission_count as _impl

    return _impl(db, form_id)


def submission_view(db: Session, submission_id: int) -> list[tuple[str, str]]:
    """Leesbare (label, waarde)-rijen van één inzending — voor gast-weergave
    buiten het component (werkbank-taakdetail, #398). Geen ORM over de grens."""
    sub = db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
    if sub is None:
        return []
    rows: list[tuple[str, str]] = [
        ("Van", sub.submitter_name or "—"),
        ("E-mail", sub.submitter_email or "—"),
        ("Ontvangen", short_datetime(sub.submitted_at)),
    ]
    # Zelfde typedekking als de export (#407-O flatten-drift): ook optie- en
    # rating-antwoorden tonen, met het optielabel i.p.v. een leeg veld.
    per_label: dict[str, list[str]] = {}
    volgorde: list[str] = []
    for ans in sub.answers:
        label = ans.field.label if ans.field else "Antwoord"
        if ans.value_text is not None:
            waarde = ans.value_text
        elif ans.value_number is not None:
            waarde = f"{ans.value_number}"
        elif ans.value_option_id is not None:
            optie = next(
                (
                    o
                    for o in (ans.field.options if ans.field else [])
                    if o.id == ans.value_option_id
                ),
                None,
            )
            waarde = optie.label if optie else ""
        elif ans.value_rating is not None:
            waarde = str(ans.value_rating)
        else:
            waarde = ""
        if not waarde:
            continue
        if label not in per_label:
            per_label[label] = []
            volgorde.append(label)
        per_label[label].append(waarde)
    rows.extend((label, "; ".join(per_label[label])) for label in volgorde)
    return rows


# ── Wat de schermen gebruiken (#635 D/I) ─────────────────────────────────────
# Onderaan, zodat de functies hierboven hun eigen naam houden: `submission_count`
# en `get_form_by_slug` staan al als facade-functie gedefinieerd en delegeren nu
# naar dezelfde service-implementatie.

from app.domains.forms.models import (  # noqa: E402,F401
    FIELD_TYPES,
    FORM_STATUSES,
)
from app.domains.forms.schemas import AnswerIn  # noqa: E402,F401

# CR-14 phase 2 adds what `activities` uses to ask a component's questions:
# `attach_refusal`, `attachable_forms`, `answers_from_form` (the one parser of a
# posted form), `submission_views` and `form_questions` (many registrations in one
# read). Storing and correcting the answers is asked through the ports
# `SubmitAttached` and `UpdateAttached` (`handlers.py`) since CR-13 phase 4c.
from app.domains.forms.service import (  # noqa: E402,F401
    CONTACT_FORM_SLUG,
    FormulierFout,
    VeldFout,
    add_field,
    add_option,
    add_section,
    answers_from_form,
    apply_definition,
    assert_definition_given,
    assert_geen_id_vorm,
    assert_known_status,
    assert_slug_vrij,
    assert_submitter,
    attach_refusal,
    attachable_forms,
    contact_form,
    create_form,
    deellink_pad,
    delete_field,
    delete_form,
    delete_option,
    delete_section,
    delete_submission,
    export_definition,
    find_form,
    form_button_target,
    form_page_context,
    form_questions,
    get_form,
    get_form_by_share_token,
    get_submission_by_edit_token,
    import_definition,
    list_forms,
    list_submissions,
    move_field,
    move_option,
    move_section,
    normaliseer_slug,
    question_groups,
    seed_contact_form,
    submission_confirmation,
    submission_form_values,
    submission_url,
    submission_views,
    update_field,
    update_form_settings,
    update_option,
    update_section,
    update_settings,
    validate_definition,
)

# ── Doorgangen waarvan de implementatie in de router blijft ──────────────────
# De publieke inzendflow is één domeinbewerking die het scherm alleen aanroept —
# hetzelfde patroon als de activiteiteninschrijving, die #635 expliciet als "zo
# hoort het" aanmerkt. Alleen de weg ernaartoe loopt via deze facade.


def submit_public_form(db, share_token: str, payload, *, proof):
    """Een publieke inzending verwerken. `proof`: see `service.submit_message` (#1297)."""
    from app.domains.forms.service import submit_form

    return submit_form(db, share_token, payload, proof=proof)


def update_public_submission(db, edit_token: str, payload):
    """Een eigen inzending bijwerken via de edit-link."""
    from app.domains.forms.service import update_submission

    return update_submission(db, edit_token, payload)


def export_submissions_ods(db, form_id: int):
    """De inzendingen als .ods."""
    from app.domains.forms.service import export_form

    return export_form(db, form_id)


def form_definition(db, form) -> dict:
    """De volledige definitie als dict (backup, inspectie, AI-gids)."""
    from app.domains.forms.service import _admin_out

    return _admin_out(db, form)


def unique_share_token(db) -> str:
    from app.domains.forms.service import _unique_share_token

    return _unique_share_token(db)
