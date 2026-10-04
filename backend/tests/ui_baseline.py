"""The frozen standing of the UI ratchets (#1563) — `test_ui_ratchets.py` reads it.

One dict per rule: template → the exact number of violations it held on
5 October 2026, when pilot A (Betalingen and the activity) stood on the kit.
The numbers may only fall. Lower a number in the change that removes a
violation, and remove the entry when the file is clean; the gate is red on room
left standing as much as on a new violation.

Never add an entry and never raise a number to make a build green: a screen
that needs a field uses `ui.field`. The templates of the pilot screens are in
none of these lists, and the gate refuses them here.

`python -m tests.test_ui_ratchets` prints the current measurement in this shape.
"""

#: Partials a pilot page includes but does not render: the pilot's "zero" is
#: about what its screens show. File → why.
INCLUDED_BY_THE_PILOT_NOT_RENDERED_THERE: dict[str, str] = {
    "domains/payment/templates/_bt_boven.html": (
        "the hand-drawn band of the household and registration tabs; behind `show_band`, "
        "which the Betalingen list and the activity's tab leave false (master CLI, 5 October 2026)"
    ),
}


#: B7 test 8 — raw <label>, <select>, <textarea>, visible <input>. 105 in 29 files.
RAW_FORM_ELEMENTS: dict[str, int] = {
    "domains/activities/templates/_inschrijf_velden.html": 8,
    "domains/activities/templates/admin_activiteit_kopieren.html": 10,
    "domains/activities/templates/admin_activiteit_nieuw.html": 2,
    "domains/auth/templates/_aanmelden_code.html": 1,
    "domains/auth/templates/_aanmelden_email.html": 1,
    "domains/auth/templates/_gu_lijst.html": 2,
    "domains/auth/templates/_gu_rollen_velden.html": 6,
    "domains/auth/templates/admin_gebruiker_nieuw.html": 1,
    "domains/cms/templates/_cp_detail.html": 8,
    "domains/cms/templates/admin_pagina_nieuw.html": 2,
    "domains/designstudio/templates/admin_ontwerp.html": 2,
    "domains/forms/templates/_fb_builder.html": 12,
    "domains/forms/templates/_formulier_veld.html": 6,
    "domains/forms/templates/admin_formulier_nieuw.html": 1,
    "domains/media/templates/_me_lijst.html": 5,
    "domains/media/templates/admin_media_nieuw.html": 1,
    "domains/meetings/templates/_vg_document.html": 1,
    "domains/meetings/templates/_vg_kring.html": 1,
    "domains/membership/templates/gezin_portaal.html": 4,
    "domains/membership/templates/lid_worden.html": 4,
    "domains/newsletter/templates/_nb_gesprek.html": 2,
    "domains/newsletter/templates/_nb_import.html": 1,
    "domains/newsletter/templates/_nb_kiezer.html": 1,
    "domains/newsletter/templates/_nb_versturen.html": 4,
    "domains/newsletter/templates/admin_nieuwsbrief.html": 3,
    "domains/reporting/templates/_rp_paneel.html": 4,
    "ui/templates/admin_organisatie_nieuw.html": 2,
    "ui/templates/admin_tenant.html": 7,
    "ui/templates/admin_tenant_nieuw.html": 3,
}

#: B7 test 9 — raw type="checkbox". 24 in 12 files.
RAW_CHECKBOXES: dict[str, int] = {
    "domains/activities/templates/admin_activiteit_kopieren.html": 1,
    "domains/activities/templates/admin_activiteit_nieuw.html": 1,
    "domains/auth/templates/_gu_lijst.html": 1,
    "domains/auth/templates/_gu_rollen_velden.html": 3,
    "domains/cms/templates/_cp_detail.html": 4,
    "domains/designstudio/templates/admin_ontwerp.html": 1,
    "domains/forms/templates/_fb_builder.html": 6,
    "domains/forms/templates/_formulier_veld.html": 1,
    "domains/media/templates/_me_lijst.html": 2,
    "domains/newsletter/templates/_nb_gesprek.html": 1,
    "domains/reporting/templates/_rp_paneel.html": 1,
    "ui/templates/admin_tenant.html": 2,
}

