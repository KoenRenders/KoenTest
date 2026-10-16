"""The help texts of the tenant record say what a value is (#1963).

A screen says what a value is, never what another domain does with it (`AGENTS.md`,
*Keep it simple*): the other domain's use can change tomorrow and the screen is wrong
without anyone having touched it. Koen approved the texts of the record as one package
on 15 October 2026; this reads them from the rendered record in edit mode.

Proven red (16 October 2026, put back): the help of "Canonieke URL" turned back into
"Publieke origin voor links in mails/Mollie/SEO, bv. https://…" → the approved text is
missing and the jargon check names "Publieke origin".
"""

import html

import pytest

from tests.test_tenant_beheer import _login

pytestmark = pytest.mark.ui_agnostisch

#: The approved help texts (Koen, 15 October 2026), as the record shows them.
APPROVED = [
    "De naam waaronder de site zich voorstelt. Leeg = de naam van de organisatie achter de site.",
    "De organisatie waarvan de site de gegevens toont. Alleen organisaties van het eigen account.",
    "Korte ondertitel van de site. Leeg = geen ondertitel.",
    "Achtergrondkleur van de kopbalk, bv. #005d29. Leeg = de standaardkleur.",
    "De hoofdkleur van de huisstijl, bv. #0051a4. Leeg = de standaardkleur.",
    "De kleur voor wat moet opvallen, bv. #ffd200. Leeg = de standaardkleur.",
    "Het webadres van de site, bv. https://…",
    "Taal van de site, bv. nl_BE.",
    "Bedrag, bv. 35.00. Leeg = het bedrag van de omgeving.",
    "Aantal dagen voor een overschrijving. Leeg = 7.",
    "Het Gmail-account waarmee de site mailt. Leeg = het account van de omgeving.",
    "Het nummer van de site bij Umami.",
    "Hoogste aantal per product in één inschrijving. Leeg = 50.",
    "Per e-mailadres en per activiteit. Leeg = 3.",
    "Werkt alleen als de omgeving Raakje toelaat.",
    "Terug naar de waarde van de omgeving.",
]

#: Words a board member cannot act on, or that name what another part does with a value.
JARGON = [".env", "SMTP", "ENABLED", "Publieke origin", "Mollie/SEO", "de mails", "de voettekst"]

#: The placeholder of an empty secret says ".env-default". It is a placeholder, not a help
#: text, and Koen's package leaves the two secrets as they are; named to him as a
#: remaining case, so the check passes over it instead of hiding it.
LEFT_FOR_KOEN = "niet gezet — .env-default geldt"


def _record(client, db_session, tenant_id) -> str:
    _login(client, db_session, operator=True)
    resp = client.get(f"/admin/tenants/{tenant_id}?bewerken=1")
    assert resp.status_code == 200
    return html.unescape(resp.text)


def test_the_record_shows_the_approved_help_texts(client, platform_workspace, db_session):
    from app.kernel.tenancy import TENANT_VOORBEELD_ID

    page = _record(client, db_session, TENANT_VOORBEELD_ID)
    missing = [text for text in APPROVED if text not in page]
    assert not missing, f"approved help texts not on the record: {missing}"


def test_no_help_text_speaks_jargon_or_other_parts(client, platform_workspace, db_session):
    from app.kernel.tenancy import TENANT_VOORBEELD_ID

    page = _record(client, db_session, TENANT_VOORBEELD_ID)
    page = page.replace(LEFT_FOR_KOEN, "")
    found = [word for word in JARGON if word in page]
    where = {w: page[max(page.index(w) - 60, 0) : page.index(w) + 40] for w in found}
    assert not found, f"the tenant record still says: {where}"
