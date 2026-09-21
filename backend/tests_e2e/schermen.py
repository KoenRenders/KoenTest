"""Selectors en stap-helpers voor de e2e-flows (#622, laag 3).

De scenario's overleven een eventuele terugkeer naar React — "bevestig een betaling
en controleer dat het saldo klopt" blijft dezelfde handeling — maar hun **selectors**
niet. Die staan daarom hier bij elkaar, zodat een UI-port precies dit ene bestand
raakt in plaats van elke flow.

De testfuncties lezen dan als scenario's, niet als klikinstructies.
"""
import os
from contextlib import contextmanager

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


# ── Waiting on htmx, not on the clock (#997) ─────────────────────────────────
#
# A fixed `wait_for_timeout` after a click is a race: on a slow runner the next
# line looks at a screen that is not there yet. Where something must APPEAR, a
# test waits on Playwright's own `expect(...)`. Where a test proves that
# something did NOT happen, there is nothing to wait for — so it waits until
# htmx is demonstrably done, and only then checks the absence.
#
# "Done" is read from htmx itself: every request that began has ended (its
# XHR fired `loadend`), and no element still carries `htmx-request`,
# `htmx-swapping` or `htmx-settling`. htmx sets `htmx-swapping` synchronously
# before a swap — also one delayed by a view transition — and removes
# `htmx-settling` only after the settle in which #726 resets attributes. So the
# condition cannot be true between the response and the end of the settle.
_HTMX_TELLER = """() => {
  if (!window.__htmxTel) {
    const t = window.__htmxTel = {begonnen: 0, afgerond: 0};
    // Counted on the XHR and not with `htmx:afterRequest`: htmx fires that on the
    // element that made the request, and when the swap removed that element the
    // event never reaches the document (measured: 2 begun, 1 ended, forever).
    // `loadend` comes after htmx's own load/error/abort handling, always.
    document.addEventListener('htmx:beforeRequest', (e) => {
      const tel = window.__htmxTel;
      tel.begonnen++;
      e.detail.xhr.addEventListener('loadend', () => { tel.afgerond++; });
    });
  }
  window.__htmxTel.begonnen = 0;
  window.__htmxTel.afgerond = 0;
}"""
_HTMX_STIL = """(minstens) => {
  const t = window.__htmxTel;
  // No counters: the answer replaced the whole document (HX-Redirect,
  // HX-Refresh). Then "done" is that document having loaded.
  if (!t) return document.readyState === 'complete';
  return t.begonnen >= minstens && t.afgerond >= t.begonnen
    && !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling');
}"""


@contextmanager
def htmx_afgerond(page, *, verzoeken: int = 1, timeout: int = 10_000):
    """Run the block, then wait until the htmx requests it started are settled.

    `verzoeken` is how many requests the block must start at least — a debounced
    input starts its request later, and waiting for "nothing running" before it
    began would be the race again. Only for htmx actions: a full page load
    replaces the document and its counters; then the wait ends once the new
    document has loaded.
    """
    page.evaluate(_HTMX_TELLER)
    yield
    page.wait_for_function(_HTMX_STIL, arg=verzoeken, timeout=timeout)


def netwerk_bijgewerkt(page, *, timeout: int = 10_000) -> None:
    """A barrier for proving that something did NOT happen (#997).

    Requests leave in the order the page starts them. So once a fresh sentinel
    request has been answered, any request the page started before it has gone
    out too — and `htmx_stil` then waits until such a request is also swapped.
    Only after that is "nothing changed" a finding. A fixed wait passes just as
    well when the thing is merely slow, and then the test proves nothing.
    """
    with page.expect_response(lambda r: "e2e-grens" in r.url, timeout=timeout):
        page.evaluate("() => fetch('/static/app.css?e2e-grens=' + Date.now())")
    htmx_stil(page, timeout=timeout)


def pagina_klaar(page, *, timeout: int = 10_000) -> None:
    """After a `goto`: Alpine has initialised every `x-data`, and htmx is idle.

    A check on the starting state ("the menu is closed") says nothing while
    Alpine has not yet evaluated its `x-show` — this is the moment it does.
    """
    page.wait_for_function(
        "() => !!window.Alpine && [...document.querySelectorAll('[x-data]')]"
        ".every(e => e._x_dataStack)", timeout=timeout)
    htmx_stil(page, timeout=timeout)


def htmx_stil(page, *, timeout: int = 10_000) -> None:
    """Wait until nothing htmx started is still running — after a page load.

    For a check right after `goto`: htmx may still be processing what the page
    loads (`hx-trigger="load"`). Starts no request of its own.
    """
    page.wait_for_function(
        "() => !!window.htmx && !document.querySelector("
        "'.htmx-request, .htmx-swapping, .htmx-settling')", timeout=timeout)


def open_de_raakje_bel(page, pad: str = "/"):
    """De zwevende Raakje-bel op een publieke pagina openen (#1120).

    De publieke pagina `/raakje` is weg — niemand kwam er, en niets verwees ernaar.
    De bel staat op élke publieke pagina en draagt dezelfde bediening, dus de
    e2e's die vroeger op die pagina maten, meten hier. Het paneel begint dicht;
    zonder de klik is het veld er wel maar onzichtbaar.

    Geeft het vraagveld terug.
    """
    page.goto(pad)
    pagina_klaar(page)
    page.get_by_role("button", name="Raakje — vraag het aan onze AI-assistent").click()
    page.wait_for_selector("#raakje-widget-vraag", state="visible", timeout=5000)
    return page.locator("#raakje-widget-vraag")


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
        with htmx_afgerond(self.page):
            self.page.get_by_role("button", name="Toevoegen", exact=True).click()


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
        # Sinds #996 een stille link met het korte label "Bevestig"; de
        # bevestigingsvraag draagt de type-woorden.
        rij.get_by_role("button", name="Bevestig", exact=True).click()
        # In-app bevestigingsmodal (#595), geen browser-confirm.
        with htmx_afgerond(self.page):
            self.page.get_by_role("button", name="Bevestigen").click()

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
        with htmx_afgerond(self.page):
            self.paneel.get_by_role("button", name="Opslaan").first.click()

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
        htmx_stil(self.page)
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
        with htmx_afgerond(self.page):
            self.page.get_by_role("button", name="Opslaan").first.click()

    def toon_html_bron(self):
        # Alpine only, no request: the caller waits on the box itself.
        self.page.get_by_role("button", name="HTML").first.click()

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
        # #997: anchored on the detail and on the card's own heading. The old
        # `div has_text=… .last` also matched on the list page, which carries the
        # word too — before the detail had arrived, it found some other div.
        return self.page.locator("#leden-detail div").filter(
            has=self.page.locator("h3", has_text="Lidmaatschappen")).last

    def lidmaatschapskop(self):
        return self.page.locator("#leden-detail h3", has_text="Lidmaatschappen")

    def lidmaatschap_verwijderknop(self):
        return self.lidmaatschapskaart().get_by_role("button", name="Verwijderen").first

    def verwijder_lidmaatschap(self):
        self.lidmaatschap_verwijderknop().click()
        # In-app bevestigingsmodal (#595), geen browser-confirm.
        with htmx_afgerond(self.page):
            self.page.get_by_role("button", name="Bevestigen").click()


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
        with htmx_afgerond(self.page):
            self.page.locator(f'aside a[href="{href}"]').first.click()
        self.page.wait_for_selector("#main h1", timeout=5000)


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
