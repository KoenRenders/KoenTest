"""De deellink van een formulier volgt de slug (#928, conventie van #870/#922).

Heeft een formulier een leesbare naam, dan is dát de link die je ziet en kopieert;
heeft het er geen, dan blijft de sleutel-URL staan. Eén regel, één functie, en de
schermen kiezen niets zelf.

**De harde eis eronder is de tokenlink** (#690). Een slug verandert wat je TOONT,
nooit wat nog WERKT: wie vorige maand `/formulier/a1b2c3` rondstuurde, mag niet
stukgaan omdat er later een naam bij komt. Elke test hier die over de slug gaat,
toetst daarom in dezelfde adem dat de sleutel-URL nog antwoordt.

En de prefix. Een deellink wordt per definitie ergens ánders geopend dan waar hij
gemaakt is — in een andere browser, zonder de cookie die de afdeling onthield.
Daarom loopt hij door `path_for`, en daarom zetten de tests hieronder de
platform-context ECHT. Zonder die opzet slaagt zo'n test leeg: `path_for` doet dan
niets en de assertie bevestigt alleen zichzelf. Dat is precies hoe het bij de
foto's (#889) misging.
"""
import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.api import deellink_pad
from app.domains.forms.models import Form
from tests.conftest import SEEDED_ADMIN_EMAIL

TOKEN = "a1b2c3d4"


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _form(db, *, titel="Zomerfeest", slug=None, token=TOKEN, status="open") -> Form:
    form = Form(title=titel, status=status, share_token=token, slug=slug)
    db.add(form)
    db.commit()
    return form


PLATFORM_HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    """Een echte platform-host, zodat de MIDDLEWARE de tenant-context zet.

    De eerste versie van deze fixture zette `current_platform_host` en
    `current_tenant_code` rechtstreeks. Dat leek te werken — `path_for` gaf netjes
    een prefix in de test — maar binnen een `client.get` zet de middleware diezelfde
    ContextVars opnieuw, uit de binnenkomende host. De gerenderde pagina wist dus
    nergens van, en de assertie viel om.

    Dat is een scherpere vorm van "zonder opzet slaagt zo'n test leeg": hier sláágde
    de opzet, maar niet op de plaats waar de code draait. Vandaar de host-header op
    elk verzoek hieronder.
    """
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


# ── De regel zelf ────────────────────────────────────────────────────────────

def test_a_form_with_a_slug_shares_the_readable_link(db_session):
    assert deellink_pad(_form(db_session, slug="zomerfeest")) == "/f/zomerfeest"


def test_a_form_without_a_slug_keeps_the_key_url(db_session):
    assert deellink_pad(_form(db_session)) == f"/formulier/{TOKEN}"


def test_the_rule_lives_in_one_place(db_session):
    """De schermen kiezen niet zelf welke van de twee URL's ze tonen.

    Twee plaatsen die dezelfde link samenstellen is het patroon dat deze maand vijf
    keer langskwam; hier is het één functie en twee sjablonen die hem renderen.

    Kapotgemaakt om het rood te zien: `/formulier/{{ f.share_token }}` teruggezet in
    `_fb_kaarten.html` — de kaart toont dan de sleutel-URL terwijl de slug er is.
    """
    from pathlib import Path

    sjablonen = Path(__file__).resolve().parents[1] / "app" / "domains" / "forms" \
        / "templates"
    bekeken = 0
    for pad in sjablonen.glob("*.html"):
        tekst = pad.read_text(encoding="utf-8")
        if pad.name == "formulier.html":
            continue  # het formulier post naar zijn eigen sleutelroute; zie hieronder
        bekeken += 1
        assert "share_token" not in tekst or "blijft werken" in tekst, (
            f"{pad.name} stelt zelf een deellink samen — dat hoort via deellink_pad")
    assert bekeken >= 3, (
        f"deze poort keek naar {bekeken} sjablonen, te weinig om iets te bewijzen (#678)")


# ── Op het scherm ────────────────────────────────────────────────────────────

def test_the_card_shows_the_readable_link_once_there_is_a_slug(client, db_session):
    _login(client)
    _form(db_session, slug="zomerfeest")

    tekst = client.get("/admin/formulieren").text

    assert "/f/zomerfeest" in tekst
    assert f"/formulier/{TOKEN}" not in tekst, (
        "met een slug is de leesbare link de getoonde link")


def test_the_card_falls_back_to_the_key_url(client, db_session):
    _login(client)
    _form(db_session, titel="Naamloos", token="zonderslug1")

    tekst = client.get("/admin/formulieren").text

    assert "/formulier/zonderslug1" in tekst


def test_the_builder_says_the_key_url_keeps_working(client, db_session):
    """#690 staat op het scherm waar iemand eraan twijfelt.

    Dit is de plek waar een beheerder net een naam invult voor een formulier dat
    hij vorige week al rondstuurde. Dat de oude link blijft werken is daar geen
    voetnoot maar het antwoord op de vraag die hij op dat moment heeft.
    """
    _login(client)
    form = _form(db_session, slug="zomerfeest")

    tekst = client.get(f"/admin/formulieren/{form.id}").text

    assert "/f/zomerfeest" in tekst
    assert "blijft werken" in tekst
    assert f"/formulier/{TOKEN}" in tekst


