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

**The account scope** (CR-26): an organisation, its addresses, contacts and
bank accounts belong to its account. The operator edits every account's
organisations from the platform, so these queries run with
`include_all_tenants=True`, and a new row takes the organisation's account, not
the current tenant's. Forget the option and you get no error but an empty
result, which is the worst kind.

**Eén rij per soort op het scherm, meer in het model.** Een tweede rekening of een
tweede btw-nummer past in het model en niet in dit formulier. Staat er toch een
tweede, dan bewerkt dit de EERSTE (op `sort_order`, dan `id`) en laat het de rest
ongemoeid — nooit stilzwijgend overschrijven of verwijderen.
"""

from __future__ import annotations

import re
from typing import Mapping

from app.domains.mdm.codes import CONTACT
from app.domains.mdm.tenant_service import OngeldigeInstelling
from app.i18n import _
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

    return (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )


#: #1885: what an organisation's own rows write in their history.
ORGANIZATION_SAVED = "organization_saved"
_SOURCE = "admin_manual"


def _log(db, rij, operation: str, actor: str | None) -> None:
    """The history row of an organisation's row, when its model is logged
    (#1885: its address and contact details are, as a person's are)."""
    from app.kernel.logged import is_logged, snapshot

    if is_logged(type(rij)):
        snapshot(
            db, rij, operation=operation, action=ORGANIZATION_SAVED, source=_SOURCE, actor=actor
        )


def _zet_lijstrij(
    db,
    model,
    filters: dict,
    kolom: str,
    waarde: str | None,
    standaard: dict | None = None,
    actor: str | None = None,
) -> None:
    """Eén rij per soort: schrijf, maak aan, of verwijder als de waarde leeg is.

    De drie lijsten van #945 worden vandaag met één rij per soort bewerkt. Leeg
    betekent "er is er geen", en dan hoort de rij weg te zijn — een rij met een
    lege waarde is een derde toestand die nergens iets betekent en die een
    volgende lezer als "ingevuld" telt.
    """
    rij = (
        db.query(model)
        .filter_by(**filters)
        .filter(model.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .first()
    )
    if not waarde:
        if rij is not None:
            _log(db, rij, "delete", actor)
            db.delete(rij)
        return
    if rij is None:
        rij = model(**filters, **(standaard or {}), **{kolom: waarde})
        db.add(rij)
        db.flush()
        _log(db, rij, "insert", actor)
    elif getattr(rij, kolom) != waarde:
        setattr(rij, kolom, waarde)
        db.flush()
        _log(db, rij, "update", actor)


def save_organization(db, organization_id: int, form: Mapping, *, actor: str | None = None) -> None:
    """The whole organisation form in ONE transaction: details and address (#1244).

    The screen saves two things with one button, and they were two transactions:
    `update_organization_details` committed, `update_organization_address` only
    flushed. `get_db` does not commit, and closing a session rolls back what is
    open — so every address change was lost after the request, while the screen,
    rendered from that same session, showed it as saved. And had the address been
    refused, the name was already committed: half a form saved.

    Now both write, and this commits once, after both succeeded. A refusal from
    either raises before that commit, so nothing of a refused form is committed:
    the request's session closes with the partial writes still open, and closing
    rolls them back.
    """
    _write_organization_details(db, organization_id, form, actor=actor)
    update_organization_address(db, organization_id, form, actor=actor)
    db.commit()


def _email_address(text: str) -> None:
    """The rule of the contact detail (`require_email_address`, #1853), as a refusal
    on the organisation form's field."""
    from app.domains.mdm.models import EmailAddressInvalid, require_email_address

    try:
        require_email_address(text)
    except EmailAddressInvalid as refused:
        raise OngeldigeInstelling({"email": str(refused)}) from None


def update_organization_details(
    db, organization_id: int, form: Mapping, *, actor: str | None = None
) -> None:
    """The details on their own, committed. The screen uses `save_organization`."""
    _write_organization_details(db, organization_id, form, actor=actor)
    db.commit()


def _write_organization_details(
    db, organization_id: int, form: Mapping, *, actor: str | None = None
) -> None:
    """De wereld-kenmerken van de organisatie bewaren (#924, herzien in #945).

    Deze velden verdwenen bij de eerste twee omschakelingen uit de
    tenant-instellingen, en daarmee was er even **geen** scherm meer waar een
    penningmeester het rekeningnummer kon wijzigen. Dat is erger dan de duplicatie
    die eruit ging: dubbel is verwarrend, onbereikbaar is stuk.

    Sinds #945 staan de waarden in drie tabellen in plaats van in elf kolommen.
    Het formulier is hetzelfde gebleven — één invoer per soort — maar het schrijft
    nu rijen. Een lege waarde wist de rij; zie :func:`_zet_lijstrij`.
    """
    from app.domains.mdm.models import ContactDetail, LegalForm, PartyIdentification

    rij = _organisatie(db, organization_id)
    if rij is None:
        return

    # #1517: the enterprise number is checked (ten digits, its check number) and
    # stored in one form, the ten digits of ISO 6523 ICD 0208 — first of all, so
    # a refused number leaves the organisation untouched.
    if (form.get("enterprise_number") or "").strip():
        form = {**form, "enterprise_number": _enterprise_number(form["enterprise_number"])}
    # #1545: the Belgian VAT number too — BE and the enterprise number.
    if (form.get("vat_number") or "").strip():
        form = {**form, "vat_number": _vat_number(form["vat_number"])}
    # #1853: the organisation's e-mail address is an address. The contact detail
    # holds that rule itself at the flush; asked here first, so the refusal
    # stands on its field and a refused form leaves the organisation untouched.
    if (form.get("email") or "").strip():
        _email_address(form["email"].strip())

    # Eerst weigeren, dan pas schrijven: een afgekeurde opslag mag niet half
    # doorgevoerd zijn. `name` voedt sinds #945 de paginatitel, de afzender van
    # mails en de footer, en `tenant_display_name` heeft geen terugval meer
    # achter de organisatie — een lege naam laat dus overal een gat vallen (#954).
    if "name" in form:
        naam = (form.get("name") or "").strip()
        if not naam:
            raise OngeldigeInstelling(
                {
                    "name": _(
                        "De naam van de organisatie mag niet leeg zijn: hij staat in de "
                        "paginatitel, de afzender van je mails en de footer."
                    )
                }
            )
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
            db,
            ContactDetail,
            {"party_id": rij.party_id, "contact_type_code": code},
            "value",
            (form.get(veld) or "").strip() or None,
            # The organisation's account (CR-26 F1), not the current tenant's:
            # the operator edits every account's organisations from the platform.
            standaard={"account_id": rij.account_id},
            actor=actor,
        )

    for veld, schema in IDENTIFICATIEVELDEN:
        if veld not in form:
            continue
        _zet_lijstrij(
            db,
            PartyIdentification,
            {"party_id": rij.party_id, "scheme": schema},
            "value",
            (form.get(veld) or "").strip() or None,
            standaard={"country": "BE", "account_id": rij.account_id},
        )

    _bewaar_rekening(db, organization_id, form)


def _enterprise_number(text: str) -> str:
    """The ten digits of an enterprise number in any usual spelling, or a refusal
    on the field (#1517). The check is of the structure — ten digits, a leading 0
    or 1, the check number — not of whether the KBO knows the number, and every
    structural refusal reads the same (#1549, Koen's text): explaining the
    arithmetic read as technical, and the hint below the field gives the shape."""
    from app.domains.mdm.enterprise_number import EnterpriseNumber, InvalidEnterpriseNumber

    try:
        return EnterpriseNumber.parse(text).digits
    except InvalidEnterpriseNumber:
        raise OngeldigeInstelling(
            {
                "enterprise_number": _(
                    "Dit ondernemingsnummer heeft niet de juiste structuur. Kijk het na."
                )
            }
        ) from None


def _vat_number(text: str) -> str:
    """A Belgian VAT number as `BE` and the ten digits, or a refusal on the field
    (#1545). A Belgian VAT number is the enterprise number with `BE` in front;
    written without a country, it is read as Belgian. Another country's number
    (two other letters in front) is not checked and is stored as typed — its
    rules are its own country's. A refusal reads like the enterprise number's
    (#1549)."""
    from app.domains.mdm.enterprise_number import EnterpriseNumber, InvalidEnterpriseNumber

    typed = text.strip()
    compact = re.sub(r"[\s.\-]", "", typed)
    if re.match(r"[A-Za-z]{2}", compact) and compact[:2].upper() != "BE":
        return typed
    try:
        return "BE" + EnterpriseNumber.parse(compact).digits
    except InvalidEnterpriseNumber:
        raise OngeldigeInstelling(
            {"vat_number": _("Dit btw-nummer heeft niet de juiste structuur. Kijk het na.")}
        ) from None


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
    organisatie = _organisatie(db, organization_id)
    rekening = (
        db.query(BankAccount)
        .filter(BankAccount.party_id == organisatie.party_id, BankAccount.deleted_at.is_(None))
        .order_by(BankAccount.sort_order, BankAccount.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    waarden = {
        kolom: ((form.get(veld) or "").strip() or None)
        for veld, kolom in REKENINGVELDEN
        if veld in form
    }
    iban = waarden.get("iban", rekening.iban if rekening else None)
    if not iban:
        if rekening is not None:
            db.delete(rekening)
        return
    if rekening is None:
        rekening = BankAccount(
            party_id=organisatie.party_id, iban=iban, account_id=organisatie.account_id
        )
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
    from app.domains.mdm.models import BankAccount, ContactDetail, PartyIdentification

    leeg = {key: "" for key in ALLE_ORGANISATIEVELDEN}
    rij = _organisatie(db, organization_id)
    if rij is None:
        return leeg

    uit = dict(leeg)
    uit["name"] = rij.name or ""
    # The CODE to the screen, because the `<option value="...">` carries the
    # code and the template compares it with the selected value.
    uit["legal_form"] = code_of(rij.legal_form) or ""

    contacten = {
        c.contact_type_code: c.value
        for c in db.query(ContactDetail)
        .filter(ContactDetail.party_id == rij.party_id, ContactDetail.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .all()
    }
    for veld, code in CONTACTVELDEN:
        uit[veld] = contacten.get(code) or ""

    nummers = {
        i.scheme: i.value
        for i in db.query(PartyIdentification)
        .filter(
            PartyIdentification.party_id == rij.party_id,
            PartyIdentification.deleted_at.is_(None),
        )
        .execution_options(include_all_tenants=True)
        .all()
    }
    for veld, schema in IDENTIFICATIEVELDEN:
        uit[veld] = nummers.get(schema) or ""

    rekening = (
        db.query(BankAccount)
        .filter(BankAccount.party_id == rij.party_id, BankAccount.deleted_at.is_(None))
        .order_by(BankAccount.sort_order, BankAccount.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    for veld, kolom in REKENINGVELDEN:
        uit[veld] = (getattr(rekening, kolom, None) or "") if rekening else ""
    return uit


# ── De organisaties zelf, en de codelijsten eromheen (#971) ──────────────────


def organization_options(db) -> list[dict]:
    """Every organisation — every party (CR-20: a tenant is no organisation any
    more), by name.

    Until CR-20 this was "every organisation, the ones that are no tenant too":
    `list_units` and `list_manageable_tenants` gave the rows that run a SITE,
    and the ACCOUNT organisation fell outside them — its name, legal form and
    enterprise number were nowhere to be edited.

    Platte dicts en geen ORM-rijen: de UI krijgt van de facade geen modelklassen
    (`test_layer_gate`).
    """
    from app.domains.mdm.models import Organization

    rijen = (
        db.query(Organization)
        .filter(Organization.deleted_at.is_(None))
        .order_by(Organization.name, Organization.id)
        .execution_options(include_all_tenants=True)
        .all()
    )
    return [
        {
            "id": r.id,
            "party_id": r.party_id,
            "name": r.name,
            "is_active": r.is_active,
            "legal_form": r.legal_form or "",
        }
        for r in rijen
    ]


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
    organisatie = _organisatie(db, organization_id)
    if organisatie is None:
        return leeg
    rij = (
        db.query(Address)
        .filter(Address.party_id == organisatie.party_id, Address.deleted_at.is_(None))
        .order_by(Address.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    if rij is None:
        return leeg
    return {
        "street": rij.street or "",
        "house_number": rij.house_number or "",
        "bus_number": rij.bus_number or "",
        "postal_code": rij.postal_code.postal_code if rij.postal_code else "",
    }


def update_organization_address(
    db, organization_id: int, form: Mapping, *, actor: str | None = None
) -> None:
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

    organisatie = _organisatie(db, organization_id)
    rij = (
        db.query(Address)
        .filter(Address.party_id == organisatie.party_id, Address.deleted_at.is_(None))
        .order_by(Address.id)
        .execution_options(include_all_tenants=True)
        .first()
    )

    if not straat and not nummer:
        if rij is not None:
            _log(db, rij, "delete", actor)
            db.delete(rij)
            db.flush()
        return

    fouten: dict[str, str] = {}
    if not straat:
        fouten["street"] = _("Vul een straat in.")
    if not nummer:
        fouten["house_number"] = _("Vul een huisnummer in.")
    pc = (
        db.query(PostalCode).filter(PostalCode.postal_code == postcode).first()
        if postcode
        else None
    )
    if pc is None:
        fouten["postal_code"] = _("Kies een postcode uit de lijst.")
    if fouten or pc is None:
        # `or pc is None` staat er voor mypy én voor de lezer: hieronder wordt
        # `pc.id` gebruikt, en dat mag alleen omdat een ontbrekende postcode
        # altijd al in `fouten` zit. Die afhankelijkheid tussen twee regels is
        # precies wat een volgende bewerking stukmaakt.
        raise OngeldigeInstelling(fouten)

    operation = "insert" if rij is None else "update"
    if rij is None:
        rij = Address(
            party_id=organisatie.party_id,
            # The organisation's account (CR-26 F1), not the current tenant's.
            account_id=organisatie.account_id,
        )
        db.add(rij)
    rij.street = straat
    rij.house_number = nummer
    rij.bus_number = bus or None
    rij.postal_code_id = pc.id
    db.flush()
    _log(db, rij, operation, actor)
