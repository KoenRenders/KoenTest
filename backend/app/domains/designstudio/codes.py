"""The code lists the design studio owns (CR-12 fase 3).

Seven lists that were module constants. **The brand assets are not among
them** (§B4.10, and the issue names them so it does not happen by accident):
the icons (code → SVG path), the colour duos (code → two house-style colours),
the paper sizes and the template keys have a *payload*. They change with the
house-style guide, not with a translator, and they stay in `brand.py` and
`icons.py`.
"""
from app.domains.designstudio.models import (
    DesignStatus,
    DesignStatusCode,
    DesignStatusLabel,
    DrawingStyle,
    DrawingStyleCode,
    DrawingStyleLabel,
    GenerationStatus,
    GenerationStatusCode,
    GenerationStatusLabel,
    InsetCorner,
    InsetCornerCode,
    InsetCornerLabel,
    Layout,
    LayoutCode,
    LayoutLabel,
    Preset,
    PresetCode,
    PresetLabel,
    RenderVariant,
    RenderVariantCode,
    RenderVariantLabel,
)
from app.kernel.codes import CodeList, CodeSeed

DESIGN_STATUS_CODES = (
    CodeSeed(code="draft", nl="Ontwerp", en="Draft", sort_order=10),
    CodeSeed(code="final", nl="Definitief", en="Final", sort_order=20),
)

DESIGN_STATUS = CodeList(
    name="design_status", schema="designstudio",
    codes=DesignStatusCode, labels=DesignStatusLabel, enum=DesignStatus,
    fk_from=("designstudio.designs.status",),
)

LAYOUT_CODES = (
    CodeSeed(code="print_a", nl="Print (A3/A4)", en="Print (A3/A4)",
             sort_order=10),
    CodeSeed(code="feed_portrait", nl="Instagram (4:5)", en="Instagram (4:5)",
             sort_order=20),
)

LAYOUT = CodeList(
    name="layout", schema="designstudio",
    codes=LayoutCode, labels=LayoutLabel, enum=Layout,
    fk_from=("designstudio.design_renditions.layout_code",),
)

RENDER_VARIANT_CODES = (
    CodeSeed(code="pdf", nl="PDF", en="PDF", sort_order=10),
    CodeSeed(code="png", nl="PNG", en="PNG", sort_order=20),
    CodeSeed(code="jpeg", nl="JPEG", en="JPEG", sort_order=30),
    CodeSeed(code="svg", nl="SVG", en="SVG", sort_order=40),
    CodeSeed(code="svg_edited", nl="Bewerkte SVG", en="Edited SVG",
             sort_order=50),
)

RENDER_VARIANT = CodeList(
    name="render_variant", schema="designstudio",
    codes=RenderVariantCode, labels=RenderVariantLabel, enum=RenderVariant,
    fk_from=("designstudio.design_renditions.variant",),
)

GENERATION_STATUS_CODES = (
    CodeSeed(code="requested", nl="Bezig…", en="In progress", sort_order=10),
    CodeSeed(code="fetched", nl="Klaar", en="Ready", sort_order=20),
    CodeSeed(code="picked", nl="Gekozen", en="Chosen", sort_order=30),
    CodeSeed(code="discarded", nl="Niet gekozen", en="Not chosen", sort_order=40),
    CodeSeed(code="refused", nl="Geweigerd (moderatie)", en="Refused (moderation)",
             sort_order=50),
    CodeSeed(code="failed", nl="Mislukt", en="Failed", sort_order=60),
)

GENERATION_STATUS = CodeList(
    name="generation_status", schema="designstudio",
    codes=GenerationStatusCode, labels=GenerationStatusLabel,
    enum=GenerationStatus,
    fk_from=("designstudio.image_generations.status",),
)

PRESET_CODES = (
    CodeSeed(code="eenvoudig",
             nl="Eenvoudig — één grote foto en de tekst van de activiteit over "
                "de volle breedte",
             en="Simple — one large photo with the activity text across the "
                "full width",
             sort_order=10),
    CodeSeed(code="beeld",
             nl="Met beeld — foto of tekening rechts, kernpunten links, "
                "omschrijving eronder",
             en="With picture — photo or drawing on the right, key points on "
                "the left, description below",
             sort_order=20),
    CodeSeed(code="tekst",
             nl="Tekst — geen beeld, kernpunten links, omschrijving rechts",
             en="Text — no picture, key points on the left, description on "
                "the right",
             sort_order=30),
)

PRESET = CodeList(
    name="preset", schema="designstudio",
    codes=PresetCode, labels=PresetLabel, enum=Preset,
    fk_from=("designstudio.designs.preset",),
)

INSET_CORNER_CODES = (
    CodeSeed(code="top_left", nl="Linksboven", en="Top left", sort_order=10),
    CodeSeed(code="top_right", nl="Rechtsboven", en="Top right", sort_order=20),
    CodeSeed(code="bottom_left", nl="Linksonder", en="Bottom left", sort_order=30),
    CodeSeed(code="bottom_right", nl="Rechtsonder", en="Bottom right",
             sort_order=40),
)

INSET_CORNER = CodeList(
    name="inset_corner", schema="designstudio",
    codes=InsetCornerCode, labels=InsetCornerLabel, enum=InsetCorner,
    fk_from=("designstudio.designs.inset_corner",),
)

DRAWING_STYLE_CODES = (
    CodeSeed(code="lijn", nl="Lijntekening (zwart-wit)",
             en="Line drawing (black and white)", sort_order=10),
    CodeSeed(code="lijnkleur", nl="Lijntekening met kleuraccenten",
             en="Line drawing with colour accents", sort_order=20),
    CodeSeed(code="kleur", nl="Kleurtekening (vlakke kleuren)",
             en="Colour drawing (flat colours)", sort_order=30),
)

DRAWING_STYLE = CodeList(
    name="drawing_style", schema="designstudio",
    codes=DrawingStyleCode, labels=DrawingStyleLabel, enum=DrawingStyle,
    fk_from=("designstudio.image_generations.style",),
)
