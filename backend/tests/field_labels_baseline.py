"""The kit fields that type their label as `_("…")`, frozen by CR-33 (T10): per template and per word, the number of calls.

A ratchet: it may only shrink. A field that is no datum — a search box, a filter, a free setting — stays here; a datum gets an `attribute=` and leaves (`tests/test_field_labels_ratchet.py`). Generated once from the templates on 15 October 2026 (124 calls), then kept by hand.
"""

TYPED_LABELS: dict[str, dict[str, int]] = {
    # #2120: the parameters of the Design Studio's commands — where an uploaded photo goes, what
    # a drawing shows and in which style, which layout an edited SVG is for. They say how one
    # command runs; none is a datum of the design.
    "domains/designstudio/templates/_ds_foto.html": {"Plaats": 1},
    "domains/designstudio/templates/_ds_tekening.html": {"Stijl": 1, "Wat moet erop staan?": 1},
    "domains/designstudio/templates/_ds_inkscape.html": {"Voor opmaak": 1},
    # #2111: the parameters of the copy step are no datum of the register — they say how
    # one action runs (where the first date goes, the copy's status, whether the components go).
    "domains/activities/templates/admin_activiteit_kopieren.html": {
        "Nieuwe begindatum": 1,
        "Ook onderdelen en producten kopiëren": 1,
        "Status van de kopie": 1,
    },
    "domains/activities/templates/_aa_detail.html": {
        "Affiche": 1,
        "Afrekening": 1,
        "Ander e-mailadres": 1,
        "Ander mobiel nummer": 1,
        "Contactpersoon": 1,
        "Datum": 1,
        "Doelpubliek": 1,
        "Einddatum": 1,
        "Enkel leden": 1,
        "Externe info-URL": 1,
        "Externe inschrijf-URL": 1,
        "Externe inschrijvingen-URL": 1,
        "Formulier": 1,
        "Info-bijlage": 1,
        "Inschrijven tot": 1,
        "Interne nota": 1,
        "Ledenprijs": 1,
        "Locatie": 1,
        "Maximum": 2,
        "Naam": 3,
        "Omschrijving": 1,
        "Ploegnaam vereist": 1,
        "Poster-URL": 1,
        "Prijs": 1,
        "Toon e-mail": 1,
        "Toon mobiel": 1,
        "Tot": 1,
        "Van": 1,
        "Vriendelijke URL": 1,
    },
    "domains/activities/templates/_inschrijf_velden.html": {
        "Wanneer vul je de vragen in?": 1,
    },
    "domains/cms/templates/_cp_record.html": {
        "Bovenkopje": 1,
        "De pagina opent met": 1,
        "In het menu": 1,
        "Inleiding": 1,
        "Startpagina": 1,
        "Tint van de hero": 1,
        "Titel": 1,
        "Toon in de voettekst": 1,
        "Webadres": 1,
    },
    "domains/forms/templates/formulier.html": {
        "E-mail": 1,
        "Naam": 1,
    },
    "domains/mdm/templates/leden_gezin.html": {
        "Verantwoordelijk bestuurslid": 1,
    },
    "domains/membership/templates/_household_address.html": {
        "Postcode en gemeente": 1,
    },
    "domains/payment/templates/_bt_boeking.html": {
        "Opmerking": 1,
        "Status": 1,
        'Terugbetaald bedrag") if rec.is_refund else _("Betaald bedrag': 1,
    },
    "domains/payment/templates/betaling_terugbetaling.html": {
        "Reden": 1,
        "Terug te betalen bedrag": 1,
    },
    "domains/pricing/templates/admin_prijs.html": {
        "Maten": 1,
    },
    "domains/product/templates/_product_bijlagen.html": {
        "Document toevoegen": 1,
        "Foto toevoegen": 1,
    },
    "domains/sales/templates/_verkoop_nieuw_form.html": {
        "Artikel": 1,
        "E-mailadres van de koper": 1,
        "Voor wie": 1,
    },
    "domains/sales/templates/_verkoop_wijzig_form.html": {
        "Artikel": 1,
    },
    "domains/stock/templates/admin_correctie.html": {
        "Artikel en maat": 1,
        "Richting": 1,
    },
    "domains/stock/templates/admin_ontvangst.html": {
        "Artikel en maat": 1,
    },
    "domains/workflow/templates/werkbank_taak.html": {
        "Besluit": 1,
    },
    # #2110: the files of an upload are no datum of the register.
    "domains/media/templates/admin_media_nieuw.html": {
        "Bestanden (afbeeldingen)": 1,
    },
    # CR-26 F7/F8: a VAT number and a legal form have no register entry on the public
    # page either (as on the back office's); the two choices are no datum.
    "domains/mdm/templates/my_organisation.html": {
        "Btw-nummer": 1,
        "Rechtsvorm": 1,
    },
    "domains/sales/templates/webshop_mandje.html": {
        "Je bestelt": 1,
    },
    "ui/templates/admin_organisatie.html": {
        "BIC": 1,
        "Begunstigde": 1,
        "Btw-nummer": 1,
        "Bus": 1,
        "E-mail": 1,
        "Facebook": 1,
        "Huisnummer": 1,
        "Instagram": 1,
        "Mobiel": 1,
        "Naam": 1,
        "Ondernemingsnummer": 1,
        "Postcode": 1,
        "Rechtsvorm": 1,
        "Rekeningnummer (IBAN)": 1,
        "Straat": 1,
        "Telefoon": 1,
        "TikTok": 1,
        "Website": 1,
    },
    # #2110: "Account" is the tenant's parent organisation, a foreign key to a table that is
    # no code list, so technical and with no register entry; "Canonieke URL" is a tenant setting
    # (`tenant_settings`), not a datum of the register. The tenant editor types both the same way.
    "ui/templates/admin_tenant_nieuw.html": {
        "Account": 1,
        "Canonieke URL": 1,
    },
    # CR-20 F5: "Toont de gegevens van" is the tenant's shown organisation, a foreign key as
    # "Account" is — technical, with no register entry.
    "ui/templates/_tenant_nieuw_getoond.html": {
        "Toont de gegevens van": 1,
    },
    "ui/templates/admin_tenant.html": {
        "Naam van de site": 1,
        "Organisatie achter de site": 1,
        "Type": 1,
    },
    "ui/templates/design_system.html": {
        "Affiche": 1,
        "Betaalwijze": 1,
        "Dagen": 1,
        "Datum": 3,
        "Dertien opties": 1,
        "Doelpubliek": 1,
        "E-mail": 3,
        "Einddatum": 1,
        "Enkel leden": 1,
        "Externe info-URL": 1,
        "Eén gekozen": 1,
        "Eén optie": 1,
        "Eén uitverkocht": 1,
        "Gelezen": 1,
        "Gratis": 1,
        "Locatie": 2,
        "Maximum": 3,
        "Merkkleur": 1,
        "Naam": 6,
        "Naast een invoerveld": 1,
        "Niets gekozen": 1,
        "Omschrijving": 3,
        "Ploegnaam vereist": 1,
        "Poster-URL": 1,
        "Prijs": 2,
        "Telefoon": 1,
        "Tot": 1,
        "Uur": 1,
        "Van": 2,
        "Vriendelijke URL": 1,
        "Website": 1,
        "Weergave": 1,
    },
}
