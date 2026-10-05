"""Selectors en stap-helpers voor de e2e-flows (#622, laag 3).

De scenario's overleven een eventuele terugkeer naar React — "bevestig een betaling
en controleer dat het saldo klopt" blijft dezelfde handeling — maar hun **selectors**
niet. Die staan daarom hier bij elkaar, zodat een UI-port precies dit ene bestand
raakt in plaats van elke flow.

De testfuncties lezen dan als scenario's, niet als klikinstructies.
"""

import os
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")

# The platform host of the e2e app (`PLATFORM_HOSTS=platform.localhost`): where a
# tenant is reached by its path prefix, as on PROD. The host is REPLACED, not
# searched: CI runs on `localhost` and the local runner on `127.0.0.1`, and a
# `replace()` of one of the two works on one machine and quietly not on the other.
_SPLIT = urlsplit(BASE)
PLATFORM = urlunsplit(
    (
        _SPLIT.scheme,
        f"platform.localhost:{_SPLIT.port}" if _SPLIT.port else "platform.localhost",
        _SPLIT.path,
        "",
        "",
    )
)


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
        ".every(e => e._x_dataStack)",
        timeout=timeout,
    )
    htmx_stil(page, timeout=timeout)


def open_registration(page, activity_id: int, component_id: int) -> None:
    """The registration page of one component, reached the way a visitor does: from
    the card's "Inschrijven", which is a link to the page since CR-14 phase 1
    (#1332) — no longer a modal loaded by htmx. One place, so the way in is not
    typed out again in every test."""
    page.goto("/activiteiten")
    page.click(f'a[href="/activiteiten/{activity_id}/inschrijven/{component_id}"]')
    page.wait_for_url(f"**/activiteiten/{activity_id}/inschrijven/{component_id}")
    pagina_klaar(page)


def pagina_beeld_in_kiezer(dialoog, titel: str = "E2E-schermafdruk aanmelden"):
    """The seeded page picture in the CMS image dialog (#1474).

    Since #1474 the dialog shows the kit's picker over the whole library: it
    loads when the dialog opens, and the page picture is one of many, so it is
    found by its title after the picker has loaded. Returns the locator; it
    counts 0 when the picture is not there, which the callers report.
    """
    knop = dialoog.locator(f"button[data-url][data-title='{titel}']").first
    try:
        knop.wait_for(timeout=10_000)
    except Exception:  # noqa: BLE001 - the caller reports a missing picture
        pass
    return knop


def htmx_stil(page, *, timeout: int = 10_000) -> None:
    """Wait until nothing htmx started is still running — after a page load.

    For a check right after `goto`: htmx may still be processing what the page
    loads (`hx-trigger="load"`). Starts no request of its own.
    """
    page.wait_for_function(
        "() => !!window.htmx && !document.querySelector("
        "'.htmx-request, .htmx-swapping, .htmx-settling')",
        timeout=timeout,
    )


_WATCH_TRANSITIONS = """() => {
  window.__vt = {frames: 0, seen: 0};
  const tick = () => {
    window.__vt.seen += 1;
    const running = document.getAnimations().filter(a => a.effect && a.effect.pseudoElement
      && a.effect.pseudoElement.startsWith('::view-transition'));
    if (running.length) window.__vt.frames += 1;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""
_TRANSITION_FRAMES = """() => new Promise(resolve => {
  const from = window.__vt.seen;
  const wait = () => window.__vt.seen - from >= 30 ? resolve(window.__vt.frames) : requestAnimationFrame(wait);
  wait();
})"""


def watch_transitions(page) -> None:
    """From now on, count every frame in which a view transition runs (Refs
    #1589). Both shells run one on every htmx swap (`globalViewTransitions`);
    a swap inside the page that is no navigation must carry `transition:false`,
    or the whole page cross-fades for 250 ms. Call it before the act, when the
    page's own arrival has ended; read the count with `transition_frames`."""
    page.wait_for_function("() => document.getAnimations().length === 0")
    page.evaluate(_WATCH_TRANSITIONS)


def watch_transitions_from_load(page) -> None:
    """The same count, from the very start of every page this `page` loads —
    for a swap that comes at load, before anything can be watched. Call it
    before `goto`. A full page load runs no view transition itself, so every
    frame counted is a swap's."""
    page.add_init_script(f"({_WATCH_TRANSITIONS})()")


def transition_frames(page) -> int:
    """The frames with a view transition since `watch_transitions`, read after
    thirty more frames — longer than the 250 ms a transition takes. Assert that
    the result of the act stands FIRST: zero is also true of a swap that never
    came."""
    return page.evaluate(_TRANSITION_FRAMES)


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


def login_met_sessie(page, sessiewaarde: str, url: str = BASE) -> None:
    """Zet de sessiecookie rechtstreeks.

    `url` is the host the cookie belongs to: `PLATFORM` for platform
    administration, which answers only in the platform workspace (#1535).

    Sneller en minder broos dan de OTP-flow doorlopen, en die flow wordt elders al
    getest (test_fase1_ui). Wie de login zélf wil dekken, doet dat in een eigen test.

    Los van `login_als_admin` sinds #718: die naam leest als admin-only terwijl er
    ook als gewoon lid ingelogd moet kunnen worden. De rol zit in de sessiewaarde,
    niet in deze functie.
    """
    page.context.add_cookies(
        [
            {
                "name": "raak_session",
                "value": sessiewaarde,
                "url": url,
                "http_only": True,
                "same_site": "Lax",
            }
        ]
    )


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

    def save_as_it_is(self):
        """Open the edit mode and press the one "Opslaan" without changing anything
        (#1590). The save writes nothing — only what changed is written — but its
        answer comes back and replaces the page like any save's."""
        self.page.goto(self.pad + "?bewerken=1")
        self.page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        with htmx_afgerond(self.page):
            self.page.locator("[data-form-save]").click()
        self.page.locator('[data-form-flow][data-mode="read"]').wait_for(state="visible")


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
            "#betalingen-lijst tbody tr", has=self.page.get_by_role("button", name=knoplabel)
        ).first

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
        links = self.page.locator('#betalingen-lijst a[href*="/admin/inschrijvingen/"]')
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
                "div.bg-gray-50.border", has=self.page.locator('form[id^="insch-form-"]')
            ).first
            if paneel.count() and paneel.get_by_role("button", name="Bewerken").count():
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
        # #1494: one counter per product of the component, `product_<id>`.
        return self.paneel.locator('input[name^="product_"]')

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


