"""What a poster shows, as one frozen value (CR-10 §3.4).

The service builds a :class:`PosterContent` from a design plus the activity it
belongs to — facts from the activity, design text from the design, image bytes
from media — and hands it to the renderer. The renderer knows nothing about
the database; a test builds this value by hand.

Facts and design text are separate on purpose: the facts (title, dates, place,
contacts) are copied *into this value* at render time and never into the
design, so a changed fact shows up in the next render and in the staleness
fingerprint.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImageBytes:
    data: bytes
    mime: str  # image/png | image/jpeg
    focus_x: float = 0.5
    focus_y: float = 0.5
    width: int = 0     # pixel size when known — lets a wide box show a drawing whole instead of cropping it
    height: int = 0


@dataclass(frozen=True)
class Highlight:
    icon: str
    text: str
    emphasis: bool = False


@dataclass(frozen=True)
class Contact:
    name: str
    mobile: str = ""
    email: str = ""


@dataclass(frozen=True)
class PosterContent:
    duo_code: str
    preset: str = "beeld"

    # Title in one or two lines; the "EN" badge sits between two lines when
    # ``title_joiner`` is set (STAPPEN *en* KLAPPEN).
    title_lines: tuple[str, ...] = ()
    title_joiner: str = ""
    bar_text: str = ""          # the rough bar under the title ("SAMEN WANDELEN")
    tagline: str = ""           # handwritten line ("Zet het in je agenda!")

    highlights: tuple[Highlight, ...] = ()
    # The same facts the first two highlight rows carry, as plain lines: the
    # simple preset has no icon rows and prints them above the picture.
    date_line: str = ""             # "ZONDAG 15 NOVEMBER OM 9U45", empty for a series
    location: str = ""
    deadline_text: str = ""         # "Inschrijven tot 8 november", empty when it differs per component
    members_only: bool = False      # "ENKEL LEDEN" instead of "IEDEREEN WELKOM!"
    dates_heading: str = ""
    dates: tuple[str, ...] = ()     # "13 JULI" … at most twelve
    explanation_md: str = ""

    main_image: ImageBytes | None = None
    inset_image: ImageBytes | None = None
    third_image: ImageBytes | None = None

    website: str = ""               # shown without scheme; the QR carries https://
    email: str = ""                 # the association's — on the poster only without contact persons
    association_mobile: str = ""    # idem
    contacts: tuple[Contact, ...] = ()
    logos: tuple[ImageBytes, ...] = ()
    more_info_label: str = "Meer info"

    # Random seeds for the speckles and rough edges — fixed per design so the
    # PDF and the PNG of one version look identical.
    seed: int = 1

    # Free-form, for the fingerprint: anything the renderer does not draw but
    # that must still count as "the facts changed" (e.g. the activity id).
    extra: tuple[tuple[str, str], ...] = field(default_factory=tuple)
