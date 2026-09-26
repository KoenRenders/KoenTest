"""De organisatie als entiteit in de wereld — niet als tenant (#971).

Dit stond tot 16 september 2026 in `tenant_service.py`, en die plaats was precies
de verwarring die #971 opruimt. **Een tenant is een site; een organisatie is een
rechtspersoon.** Meestal vallen ze samen — Raak Millegem is allebei — maar niet
altijd: de ACCOUNT-organisatie (Raak vzw) is géén tenant, en zij is nu net degene
met een ondernemingsnummer en een rekening. Zolang deze functies `tenant_id` als
parameter droegen, las de code alsof zo'n organisatie niet kon bestaan.

De parameter heet daarom overal `organization_id`. Voor een UNIT of een PLATFORM is
dat hetzelfde getal als het tenant-id — die rijen zijn allebei — maar de naam zegt
nu welke van de twee betekenissen bedoeld is.

**De tenant-naad, in het kort** (uitgebreid in de docstrings van `ContactDetail` en
`Address`): `addresses` en `contact_details` worden gedeeld met personen en dragen
daarom een `tenant_id`. Voor een organisatierij is dat NIET de scope —
`organization_id` is dat — dus die query's draaien met
`include_all_tenants=True`. Vergeet je dat, dan krijg je geen fout maar een leeg
resultaat, en dat is de beroerdste soort.

**Eén rij per soort op het scherm, meer in het model.** Een tweede rekening of een
tweede btw-nummer past in het model en niet in dit formulier. Staat er toch een
tweede, dan bewerkt dit de EERSTE (op `sort_order`, dan `id`) en laat het de rest
ongemoeid — nooit stilzwijgend overschrijven of verwijderen.
"""
from __future__ import annotations

from typing import Mapping

from app.i18n import _
from app.domains.mdm.tenant_service import OngeldigeInstelling
from app.domains.mdm.codes import CONTACT
from app.kernel.codes import Code, code_of

# #924: wat de organisatie IS, tegenover wat de site instelt. Twee assen, dus twee
# functies — maar allebei in de servicelaag: het scherm raakt de sessie niet zelf
# aan (`test_layer_gate`).
#
# #945: van de elf kolommen blijft er één over. De rest is een rij geworden in een
# van de drie lijsten hieronder, en het scherm bewerkt nog steeds één rij per
# soort — dat is wat het vandaag nodig heeft. Een tweede btw-nummer of een tweede
# rekening bestaat in het model en is nog geen scherm; dat is het verschil tussen
# "de vorm laat het toe" en "we bouwen het vooruit".
# `name` staat vooraan: het is het veld waar alle andere bij horen (#954). Hij
# ontbrak hier tussen #945 en #954, en daardoor was de naam van de vereniging
# nergens meer te wijzigen — wél te zetten bij het aanmaken van een tenant, en
# daarna nooit meer. Eén bron, nul invoervelden.
ORGANISATIEVELDEN: tuple[str, ...] = ("name", "legal_form")

