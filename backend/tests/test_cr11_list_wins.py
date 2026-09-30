"""CR-11 W11 (#1391): a record opens from its list.

- Six card lists whose card already is the link lose the words "Bewerken ›"
  ("Instellingen bewerken ›" on the tenants); a bare "›" stays as the sign that
  the card opens. The pages list becomes a stretched link over the whole card.
- In the registrations table the contact's name is plain text: a blue name
  promised the person and opened the registration; "Details" is the way in.
- On Betalingen a click on the row opens it, like "Bewerken", unless it lands on
  something that acts itself.

The click geometry (20 px from a card's right edge opens the record) was
measured in a browser for the handover; here the markup that produces it is
pinned. Proven red: the old label put back in `_aa_kaarten.html`; the name link
put back in `_inschrijvingen_groepen.html`; the row handler removed.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

CARD_LISTS = {
    "domains/activities/templates/_aa_kaarten.html": "Bewerken",
    "domains/mdm/templates/_leden_lijst.html": "Bewerken",
    "domains/forms/templates/_fb_kaarten.html": "Bewerken",
    "ui/templates/_org_kaarten.html": "Bewerken",
    "ui/templates/_tn_kaarten.html": "Instellingen bewerken",
    "domains/cms/templates/_cp_kaarten.html": "Bewerken",
}


def test_the_cards_lose_the_edit_label_and_keep_a_bare_chevron():
    for rel, word in CARD_LISTS.items():
        text = (APP / rel).read_text()
        assert f'{{{{ _("{word}") }}}} ›' not in text, f"{rel}: the label is back"
        assert 'aria-hidden="true">›</span>' in text, f"{rel}: no bare chevron"


def test_the_pages_card_is_one_stretched_link_with_the_arrows_above_it():
    text = (APP / "domains/cms/templates/_cp_kaarten.html").read_text()
    assert 'class="absolute inset-0 rounded-xl"' in text
    # Only the arrows get a layer above the link. A z-10 on their whole wrapper
    # (measured: a click 20 px from the card's edge landed on the wrapper and
    # opened nothing) swallowed the clicks meant for the card.
    assert '<div class="relative z-10">{{ ui.reorder(' in text
    assert '<div class="shrink-0 flex items-center gap-3">' in text
    assert text.count('href="/admin/paginas/{{ p.id }}"') == 1


def test_the_contact_name_is_plain_text_and_details_is_the_way_in():
    text = (APP / "domains/activities/templates/_inschrijvingen_groepen.html").read_text()
    assert "{{ r.contact_name }}</a>" not in text
    assert 'ui.btn_secondary(_("Details")' in text


def test_a_payment_row_opens_on_a_click_but_not_through_a_control():
    text = (APP / "domains/payment/templates/_betalingen_lijst.html").read_text()
    row = text[text.index("{% macro _rij(") :]
    row = row[: row.index("</td>")]
    assert "data-row-opens" in row and "@click=" in row
    assert "closest('a,button,input,select,textarea,label')" in row
    assert "open = open === '{{ r.id }}' ? null : '{{ r.id }}'" in row