#: B7 test 8 — margin/padding/gap/space class on a raw form element. 76 in 22 files.
SPACING_ON_FORM_ELEMENTS: dict[str, int] = {
    "domains/activities/templates/_inschrijf_velden.html": 8,
    "domains/activities/templates/admin_activiteit_kopieren.html": 14,
    "domains/activities/templates/admin_activiteit_nieuw.html": 1,
    "domains/auth/templates/_aanmelden_code.html": 1,
    "domains/auth/templates/_aanmelden_email.html": 1,
    "domains/auth/templates/_gu_lijst.html": 1,
    "domains/auth/templates/_gu_rollen_velden.html": 3,
    "domains/cms/templates/_cp_detail.html": 4,
    "domains/designstudio/templates/admin_ontwerp.html": 1,
    "domains/forms/templates/_fb_builder.html": 7,
    "domains/forms/templates/_formulier_veld.html": 6,
    "domains/media/templates/_me_lijst.html": 3,
    "domains/meetings/templates/_vg_document.html": 3,
    "domains/meetings/templates/_vg_kring.html": 3,
    "domains/membership/templates/gezin_portaal.html": 2,
    "domains/membership/templates/lid_worden.html": 4,
    "domains/newsletter/templates/_nb_gesprek.html": 2,
    "domains/newsletter/templates/_nb_kiezer.html": 2,
    "domains/newsletter/templates/_nb_versturen.html": 2,
    "domains/newsletter/templates/admin_nieuwsbrief.html": 3,
    "domains/reporting/templates/_rp_paneel.html": 2,
    "ui/templates/admin_tenant.html": 3,
}

#: B7 test 8 — bg-white, bg-gray-50, bg-gray-100 written by the template. 95 in 50 files.
RAW_SURFACES: dict[str, int] = {
    "domains/activities/templates/_aa_kaarten.html": 1,
    "domains/activities/templates/_inschrijf_totaal.html": 1,
    "domains/activities/templates/_inschrijving_detail.html": 5,
    "domains/activities/templates/admin_activiteit_kopieren.html": 1,
    "domains/activities/templates/admin_activiteit_nieuw.html": 1,
    "domains/activities/templates/admin_activiteiten.html": 1,
    "domains/auth/templates/_gu_lijst.html": 1,
    "domains/auth/templates/admin_gebruiker_nieuw.html": 1,
    "domains/auth/templates/login_verlopen.html": 1,
    "domains/chatbot/templates/_ai_context_lijst.html": 2,
    "domains/chatbot/templates/_raakje_ballon.html": 1,
    "domains/chatbot/templates/_raakje_controls.html": 1,
    "domains/cms/templates/_cp_detail.html": 6,
    "domains/cms/templates/_cp_kaarten.html": 1,
    "domains/cms/templates/admin_pagina_nieuw.html": 1,
    "domains/cms/templates/betaling_resultaat.html": 1,
    "domains/forms/templates/_fb_builder.html": 6,
    "domains/forms/templates/_fb_kaarten.html": 1,
    "domains/forms/templates/_fb_resultaten.html": 1,
    "domains/forms/templates/_formulier_veld.html": 1,
    "domains/forms/templates/admin_formulier_nieuw.html": 1,
    "domains/mail/templates/_email_log_lijst.html": 3,
    "domains/mdm/templates/_leden_import_resultaat.html": 1,
    "domains/mdm/templates/_leden_kaarten.html": 4,
    "domains/mdm/templates/_leden_lijst.html": 1,
    "domains/mdm/templates/leden.html": 1,
    "domains/mdm/templates/leden_import.html": 1,
    "domains/media/templates/_me_boom.html": 1,
    "domains/media/templates/_me_lijst.html": 3,
    "domains/media/templates/_media_picker.html": 1,
    "domains/media/templates/admin_media_nieuw.html": 1,
    "domains/media/templates/fotos.html": 2,
    "domains/media/templates/fotos_album.html": 1,
    "domains/membership/templates/_lid_persoon_rij.html": 1,
    "domains/membership/templates/gezin_portaal.html": 1,
    "domains/payment/templates/_bt_boeking.html": 4,
    "domains/payment/templates/_bt_boven.html": 1,
    "domains/reporting/templates/_rp_kaarten.html": 2,
    "domains/reporting/templates/_rp_paneel.html": 14,
    "domains/reporting/templates/_rp_raakje_antwoord.html": 1,
    "domains/workflow/templates/_werkbank_lijst.html": 1,
    "ui/templates/_lw_inhoud.html": 2,
    "ui/templates/_org_kaarten.html": 1,
    "ui/templates/_tn_kaarten.html": 1,
    "ui/templates/admin_dashboard.html": 1,
    "ui/templates/admin_info.html": 4,
    "ui/templates/admin_organisatie_nieuw.html": 1,
    "ui/templates/admin_tenant.html": 2,
    "ui/templates/admin_tenant_nieuw.html": 1,
    "ui/templates/admin_werkruimte_wisselen.html": 1,
}

