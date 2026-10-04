"""The activity fiche as its form sends it (#1559): from field names to a `FicheSave`.

The fiche is one form. Its sections send plain fields (`name`, `location`, …);
its repeating groups send, per row, an order field with the row's key and the
row's fields under that key:

    d_order=<key> …            d.<key>.start_date | end_date | start_time | end_time
    c_order=<key> …            c.<key>.name | max_participants | registration_closes_on
                               | team_name_required | form_id | file | info_delete
                               | external_register_url | external_registrations_url | info_url
    p_order.<component key>=…  p.<key>.name | price | member_price | is_free | pay_on_site
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
    return ProductRow(
        key=key,
        name=name,
        price=price if price is not None else Decimal("0"),
        member_price=_money(
            form,
            f"p.{key}.member_price",
            _("de ledenprijs van “%(name)s”") % {"name": what},
            errors,
        ),
        is_free=_on(form, f"p.{key}.is_free"),
        pay_on_site=_on(form, f"p.{key}.pay_on_site"),
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
