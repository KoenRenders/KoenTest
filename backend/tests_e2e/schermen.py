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

    def kaart_met_knop(self, knoplabel: str):
        """De eerste kaart die deze actie aanbiedt.

        Betrouwbaarder dan "de eerste kaart" of een kaart op naam (#644-D): op één
        payable staan meerdere records (een openstaande vordering, een betaalde,
        een terugbetaling) met dezelfde contactnaam, en welke bovenaan staat hangt
        van de aanmaakvolgorde af. Een test die "bevestig betaald" wil, hoort de
        kaart te kiezen die dat kán.
        """
        return self.page.locator(
            ".bg-white", has=self.page.get_by_role("button", name=knoplabel)).first

    def ogm_van(self, kaart) -> str | None:
        tekst = kaart.locator("text=OGM").first
        if tekst.count() == 0:
            return None
        return tekst.inner_text().split("OGM")[-1].strip()

    def bevestig_betaald(self, kaart):
        kaart.get_by_role("button", name="Bevestig betaald").click()
        # In-app bevestigingsmodal (#595), geen browser-confirm.
        self.page.get_by_role("button", name="Bevestigen").click()
        self.page.wait_for_timeout(300)

    def badges(self, ogm: str) -> list[str]:
        return self.kaart(ogm).locator("span.rounded-full").all_inner_texts()

    def toon_inschrijvingsdetails(self, kaart):
        """Klap het detail open en geef het paneel terug, zodat de bewerkingen
        erna binnen díe kaart gebeuren en niet in een andere op de pagina.

        Wacht op de INHOUD, niet op de zichtbaarheid van het paneel zelf. Alpine
        zet `x-show` meteen om, maar htmx vult het paneel pas met de eerste
        `hx-get`. Een lege div heeft geen hoogte, en Playwright rekent een element
        van nul bij nul als verborgen — dus "wacht tot het paneel zichtbaar is"
        was in werkelijkheid "wacht tot het antwoord binnen is", met een
        wedloop als het even traag ging. Deze test viel daar geregeld over.
        """
        kaart.get_by_text("Toon inschrijvingsdetails").click()
        paneel = kaart.locator('[id^="det-"]').first
        paneel.locator("> *").first.wait_for(state="visible", timeout=10000)
        return paneel


class Inschrijvingsdetail:
    """Het gedeelde detail/editor-fragment onder een betaalkaart.

    Krijgt het paneel mee i.p.v. de hele pagina: op het betalingenscherm staan
    meerdere kaarten met elk hun eigen "Bewerken" en "Opslaan", en `.first` op de
    pagina belandde in de verkeerde.
    """

    def __init__(self, paneel):
        self.paneel = paneel
        self.page = paneel.page

    def bewerken(self):
        self.paneel.get_by_role("button", name="Bewerken").first.click()

    def aantalvelden(self):
        return self.paneel.locator('input[name^="quantity_"]')

    def zet_aantal(self, index: int, aantal: int):
        self.aantalvelden().nth(index).fill(str(aantal))

    def opslaan(self):
        self.paneel.get_by_role("button", name="Opslaan").first.click()
        self.page.wait_for_timeout(400)

    def totaal(self) -> str:
        return self.paneel.locator("text=Totaal").first.inner_text()


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


class Activiteitdetail:
    """/admin/activiteiten/<id> — het scherm waarop #649 gemeld werd.

    De datumsectie is er het kleinste bewerkformulier op: één regel, één
    Bewerken-knop, één Opslaan. Precies de POST die op HDEV elf keer 403 gaf
    zonder dat er iets op het scherm veranderde.
    """

    def __init__(self, page):
        self.page = page

    def open_eerste(self, naam: str | None = None):
        """Open een activiteitdetail vanuit de lijst; geeft False als er geen is."""
        self.page.goto("/admin/activiteiten")
        self.page.wait_for_selector("main", timeout=5000)
        if naam:
            link = self.page.get_by_text(naam).first
            if link.count() == 0:
                return False
            link.click()
        else:
            # Niet de eerste /admin/activiteiten/-link nemen: "+ Activiteit" wijst
            # naar /nieuw en staat bovenaan. Alleen een link naar een echt id telt.
            pad = self.page.evaluate(
                r"""Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.getAttribute('href'))
                        .find(h => /^\/admin\/activiteiten\/\d+$/.test(h)) || null""")
            if not pad:
                return False
            self.page.goto(pad)
        self.page.wait_for_selector("#aa-detail", timeout=5000)
        return True

    def datumregel(self):
        """De eerste datumregel — herkenbaar aan haar eigen bewerkformulier."""
        return self.page.locator('form[hx-post*="/datums/"]').first

    def bewerk_de_eerste_datum(self):
        """Klap het bewerkformulier van de eerste datumregel open."""
        rij = self.datumregel().locator("xpath=..")
        rij.get_by_role("button", name="Bewerken").first.click()

    def bewaar(self):
        self.datumregel().get_by_role("button", name="Opslaan").first.click()

    def breek_het_csrf_token(self) -> None:
        """Vervang het CSRF-token door een ongeldige waarde.

        Dat is exact wat er bij Koen gebeurde, zonder een tweede venster nodig te
        hebben: het token is afgeleid van de sessiecookie, dus na een herinlog
        elders draagt dit tabblad een token dat niet meer bij de cookie past.
        require_csrf antwoordt dan 403.
        """
        self.page.evaluate(
            """document.body.setAttribute('hx-headers',
                   JSON.stringify({'X-CSRF-Token': 'verlopen-token'}))""")

    def datum_leesregel(self):
        """De tekstregel met de datum — die hoort te verdwijnen tijdens bewerken (#648)."""
        return self.datumregel().locator('xpath=../div/span[@x-show="!edit"]').first

    def foutmeldingen(self):
        """De meldingen die htmx_ux() in de toast-host zet (#649)."""
        return self.page.locator("#toasts [data-fout]")
