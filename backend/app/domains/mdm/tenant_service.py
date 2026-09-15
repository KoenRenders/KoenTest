"""Tenants aanmaken en hun instellingen bewaren (#635 G).

Stond volledig inline in `app/ui/tenants_ui.py`: de slug-regex, de uniciteitscheck
op `Organization.code`, het `org_type="UNIT"`, de basis-settings, het wissen van de
tenant-cache, en de "leeg laten = ongewijzigd"-semantiek voor geheime sleutels.
Dat laatste is de gevoeligste regel van het scherm — een lege invoer mag een
opgeslagen Mollie-key of Gmail-wachtwoord níet wissen — en ze was alleen als
scherm-code testbaar.

Woont in `domains/mdm/` en niet in de kernel, omdat `Organization` hier woont: de
kernel mag per laagmodel (§8) niet uit een domein importeren, en die regel is
terecht — de kernel draagt geen domeinkennis. Een tenant is weliswaar de omgeving
waarin alle domeinen draaien, maar hij is opgeslagen als een organisatie, en dat
is mdm-data.

De schrijffuncties committen zélf. Dat is de regel uit #635-2: de transactiegrens
ligt in de service, niet in het scherm — zo geldt ze voor élke ingang en niet
alleen voor de route die er toevallig aan dacht.
"""
import re
from typing import Iterable, Mapping

_CODE = re.compile(r"[a-z0-9-]+")


class TenantFout(ValueError):
    """Een invoerfout die het scherm als banner toont. Bewust geen HTTPException:
    de service kent geen HTTP, en de UI-route bepaalt zelf welke statuscode of
    welk sjabloon erbij hoort."""


def create_tenant(db, *, name: str, code: str, parent_id: int | None = None,
                  base_url: str = ""):
    """Maak een tenant (een `UNIT`-organisatie) met haar basisinstellingen.

    De code is de sleutel waarmee een binnenkomend verzoek naar zijn tenant
    resolvet, dus hij moet aan de slug-vorm voldoen en uniek zijn. Na het
    aanmaken wordt de codecache gewist, anders resolvet de nieuwe tenant pas na
    een herstart (#546).
    """
    from app.domains.mdm.models import Organization
    from app.domains.mdm.tenant_lookup import invalidate_tenant_codes
    from app.kernel.tenant_config import set_setting

    name = (name or "").strip()
    code = (code or "").strip().lower()
    if not name or not _CODE.fullmatch(code):
        raise TenantFout(
            "Naam én een geldige code (kleine letters, cijfers, streepjes) zijn verplicht.")
    if db.query(Organization).filter(Organization.code == code).first():
        raise TenantFout("Die code bestaat al.")


    org = Organization(org_type="UNIT", code=code, name=name,
                       parent_id=parent_id, is_active=True)
    db.add(org)
    db.flush()

    # Basis-settings; de rest zet de OPERATOR in de editor van deze tenant.
    # Geen `display_name` meer (#945): die schreef de naam een tweede keer weg,
    # naast `organizations.name` waar hij net in gezet is. Twee plaatsen voor één
    # feit, aangelegd op het moment van aanmaken — dat is waar ze uit elkaar
    # beginnen te lopen.
    if (base_url or "").strip():
        set_setting(db, "base_url", base_url.strip(), tenant_id=org.id)
    db.commit()
    # Cache wissen zodat de nieuwe tenant meteen resolvet (#546) — ná de commit,
    # anders vult een gelijktijdig verzoek de cache met de oude toestand.
    invalidate_tenant_codes()
    return org


# #797: welke instellingen een getal moeten zijn. Een tenant-instelling is door
# mensen te bewerken data die op élke publieke pagina gelezen wordt, dus een
# onleesbare waarde is geen lokaal probleem: `17,5` bij `membership_price_half`
# gaf een `decimal.InvalidOperation` in `tenant_membership_config`, en die hangt
# onder `site_context` — dus 500 op de homepage.
BEDRAG_SLEUTELS = ("membership_price_full", "membership_price_half")
GEHEEL_SLEUTELS = ("payment_term_days", "max_item_quantity",
                   "max_registrations_per_email")


class OngeldigeInstelling(TenantFout):
    """Eén of meer velden bevatten geen bruikbaar getal.

    Draagt de meldingen per sleutel mee, zodat het scherm kan zeggen wélk veld het
    is in plaats van "er ging iets mis".
    """

    def __init__(self, fouten: dict[str, str]):
        self.fouten = fouten
        super().__init__("; ".join(f"{k}: {v}" for k, v in fouten.items()))


