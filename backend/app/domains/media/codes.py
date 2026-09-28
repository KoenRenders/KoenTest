"""The code list the media domain owns (CR-12 phase 4): the kind of a file.

The words of the four kinds the media screen offers are taken literally from
`kind_labels` in `media/admin_ui.py` (§B8.5: the same words as before). The
other five never reached a screen as a word — they are stored by the design
studio, the newsletter, the activity pages and the chatbot — so theirs are new.

`page_image` carries ONE name again, "Pagina-afbeelding". The short chip label
"Pagina" of #1173 was a stopgap for a filter row that could not grow; #1194
makes the filter a list, and the second name goes with it.
"""

from app.domains.media.models import MediaKind, MediaKindCode, MediaKindLabel
from app.kernel.codes import CodeList, CodeSeed

MEDIA_KIND_CODES = (
    CodeSeed(code="sponsor", nl="Sponsorlogo", en="Sponsor logo", sort_order=10),
    CodeSeed(code="activity_photo", nl="Activiteitenfoto", en="Activity photo", sort_order=20),
    CodeSeed(code="tenant_logo", nl="Logo van de vereniging", en="Association logo", sort_order=30),
    CodeSeed(code="page_image", nl="Pagina-afbeelding", en="Page image", sort_order=40),
    CodeSeed(
        code="activity_poster", nl="Affiche van een activiteit", en="Activity poster", sort_order=50
    ),
    CodeSeed(
        code="component_info",
        nl="Info bij een onderdeel",
        en="Component information",
        sort_order=60,
    ),
    CodeSeed(code="newsletter_file", nl="Nieuwsbriefbestand", en="Newsletter file", sort_order=70),
    CodeSeed(code="design_image", nl="Ontwerpbeeld", en="Design image", sort_order=80),
    CodeSeed(code="design_render", nl="Gerenderd ontwerp", en="Rendered design", sort_order=90),
)

MEDIA_KIND = CodeList(
    name="media_kind",
    schema="media",
    codes=MediaKindCode,
    labels=MediaKindLabel,
    enum=MediaKind,
    fk_from=("media.media_assets.kind",),
)
