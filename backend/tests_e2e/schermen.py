"""Selectors en stap-helpers voor de e2e-flows (#622, laag 3).

De scenario's overleven een eventuele terugkeer naar React — "bevestig een betaling
en controleer dat het saldo klopt" blijft dezelfde handeling — maar hun **selectors**
niet. Die staan daarom hier bij elkaar, zodat een UI-port precies dit ene bestand
raakt in plaats van elke flow.

De testfuncties lezen dan als scenario's, niet als klikinstructies.
"""
import os

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


def login_met_sessie(page, sessiewaarde: str) -> None:
    """Zet de sessiecookie rechtstreeks.

    Sneller en minder broos dan de OTP-flow doorlopen, en die flow wordt elders al
    getest (test_fase1_ui). Wie de login zélf wil dekken, doet dat in een eigen test.

    Los van `login_als_admin` sinds #718: die naam leest als admin-only terwijl er
    ook als gewoon lid ingelogd moet kunnen worden. De rol zit in de sessiewaarde,
    niet in deze functie.
    """
    page.context.add_cookies([{
        "name": "raak_session", "value": sessiewaarde,
        "url": BASE, "http_only": True, "same_site": "Lax",
    }])


def login_als_admin(page, email: str, sessiewaarde: str) -> None:
    """Zie `login_met_sessie`; `email` staat er voor de leesbaarheid van de aanroep."""
    login_met_sessie(page, sessiewaarde)


class Gezinsportaal:
    """/leden/gezin — het portaal van een lid (#718)."""

    pad = "/leden/gezin"

    def __init__(self, page):
        self.page = page

    def open(self):
        self.page.goto(self.pad)
        self.page.wait_for_selector("main", timeout=5000)
        return self

    def navigatiebalk(self):
        """De brede menubalk van de publieke schil — het onderwerp van #718."""
        return self.page.locator("#site-nav-breed")

    def voeg_gezinslid_toe(self, voornaam: str, achternaam: str):
        self.page.get_by_role("button", name="+ Gezinslid toevoegen").click()
        self.page.fill("#np-first_name", voornaam)
        self.page.fill("#np-last_name", achternaam)
        self.page.fill("#np-date_of_birth", "2012-03-04")
        self.page.select_option("#np-gender_code", "M")
        self.page.get_by_role("button", name="Toevoegen", exact=True).click()
        self.page.wait_for_timeout(600)


class Betalingenscherm:
    """/admin/betalingen — sinds golf 10 (#913) een dichte tabel: één rij per
    boeking, de FINANCE-acties per rij, de editors als uitklaprij eronder."""

    pad = "/admin/betalingen"

    def __init__(self, page):
        self.page = page

    def open(self):
        self.page.goto(self.pad)
        # Korte wacht: is de lijst er niet, dan is dat een overslaan-geval voor de
        # test, geen reden om 30 seconden in een timeout te lopen.
        self.page.wait_for_selector("#betalingen-lijst", timeout=5000)
        return self

    def rij(self, ogm: str):
        """Een rij aanwijzen via haar OGM — die is uniek en zichtbaar."""
        return self.page.locator("#betalingen-lijst tbody tr", has_text=ogm).first

    def rij_met_knop(self, knoplabel: str):
        """De eerste rij die deze actie aanbiedt.

        Betrouwbaarder dan "de eerste rij" of een rij op naam (#644-D): op één
        payable staan meerdere records (een openstaande vordering, een betaalde,
        een terugbetaling) met dezelfde contactnaam, en welke bovenaan staat hangt
        van de aanmaakvolgorde af. Een test die "bevestig betaald" wil, hoort de
        rij te kiezen die dat kán.
        """
        return self.page.locator(
            "#betalingen-lijst tbody tr",
            has=self.page.get_by_role("button", name=knoplabel)).first

    def ogm_van(self, rij) -> str | None:
        """Sinds golf 10 staat de OGM kaal (mono) onder de naam, zonder
        "OGM"-voorvoegsel — zoals de Cobalt-referentie."""
        cel = rij.locator(".font-mono").first
        if cel.count() == 0:
            return None
        return cel.inner_text().strip()

    def bevestig_betaald(self, rij):
        rij.get_by_role("button", name="Bevestig betaald").click()
        # In-app bevestigingsmodal (#595), geen browser-confirm.
        self.page.get_by_role("button", name="Bevestigen").click()
        self.page.wait_for_timeout(300)

    def badges(self, ogm: str) -> list[str]:
        return self.rij(ogm).locator("span.rounded-full").all_inner_texts()

    def bewerkbaar_detailpaneel(self):
        """Het eerste inschrijvingsdetail dat écht te bewerken is.

        Sinds golf 10 zonder inline-disclosure op het betalingenscherm: de naam
        in de tabel is de B2-link naar de inschrijvingspagina, en het gedeelde
        detailfragment staat dáár. Dezelfde #644-D-redenering blijft: kies de
        inschrijving die de handeling kán — een geschrapte toont haar paneel
        read-only, zonder bewerk-toggle.

        Geeft None als geen enkele inschrijving bewerkbaar is — dan is het een
        overslaan-geval voor de test, geen bevinding.
        """
        # Begin bij een VERSE lijst (#736): de helper wordt ook ná een bewerking
        # aangeroepen, en de tabel van dat moment kan al ververst zijn.
        self.open()
        links = self.page.locator(
            '#betalingen-lijst a[href*="/admin/inschrijvingen/"]')
        hrefs: list[str] = []
        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")
            if href and href not in hrefs:
                hrefs.append(href)
        for href in hrefs:
            self.page.goto(href)
            # Ankeren op het formulier-id en niet op de Bewerken-knop: locators
            # her-resolven bij elke actie, en zodra Bewerken geklikt is verbergt
            # x-show hem — een has=Bewerken-paneel lost dan op naar niets.
            paneel = self.page.locator(
                "div.bg-gray-50.border",
                has=self.page.locator('form[id^="insch-form-"]')).first
            if paneel.count() and paneel.get_by_role(
                    "button", name="Bewerken").count():
                return paneel
        return None


