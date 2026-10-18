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
pinned. Proven red: the old label put back in `_fb_kaarten.html`; the name link
put back in `_inschrijvingen_groepen.html`; the row handler removed.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

LISTS = (
    "domains/forms/templates/_fb_kaarten.html",
    "domains/cms/templates/_cp_kaarten.html",
)


def test_the_lists_are_tables_whose_row_link_is_the_way_in():
    """#2123: Formulieren and Pagina's are rows of the kit's table, no longer cards with a
    chevron — the title is the row's link (`ui.row_link`), its click area covers the row."""
    for rel in LISTS:
        text = (APP / rel).read_text()
        assert "ui.data_table(" in text and "ui.row_link(" in text, f"{rel}: not the kit's table"
        assert "Bewerken" not in text and "›" not in text, f"{rel}: the card's label is back"


def test_the_pages_row_has_the_arrows_in_a_column_of_their_own_at_44_px():
    text = (APP / "domains/cms/templates/_cp_kaarten.html").read_text()
    assert "ui.reorder(" in text and "touch=True" in text, "44 px arrows on a phone"
    assert '<td data-cell="actions"' in text, "the arrows have a column of their own"
    # The arrows are buttons beside the row's link, never inside it (#745).
    assert text.count('href="/admin/paginas/') == 0 and text.count("ui.row_link(") == 1


def test_the_contact_name_is_plain_text_and_details_is_the_way_in():
    """W11 (#1391): a name as a link raises the expectation of going to the
    person, so "Details" was the way in. K6 (#1560) let the row unfold; #1636
    (Koen, 5 October 2026; CR-11 Q75) makes the row itself the way in, as K2
    did on Betalingen: the name is the row's link (`ui.row_link`) and leads to
    the REGISTRATION, never to the person. No "Details", no toggle; the jump
    "Inschrijving openen" stands in the row's menu, built by the table's
    builder."""
    text = (APP / "domains/activities/templates/_inschrijvingen_groepen.html").read_text()
    assert "ui.row_link(" in text and "r.href" in text
    assert "ui.row_toggle(" not in text and "ui.row_detail(" not in text
    assert '_("Details")' not in text
    builder = (APP / "domains/activities/registration_table.py").read_text()
    assert '_("Inschrijving openen")' in builder and "/admin/inschrijvingen/" in builder
    assert "/admin/leden/" not in builder, "the row leads to the registration, not to the person"


def test_a_payment_row_opens_on_a_click_but_not_through_a_control():
    """W11 (#1391) made a click anywhere on the row unfold its editor, through an
    Alpine handler that skipped clicks on a control. K2 (#1556, block 4) keeps
    the rule — the whole row opens — and changes the way: the name is the row's
    link (`ui.row_link`) and its click area covers the row; what must stay
    clickable itself sits above it (`data-above-row`). The row opens the
    booking's page; nothing unfolds. That the click works on the amount is
    measured in a browser (`tests_e2e/test_betalingen_table.py`)."""
    text = (APP / "domains/payment/templates/_betalingen_lijst.html").read_text()
    row = text[text.index("{% macro _rij(") : text.index("{% endmacro %}")]
    assert "<tr data-row" in row and "ui.row_link(" in row
    assert "@click=" not in row and "data-row-opens" not in row
    assert "data-above-row" in row, "the reference under Context is not above the row's link"
    macros = (APP / "ui/templates/_macros.html").read_text()
    css = (APP.parent.parent / "scripts/build-css.sh").read_text()
    assert "data-row-link" in macros
    assert '[data-row-link]::after{content:"";position:absolute;inset:0' in css
