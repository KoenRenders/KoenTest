"""#821 — je wisselde ongemerkt van afdeling.

`resolve_request` raadpleegt de tenant-cookie **alleen op een platform-host**. Op
PROD stond `PLATFORM_HOSTS` leeg — de variabele stond in `.env.prod` maar niet in het
`environment:`-blok van de compose — dus die cookie werd gezet en nooit gelezen.

De navigatie van een tenant-site bestaat uit absolute paden zónder prefix. Gemeten op
de Voorbeeldafdeling: `/aanmelden`, `/archief`, `/lid-worden`, en **nul** links met
prefix. Je kwam dus via de prefix binnen bij de ene afdeling en stond na één klik bij
de andere — zonder foutmelding, met een inschrijfformulier voor de verkeerde
afdeling.

**Deze tests toetsen het gedrag en niet of de variabele ergens in een bestand staat.**
Dat laatste was hier juist de valse geruststelling: de naam stond netjes in `.env`.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `platform_hosts`
leeggemaakt (precies de gemeten toestand op PROD) → de eerste twee vallen om, de
derde blijft groen omdat pad-prefixen niet van deze variabele afhangen.

**Die tegenproef heeft meteen een fout in deze test zelf gevonden.** De eerste versie
gaf de tweede tenant id 2 — en `DEFAULT_TENANT_ID` ís 2, dus "je blijft op dezelfde
afdeling" was waar wat er ook gebeurde. Met een leeg `platform_hosts` bleef hij
groen. Vandaar `ANDERE_TENANT = 7` hieronder: een id dat niets anders kan zijn.
"""
import pytest

from app.kernel.tenancy import DEFAULT_TENANT_ID, resolve_request

pytestmark = pytest.mark.ui_agnostisch

# LET OP het getal: `DEFAULT_TENANT_ID` is 2, dus een tweede tenant met id 2 maakt
# elke assertie hieronder waar zonder iets te bewijzen. Dat is precies wat er in de
# eerste versie van deze test gebeurde — de tegenproef liet hem groen, en pas toen
# viel het op. Vandaar 7: een id dat niets anders kan zijn dan "de andere afdeling".
ANDERE_TENANT = 7
CODES = {"raakmillegem": DEFAULT_TENANT_ID, "raakvoorbeeld": ANDERE_TENANT}
PLATFORM = {"platform.voorbeeld.test"}


def _los(host, pad, cookie=None, platform=PLATFORM):
    return resolve_request(host, pad, cookie, {}, platform, CODES)


def test_je_blijft_op_dezelfde_afdeling_na_een_pad_zonder_prefix():
    """Het ergste gevolg, en de test die vandaag rood stond.

    Binnenkomen via de prefix zet de tenant-cookie; het volgende verzoek is een
    absoluut pad zonder prefix. Dat hoort op dezelfde afdeling uit te komen.
    """
    tenant, pad, landing = _los("platform.voorbeeld.test", "/raakvoorbeeld/activiteiten")
    assert tenant == ANDERE_TENANT and pad == "/activiteiten" and not landing

    # Zoals de navigatie het doet: absoluut, zonder prefix, mét de cookie.
    tenant_na, _pad, _l = _los("platform.voorbeeld.test", "/activiteiten",
                               cookie="raakvoorbeeld")

    assert tenant_na == ANDERE_TENANT, (
        "na één klik sta je bij een andere afdeling — met een inschrijfformulier voor "
        "de verkeerde vereniging")


def test_de_wortel_van_een_platform_host_is_de_landing():
    tenant, pad, landing = _los("platform.voorbeeld.test", "/")

    assert landing is True and pad is None and tenant == DEFAULT_TENANT_ID


def test_een_pad_prefix_werkt_zonder_platform_hosts():
    """Wat NIET stuk was, en dat hoort vastgelegd te worden.

    De prefix wordt gematcht vóór er naar host of cookie gekeken wordt, dus dat pad
    is onafhankelijk van `PLATFORM_HOSTS`. Zonder deze test zou een latere
    'vereenvoudiging' die volgorde kunnen omdraaien zonder dat iets faalt.
    """
    tenant, pad, landing = _los("wat.dan.ook.test", "/raakvoorbeeld/activiteiten",
                                platform=set())

    assert tenant == ANDERE_TENANT and pad == "/activiteiten" and not landing


def test_een_cookie_geldt_niet_op_een_gewone_host():
    """De tegenproef bij de eerste test: de cookie mag niet overal gelden.

    Op het domein van een afdeling zou een blijven hangen cookie anders een ándere
    afdeling tonen — hetzelfde soort verwarring, maar dan op de plek waar de bezoeker
    juist zeker moet weten waar hij is.
    """
    tenant, _pad, _landing = _los("www.voorbeeld.test", "/activiteiten",
                                  cookie="raakvoorbeeld")

    assert tenant == DEFAULT_TENANT_ID


def test_de_landing_draagt_geen_merknaam_en_wijst_niet_naar_een_afdeling(client):
    """#821 — het platform is niet van één afdeling.

    Ook de ingang voor de platformbeheerder staat erop: het beheerscherm bestond al,
    er was alleen geen weg ernaartoe.
    """
    from pathlib import Path

    sjabloon = (Path(__file__).resolve().parents[1]
                / "app/ui/templates/platform_landing.html").read_text()
    zichtbaar = "\\n".join(r for r in sjabloon.splitlines()
                          if not r.lstrip().startswith("{#") and "#821" not in r)

    assert '_("Digital Platform")' in zichtbaar
    assert '_("Raak Digital Platform")' not in zichtbaar
    assert "Millegem" not in zichtbaar, (
        "de landing verwijst voor beheer naar een van zijn eigen afdelingen")
    assert "/aanmelden" in zichtbaar, "er is geen ingang voor de platformbeheerder"