# (veldnaam in het formulier, code in `contact_type_codes`)
#
# CR-12 phase 2: the right-hand column is a named `Code` from `CONTACT`. This
# is exactly the pair that §B5.3 note 3 calls "two spellings" — and it is not
# one: on the left is a form FIELD NAME (`mobile`), on the right a CODE
# (`MOBILE`). Two different things that happen to look alike. With the named
# constant in place they can no longer be confused, and a misspelt code is an
# `AttributeError` at import instead of a comparison that is never true.
CONTACTVELDEN: tuple[tuple[str, Code], ...] = (
    ("email", CONTACT.EMAIL),
    ("phone", CONTACT.PHONE),
    ("mobile", CONTACT.MOBILE),
    ("website", CONTACT.WEBSITE),
    ("facebook_url", CONTACT.FACEBOOK),
    ("instagram_url", CONTACT.INSTAGRAM),
    ("tiktok_url", CONTACT.TIKTOK),
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


def _organisatie(db, organization_id: int):
    from app.domains.mdm.models import Organization

    return (db.query(Organization).filter(Organization.id == organization_id)
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


def update_organization_details(db, organization_id: int, form: Mapping) -> None:
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

    rij = _organisatie(db, organization_id)
    if rij is None:
        return

    # Eerst weigeren, dan pas schrijven: een afgekeurde opslag mag niet half
    # doorgevoerd zijn. `name` voedt sinds #945 de paginatitel, de afzender van
    # mails en de footer, en `tenant_display_name` heeft geen terugval meer
    # achter de organisatie — een lege naam laat dus overal een gat vallen (#954).
    if "name" in form:
        naam = (form.get("name") or "").strip()
        if not naam:
            raise OngeldigeInstelling({"name": _(
                "De naam van de organisatie mag niet leeg zijn: hij staat in de "
                "paginatitel, de afzender van je mails en de footer.")})
        rij.name = naam

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
            {"organization_id": organization_id, "contact_type_code": code},
            "value", (form.get(veld) or "").strip() or None,
            # De KOLOM heet `tenant_id` en draagt hier de eigenaar, niet de scope
            # — zie de docstring van `ContactDetail`. (Bij het verplaatsen van deze
            # module hernoemde een blinde zoek-en-vervang ook deze sleutel; de
            # tests vielen er meteen over, wat precies is waar ze voor zijn.)
            standaard={"tenant_id": organization_id, "person_id": None})

    for veld, schema in IDENTIFICATIEVELDEN:
        if veld not in form:
            continue
        _zet_lijstrij(
            db, OrganizationIdentification,
            {"organization_id": organization_id, "scheme": schema},
            "value", (form.get(veld) or "").strip() or None,
            standaard={"country": "BE"})

    _bewaar_rekening(db, organization_id, form)
    db.commit()


def _bewaar_rekening(db, organization_id: int, form: Mapping) -> None:
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
                .filter(BankAccount.organization_id == organization_id,
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
        rekening = BankAccount(organization_id=organization_id, iban=iban)
        db.add(rekening)
    for kolom, waarde in waarden.items():
        setattr(rekening, kolom, waarde)
    rekening.iban = iban


def organization_details(db, organization_id: int) -> dict[str, str]:
    """Diezelfde velden als platte tekst, voor het formulier.

    Platte waarden en geen ORM-rij: de facade geeft de UI geen modelklassen
    (`test_layer_gate`). Sinds #945 komen ze uit drie tabellen, maar het formulier
    ziet nog altijd één plat woordenboek — het scherm hoeft niet te weten welke
    tabel welk veld draagt.
    """
    from app.domains.mdm.models import (BankAccount, ContactDetail,
                                        OrganizationIdentification)

    leeg = {key: "" for key in ALLE_ORGANISATIEVELDEN}
    rij = _organisatie(db, organization_id)
    if rij is None:
        return leeg

    uit = dict(leeg)
    uit["name"] = rij.name or ""
    # The CODE to the screen, because the `<option value="...">` carries the
    # code and the template compares it with the selected value.
    uit["legal_form"] = code_of(rij.legal_form) or ""

    contacten = {c.contact_type_code: c.value for c in
                 db.query(ContactDetail)
                 .filter(ContactDetail.organization_id == organization_id,
                         ContactDetail.deleted_at.is_(None))
                 .execution_options(include_all_tenants=True).all()}
    for veld, code in CONTACTVELDEN:
        uit[veld] = contacten.get(code) or ""

    nummers = {i.scheme: i.value for i in
               db.query(OrganizationIdentification)
               .filter(OrganizationIdentification.organization_id == organization_id,
                       OrganizationIdentification.deleted_at.is_(None))
               .execution_options(include_all_tenants=True).all()}
    for veld, schema in IDENTIFICATIEVELDEN:
        uit[veld] = nummers.get(schema) or ""

    rekening = (db.query(BankAccount)
                .filter(BankAccount.organization_id == organization_id,
                        BankAccount.deleted_at.is_(None))
                .order_by(BankAccount.sort_order, BankAccount.id)
                .execution_options(include_all_tenants=True).first())
    for veld, kolom in REKENINGVELDEN:
        uit[veld] = (getattr(rekening, kolom, None) or "") if rekening else ""
    return uit

# ── De organisaties zelf, en de codelijsten eromheen (#971) ──────────────────

def organization_options(db) -> list[dict]:
    """Élke organisatie, ook die geen tenant is.

    Dat laatste is de reden dat deze functie bestaat. `list_units` en
    `list_manageable_tenants` geven de organisaties die een SITE draaien; de
    ACCOUNT-organisatie doet dat niet en viel daardoor overal buiten — haar naam,
    rechtsvorm en ondernemingsnummer waren nergens te bewerken, terwijl zij nu net
    de vzw met een ondernemingsnummer is.

    Platte dicts en geen ORM-rijen: de UI krijgt van de facade geen modelklassen
    (`test_layer_gate`).
    """
    from app.domains.mdm.models import Organization

    rijen = (db.query(Organization)
             .filter(Organization.deleted_at.is_(None))
             .order_by(Organization.org_type, Organization.name)
             .execution_options(include_all_tenants=True).all())
    return [{"id": r.id, "code": r.code, "name": r.name,
             # The code, not the member: these are plain dicts for a screen,
             # and a member equals no string it is compared with (CR-12 phase 2).
             "org_type": code_of(r.org_type), "is_active": r.is_active,
             "legal_form": r.legal_form or ""} for r in rijen]


def legal_form_options(db, taal: str = "nl") -> list[tuple[str, str]]:
    """De rechtsvormen uit `mdm.legal_form_codes`, als (code, label).

    Uit de codelijst en niet uit een lijst in de template: die tabel draagt de
    labels al in nl én en, en een tweede opsomming in een sjabloon is een tweede
    plek voor hetzelfde feit. Voeg er een rij aan toe en de dropdown groeit mee
    zonder codewijziging — daar is een test voor.

    Valt terug op de Nederlandse labels wanneer een taal ontbreekt, en daarna op de
    code zelf: een lege dropdown is erger dan een onvertaald label.
    """
    # CR-12 phase 2: this used to be a hand-written fallback from language to
    # `nl` to the code. Exactly those three steps now live in `code_label()`,
    # so this has become one call — and the same fallback every other screen
    # has.
    from app.kernel.codes import code_labels

    # Pass the session along: this screen can show a just-added legal form
    # that is still in the open transaction, and the kernel's cache reads
    # through a session of its own that by definition sees none of it.
    return code_labels("legal_form", language=taal, db=db)


# ── Het adres (#971) ─────────────────────────────────────────────────────────
#
# Eén adres op het scherm, meer in het model — dezelfde regel als bij de rekening.
# De vorm is LETTERLIJK die van het hoofdlid: vier kolommen, straat over twee,
# huisnummer en bus ernaast, postcode als dropdown over de volle breedte. Dat is
# een vastgelegde UI-beslissing (CLAUDE.md) en geen keuze die hier opnieuw gemaakt
# wordt.

def organization_address(db, organization_id: int) -> dict[str, str]:
    """Het eerste adres van deze organisatie, als platte waarden.

    `first()` en niet `one_or_none()`: staat er ooit een tweede adres, dan hoort dit
    scherm de eerste te tonen en niet om te vallen.
    """
    from app.domains.mdm.models import Address

    leeg = {"street": "", "house_number": "", "bus_number": "", "postal_code": ""}
    rij = (db.query(Address)
           .filter(Address.organization_id == organization_id,
                   Address.deleted_at.is_(None))
           .order_by(Address.id)
           .execution_options(include_all_tenants=True).first())
    if rij is None:
        return leeg
    return {"street": rij.street or "", "house_number": rij.house_number or "",
            "bus_number": rij.bus_number or "",
            "postal_code": rij.postal_code.postal_code if rij.postal_code else ""}


def update_organization_address(db, organization_id: int, form: Mapping) -> None:
    """Het adres bewaren: aanmaken, wijzigen, of weghalen als alles leeg is.

    **De postcode komt uit de postcodetabel**, zoals overal in v2.0: een vrij
    tekstveld zou hier een gemeente zonder postcode toelaten en het adres
    onbruikbaar maken voor elke afleiding die erop steunt.

    Leeg straat- én huisnummer betekent "er is geen adres", en dan hoort de rij weg
    — dezelfde regel als bij de contactgegevens, om dezelfde reden: een rij met lege
    velden is een derde toestand die een volgende lezer als "ingevuld" telt.
    """
    from app.domains.mdm.models import Address, PostalCode

    straat = (form.get("street") or "").strip()
    nummer = (form.get("house_number") or "").strip()
    bus = (form.get("bus_number") or "").strip()
    postcode = (form.get("postal_code") or "").strip()

    rij = (db.query(Address)
           .filter(Address.organization_id == organization_id,
                   Address.deleted_at.is_(None))
           .order_by(Address.id)
           .execution_options(include_all_tenants=True).first())

    if not straat and not nummer:
        if rij is not None:
            db.delete(rij)
            db.flush()
        return

    fouten: dict[str, str] = {}
    if not straat:
        fouten["street"] = _("Vul een straat in.")
    if not nummer:
        fouten["house_number"] = _("Vul een huisnummer in.")
    pc = (db.query(PostalCode).filter(PostalCode.postal_code == postcode).first()
          if postcode else None)
    if pc is None:
        fouten["postal_code"] = _("Kies een postcode uit de lijst.")
    if fouten or pc is None:
        # `or pc is None` staat er voor mypy én voor de lezer: hieronder wordt
        # `pc.id` gebruikt, en dat mag alleen omdat een ontbrekende postcode
        # altijd al in `fouten` zit. Die afhankelijkheid tussen twee regels is
        # precies wat een volgende bewerking stukmaakt.
        raise OngeldigeInstelling(fouten)

    if rij is None:
        rij = Address(organization_id=organization_id, person_id=None,
                      # `tenant_id` is hier de eigenaar en niet de scope — zie de
                      # moduledocstring en die van `ContactDetail`.
                      tenant_id=organization_id)
        db.add(rij)
    rij.street = straat
    rij.house_number = nummer
    rij.bus_number = bus or None
    rij.postal_code_id = pc.id
    db.flush()
