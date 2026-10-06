"""The activity fiche as its form sends it, for tests that save through the route (#1559).

Since #1559 the fiche has one write route: `POST /admin/activiteiten/{id}` with
the whole form. A test that used to post one row to a row route builds the form
here — `Fiche(db, id)` is the form of an untouched fiche — changes what it is
about, and posts it:

    fiche = Fiche(db_session, activity.id)
    key = fiche.add("d", start_date="2031-06-14", start_time="14:00")
    fiche.set("c", component.id, name="Anders")
    fiche.remove("p", product.id, parent=component.id)
    response = fiche.post(client, headers)

The field names are those of `activities.fiche_form`.
"""

from __future__ import annotations

from typing import Any

from app.domains.activities.settlement import PAID, settlement_of

ORDER = {"d": "d_order", "c": "c_order", "o": "o_order"}


def _text(value: Any) -> str:
    if value is None or value is False:
        return ""
    if value is True:
        return "1"
    if hasattr(value, "isoformat"):
        return value.isoformat()[:5] if hasattr(value, "hour") else value.isoformat()
    return str(value)


class Fiche:
    """The form of one activity's fiche, as the edit screen would send it untouched."""

    def __init__(self, db, activity_id: int):
        from app.domains.activities import service

        db.expire_all()
        activity = service._activity_met_boom(db, activity_id)
        self.activity_id = activity_id
        self._new = 0
        self.data: dict[str, Any] = {
            "fiche_groups": "dates components organisers",
            "name": activity.name,
            "slug": activity.slug or "",
            "location": activity.location or "",
            "description": activity.description or "",
            "board_notes": activity.board_notes or "",
            "target_audience": getattr(activity.target_audience, "value", activity.target_audience)
            or "",
            "poster_url": activity.poster_url or "",
            "members_only": _text(activity.members_only),
            "d_order": [],
            "c_order": [],
            "o_order": [],
        }
        for d in sorted(activity.dates, key=lambda d: d.start_date):
            self._row(
                "d",
                str(d.id),
                start_date=d.start_date,
                end_date=d.end_date,
                start_time=d.start_time,
                end_time=d.end_time,
            )
        for c in activity.sub_registrations:
            self._row(
                "c",
                str(c.id),
                name=c.name,
                max_participants=c.max_participants,
                registration_closes_on=c.registration_closes_on,
                team_name_required=c.team_name_required,
                form_id=c.form_id,
                external_register_url=c.external_register_url,
                external_registrations_url=c.external_registrations_url,
                info_url=c.info_url,
            )
            self.data[f"p_order.{c.id}"] = []
            for p in c.products:
                # #1608: the screen sends one choice, and the price fields only for
                # a paid product (they are switched off for the other two).
                choice = settlement_of(p.is_free, p.pay_on_site)
                prices = (
                    {"price": p.price, "member_price": p.member_price} if choice == PAID else {}
                )
                self._row(
                    "p",
                    str(p.id),
                    parent=str(c.id),
                    name=p.name,
                    **prices,
                    settlement=choice,
                    is_active=p.is_active,
                    max_participants=p.max_participants,
                )
        for o in service._organiser_rows(db, activity_id):
            self._row(
                "o",
                str(o.id),
                person_id=o.person_id,
                is_contact=o.is_contact,
                show_email=o.show_email,
                show_mobile=o.show_mobile,
                email_override=o.email_override,
                mobile_override=o.mobile_override,
            )

    def _order(self, prefix: str, parent: Any = None) -> list:
        name = f"p_order.{parent}" if prefix == "p" else ORDER[prefix]
        return self.data.setdefault(name, [])

    def _row(self, prefix: str, key: str, parent: Any = None, **fields: Any) -> str:
        self._order(prefix, parent).append(key)
        self.set(prefix, key, **fields)
        return key

    def add(self, prefix: str, parent: Any = None, **fields: Any) -> str:
        """A row added in the page: a key that is no id."""
        self._new += 1
        key = f"n{self._new}"
        if prefix == "p":
            fields = {"is_active": True, **fields}
        if prefix == "o":
            fields = {"show_email": True, "show_mobile": True, **fields}
        if prefix == "c":
            self.data.setdefault(f"p_order.{key}", [])
        return self._row(prefix, key, parent=parent, **fields)

    def set(self, prefix: str, key: Any, **fields: Any) -> None:
        # A test that names the two flags speaks as a caller of the old shape (the
        # JSON API still does): the one choice the screen sends is then left out,
        # so the flags are what the reader hears.
        if prefix == "p" and ("is_free" in fields or "pay_on_site" in fields):
            self.data.pop(f"p.{key}.settlement", None)
        for name, value in fields.items():
            self.data[f"{prefix}.{key}.{name}"] = _text(value)

    def remove(self, prefix: str, key: Any, parent: Any = None) -> None:
        self._order(prefix, parent).remove(str(key))

    def move(self, prefix: str, key: Any, to: int, parent: Any = None) -> None:
        order = self._order(prefix, parent)
        order.remove(str(key))
        order.insert(to, str(key))

    def post(
        self,
        client,
        headers: dict | None = None,
        files: dict | None = None,
        query: str = "bewerken=1",
    ):
        """Send the form as htmx does from the fiche in its edit state."""
        return client.post(
            f"/admin/activiteiten/{self.activity_id}",
            headers={
                **(headers or {}),
                "HX-Request": "true",
                "HX-Current-URL": f"http://testserver/admin/activiteiten/{self.activity_id}?{query}",
            },
            data=self.data,
            files=files,
        )


FIRST_DATE = ("start_date", "end_date", "start_time", "end_time")


def post_new_activity(client, headers: dict | None = None, data: dict | None = None, files=None):
    """The NEW fiche as its form sends it (#1649): `POST /admin/activiteiten/nieuw`.

    `data` are the activity's own fields by name (`name`, `location`,
    `poster_url`, `members_only`, …). The four keys of a date (`start_date`,
    `end_date`, `start_time`, `end_time`) fill the first date row, the one the
    empty fiche opens with — sent also when empty, as the page sends it.
    Anything else in `data` goes along as it is (rows of a group, by the names of
    `activities.fiche_form`)."""
    data = dict(data or {})
    form: dict[str, Any] = {
        "fiche_groups": "dates components organisers",
        "name": data.pop("name", ""),
        "slug": "",
        "location": "",
        "description": "",
        "board_notes": "",
        "target_audience": "",
        "poster_url": "",
        "d_order": ["n1"],
        "c_order": [],
        "o_order": [],
    }
    for name in FIRST_DATE:
        form[f"d.n1.{name}"] = _text(data.pop(name, ""))
    form.update(
        {
            name: (_text(value) if not isinstance(value, list) else value)
            for name, value in data.items()
        }
    )
    return client.post(
        "/admin/activiteiten/nieuw",
        headers={
            **(headers or {}),
            "HX-Request": "true",
            "HX-Current-URL": "http://testserver/admin/activiteiten/nieuw",
        },
        data=form,
        files=files,
    )