#: B7 test 17 — a header button that is neither the create nor "Instellingen". 20 in 12 files.
HEADER_EXTRAS: dict[str, int] = {
    "domains/auth/templates/admin_gebruikers.html": 1,
    "domains/auth/templates/admin_gebruikers_overzicht.html": 1,
    "domains/designstudio/templates/admin_ontwerp.html": 1,
    "domains/forms/templates/admin_formulieren.html": 1,
    "domains/mdm/templates/leden.html": 1,
    "domains/meetings/templates/_vg_document.html": 5,
    "domains/meetings/templates/_vg_verstuur.html": 1,
    "domains/newsletter/templates/admin_abonnees.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief.html": 5,
    "domains/newsletter/templates/admin_nieuwsbrief_archief.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrieven.html": 1,
    "ui/templates/admin_tenant.html": 1,
}

#: B7 test 18 — a tile strip outside `ui.key_figures`. 3 in 3 files.
HAND_DRAWN_TILES: dict[str, int] = {
    "domains/activities/templates/admin_activiteiten.html": 1,
    "domains/mdm/templates/leden.html": 1,
    "domains/payment/templates/_bt_boven.html": 1,
}

#: a list that scrolls sideways (`overflow-x-auto`). 9 in 8 files.
SIDEWAYS_SCROLLS: dict[str, int] = {
    "domains/chatbot/templates/_ai_kosten_lijst.html": 1,
    "domains/chatbot/templates/admin_ai_kosten.html": 1,
    "domains/mail/templates/_email_log_lijst.html": 1,
    "domains/newsletter/templates/_nb_abonnees.html": 1,
    "domains/newsletter/templates/_nb_afleveringen.html": 1,
    "domains/reporting/templates/_rp_paneel.html": 2,
    "domains/reporting/templates/_rp_raakje_antwoord.html": 1,
    "ui/templates/_lw_inhoud.html": 1,
}

#: B7 test 22 — nowrap or a fixed min-width on a flex row itself. 7 in 3 files.
WIDENED_ROWS: dict[str, int] = {
    "domains/payment/templates/_bt_boven.html": 4,
    "domains/reporting/templates/_assistant_trigger.html": 1,
    "ui/templates/admin_base.html": 2,
}

#: B7 test 23 — a `checkbox_group` in a toolbar or filter bar. 0 in 0 files.
CHECKBOX_GROUPS_IN_TOOLBARS: dict[str, int] = {}

