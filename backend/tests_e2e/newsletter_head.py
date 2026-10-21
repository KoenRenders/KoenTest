"""The letter in the browser tests (#2183): subject, preview text, audience and text are
one record page — "Bewerken" opens all of it, one Opslaan stores it and sends the
browser back to the page, read."""


def open_head_card(page) -> None:
    """Bewerken: the letter opens for editing (the action bar stands under it). A new
    letter opens that way already."""
    if page.locator("[data-action-bar]").is_visible():
        return
    page.locator("#nb-kop [data-head-secondary]").click()
    page.locator("[data-action-bar]").wait_for(state="visible")


def save_letter(page) -> None:
    """Opslaan, and wait for the read page it sends the browser back to: the browser
    goes there as a boosted visit, so the page is settled when the bar is gone and the
    record form has taken its first state again."""
    page.locator("[data-action-bar] [data-form-save]").click()
    page.locator("[data-action-bar]").wait_for(state="hidden", timeout=15_000)
    page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")


def set_head(page, *, subject=None, preview=None, audience=None) -> str:
    """Open the letter the browser is on for editing, fill it, press Opslaan and wait
    for the read page. Returns the letter's address."""
    address = page.url.split("?")[0]
    open_head_card(page)
    if subject is not None:
        page.fill("#nb-onderwerp", subject)
    if preview is not None:
        page.fill("#nb-voorbeeldtekst", preview)
    if audience is not None:
        page.locator(f'input[name="audience"][value="{audience}"]').check()
    save_letter(page)
    return address
