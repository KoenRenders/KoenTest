"""Per-tenant config + secrets in de DB (§7, fase 5b #406).

Config die per tenant verschilt (afzendnaam, canonieke base-URL, taal,
Mollie-key, mail-modus) leeft DB-beheerd in ``kernel_tenant_settings``;
de ``.env``-settings blijven de default zolang een sleutel niet gezet is.
Secrets (Mollie-key) worden **versleuteld** opgeslagen (Fernet, sleutel
afgeleid van ``SECRET_KEY``). Infra-secrets (DB-wachtwoord, SECRET_KEY zelf)
blijven in ``.env`` — die zijn niet tenant-gebonden.

Bekende sleutels:
- ``base_url``       — canonieke publieke origin voor links in mails/redirects
  (de plek van déze site; de *website* van de vereniging is iets anders en staat
  sinds #945 als contactgegeven bij de organisatie)
- ``mollie_api_key`` — (secret) per-tenant Mollie-key; default env-key
- ``mail_mode``      — "send" (default) of "log_only" (demo-tenant: mails
                       worden enkel gelogd, nooit echt verstuurd)
- ``noindex``        — "1" = robots-noindex voor deze tenant (demo)
"""
from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from sqlalchemy import (Column, DateTime, Integer, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import Base
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id, parse_hostname_map


class TenantSetting(Base):
    """Eén config-sleutel voor één tenant. Secrets staan in ``value_encrypted``
    (Fernet); gewone config in ``value``. Bewust géén TenantMixin: deze tabel
    is platform-plumbing en wordt altijd expliciet op tenant_id bevraagd."""

    __tablename__ = "kernel_tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_setting"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=True)
    value_encrypted = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)


