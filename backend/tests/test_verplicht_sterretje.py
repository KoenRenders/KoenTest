"""#646 — de rode `*` markeert precies de verplichte velden, en niets anders.

Op `/lid-worden` (het scherm dat Koen "Word lid" noemt) stonden twee kleuren
sterretje naast elkaar: Voornaam/Achternaam rood, E-mail/GSM grijs. Oorzaak was
niet de `label()`-macro maar vier aanroepen in `person_fields` die het sterretje
in de *labeltekst* plakten, waar het `text-gray-700` van het label erfde.

Deze test vergelijkt daarom niet met een verwachte string, maar toetst de
invariant zelf: **de verzameling velden met een rood sterretje is exact de
verzameling verplichte velden.** Zo vangt hij beide richtingen — een verplicht
veld zonder rode markering (de bug van #646) én een rode markering bij een veld
dat niet verplicht is, wat de gebruiker even hard misleidt.

De koppeling loopt via `label for=` ↔ `control id=`, niet via een telling: twee
even grote verzamelingen kunnen nog altijd de verkeerde velden bevatten.

Since #1590 the page is built from the kit's `field` macro and the household is
a repeating group: the main member is row `n0` (ids `h-n0-…`, its first e-mail
row `e-n0e-…`), and what "+ Gezinslid toevoegen" adds is the group's template
row (`h-__H__-…`), which stands in the page itself — there is no route for a
row any more. A radio group's star stands on the group's label
(`<p id="…-label">`), which the comparison below does not cover, so it is asked
separately (the payment method).

Since #1632 the gender is a select — an ordinary labelled field, so it is in
the comparison — and an e-mail row has no label of its own: the title of its
group, "E-mailadressen", is its label and carries the star when an address is
asked (`_group_title_marked`). The comparison leaves such a field out and the
title is asked for it, in both directions.
"""

import re

from tests.conftest import seed_postal_code

# Het sterretje zoals de B2-conventie het voorschrijft (docs/ui-conventies.md:383).
ROOD_STERRETJE = re.compile(r'class="text-red-600">\s*\*')
LABEL = re.compile(r'<label\s+for="([^"]+)"[^>]*>(.*?)</label>', re.S)
CONTROL = re.compile(r"<(input|select|textarea)\s([^>]*)>", re.S)
ID_ATTR = re.compile(r'\bid="([^"]+)"')


def _gemarkeerd(html: str) -> set[str]:
    """Veld-id's waarvan het label een rood sterretje draagt."""
    return {for_id for for_id, inhoud in LABEL.findall(html) if ROOD_STERRETJE.search(inhoud)}


def _verplicht(html: str) -> set[str]:
    """Veld-id's van formuliervelden met het HTML-attribuut `required`."""
    ids = set()
    for _tag, attrs in CONTROL.findall(html):
        treffer = ID_ATTR.search(attrs)
        if treffer and re.search(r"(?:^|\s)required(?:[\s=>]|$)", attrs):
            ids.add(treffer.group(1))
    return ids


NAME_ATTR = re.compile(r'\bname="([^"]+)"')


def _radiogroepen(html: str) -> set[str]:
    """Namen van radiogroepen.

    Een radiogroep draagt geen `required` en heeft geen enkelvoudige `id`: het
    label wijst naar de groep als geheel (`Betaalwijze`, met "online" voorgevinkt).
    Zo'n groep is per constructie altijd ingevuld, dus een rood sterretje erbij is
    correct en mag de vergelijking hieronder niet doen struikelen. De keerzijde:
    op radiogroepen toetst deze test de markering niet.
    """
    namen = set()
    for _tag, attrs in CONTROL.findall(html):
        treffer = NAME_ATTR.search(attrs)
        if treffer and re.search(r'type="radio"', attrs):
            namen.add(treffer.group(1))
    return namen


LABELLESS = re.compile(r'<(?:input|select|textarea)\s[^>]*aria-label="[^"]*"[^>]*>', re.S)


def _named_by_its_group(html: str) -> set[str]:
    """Ids of the controls without a label of their own (`label_hidden`)."""
    return {m.group(1) for tag in LABELLESS.findall(html) if (m := ID_ATTR.search(tag))}


def _group_title_marked(html: str, group: str) -> bool:
    """Does the title of the repeating group `group` carry the red star?"""
    found = re.search(
        rf'data-repeating-group="{re.escape(group)}".*?<h[23][^>]*>(.*?)</h[23]>', html, re.S
    )
    assert found, f"no repeating group {group}"
    return bool(ROOD_STERRETJE.search(found.group(1)))


