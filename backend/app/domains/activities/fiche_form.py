"""The activity fiche as its form sends it (#1559): from field names to a `FicheSave`.

The fiche is one form. Its sections send plain fields (`name`, `location`, …);
its repeating groups send, per row, an order field with the row's key and the
row's fields under that key:

    d_order=<key> …            d.<key>.start_date | end_date | start_time | end_time
    c_order=<key> …            c.<key>.name | max_participants | registration_closes_on
                               | team_name_required | form_id | file | info_delete
                               | external_register_url | external_registrations_url | info_url
    p_order.<component key>=…  p.<key>.name | price | member_price | settlement
                               (or the two flags is_free | pay_on_site)
                               | is_active | max_participants
    o_order=<key> …            o.<key>.person_id | is_contact | show_email | show_mobile
                               | email_override | mobile_override

A key is the row's id, or anything else for a row added in the page. The rows are
read in the order of their order fields: that order is the order on the screen.
`fiche_groups` names the groups the form carries; a group it does not name is
left alone by the save.

This module reads the SHAPE — a date is a date, an amount an amount — and says so
in the user's words when it is not; what a value MEANS is the save's
(`activities.fiche`).

Since #1561 a value of the wrong shape does not stop the reading: it is noted at
its field (`FicheSave.errors`) and the save reports it with everything else it
refuses, so the screen can show every field to correct at once.
"""

from __future__ import annotations

import json
from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.domains.activities.fiche import (
    COMPONENT_LINKS,
    ComponentRow,
    DateRow,
    FicheSave,
    FieldError,
    OrganiserRow,
    ProductRow,
)
from app.domains.activities.settlement import flags_of
from app.i18n import _

GROUPS = ("dates", "components", "organisers")


def _last(form: Any, name: str) -> str:
    """The value of a field. A switch sends its off value first and, ticked, its
    on value after it — the last one is what was chosen."""
    values = form.getlist(name)
    value = values[-1] if values else ""
    return value.strip() if isinstance(value, str) else ""


def _on(form: Any, name: str) -> bool:
    return _last(form, name) not in ("", "0")


def _text(form: Any, name: str) -> Optional[str]:
    return _last(form, name) or None


