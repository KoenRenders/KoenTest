"""What the public pages still write by hand, per template (#1591, CR-11 pilot
B, P4) — the frozen side of `test_public_ratchets.py`.

One exact number per file, counted on 5 October 2026 on master after P1 (the
shell) and P2 (the public form page). A count may only fall: lower the number
in the change that removes a violation, and remove the entry when the file is
clean. P3 (#1590: Word lid, renew, Mijn gezin) empties the membership entries.
"""

#: A `<button>` or a submit written by the template — a button comes from the
#: kit (`ui.btn_*`, `ui.action_bar`, `ui.stepper`). 13 in 7 files.
HAND_WRITTEN_BUTTONS: dict[str, int] = {
    "domains/activities/templates/_onderdeel_acties.html": 1,
    "domains/media/templates/_duim.html": 1,
    "domains/media/templates/fotos_album.html": 4,
    "domains/membership/templates/_lid_persoon_rij.html": 2,
    "domains/membership/templates/gezin_portaal.html": 1,
    "domains/membership/templates/lid_worden.html": 1,
    "ui/templates/_email_rij.html": 3,
}

#: A card drawn by the template itself (a rounded, bordered, white surface) —
#: a card comes from `ui.section`, `ui.flow_card` or `ui.card`. 4 in 4 files.
HAND_WRITTEN_CARDS: dict[str, int] = {
    "domains/auth/templates/login_verlopen.html": 1,
    "domains/media/templates/fotos.html": 1,
    "domains/membership/templates/_lid_persoon_rij.html": 1,
    "domains/membership/templates/gezin_portaal.html": 1,
}

#: A field of the organisation (address, e-mail, phone, account number) written
#: by a page. The organisation's data stand in the footer's legal line
#: (`legal_parts`, §2.5) and on ONE page of their own: "Onze organisatie", the
#: CMS page that is the organisation's (`cms_pagina.html`, #1588) — that is the
#: six here, and it is meant to stay; a seventh, or a second file, is red.
ORGANISATION_FIELDS: dict[str, int] = {
    "domains/cms/templates/cms_pagina.html": 6,
}
