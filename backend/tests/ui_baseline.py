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
INCLUDED_BY_THE_PILOT_NOT_RENDERED_THERE: dict[str, str] = {}


#: A control the kit has no macro for on purpose: a drawing of its own that the template
#: names ("DECLARED EXCEPTION") and that stands here with its reason. File → why.
DECLARED_KIT_EXCEPTIONS: dict[str, str] = {
    "domains/meetings/templates/_vg_document.html": (
        "the attendance button of a meeting — one button that cycles present, excused, "
        "empty, a chip per person; not a switch, not a checkbox, not a segment (#2112, Koen, "
        '18 October 2026: "akkoord op alles")'
    ),
}


#: B7 test 8 — raw <label>, <select>, <textarea>, visible <input>. 55 in 16 files.
RAW_FORM_ELEMENTS: dict[str, int] = {
    "domains/forms/templates/_fb_builder.html": 12,
    "domains/forms/templates/_formulier_veld.html": 4,
    "domains/meetings/templates/_vg_kring.html": 1,
    "domains/newsletter/templates/_nb_gesprek.html": 2,
    "domains/newsletter/templates/_nb_import.html": 1,
    "domains/newsletter/templates/_nb_kiezer.html": 1,
    "domains/newsletter/templates/_nb_versturen.html": 4,
    "domains/newsletter/templates/admin_nieuwsbrief.html": 1,
    "domains/reporting/templates/_rp_paneel.html": 4,
}

#: B7 test 9 — raw type="checkbox". 14 in 7 files.
RAW_CHECKBOXES: dict[str, int] = {
    "domains/forms/templates/_fb_builder.html": 6,
    "domains/newsletter/templates/_nb_gesprek.html": 1,
    "domains/reporting/templates/_rp_paneel.html": 1,
}

#: B7 test 8 — margin/padding/gap/space class on a raw form element. 47 in 15 files.
SPACING_ON_FORM_ELEMENTS: dict[str, int] = {
    "domains/forms/templates/_fb_builder.html": 7,
    "domains/forms/templates/_formulier_veld.html": 2,
    "domains/meetings/templates/_vg_kring.html": 3,
    "domains/newsletter/templates/_nb_gesprek.html": 2,
    "domains/newsletter/templates/_nb_kiezer.html": 2,
    "domains/newsletter/templates/_nb_versturen.html": 2,
    "domains/reporting/templates/_rp_paneel.html": 2,
}

#: B7 test 8 — bg-white, bg-gray-50, bg-gray-100 written by the template. 50 in 23 files.
RAW_SURFACES: dict[str, int] = {
    "domains/forms/templates/_fb_builder.html": 6,
    "domains/forms/templates/_fb_resultaten.html": 1,
    "domains/media/templates/_me_boom.html": 1,
    "domains/media/templates/_media_picker.html": 1,
    "domains/reporting/templates/_rp_paneel.html": 14,
    "domains/reporting/templates/_rp_raakje_antwoord.html": 1,
}

#: B7 test 17 — a header button that is neither the create nor "Instellingen". 18 in 10 files.
HEADER_EXTRAS: dict[str, int] = {
    "domains/auth/templates/admin_gebruikers_overzicht.html": 1,
    "domains/meetings/templates/_vg_verstuur.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_archief.html": 1,
}

#: B7 test 18 — a tile strip outside `ui.key_figures`. 0 in 0 files.
HAND_DRAWN_TILES: dict[str, int] = {}

#: a list that scrolls sideways (`overflow-x-auto`). 6 in 5 files.
SIDEWAYS_SCROLLS: dict[str, int] = {
    "domains/newsletter/templates/_nb_afleveringen.html": 1,
    "domains/reporting/templates/_rp_paneel.html": 2,
    "domains/reporting/templates/_rp_raakje_antwoord.html": 1,
}

#: B7 test 22 — nowrap or a fixed min-width on a flex row itself. 3 in 2 files.
WIDENED_ROWS: dict[str, int] = {
    "domains/reporting/templates/_assistant_trigger.html": 1,
    "ui/templates/admin_base.html": 2,
}

#: B7 test 23 — a `checkbox_group` in a toolbar or filter bar. 0 in 0 files.
CHECKBOX_GROUPS_IN_TOOLBARS: dict[str, int] = {}

#: B7 test 1 — an admin page on the shell itself, no layout and no record head. 26 in 26 files.
SHELL_EXTENDED_DIRECTLY: dict[str, int] = {
    "domains/auth/templates/admin_gebruikers_overzicht.html": 1,
    "domains/designstudio/templates/admin_ontwerp_nieuw.html": 1,
    "domains/forms/templates/admin_formulier_builder.html": 1,
    "domains/forms/templates/admin_formulier_inzendingen.html": 1,
    "domains/forms/templates/admin_formulier_resultaten.html": 1,
    "domains/mdm/templates/leden_import.html": 1,
    "domains/meetings/templates/admin_vergadering_verstuur.html": 1,
    "domains/meetings/templates/admin_vergaderkring.html": 1,
    "domains/newsletter/templates/admin_abonnees_import.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_archief.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_instellingen.html": 1,
    "domains/newsletter/templates/admin_nieuwsbrief_versturen.html": 1,
    "domains/reporting/templates/admin_rapport_paneel.html": 1,
    "ui/templates/admin_dashboard.html": 1,
    "ui/templates/admin_info.html": 1,
    "ui/templates/admin_werkruimte_wisselen.html": 1,
    "ui/templates/list_page.html": 1,
    "ui/templates/no_access.html": 1,
}
