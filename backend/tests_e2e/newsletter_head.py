"""The head of a draft letter in the browser tests (#2113): subject, preview text and
audience are saved on the head's edit card of the letter's page (Acties › Onderwerp en
doelgroep, then Opslaan); the text of the letter saves itself."""


def open_head_card(page) -> None:
    """Acties › Onderwerp en doelgroep: the head's edit card opens in the page."""
    page.locator("#nb-kop [data-actions-trigger]").click()
    page.locator("#nb-kop").get_by_role("menuitem", name="Onderwerp en doelgroep").click()
    page.locator("#nb-kop-form").wait_for(state="visible")


def set_head(page, *, subject=None, preview=None, audience=None) -> str:
    """Open the card of the letter the browser is on, fill it, press Opslaan and wait for
    it to close. Returns the letter's address."""
    address = page.url.split("?")[0]
    open_head_card(page)
    if subject is not None:
        page.fill("#nb-onderwerp", subject)
    if preview is not None:
        page.fill("#nb-voorbeeldtekst", preview)
    if audience is not None:
        page.locator("#nb-doelgroep").select_option(audience)
    page.locator("[data-action-bar] [data-form-save]").click()
    page.locator("#nb-kop-form").wait_for(state="hidden", timeout=10_000)
    return address