def _fernet() -> Fernet:
    from app.config import settings

    # Deterministische afleiding uit SECRET_KEY: geen extra key-management,
    # zelfde sleutel op alle replica's van dezelfde omgeving.
    digest = hashlib.sha256(f"tenant-config:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _actieve_tenant(tenant_id: int | None) -> int:
    return tenant_id or current_tenant_id.get() or DEFAULT_TENANT_ID


def get_setting(db: Session, key: str, default: str | None = None,
                tenant_id: int | None = None) -> str | None:
    row = (db.query(TenantSetting)
           .filter(TenantSetting.tenant_id == _actieve_tenant(tenant_id),
                   TenantSetting.key == key).first())
    if row is None:
        return default
    if row.value_encrypted is not None:
        return _fernet().decrypt(row.value_encrypted.encode()).decode()
    return row.value if row.value is not None else default


def set_setting(db: Session, key: str, value: str | None, *, secret: bool = False,
                tenant_id: int | None = None) -> None:
    tenant = _actieve_tenant(tenant_id)
    row = (db.query(TenantSetting)
           .filter(TenantSetting.tenant_id == tenant, TenantSetting.key == key).first())
    if row is None:
        row = TenantSetting(tenant_id=tenant, key=key)
        db.add(row)
    if value is None:
        row.value = None
        row.value_encrypted = None
    elif secret:
        row.value = None
        row.value_encrypted = _fernet().encrypt(value.encode()).decode()
    else:
        row.value = value
        row.value_encrypted = None


# ── Afgeleide helpers (met .env als default) ───────────────────────────────────

def _origin_serves_this_environment(url: str) -> bool:
    """Wijst deze ``base_url`` naar een host die déze omgeving werkelijk bedient?

    OMGEVINGSVEILIGHEID (#477), preciezer gemaakt met #860. De oorspronkelijke rem
    liet op niet-prod ``FRONTEND_URL`` altijd winnen, met als motivering: *"op
    HDEV/UAT draait alles op één origin"*. Sinds #821 en #854 klopt dat niet meer —
    UAT heeft een platform-host én afdelingsadressen — en de brede rem maakte de
    platform-stroom daar onttestbaar.

    Het gevaar is nooit een per-tenant adres op zich geweest, maar een adres dat naar
    een ÁNDERE OMGEVING wijst: een prod-URL die na een restore of een seed in de
    UAT-databank staat, en dan in een test-inloglink of een betaalredirect naar
    productie zou wijzen. Die bescherming blijft volledig overeind — zo'n host hoort
    bij geen van de drie bronnen hieronder en wordt nog altijd genegeerd.

    Op prod is de DB-waarde onverkort leidend; daar is dit gedrag ongewijzigd.
    """
    from urllib.parse import urlparse

    from app.config import settings

    if settings.app_env == "prod":
        return True
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host:
        return False
    known = {(urlparse(settings.frontend_url).hostname or "")}
    known |= {h.strip() for h in settings.platform_hosts.split(",") if h.strip()}
    known |= set(parse_hostname_map(settings.tenant_hostnames))
    return host in {h.lower().removeprefix("www.") for h in known if h}


def tenant_base_url(db: Session, tenant_id: int | None = None, *,
                    code: str | None = None) -> str:
    """Canonieke publieke origin van een tenant, voor absolute URL's in mails,
    Mollie-redirects en SEO.

    **De regel, in één zin (#860): een absolute URL volgt de host waarop het verzoek
    binnenkwam, tenzij de tenant een eigen canoniek domein heeft.** Dat is de host uit
    dít verzoek en niet "een" host uit `PLATFORM_HOSTS` — dat is een lijst, en een kaart
    die je wegstuurt van de site die je op dat moment bekijkt is precies de klacht.
    Daarom zijn de landingspagina en de inloglink ook geen twee fixes: het is hetzelfde
    geval, één keer mét een tenant-id en één keer zonder.

    Volgorde:

    1. de opgeslagen ``base_url``, als die naar deze omgeving wijst — zie
       ``_origin_serves_this_environment``. Een afdeling met een eigen domein houdt
       zo haar canonieke adres, want dát is het canonieke adres.
    2. anders **de host waarop dit verzoek binnenkwam**. Dat is de eigenlijke
       correctie: absolute URL's negeerden die host volledig, dus aanmelden op een
       platform-host leverde een inloglink naar een afdelingssite op — je
       sessiecookie belandde op de verkeerde host en op het platform bleef je
       anoniem. De platform-tenant heeft daardoor ook geen eigen ``base_url`` nodig;
       ze volgt de host waarop je haar bezoekt, en dat kan niet uit elkaar lopen.
    3. buiten een verzoek: ``FRONTEND_URL``, de enige waarheid die er dan is.

    **Een afdeling zonder eigen domein vult niets in.** Haar adres is afleidbaar uit
    de platform-host plus haar code, en dat met de hand bewaren zou hetzelfde gegeven
    op twee plaatsen zetten — dan is het geen kwestie óf ze uit elkaar lopen maar
    wanneer. Op een platform-host krijgt zo'n afdeling dus ``<origin>/<code>``.
    ``code`` mag expliciet meegegeven worden (de landingspagina doet dat voor élke
    afdeling); zonder wordt de code van de actieve tenant gebruikt.
    """
    from app.config import settings
    from app.kernel.tenancy import (current_origin, current_platform_host,
                                    current_tenant_code, current_tenant_id)

    stored = (get_setting(db, "base_url", tenant_id=tenant_id) or "").strip()
    if stored and _origin_serves_this_environment(stored):
        return stored.rstrip("/")

    origin = (current_origin.get() or settings.frontend_url).rstrip("/")
    if current_platform_host.get():
        prefix = code
        if prefix is None and tenant_id in (None, current_tenant_id.get()):
            prefix = current_tenant_code.get()
        if prefix:
            return f"{origin}/{prefix}"
    return origin


def _omgevingspoort(schema: str) -> str:
    """De poort van déze omgeving, als ze er een nodig heeft (#863).

    ``TENANT_HOSTNAMES`` bevat hostnamen **zonder** poort, en dat hoort ook zo: de
    tenant-resolutie vergelijkt met ``host.split(":")[0]``. Maar een adres dat daaruit
    gebouwd wordt, verloor daarmee de poort. Op HDEV — dat op 8081 draait — leverde dat
    een dode kaart op: poort 80 stuurt met een 308 naar https, en dat antwoordt niet.

    Eerst uit de oorsprong van het lopende verzoek, anders uit ``FRONTEND_URL``. Die
    tweede helft is geen detail: een sitemap of een mail kan uit een achtergrondtaak
    komen, en dan is er geen verzoek — zonder terugval bouw je daar opnieuw een adres
    zonder poort.

    Een standaardpoort blijft weg. Een canoniek adres met een expliciete ``:443`` is een
    tweede schrijfwijze van dezelfde URL, en dat is voor SEO precies wat je niet wil —
    UAT en PROD veranderen hier dus niet.
    """
    from urllib.parse import urlparse

    from app.config import settings
    from app.kernel.tenancy import current_origin

    poort = None
    for bron in (current_origin.get(), settings.frontend_url):
        if not bron:
            continue
        try:
            poort = urlparse(bron).port
        except ValueError:  # een onparseerbare poort is geen poort
            poort = None
        if poort:
            break
    if not poort or (schema, poort) in (("http", 80), ("https", 443)):
        return ""
    return f":{poort}"


def _origin_voor(host: str) -> str:
    """``<schema>://<host>[:poort]`` voor een hostnaam uit de routering (#863).

    Het schema komt uit ``FRONTEND_URL`` (de omgeving weet of ze https draait), de host
    uit ``TENANT_HOSTNAMES``, en de poort uit deze omgeving — zie ``_omgevingspoort``.
    Elk levert wat het werkelijk weet.
    """
    from app.config import settings

    schema = (settings.frontend_url.split("://", 1)[0]
              if "://" in settings.frontend_url else "https")
    return f"{schema}://{host}{_omgevingspoort(schema)}"


def tenant_home_url(db: Session, tenant_id: int | None = None, *,
                    code: str | None = None) -> str:
    """Waar WOONT deze tenant — haar eigen canonieke adres (#860).

    Dit is een andere vraag dan die van ``tenant_base_url``, en ze hebben een ander
    antwoord zodra een afdeling een eigen host heeft:

    ===============================  =====================================
    De vraag                         Antwoord
    ===============================  =====================================
    *Waar woont die afdeling?*       haar eigen canonieke adres — hier
    *Waar breng je mij terug?*       de host waarop je binnenkwam — ginder
    ===============================  =====================================

    Voor een afdeling zonder eigen host vallen die samen op ``<host>/<code>``, en
    daarom lijkt het één regel. Ze lopen uiteen wanneer het telt: sta je op de
    platform-host, dan hoort de kaart van Raak Millegem naar het eigen domein van
    Millegem te wijzen en niet naar ``<platform-host>/raakmillegem`` — anders
    verzwak je haar canonieke adres.

    **De bron is de routering, niet een ingetypt veld.** ``TENANT_HOSTNAMES`` koppelt
    per omgeving een host aan een afdeling; dat is exact hetzelfde feit als "deze
    afdeling woont daar", het staat er al, en het kan niet uit elkaar lopen met de
    routering want het *is* de routering. Gemeten op 10 september 2026: Raak Millegem
    heeft op UAT én PROD geen ``base_url`` in haar instellingen — wél die koppeling.

    Een opgeslagen ``base_url`` blijft bestaan voor een domein dat níét via deze
    omgeving gerouteerd wordt, maar is niet meer de normale weg.
    """
    from app.config import settings
    from app.kernel.tenancy import current_origin, current_tenant_code, current_tenant_id

    if code is None and tenant_id in (None, current_tenant_id.get()):
        code = current_tenant_code.get()

    if code:
        hosts = parse_hostname_map(settings.tenant_hostnames)
        eigen = next((h for h, c in hosts.items() if c == code.lower()), None)
        if eigen:
            return _origin_voor(eigen)

    stored = (get_setting(db, "base_url", tenant_id=tenant_id) or "").strip()
    if stored and _origin_serves_this_environment(stored):
        return stored.rstrip("/")

    origin = (current_origin.get() or settings.frontend_url).rstrip("/")
    return f"{origin}/{code}" if code else origin


def _organisatie(db: Session, tenant_id: int | None = None):
    """De organisatie achter deze tenant (#924).

    Een tenant *is* een organisatie — `org_type` is de rol die ze speelt, de
    kolommen ernaast zeggen wat ze is. Vandaar dat dit gewoon de rij is en geen
    tweede entiteit.

    Gelezen met SQL en niet via het mdm-model, want de kernel mag geen domein
    importeren (`test_import_boundaries`). Dat is geen omweg om een poort heen:
    de kernel wéét al dat een tenant een `mdm.organizations`-rij is — `tenancy.py`
    schrijft het in zijn eerste regel — maar hij hoort dat domein niet aan te
    trekken om het te lezen. De kolomlijst staat er daarom uitgeschreven, zodat
    een wijziging aan het model hier zichtbaar breekt in plaats van stil iets
    anders te leveren.
    """
    return db.execute(text(
        "SELECT name FROM mdm.organizations "
        "WHERE id = :id AND deleted_at IS NULL"),
        {"id": _actieve_tenant(tenant_id)}).first()


def _eerste_rekening(db: Session, tenant_id: int | None = None):
    """De eerste rekening van deze organisatie (#945), of None.

    `sort_order` bepaalt welke "de eerste" is zodra er meer dan één bestaat — dat
    is het hele punt van de eigen tabel. Ook hier met SQL en een uitgeschreven
    kolomlijst, om dezelfde reden als `_organisatie` hierboven.
    """
    return db.execute(text(
        "SELECT iban, bic, beneficiary FROM mdm.bank_accounts "
        "WHERE organization_id = :id AND deleted_at IS NULL "
        "ORDER BY sort_order, id LIMIT 1"),
        {"id": _actieve_tenant(tenant_id)}).first()


def tenant_display_name(db: Session, tenant_id: int | None = None) -> str:
    """De naam van de tenant: die van de organisatie (#945).

    Tot #945 stond hier een `display_name`-instelling **met** de organisatienaam
    als terugval. De overrule bestond dus al terwijl niemand erom gevraagd had, en
    het was opnieuw twee plaatsen voor één feit met de bekende afloop: ze lopen
    uit elkaar en de instelling wint. Koen op 14 september: *"laten we gaan voor de
    naam die we in organisatie hebben — als we een merknaam willen introduceren die
    overruled zullen we dat dan wel doen."*

    Komt die merknaam er, dan is het een kolom op de organisatie
    (`cbc:RegistrationName` naast de roepnaam) en geen tenant-instelling: een naam
    is een kenmerk van de vereniging, ook zonder site.

    De letterlijke terugval "Raak Millegem" blijft staan voor het geval er géén
    organisatie is — dat is geen tenant en dan is elke naam fout, maar een lege
    paginatitel is erger.
    """
    organisatie = _organisatie(db, tenant_id)
    return organisatie.name if organisatie else "Raak Millegem"


def tenant_meeting_signature(db: Session, tenant_id: int | None = None) -> str:
    """De ondertekening onder de agenda- en verslagmail (CR-09 §3.26).

    Leeg is de juiste standaard. Bij Raak Millegem eindigt elke vergadermail met
    *"Met vriendelijke groet,"* en daaronder de voornamen van het dagelijks
    bestuur — maar dat zijn bij een andere Raak-afdeling andere mensen (Koen,
    16 september 2026). Een ingebakken tekst zou bij iedereen behalve Millegem
    fout zijn, en fout op een plek die naar buiten gaat.

    Géén afleiding uit de vergaderkring: die telt ook de afdelingsondersteuner en
    de vaste deelnemers, en dat zijn niet de mensen die tekenen. Wie ondertekent
    is een keuze, geen gevolg.
    """
    return (get_setting(db, "meeting_mail_signature", tenant_id=tenant_id) or "").strip()


def tenant_mollie_key(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings

    return get_setting(db, "mollie_api_key", tenant_id=tenant_id) or settings.mollie_api_key


def tenant_mail_mode(db: Session, tenant_id: int | None = None) -> str:
    return get_setting(db, "mail_mode", tenant_id=tenant_id) or "send"


def tenant_admin_chat_enabled(db: Session, tenant_id: int | None = None) -> bool:
    """Mag het bestuur van deze tenant Raakje vragen stellen? (#917, CR-07 §6.3)

    Twee schakelaars in serie, en dat is de bedoeling: de omgeving zet
    ``ADMIN_CHAT_ENABLED`` (standaard uit, zodat de code naar PROD mag zonder dat
    er iets draait), en de tenant zet er de zijne naast. Zo kan Raak Millegem aan
    staan terwijl het platform en elke andere afdeling uit blijven, zonder dat
    iemand de omgeving hoeft te splitsen.

    Uit wint altijd. Een kill-switch die je op twee plaatsen moet uitzetten is er
    geen.
    """
    from app.config import settings

    if not settings.admin_chat_enabled:
        return False
    return (get_setting(db, "admin_chat_enabled", tenant_id=tenant_id) or "") == "1"


def tenant_language(db: Session, tenant_id: int | None = None) -> str:
    """Taal van de tenant (#407-T) — default nl_BE; voorbereiding meertaligheid."""
    return get_setting(db, "language", tenant_id=tenant_id) or "nl_BE"


def _int_setting(db: Session, key: str, fallback: int,
                 tenant_id: int | None = None) -> int:
    value = get_setting(db, key, tenant_id=tenant_id)
    if not value:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


# ── Per-tenant e-mail-, betaal-, limiet- en analytics-config (#451). DB-sleutel
#    wint, de .env-setting blijft de fallback (net als tenant_mollie_key). ──────

def tenant_gmail_user(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return get_setting(db, "gmail_user", tenant_id=tenant_id) or settings.gmail_user


def tenant_gmail_app_password(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return (get_setting(db, "gmail_app_password", tenant_id=tenant_id)
            or settings.gmail_app_password)


def tenant_gmail_from(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return get_setting(db, "gmail_from", tenant_id=tenant_id) or settings.gmail_from


def tenant_payment_iban(db: Session, tenant_id: int | None = None) -> str | None:
    """Het rekeningnummer van de organisatie, met `.env` als vangnet (#924).

    De tenant-instelling zit hier **niet** meer tussen, en dat is de hele
    omschakeling: migratie 119 heeft de waarden naar de organisatie gebracht én de
    rijen verwijderd. Ze als derde niveau laten staan zou betekenen dat het veld op
    twee plaatsen bewerkbaar blijft — dan is het verplaatst in plaats van
    weggenomen, en dat is precies het patroon dat dit issue opruimt.

    Hier omgeschakeld en niet bij de drie aanroepers: de leesvolgorde hoort op één
    plek te staan, en de schermen hoeven niet te weten dat er een organisatie
    bestaat.
    """
    from app.config import settings

    rekening = _eerste_rekening(db, tenant_id)
    return (rekening.iban if rekening and rekening.iban
            else settings.payment_iban)


def tenant_payment_beneficiary(db: Session, tenant_id: int | None = None) -> str | None:
    """De begunstigde van de organisatie, met `.env` als vangnet (#924)."""
    from app.config import settings

    rekening = _eerste_rekening(db, tenant_id)
    return (rekening.beneficiary
            if rekening and rekening.beneficiary
            else settings.payment_beneficiary)


def tenant_payment_term_days(db: Session, tenant_id: int | None = None) -> int:
    from app.config import settings
    return _int_setting(db, "payment_term_days", settings.payment_term_days, tenant_id)


def tenant_max_item_quantity(db: Session, tenant_id: int | None = None) -> int:
    from app.config import settings
    return _int_setting(db, "max_item_quantity", settings.max_item_quantity, tenant_id)


def tenant_max_registrations_per_email(db: Session, tenant_id: int | None = None) -> int:
    from app.config import settings
    return _int_setting(db, "max_registrations_per_email",
                        settings.max_registrations_per_email, tenant_id)


def tenant_umami_src(db: Session, tenant_id: int | None = None) -> str:
    from app.config import settings
    return get_setting(db, "umami_src", tenant_id=tenant_id) or settings.umami_src


def tenant_umami_website_id(db: Session, tenant_id: int | None = None) -> str:
    from app.config import settings
    return (get_setting(db, "umami_website_id", tenant_id=tenant_id)
            or settings.umami_website_id)


def umami_tracking(db: Session, tenant_id: int | None = None) -> tuple[str, str]:
    """(script-URL, website-id) — of twee lege strings (#808).

    **Beide of geen van beide.** Een half ingevulde instelling zou een scripttag met
    een lege `src` of een leeg `data-website-id` opleveren: een verzoek dat nergens
    heen gaat, of een script dat naar niets rapporteert. Geen van beide meet iets, en
    allebei zien ze er in de broncode uit alsof er wél iets gebeurt.

    Eén functie, want de publieke schil en het Systeeminfo-scherm moeten hetzelfde
    zeggen. Vóór #808 rekende Systeeminfo zelf `bool(src and id)` uit en toonde
    "geconfigureerd" — terwijl er sinds de React-exit nergens een script gerenderd
    werd. Die vlag toetste of er tekst stond, niet of er iets gebeurde. Nu is ze
    hetzelfde antwoord als dat van de schil, dus ze kunnen niet meer uit elkaar
    lopen.
    """
    src = tenant_umami_src(db, tenant_id)
    website_id = tenant_umami_website_id(db, tenant_id)
    if not (src and website_id):
        return "", ""
    return src, website_id


def tenant_membership_config(db: Session | None = None,
                             tenant_id: int | None = None) -> dict:
    """Lidmaatschapsprijzen en -datumgrenzen van de actieve tenant (branding-
    slice #407): DB-sleutels winnen, de .env-settings blijven de default.
    Zonder meegegeven sessie wordt een eigen SessionLocal geopend, zodat ook
    servicefuncties zonder db-parameter tenant-bewust zijn."""
    from decimal import Decimal, InvalidOperation

    from app.config import settings

    eigen_sessie = db is None
    if eigen_sessie:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        def _s(key: str, default):
            waarde = get_setting(db, key, tenant_id=tenant_id)
            return waarde if waarde is not None else default

        def _bedrag(key: str, default) -> Decimal:
            """Een onleesbaar bedrag mag de site niet platleggen (#797).

            `tenant_membership_config` hangt onder `site_context` en draait dus op
            ÉLKE publieke pagina. Toen hier `17,5` stond — de Belgische notatie, en
            precies wat de applicatie zelf toont — gooide `Decimal` een
            `InvalidOperation` en gaf de homepage een 500. Sinds #797 aanvaardt het
            formulier de komma en normaliseert het naar een punt, dus dit pad hoort
            niet meer geraakt te worden; het is er voor waarden die er langs een
            andere weg in komen (een import, een handmatige insert, een oudere rij).

            De terugval is de `.env`-default, mét een waarschuwing die de SLEUTEL
            noemt. Zonder die naam blijft een beheerder zoeken in een scherm met
            twintig velden — dat was bij de storing precies het dure deel.
            """
            ruw = _s(key, default)
            try:
                return Decimal(str(ruw))
            except InvalidOperation:
                logger.warning(
                    "Tenant-instelling %r is geen bedrag (%r); terug op de "
                    "omgevingswaarde %r.", key, ruw, default)
                return Decimal(str(default))

        return {
            "price_full": _bedrag("membership_price_full", settings.membership_price_full),
            "price_half": _bedrag("membership_price_half", settings.membership_price_half),
            "half_start_md": _s("membership_half_price_start_md", settings.membership_half_price_start_md),
            "half_end_md": _s("membership_half_price_end_md", settings.membership_half_price_end_md),
            "next_year_from_md": _s("membership_next_year_from_md", settings.membership_next_year_from_md),
            "renewal_start_md": _s("membership_renewal_start_md", settings.membership_renewal_start_md),
        }
    finally:
        if eigen_sessie and db is not None:
            db.close()