def _als_bedrag(ruw: str) -> str:
    """`17,50` → `17.50`. De komma wordt AANVAARD, niet geweigerd.

    De hele applicatie toont bedragen als `€ 17,50`; iemand die dat overtypt doet
    wat de interface hem voordoet. Hem corrigeren voor de notatie van zijn eigen
    taal is de verkeerde kant op — dus normaliseren we naar het punt dat `Decimal`
    verwacht, en slaan we die genormaliseerde vorm op.
    """
    from decimal import Decimal, InvalidOperation

    genormaliseerd = ruw.replace(",", ".")
    try:
        waarde = Decimal(genormaliseerd)
    except InvalidOperation:
        raise ValueError("Geef een bedrag, bv. 17,50.")
    if waarde < 0:
        raise ValueError("Een bedrag kan niet negatief zijn.")
    return genormaliseerd


def _als_geheel(ruw: str) -> str:
    if not ruw.lstrip("+").isdigit():
        raise ValueError("Geef een geheel getal, bv. 7.")
    return str(int(ruw))


def update_tenant_settings(db, tenant_id: int, form: Mapping, *,
                           known: Iterable[str], secret: Iterable[str]) -> None:
    """Schrijf de instellingen van één tenant weg.

    Twee soorten sleutels, met verschillende semantiek:

    - **gewone sleutels**: wat in het formulier staat, is de nieuwe waarde; leeg
      betekent leeg.
    - **geheime sleutels**: leeg laten = **ongewijzigd**. Ze worden nooit
      teruggetoond, dus een leeg veld betekent "ik heb niets ingetypt", niet "wis
      dit". Wissen gebeurt expliciet met `<sleutel>_wissen`. Zonder die regel
      wist elke opslag van een ander veld stilzwijgend de Mollie-key.

    Getalvelden worden eerst gecontroleerd (#797). ALLE velden eerst, en pas daarna
    schrijven: anders staat de helft van het formulier in de databank en de andere
    helft niet, en dan is de toestand na een tikfout onduidelijker dan ervoor.
    """
    from app.kernel.tenant_config import set_setting

    def _tekst(key: str) -> str:
        waarde = form.get(key)
        return waarde.strip() if isinstance(waarde, str) else ""

    schoon: dict[str, str | None] = {}
    fouten: dict[str, str] = {}
    for key in known:
        ruw = _tekst(key)
        if not ruw:
            schoon[key] = None  # leeg = terug naar de .env-default
            continue
        try:
            if key in BEDRAG_SLEUTELS:
                schoon[key] = _als_bedrag(ruw)
            elif key in GEHEEL_SLEUTELS:
                schoon[key] = _als_geheel(ruw)
            else:
                schoon[key] = ruw
        except ValueError as fout:
            fouten[key] = str(fout)
    if fouten:
        raise OngeldigeInstelling(fouten)

    for key, waarde in schoon.items():
        set_setting(db, key, waarde, tenant_id=tenant_id)

    for key in secret:
        if form.get(f"{key}_wissen"):
            set_setting(db, key, None, tenant_id=tenant_id)
        elif _tekst(key):
            set_setting(db, key, _tekst(key), secret=True, tenant_id=tenant_id)
    db.commit()


def list_units(db, *, alleen_actief: bool = False):
    """De tenants (UNIT-organisaties), op id."""
    from app.domains.mdm.models import Organization

    query = db.query(Organization).filter(Organization.org_type == "UNIT")
    if alleen_actief:
        query = query.filter(Organization.is_active.is_(True))
    return query.order_by(Organization.id).all()


def platform_org(db):
    """The PLATFORM organization, or None if this database has none (#854).

    Separate from ``list_units`` on purpose: the platform is not a UNIT and must not
    appear where afdelingen are listed — the landing page of the platform lists its
    afdelingen, and the platform itself is not one of them.
    """
    from app.domains.mdm.models import Organization

    return (db.query(Organization)
            .filter(Organization.org_type == "PLATFORM")
            .order_by(Organization.id).first())


def list_manageable_tenants(db, *, alleen_actief: bool = False):
    """What /admin/tenants may configure: the platform first, then the units (#854).

    The platform carries the same settings as any tenant — that is the whole point of
    making it one — so it needs the same editor. It leads the list because it is the
    thing you are standing in when you are on a platform host.
    """
    platform = platform_org(db)
    units = list_units(db, alleen_actief=alleen_actief)
    if platform is None or (alleen_actief and not platform.is_active):
        return units
    return [platform] + units


def list_accounts(db):
    """De accounts waar een tenant onder kan hangen."""
    from app.domains.mdm.models import Organization

    return (db.query(Organization).filter(Organization.org_type == "ACCOUNT")
            .order_by(Organization.id).all())