#: B7 test 1 — an admin page on the shell itself, no layout and no record head. 60 in 60 files.
SHELL_EXTENDED_DIRECTLY: dict[str, int] = {
    "domains/activities/templates/admin_activiteit_kopieren.html": 1,
    "domains/activities/templates/admin_activiteit_nieuw.html": 1,
    "domains/activities/templates/admin_activiteiten.html": 1,
    "domains/activities/templates/admin_inschrijving.html": 1,
    "domains/activities/templates/admin_inschrijving_nieuw.html": 1,
    "domains/auth/templates/admin_gebruiker_nieuw.html": 1,
    "domains/auth/templates/admin_gebruikers.html": 1,
    "domains/auth/templates/admin_gebruikers_overzicht.html": 1,
    "domains/chatbot/templates/admin_ai_kosten.html": 1,
    "domains/chatbot/templates/ai_context.html": 1,
    "domains/cms/templates/admin_pagina.html": 1,
    "domains/cms/templates/admin_pagina_nieuw.html": 1,
    "domains/cms/templates/admin_paginas.html": 1,
    "domains/designstudio/templates/admin_ontwerp.html": 1,
    "domains/designstudio/templates/admin_ontwerp_nieuw.html": 1,
    "domains/designstudio/templates/admin_ontwerpen.html": 1,
    "domains/forms/templates/admin_formulier_builder.html": 1,
    "domains/forms/templates/admin_formulier_inzendingen.html": 1,
    "domains/forms/templates/admin_formulier_nieuw.html": 1,
    "domains/forms/templates/admin_formulier_resultaten.html": 1,
    "domains/forms/templates/admin_formulieren.html": 1,
    "domains/mail/templates/email_log.html": 1,
    "domains/mdm/templates/admin_gezin_inschrijvingen.html": 1,
    "domains/mdm/templates/leden.html": 1,
    "domains/mdm/templates/leden_gezin.html": 1,
    "domains/mdm/templates/leden_import.html": 1,
    "domains/mdm/templates/leden_nieuw.html": 1,
    "domains/media/templates/admin_media.html": 1,
    "domains/media/templates/admin_media_nieuw.html": 1,
    "domains/meetings/templates/admin_vergadering.html": 1,
    "domains/meetings/templates/admin_vergadering_nieuw.html": 1,
    "domains/meetings/templates/admin_vergadering_verstuur.html": 1,
    "domains/meetings/templates/admin_vergaderingen.html": 1,
    "domains/meetings/templates/admin_vergaderkring.html": 1,
    "domains/newsletter/templates/admin_abonnees.html": 1,
    "domains/newsletter/templates/admin_abonnees_import.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_archief.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_instellingen.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_versturen.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrieven.html": 1,
    "domains/payment/templates/admin_gezin_betalingen.html": 1,
    "domains/payment/templates/admin_inschrijving_betalingen.html": 1,
    "domains/reporting/templates/admin_rapport_paneel.html": 1,
    "domains/reporting/templates/admin_rapporten.html": 1,
    "domains/workflow/templates/werkbank.html": 1,
    "domains/workflow/templates/werkbank_taak.html": 1,
    "ui/templates/admin_dashboard.html": 1,
    "ui/templates/admin_info.html": 1,
    "ui/templates/admin_ledenwijzigingen.html": 1,
    "ui/templates/admin_organisatie.html": 1,
    "ui/templates/admin_organisatie_nieuw.html": 1,
    "ui/templates/admin_organisaties.html": 1,
    "ui/templates/admin_profiel.html": 1,
    "ui/templates/admin_tenant.html": 1,
    "ui/templates/admin_tenant_nieuw.html": 1,
    "ui/templates/admin_tenants.html": 1,
    "ui/templates/admin_werkruimte_wisselen.html": 1,
    "ui/templates/list_page.html": 1,
    "ui/templates/no_access.html": 1,
}