def _controleer(html: str, *, minstens: set[str]) -> None:
    gemarkeerd, verplicht = _gemarkeerd(html), _verplicht(html)
    assert minstens <= verplicht, (
        f"velden die verplicht horen te zijn, zijn het niet: {sorted(minstens - verplicht)}"
    )
    # A field its group names has its star on the group's title; the caller asks that.
    verplicht -= _named_by_its_group(html)
    assert verplicht - gemarkeerd == set(), (
        f"verplicht veld zonder rood sterretje (#646): {sorted(verplicht - gemarkeerd)}"
    )
    assert gemarkeerd - verplicht - _radiogroepen(html) == set(), (
        "rood sterretje bij een veld dat niet verplicht is: "
        f"{sorted(gemarkeerd - verplicht - _radiogroepen(html))}"
    )


def _new_person_row(html: str) -> str:
    """The template row a new person is made from, as it stands in the page."""
    found = re.search(
        r'<template data-group-template>\s*<div data-group-row data-row-key="__H__"', html
    )
    assert found, "the page has no row to add a person from"
    return html[found.start() : html.rindex("</template>")]


def _group_label_marked(html: str, field_id: str) -> bool:
    """Does the label of a radio group carry the red star?"""
    label = re.search(rf'<p id="{re.escape(field_id)}-label"[^>]*>(.*?)</p>', html, re.S)
    assert label, f"no group label for {field_id}"
    return bool(ROOD_STERRETJE.search(label.group(1)))


def test_hoofdlid_elk_verplicht_veld_draagt_het_rode_sterretje(client, db_session):
    """Het gemelde scherm: hoofdlid + adres, in één render."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    resp = client.get("/lid-worden")
    assert resp.status_code == 200
    # E-mail en GSM zijn de twee velden uit de melding; voornaam/achternaam
    # deden het al goed en horen mee in dezelfde vergelijking.
    _controleer(
        resp.text,
        minstens={
            "h-n0-first_name",
            "h-n0-last_name",
            "h-n0-date_of_birth",
            "e-n0e-value",
            "h-n0-mobile",
            "address-street",
            "address-house_number",
            "address-postal_code",
        },
    )
    assert "h-n0-gender_code" in _gemarkeerd(resp.text) & _verplicht(resp.text)
    assert _named_by_its_group(resp.text) >= {"e-n0e-value"}
    assert _group_title_marked(resp.text, "e_order.n0"), "the asked e-mail address has no star"
    assert _group_label_marked(resp.text, "payment_method")
    assert "h-n0-phone" not in _gemarkeerd(resp.text), "an optional field carries the star"


def test_bijkomend_lid_geboortedatum_en_geslacht_dragen_het_rode_sterretje(client, db_session):
    """De rij voor een bijkomend lid: daar zijn geboortedatum en geslacht verplicht
    (#551/#681) en e-mail/GSM juist niet — omgekeerd aan het hoofdlid, dat e-mail
    en GSM wél verplicht heeft. Dat verschil bewijst dat de markering de vlag volgt
    en niet het veld. (Geboortedatum en geslacht zijn sinds #681 aan beide kanten
    verplicht; e-mail/GSM dragen het onderscheid.)"""
    page = client.get("/lid-worden")
    assert page.status_code == 200
    rij = _new_person_row(page.text)
    _controleer(rij, minstens={"h-__H__-first_name", "h-__H__-last_name", "h-__H__-date_of_birth"})
    assert "h-__H__-gender_code" in _gemarkeerd(rij) & _verplicht(rij)
    assert "e-__E__-value" not in _verplicht(rij) and "e-__E__-value" not in _gemarkeerd(rij)
    assert not _group_title_marked(rij, "e_order.__H__"), "an unasked address carries the star"
    assert "h-__H__-mobile" not in _gemarkeerd(rij) and "h-__H__-mobile" not in _verplicht(rij)
    # The other side of the difference, on the same page: the main member's row.
    assert "h-n0-mobile" in _gemarkeerd(page.text) & _verplicht(page.text)
    assert "e-n0e-value" in _verplicht(page.text)
    assert _group_title_marked(page.text, "e_order.n0")


def test_geen_grijs_sterretje_meer_in_de_labeltekst(client, db_session):
    """De concrete regressie: een `*` in de labeltekst erft de kleur van het label.
    Elk sterretje in een label hoort in de rode span te zitten. The page holds
    the new person's row too (the group's template)."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    html = client.get("/lid-worden").text
    labels = LABEL.findall(html)
    assert {"h-n0-mobile", "h-__H__-first_name"} <= {for_id for for_id, _inhoud in labels}, (
        "the labels of the main member and of a new person are not both on the page"
    )
    for for_id, inhoud in labels:
        zonder_rode_span = re.sub(r'<span class="text-red-600">.*?</span>', "", inhoud, flags=re.S)
        assert "*" not in zonder_rode_span, (
            f"sterretje buiten de rode span in het label van {for_id}"
        )