def secrets_gezet(db, tenant_id: int, keys) -> dict[str, bool]:
    """Per geheime sleutel: staat er een waarde? (niet wélke — die wordt nooit
    teruggetoond)

    Het scherm heeft dit nodig om "ingesteld" of "nog niet ingesteld" te tonen
    naast een veld dat leeg blijft. Eén query voor alle sleutels samen: het waren
    er twee per sleutel.
    """
    from app.kernel.tenant_config import TenantSetting

    gezet = {rij.key for rij in
             db.query(TenantSetting.key)
             .filter(TenantSetting.tenant_id == tenant_id,
                     TenantSetting.key.in_(list(keys)),
                     TenantSetting.value_encrypted.isnot(None)).all()}
    return {key: key in gezet for key in keys}


# #924: wat de organisatie IS, tegenover wat de site instelt. Twee assen, dus twee
# functies — maar allebei in de servicelaag: het scherm raakt de sessie niet zelf
# aan (`test_layer_gate`).
#
# #945: van de elf kolommen blijft er één over. De rest is een rij geworden in een
# van de drie lijsten hieronder, en het scherm bewerkt nog steeds één rij per
# soort — dat is wat het vandaag nodig heeft. Een tweede btw-nummer of een tweede
# rekening bestaat in het model en is nog geen scherm; dat is het verschil tussen
# "de vorm laat het toe" en "we bouwen het vooruit".
ORGANISATIEVELDEN: tuple[str, ...] = ("legal_form",)

# (veldnaam in het formulier, code in `contact_type_codes`)
CONTACTVELDEN: tuple[tuple[str, str], ...] = (
    ("email", "EMAIL"),
    ("phone", "PHONE"),
    ("website", "WEBSITE"),
    ("facebook_url", "FACEBOOK"),
    ("instagram_url", "INSTAGRAM"),
    ("tiktok_url", "TIKTOK"),
)

# (veldnaam in het formulier, schema in `identification_schemes`)
IDENTIFICATIEVELDEN: tuple[tuple[str, str], ...] = (
    ("enterprise_number", "KBO"),
    ("vat_number", "VAT"),
)

# (veldnaam in het formulier, kolom op `bank_accounts`)
REKENINGVELDEN: tuple[tuple[str, str], ...] = (
    ("payment_iban", "iban"),
    ("payment_beneficiary", "beneficiary"),
    ("payment_bic", "bic"),
)

ALLE_ORGANISATIEVELDEN: tuple[str, ...] = (
    ORGANISATIEVELDEN
    + tuple(veld for veld, _ in IDENTIFICATIEVELDEN)
    + tuple(veld for veld, _ in CONTACTVELDEN)
    + tuple(veld for veld, _ in REKENINGVELDEN)
)


def _organisatie(db, tenant_id: int):
    from app.domains.mdm.models import Organization

    return (db.query(Organization).filter(Organization.id == tenant_id)
            .execution_options(include_all_tenants=True).one_or_none())


def _zet_lijstrij(db, model, filters: dict, kolom: str, waarde: str | None,
                  standaard: dict | None = None) -> None:
    """Eén rij per soort: schrijf, maak aan, of verwijder als de waarde leeg is.

    De drie lijsten van #945 worden vandaag met één rij per soort bewerkt. Leeg
    betekent "er is er geen", en dan hoort de rij weg te zijn — een rij met een
    lege waarde is een derde toestand die nergens iets betekent en die een
    volgende lezer als "ingevuld" telt.
    """
    rij = (db.query(model).filter_by(**filters)
           .filter(model.deleted_at.is_(None))
           .execution_options(include_all_tenants=True).first())
    if not waarde:
        if rij is not None:
            db.delete(rij)
        return
    if rij is None:
        rij = model(**filters, **(standaard or {}), **{kolom: waarde})
        db.add(rij)
    else:
        setattr(rij, kolom, waarde)