def test_the_builder_shows_only_the_key_url_without_a_slug(client, db_session):
    _login(client)
    form = _form(db_session, token="zonderslug2")

    tekst = client.get(f"/admin/formulieren/{form.id}").text

    assert "/formulier/zonderslug2" in tekst
    assert "blijft werken" not in tekst, (
        "zonder slug is er niets om naast te zetten")


# ── De belofte: de sleutel-URL blijft bereikbaar ─────────────────────────────

def test_the_key_url_still_answers_when_a_slug_exists(client, db_session):
    """De kern van #690, en de reden dat dit issue bestaat.

    Kapotgemaakt om het rood te zien: de tokenroute in `ui.py` achter een
    `if not form.slug` gezet — dan geeft dit 404 en breekt elke link die ooit
    verstuurd is.
    """
    _form(db_session, slug="zomerfeest")

    via_slug = client.get("/f/zomerfeest")
    via_sleutel = client.get(f"/formulier/{TOKEN}")

    assert via_slug.status_code == 200
    assert via_sleutel.status_code == 200
    assert "Zomerfeest" in via_sleutel.text


# ── De prefix ────────────────────────────────────────────────────────────────

def test_the_shared_link_carries_the_afdeling_prefix(client, db_session,
                                                    platform_host):
    """Een deellink zonder prefix komt bij de verkeerde afdeling uit (#889).

    Hij wordt geopend zonder de cookie die onthield waar je zat — een andere
    browser, een mail, weken later. Dan is het pad het enige signaal dat er nog is.

    Het verzoek komt binnen op de platform-host mét prefix, want alleen dan zet de
    middleware de tenant-context die `path_for` leest. Zie de fixture voor waarom
    dat niet naast het verzoek te regelen valt.

    Kapotgemaakt om het rood te zien: `path_for(...)` uit `_fb_kaarten.html`
    gehaald — de assertie valt dan om op het kale `/f/zomerfeest`.
    """
    _login(client)
    _form(db_session, slug="zomerfeest")

    tekst = client.get("/raakmillegem/admin/formulieren",
                       headers={"host": PLATFORM_HOST}).text

    assert "/raakmillegem/f/zomerfeest" in tekst


def test_the_edit_link_in_the_mail_points_at_where_the_afdeling_lives(db_session,
                                                                     monkeypatch):
    """De link die het gebouw verlaat (#928) — en wat hier NIET aan de hand was.

    Eerste aanname: `tenant_base_url` zou op een platform-host de pad-prefix
    verliezen, zodat een ontvanger bij de verkeerde afdeling uitkwam. Die aanname
    was fout, en deze test wees hem af voor de commit: allebei de functies zetten
    die prefix. De mail was dus niet stuk.

    Ze lopen wél uiteen zodra de afdeling een EIGEN domein heeft. Dan geeft
    `tenant_base_url` de host waar de beheerder toevallig werkte en
    `tenant_home_url` het adres waar de afdeling woont. Voor een mail is dat tweede
    het juiste: er is geen "terug" — hij wordt weken later geopend, in een andere
    browser, door iemand die nooit op die platform-host geweest is.

    Dat is dus een betekeniscorrectie en geen bugfix, en deze test zegt dat door
    beide takken te tonen in plaats van alleen de gewenste.
    """
    from app.config import settings
    from app.kernel.tenancy import (
        current_origin, current_platform_host, current_tenant_code,
    )
    from app.kernel.tenant_config import tenant_base_url, tenant_home_url

    origin = current_origin.set("https://platform.example")
    host = current_platform_host.set(True)
    code = current_tenant_code.set("raakmillegem")
    try:
        # Zonder eigen domein: gelijk, en allebei mét prefix. De mail was niet stuk.
        monkeypatch.setattr(settings, "tenant_hostnames", "")
        assert tenant_base_url(db_session) == "https://platform.example/raakmillegem"
        assert tenant_home_url(db_session) == "https://platform.example/raakmillegem"

        # Mét eigen domein lopen ze uiteen, en dan telt welke je kiest.
        monkeypatch.setattr(settings, "tenant_hostnames",
                            "raakmillegem.example=raakmillegem")
        assert tenant_base_url(db_session) == "https://platform.example/raakmillegem"
        # `in` en niet `endswith`: het adres draagt de omgevingspoort mee (#863),
        # dus op dev staat er `:3000` achter.
        assert "raakmillegem.example" in tenant_home_url(db_session), (
            "de mail hoort naar het adres van de afdeling te wijzen")
    finally:
        current_tenant_code.reset(code)
        current_platform_host.reset(host)
        current_origin.reset(origin)


def test_the_mail_uses_the_home_url(db_session):
    """En de route gebruikt effectief die functie — anders bewijst het bovenstaande
    alleen iets over twee helpers die niemand aanroept."""
    from pathlib import Path

    ruw = (Path(__file__).resolve().parents[1] / "app" / "domains" / "forms"
           / "router.py").read_text(encoding="utf-8")
    # Commentaar eerst weg. De uitleg bóven deze regel noemt `tenant_base_url` met
    # opzet — ze legt uit waarom het die niet is — en een scan die dat als code
    # leest, is dezelfde valse treffer die de #866-poort ooit rood maakte.
    bron = "\n".join(regel.split("#", 1)[0] for regel in ruw.splitlines())
    assert "tenant_home_url(db)}/formulier/" in bron
    assert "tenant_base_url" not in bron, (
        "de mailroute stelt zijn adres nog met `tenant_base_url` samen")