def _date(form: Any, name: str, what: str, errors: list[FieldError]) -> Optional[date]:
    raw = _last(form, name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append(FieldError(name, _("Ongeldige datum bij %(what)s.") % {"what": what}))
        return None


def _time(form: Any, name: str, what: str, errors: list[FieldError]) -> Optional[time]:
    raw = _last(form, name)
    if not raw:
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        errors.append(FieldError(name, _("Ongeldig uur bij %(what)s.") % {"what": what}))
        return None


def _int(form: Any, name: str, what: str, errors: list[FieldError]) -> Optional[int]:
    raw = _last(form, name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        errors.append(FieldError(name, _("%(what)s is geen geheel getal.") % {"what": what}))
        return None


def _money(form: Any, name: str, what: str, errors: list[FieldError]) -> Optional[Decimal]:
    raw = _last(form, name)
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        errors.append(FieldError(name, _("Ongeldig bedrag bij %(what)s.") % {"what": what}))
        return None


def fiche_from_form(form: Any) -> tuple[FicheSave, dict[str, Any]]:
    """The fiche this form carries, and the info files by component row key."""
    groups = frozenset(_last(form, "fiche_groups").split()) & frozenset(GROUPS)
    # The switch always arrives (its off value travels in a hidden field), so an
    # absent key is "off", as it was for the checkbox before it.
    fields: dict[str, Any] = {"members_only": _on(form, "members_only")}
    # A text field is written when the form carries it, and then also when it is
    # empty: emptying the friendly URL, the description, the note or the audience
    # was always a valid choice (#884, #1016, #1028, #1428), and since #1559 so
    # is emptying the location and the poster address — the route before it kept
    # the old value there without saying so. A field the form does not carry is
    # left alone.
    for name in ("slug", "description", "board_notes", "target_audience", "location", "poster_url"):
        if name in form:
            fields[name] = _text(form, name)
    errors: list[FieldError] = []
    if "name" in form:
        name = _last(form, "name")
        if name:
            fields["name"] = name
        else:
            # Until #1561 an empty name silently kept the old one; the form now
            # says so at the field.
            errors.append(FieldError("name", _("De activiteit heeft een naam nodig.")))

    files: dict[str, Any] = {}
    fiche = FicheSave(
        fields=fields,
        groups=groups,
        errors=errors,
        confirmed_no_contact=_last(form, "bevestigd") == "1",
        drop_poster=_last(form, "file_delete") == "1",
    )
    if "dates" in groups:
        fiche.dates = [_date_row(form, key, errors) for key in form.getlist("d_order")]
    if "components" in groups:
        for key in form.getlist("c_order"):
            fiche.components.append(_component_row(form, key, errors))
            upload = form.get(f"c.{key}.file")
            if upload is not None and not isinstance(upload, str):
                files[key] = upload
    if "organisers" in groups:
        fiche.organisers = [_organiser_row(form, key, errors) for key in form.getlist("o_order")]
    return fiche, files


#: The fields of the fiche a proposal can touch, and so the ones the
#: Assistent's panel sends along with a request (#1659): the three texts, and
#: the date rows with their order. The one list — what the panel sends is
#: built from it (`PROPOSAL_VALS`), `proposal_fields` reads it.
PROPOSAL_TEXTS = ("name", "location", "description")
#: As computed values (`hx-vals`), read from the record form when the request
#: leaves — NOT as included fields: htmx validates a field it includes, and a
#: date row without its required day (hours applied, the day still to come)
#: then stops the request without a word. Measured in the e2e of #1659.
PROPOSAL_VALS = "js:{...window.raakRecordForm.valuesOf(%s, %s)}" % (
    json.dumps([*PROPOSAL_TEXTS, "d_order"]),
    json.dumps(["d."]),
)


def proposal_fields(form: Any) -> Optional[tuple[dict[str, str], list[DateRow]]]:
    """The fiche's form as it stands, as far as a proposal reads it: the three
    texts and the date rows in the order of the screen. None when the request
    did not carry the form (a caller that sends the question alone).

    A value of the wrong shape is no refusal here — nothing is saved: a date
    that is none reads as a row without that date."""
    if "name" not in form:
        return None
    unused: list[FieldError] = []
    texts = {name: _last(form, name) for name in PROPOSAL_TEXTS}
    rows = [
        DateRow(
            key=key,
            start_date=_date(form, f"d.{key}.start_date", "", unused),
            end_date=_date(form, f"d.{key}.end_date", "", unused),
            start_time=_time(form, f"d.{key}.start_time", "", unused),
            end_time=_time(form, f"d.{key}.end_time", "", unused),
        )
        for key in form.getlist("d_order")
    ]
    return texts, rows


def _date_row(form: Any, key: str, errors: list[FieldError]) -> DateRow:
    start = _date(form, f"d.{key}.start_date", _("een datum"), errors)
    if start is None and not _last(form, f"d.{key}.start_date"):
        errors.append(FieldError(f"d.{key}.start_date", _("Een datum heeft een begindatum nodig.")))
    return DateRow(
        key=key,
        start_date=start,
        end_date=_date(form, f"d.{key}.end_date", _("een einddatum"), errors),
        start_time=_time(form, f"d.{key}.start_time", _("een beginuur"), errors),
        end_time=_time(form, f"d.{key}.end_time", _("een einduur"), errors),
    )


def _component_row(form: Any, key: str, errors: list[FieldError]) -> ComponentRow:
    name = _last(form, f"c.{key}.name")
    what = name or _("een onderdeel")
    links = None
    if any(f"c.{key}.{link}" in form for link in COMPONENT_LINKS):
        links = {link: _text(form, f"c.{key}.{link}") for link in COMPONENT_LINKS}
    return ComponentRow(
        key=key,
        name=name,
        team_name_required=_on(form, f"c.{key}.team_name_required"),
        max_participants=_int(
            form,
            f"c.{key}.max_participants",
            _("Het maximum van “%(name)s”") % {"name": what},
            errors,
        ),
        registration_closes_on=_date(
            form,
            f"c.{key}.registration_closes_on",
            _("“Inschrijven tot” van “%(name)s”") % {"name": what},
            errors,
        ),
        form_id=_int(
            form, f"c.{key}.form_id", _("Het formulier van “%(name)s”") % {"name": what}, errors
        ),
        links=links,
        products=[
            _product_row(form, product, errors) for product in form.getlist(f"p_order.{key}")
        ],
        drop_info=_last(form, f"c.{key}.info_delete") == "1",
    )


def _product_row(form: Any, key: str, errors: list[FieldError]) -> ProductRow:
    name = _last(form, f"p.{key}.name")
    what = name or _("een product")
    price = _money(form, f"p.{key}.price", _("de prijs van “%(name)s”") % {"name": what}, errors)
    # #1608: the screen sends ONE choice, `settlement`; it becomes the two flags
    # the model stores. A caller that still sends the flags themselves is read as
    # before — and may send both, which the service refuses.
    choice = _last(form, f"p.{key}.settlement")
    if choice:
        try:
            is_free, pay_on_site = flags_of(choice)
        except ValueError:
            errors.append(
                FieldError(f"p.{key}.settlement", _("Kies hoe het product afgerekend wordt."))
            )
            is_free = pay_on_site = False
    else:
        is_free, pay_on_site = _on(form, f"p.{key}.is_free"), _on(form, f"p.{key}.pay_on_site")
    # The price fields are switched off while the product is free or paid on the
    # spot, and a switched-off field is not sent. Not sent is "leave it", not
    # "nothing": the price a product had is kept, as it was when the two switches
    # stood beside enabled price fields.
    prices_sent = f"p.{key}.price" in form or f"p.{key}.member_price" in form
    return ProductRow(
        key=key,
        name=name,
        prices_sent=prices_sent or not choice,
        price=price if price is not None else Decimal("0"),
        member_price=_money(
            form,
            f"p.{key}.member_price",
            _("de ledenprijs van “%(name)s”") % {"name": what},
            errors,
        ),
        is_free=is_free,
        pay_on_site=pay_on_site,
        is_active=_on(form, f"p.{key}.is_active"),
        max_participants=_int(
            form,
            f"p.{key}.max_participants",
            _("Het maximum van “%(name)s”") % {"name": what},
            errors,
        ),
    )


def _organiser_row(form: Any, key: str, errors: list[FieldError]) -> OrganiserRow:
    return OrganiserRow(
        key=key,
        person_id=_int(form, f"o.{key}.person_id", _("De organisator"), errors),
        is_contact=_on(form, f"o.{key}.is_contact"),
        show_email=_on(form, f"o.{key}.show_email"),
        show_mobile=_on(form, f"o.{key}.show_mobile"),
        email_override=_text(form, f"o.{key}.email_override"),
        mobile_override=_text(form, f"o.{key}.mobile_override"),
    )