#: The persons of the household group on Word lid and Mijn gezin (#1590).
HOUSEHOLD_ROWS = "#gezinsleden > [data-group-rows] > [data-group-row]"


def fill_person(row, first: str, last: str, *, born: str = "1980-01-01", gender: str = "M") -> None:
    """The four things every person of a household needs, in one row of the group."""
    row.locator('input[name$=".first_name"]').fill(first)
    row.locator('input[name$=".last_name"]').fill(last)
    row.locator('input[name$=".date_of_birth"]').fill(born)
    row.locator(f'input[name$=".gender_code"][value="{gender}"]').check()


def fill_signup(
    page, email: str, *, first: str = "Test", last: str = "Gezin", postal_code: bool = True
) -> None:
    """The Word lid page, filled in as far as a main member with an address: the
    caller chooses the payment method and sends. `postal_code=False` leaves the
    select on its empty choice."""
    head = page.locator(HOUSEHOLD_ROWS).first
    fill_person(head, first, last)
    head.locator('input[name$=".mobile"]').fill("0470000000")
    head.locator('input[type="email"]').first.fill(email)
    page.fill("#address-street", "Teststraat")
    page.fill("#address-house_number", "1")
    if postal_code:
        page.select_option("#address-postal_code", index=1)


def send_form(page) -> None:
    """Press the one button of the page's action bar."""
    page.locator("[data-form-save]").click()


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
        return (
            self.page.locator("#leden-detail div")
            .filter(has=self.page.locator("h3", has_text="Lidmaatschappen"))
            .last
        )

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
        return bool(
            self.page.evaluate(
                "!!(document.querySelector('aside') && document.querySelector('aside').__raakMerk)"
            )
        )

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
    velden = page.locator(
        f"{container_selector} input:not([type=checkbox]):not([type=hidden]):not([type=file]), "
        f"{container_selector} select"
    )
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

    The POST of this screen gave eleven 403's on HDEV without anything
    changing on screen. Since #1559 that POST is the fiche's one save.
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
                        .map(a => a.getAttribute('href').split('?')[0])
                        .find(h => /^\/admin\/activiteiten\/\d+$/.test(h)) || null"""
            )
            if not pad:
                return False
            self.page.goto(pad)
        self.page.wait_for_selector("#aa-detail", timeout=5000)
        return True

    def bewerk(self):
        """Open the fiche in edit mode. Since #1559 the page has one form and one
        save; a row has no edit form of its own."""
        self.page.goto(self.page.url.split("?")[0] + "?bewerken=1")
        self.page.wait_for_selector('[data-form-flow][data-mode="edit"]', timeout=5000)
        pagina_klaar(self.page)

    def datumregel(self):
        """The first date row of the Datums group."""
        return self.page.locator("#aa-group-dates > [data-group-rows] > [data-group-row]").first

    def bewaar(self):
        """The fiche's one save."""
        self.page.click("[data-action-bar] [data-form-save]")

    def staatscommando(self):
        """Press the state command of the head's Acties menu (Publiceren / Terug
        naar concept) and confirm its dialog: a plain htmx POST outside any form.

        The item is pressed by its own click event, so a repeated press does not
        depend on whether the menu is still open from the press before."""
        item = self.page.locator('[data-actions-menu] [role=menuitem][hx-post$="/status"]').first
        item.dispatch_event("click")
        ok = self.page.locator("[data-dialog] [data-dialog-ok]")
        ok.wait_for(state="visible")
        ok.click()
        self.page.locator("[data-dialog]").wait_for(state="hidden")

    def breek_het_csrf_token(self) -> None:
        """Vervang het CSRF-token door een ongeldige waarde.

        Dat is exact wat er bij Koen gebeurde, zonder een tweede venster nodig te
        hebben: het token is afgeleid van de sessiecookie, dus na een herinlog
        elders draagt dit tabblad een token dat niet meer bij de cookie past.
        require_csrf antwoordt dan 403.
        """
        self.page.evaluate(
            """document.body.setAttribute('hx-headers',
                   JSON.stringify({'X-CSRF-Token': 'verlopen-token'}))"""
        )

    def datum_leesregel(self):
        """The date in words, as read mode shows it (#648: gone while editing)."""
        return self.page.locator("#aa-group-dates [data-date-line]").first

    def foutmeldingen(self):
        """De meldingen die htmx_ux() in de toast-host zet (#649)."""
        return self.page.locator("#toasts [data-fout]")
