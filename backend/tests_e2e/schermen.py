"""Selectors en stap-helpers voor de e2e-flows (#622, laag 3).

De scenario's overleven een eventuele terugkeer naar React — "bevestig een betaling
en controleer dat het saldo klopt" blijft dezelfde handeling — maar hun **selectors**
niet. Die staan daarom hier bij elkaar, zodat een UI-port precies dit ene bestand
raakt in plaats van elke flow.

De testfuncties lezen dan als scenario's, niet als klikinstructies.
"""
import os

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


def login_als_admin(page, email: str, sessiewaarde: str) -> None:
    """Zet de sessiecookie rechtstreeks.

    Sneller en minder broos dan de OTP-flow doorlopen, en die flow wordt elders al
    getest (test_fase1_ui). Wie de login zélf wil dekken, doet dat in een eigen test.
    """
    page.context.add_cookies([{
        "name": "raak_session", "value": sessiewaarde,
        "url": BASE, "http_only": True, "same_site": "Lax",
    }])


class Betalingenscherm:
    """/admin/betalingen — de kaartenlijst met de FINANCE-acties."""

    pad = "/admin/betalingen"

    def __init__(self, page):
        self.page = page

    def open(self):
        self.page.goto(self.pad)
        # Korte wacht: is de lijst er niet, dan is dat een overslaan-geval voor de
        # test, geen reden om 30 seconden in een timeout te lopen.
        self.page.wait_for_selector("#betalingen-lijst", timeout=5000)
        return self

    def kaart(self, ogm: str):
        """Een kaart aanwijzen via haar OGM — die is uniek en zichtbaar."""
        return self.page.locator(".bg-white", has_text=ogm).first

    def bevestig_betaald(self, ogm: str):
        kaart = self.kaart(ogm)
        kaart.get_by_role("button", name="Bevestig betaald").click()
        # In-app bevestigingsmodal (#595), geen browser-confirm.
        self.page.get_by_role("button", name="Bevestigen").click()
        self.page.wait_for_timeout(300)

    def badges(self, ogm: str) -> list[str]:
        return self.kaart(ogm).locator("span.rounded-full").all_inner_texts()

    def toon_inschrijvingsdetails(self, ogm: str):
        self.kaart(ogm).get_by_text("Toon inschrijvingsdetails").click()
        self.page.wait_for_selector(".bg-gray-50", timeout=5000)


class Inschrijvingsdetail:
    """Het gedeelde detail/editor-fragment onder een betaalkaart."""

    def __init__(self, page):
        self.page = page

    def bewerken(self):
        self.page.get_by_role("button", name="Bewerken").first.click()

    def zet_aantal(self, index: int, aantal: int):
        veld = self.page.locator('input[name^="quantity_"]').nth(index)
        veld.fill(str(aantal))

    def opslaan(self):
        self.page.get_by_role("button", name="Opslaan").first.click()
        self.page.wait_for_timeout(400)

    def totaal(self) -> str:
        return self.page.locator("text=Totaal").first.inner_text()


class Ledenscherm:
    """/admin/leden — gezinnenlijst en het gezinsdetail."""

    pad = "/admin/leden"

    def __init__(self, page):
        self.page = page

    def open(self):
        self.page.goto(self.pad)
        self.page.wait_for_selector("#leden-lijst", timeout=5000)
        return self

    def open_gezin(self, naam: str):
        self.page.get_by_text(naam).first.click()
        self.page.wait_for_selector("#leden-detail, main")

    def lidmaatschapskaart(self):
        """De kaart met de lidmaatschapsjaren — herkenbaar aan haar eigen kop.

        Niet ".last": op het gezinsdetail staan meerdere Verwijderen-knoppen
        (personen, lidmaatschappen) en welke de laatste is, hangt af van de data
        (#644-D).
        """
        return self.page.locator("div", has_text="Lidmaatschappen").last

    def lidmaatschap_verwijderknop(self):
        return self.lidmaatschapskaart().get_by_role("button", name="Verwijderen").first

    def verwijder_lidmaatschap(self):
        self.lidmaatschap_verwijderknop().click()
        # In-app bevestigingsmodal (#595), geen browser-confirm.
        self.page.get_by_role("button", name="Bevestigen").click()
        self.page.wait_for_timeout(400)


class Adminschil:
    """De AdminShell zelf (#634): zijbalk, titel en de wachtfeedback van htmx.

    Deze klasse test geen scherm maar de *navigatie* — de eigenschap die met
    hx-boost is toegevoegd. Bij een UI-port verdwijnt de zijbalk misschien, maar
    "navigeren mag de schil niet opnieuw opbouwen" blijft een zinnig scenario.
    """

    def __init__(self, page):
        self.page = page

    def merk_de_zijbalk(self) -> None:
        """Zet een JS-eigenschap op de <aside>; die overleeft geen herlaad."""
        self.page.evaluate("document.querySelector('aside').__raakMerk = 1")

    def zijbalk_is_nog_dezelfde(self) -> bool:
        return bool(self.page.evaluate(
            "!!(document.querySelector('aside') && document.querySelector('aside').__raakMerk)"))

    def klik_in_de_zijbalk(self, href: str) -> None:
        self.page.locator(f'aside a[href="{href}"]').first.click()
        self.page.wait_for_selector("#main h1", timeout=5000)
        self.page.wait_for_timeout(200)