def update_organization_details(db, tenant_id: int, form: Mapping) -> None:
    """De wereld-kenmerken van de organisatie bewaren (#924, herzien in #945).

    Deze velden verdwenen bij de eerste twee omschakelingen uit de
    tenant-instellingen, en daarmee was er even **geen** scherm meer waar een
    penningmeester het rekeningnummer kon wijzigen. Dat is erger dan de duplicatie
    die eruit ging: dubbel is verwarrend, onbereikbaar is stuk.

    Sinds #945 staan de waarden in drie tabellen in plaats van in elf kolommen.
    Het formulier is hetzelfde gebleven — één invoer per soort — maar het schrijft
    nu rijen. Een lege waarde wist de rij; zie :func:`_zet_lijstrij`.
    """
    from app.domains.mdm.models import (ContactDetail, LegalForm,
                                        OrganizationIdentification)

    rij = _organisatie(db, tenant_id)
    if rij is None:
        return

    geldig = {vorm.value for vorm in LegalForm}
    if "legal_form" in form:
        waarde = (form.get("legal_form") or "").strip() or None
        # Een onbekende rechtsvorm stil opslaan zou een code opleveren die nergens
        # een label heeft; dan staat er straks een lege cel.
        if waarde is None or waarde in geldig:
            rij.legal_form = waarde

    for veld, code in CONTACTVELDEN:
        if veld not in form:
            continue
        _zet_lijstrij(
            db, ContactDetail,
            {"organization_id": tenant_id, "contact_type_code": code},
            "value", (form.get(veld) or "").strip() or None,
            # `tenant_id` is hier niet de scope maar de eigenaar — zie de
            # docstring van `ContactDetail`.
            standaard={"tenant_id": tenant_id, "person_id": None})

    for veld, schema in IDENTIFICATIEVELDEN:
        if veld not in form:
            continue
        _zet_lijstrij(
            db, OrganizationIdentification,
            {"organization_id": tenant_id, "scheme": schema},
            "value", (form.get(veld) or "").strip() or None,
            standaard={"country": "BE"})

    _bewaar_rekening(db, tenant_id, form)
    db.commit()


def _bewaar_rekening(db, tenant_id: int, form: Mapping) -> None:
    """De eerste rekening van de organisatie (#945).

    Apart van :func:`_zet_lijstrij` omdat een rekening uit drie velden bestaat en
    niet uit één: de IBAN maakt de rekening, de BIC en de begunstigde horen erbij.
    Zonder IBAN is er geen rekening, ook niet als er een begunstigde ingevuld is —
    dat zou een rij zijn die niets identificeert.
    """
    from app.domains.mdm.models import BankAccount

    if not any(veld in form for veld, _ in REKENINGVELDEN):
        return
    rekening = (db.query(BankAccount)
                .filter(BankAccount.organization_id == tenant_id,
                        BankAccount.deleted_at.is_(None))
                .order_by(BankAccount.sort_order, BankAccount.id)
                .execution_options(include_all_tenants=True).first())
    waarden = {kolom: ((form.get(veld) or "").strip() or None)
               for veld, kolom in REKENINGVELDEN
               if veld in form}
    iban = waarden.get("iban", rekening.iban if rekening else None)
    if not iban:
        if rekening is not None:
            db.delete(rekening)
        return
    if rekening is None:
        rekening = BankAccount(organization_id=tenant_id, iban=iban)
        db.add(rekening)
    for kolom, waarde in waarden.items():
        setattr(rekening, kolom, waarde)
    rekening.iban = iban


def organization_details(db, tenant_id: int) -> dict[str, str]:
    """Diezelfde velden als platte tekst, voor het formulier.

    Platte waarden en geen ORM-rij: de facade geeft de UI geen modelklassen
    (`test_layer_gate`). Sinds #945 komen ze uit drie tabellen, maar het formulier
    ziet nog altijd één plat woordenboek — het scherm hoeft niet te weten welke
    tabel welk veld draagt.
    """
    from app.domains.mdm.models import (BankAccount, ContactDetail,
                                        OrganizationIdentification)

    leeg = {key: "" for key in ALLE_ORGANISATIEVELDEN}
    rij = _organisatie(db, tenant_id)
    if rij is None:
        return leeg

    uit = dict(leeg)
    uit["legal_form"] = rij.legal_form or ""

    contacten = {c.contact_type_code: c.value for c in
                 db.query(ContactDetail)
                 .filter(ContactDetail.organization_id == tenant_id,
                         ContactDetail.deleted_at.is_(None))
                 .execution_options(include_all_tenants=True).all()}
    for veld, code in CONTACTVELDEN:
        uit[veld] = contacten.get(code) or ""

    nummers = {i.scheme: i.value for i in
               db.query(OrganizationIdentification)
               .filter(OrganizationIdentification.organization_id == tenant_id,
                       OrganizationIdentification.deleted_at.is_(None))
               .execution_options(include_all_tenants=True).all()}
    for veld, schema in IDENTIFICATIEVELDEN:
        uit[veld] = nummers.get(schema) or ""

    rekening = (db.query(BankAccount)
                .filter(BankAccount.organization_id == tenant_id,
                        BankAccount.deleted_at.is_(None))
                .order_by(BankAccount.sort_order, BankAccount.id)
                .execution_options(include_all_tenants=True).first())
    for veld, kolom in REKENINGVELDEN:
        uit[veld] = (getattr(rekening, kolom, None) or "") if rekening else ""
    return uit