class Inschrijvingsdetail:
    """Het gedeelde detail/editor-fragment (#455/#613), sinds golf 10 op de
    inschrijvingspagina zelf.

    Krijgt het paneel mee i.p.v. de hele pagina, zodat de bewerkingen binnen
    het fragment blijven en niet in een ander element met dezelfde knoppen.
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

    def staat_in_bewerkmodus(self) -> bool:
        """De bewerkstand herkennen aan de Opslaan-knop, niet aan de x-data.

        Alpine zet `x-show` om naar `display:none`; het attribuut blijft staan. Wat
        de gebruiker ziet, is dus of de knop er staat — en dat is ook waar #717 over
        gaat.
        """
        knop = self.paneel.get_by_role("button", name="Opslaan")
        return knop.count() > 0 and knop.first.is_visible()


class Paginascherm:
    """/admin/paginas — de CMS-lijst en de paginabrede editor (#726)."""

    pad = "/admin/paginas"

    def __init__(self, page):
        self.page = page

    def open_eerste(self):
        self.page.goto(self.pad)
        self.page.wait_for_timeout(400)
        # De kaarten zijn gewone links naar /admin/paginas/<id>; hx-boost maakt er
        # een fragment-navigatie van. "Nieuw" valt af omdat die op /nieuw uitkomt.
        links = self.page.locator("a[href^='/admin/paginas/']:not([href$='/nieuw'])")
        if links.count() == 0:
            return None
        links.first.click()
        # Op ATTACHED wachten en niet op zichtbaarheid: dit vak hóórt verborgen te
        # zijn, en "wacht tot het zichtbaar is" zou hier de bug als geslaagd lezen.
        self.page.wait_for_selector("#cp-htmlsrc", state="attached", timeout=10000)
        return self

    def htmlbron(self):
        return self.page.locator("#cp-htmlsrc")

    def opslaan(self):
        self.page.get_by_role("button", name="Opslaan").first.click()
        self.page.wait_for_timeout(800)

    def toon_html_bron(self):
        self.page.get_by_role("button", name="HTML").first.click()
        self.page.wait_for_timeout(300)

    def editorinhoud(self) -> str:
        return self.page.locator("#cp-content-input").first.input_value() or ""


def toasts(page):
    """De bevestigingen die in de vaste landingsplek zijn beland (#528/#717).

    `#toasts` staat in de schil; htmx zet er out-of-band elementen in. Alleen de
    kinderen tellen — de host zelf staat er altijd, ook leeg.
    """
    return page.locator("#toasts > *")


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


def controlhoogtes(page, container_selector: str) -> dict:
    """De GERENDERDE hoogte van elk formulierveld in een container (#677).

    Een rendertest op klassen zegt hier niets: beide controls dragen al dezelfde
    opmaak. De fout zit in wat de BROWSER ervan maakt — een <select> krijgt
    intrinsieke ruimte voor zijn pijltje, een <input> niet. Alleen een echte
    browser kan dat meten.
    """
    hoogtes: dict = {}
    velden = page.locator(f"{container_selector} input:not([type=checkbox]):not([type=hidden]), "
                          f"{container_selector} select")
    for i in range(velden.count()):
        veld = velden.nth(i)
        if not veld.is_visible():
            continue
        doos = veld.bounding_box()
        if doos:
            naam = veld.get_attribute("name") or veld.get_attribute("id") or f"veld{i}"
            hoogtes[naam] = round(doos["height"], 1)
    return hoogtes


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
        """Sinds de kop-herziening van golf 6 (#913) staat Opslaan niet meer ín
        de datumvorm maar in het kop-cluster van de rij, via het HTML
        form=-attribuut aan de vorm gekoppeld — dus zoeken op die koppeling."""
        form_id = self.datumregel().get_attribute("id")
        self.page.locator(f'button[form="{form_id}"]').first.click()

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
