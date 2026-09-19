"""SVG for the association logo (#989): cleaned on upload, rendered to PNG.

A raster upload is re-encoded by Pillow, and that re-encoding is the defence: it
strips metadata and neutralises files posing as images. An SVG cannot go that
way — it is a document, and a document can carry code (`<script>`, `on…`
attributes, `<foreignObject>`, external references). So it gets two other
lines of defence:

1. **Cleaned here, with an allowlist.** Elements and attributes that are not on
   the list are dropped, whatever they are called. A denylist would have to know
   every dangerous construct, and that list is long and grows. References may
   only point inside the document (`#id`); style text may not load anything.
2. **Served with a CSP and `nosniff`** (`media/router.py`). If this cleaning ever
   misses something, the browser still runs nothing.

Parsed with `defusedxml`, which refuses entity expansion and external entities
(billion laughs, XXE). Rendered to PNG with CairoSVG (Kozea, France — the maker
of WeasyPrint), because e-mail clients do not show SVG: the newsletter uses the
PNG, the site and the PDF the SVG. CairoSVG needs `libcairo2`, added to the
image for this (WeasyPrint 70 no longer uses Cairo — measured at the build).

Only for `tenant_logo`. Every other kind stays raster — the service decides that.
"""
from __future__ import annotations

import re
from io import BytesIO
from xml.etree import ElementTree as ET

# Imported at module level on purpose: `check_imports.py` imports every module,
# so a missing package breaks the build instead of the first logo upload.
import cairosvg
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from PIL import Image

from app.domains.media.images import MAX_UPLOAD_BYTES, ImageError

SVG_CONTENT_TYPE = "image/svg+xml"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

#: Longest side of the PNG rendering. Twice what a mail header shows, for sharp
#: screens; small enough to stay a few tens of kilobytes.
PNG_MAX_SIDE = 800
#: A logo has hundreds of elements, not tens of thousands. The cap keeps a
#: crafted file from tying up the renderer.
MAX_ELEMENTS = 20_000

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"

# ── Wat mag er in een SVG staan, en waarom ───────────────────────────────────
#
# Eén lijst voor élke soort (#1011). De scheidslijn is niet "logo tegenover
# affiche" maar **tekenen tegenover doen**:
#
#   MAG — alles wat alleen vorm, kleur of tekst beschrijft. Een vorm kan niets
#   uitvoeren en haalt niets op; of ze in een logo of in een affiche staat,
#   verandert daar niets aan. Vandaar dat de lijst van #989 hier verbreed wordt
#   in plaats van dat er een tweede, ruimere lijst naast komt: twee lijsten voor
#   dezelfde vraag lopen uit elkaar, en dan is de strengste van de twee de
#   enige die telt op de dag dat iemand de verkeerde gebruikt.
#
#   MAG NIET — twee dingen, en alleen deze twee:
#     * **uitvoeren**: `script`, elk `on…`-attribuut, `foreignObject` (dat haalt
#       HTML binnen en daarmee alles wat HTML kan), `javascript:` in een waarde;
#     * **ophalen van buiten**: een verwijzing die het document verlaat — een
#       externe `href`/`xlink:href`, `image` (verwijst per definitie naar een
#       bestand), `feImage`, en `url(...)` in stijl die niet naar `#id` wijst.
#       Wat van buiten komt, kan morgen iets anders zijn dan vandaag, en het
#       vertelt de buitenwereld wie het document opende.
#
# Wie hier iets bij wil zetten, toetst aan die twee vragen: kan het uitvoeren?
# kan het iets ophalen? Twee keer nee → het hoort thuis op de lijst. Twee keer
# nee is ook precies waarom de filters hieronder mochten: een gaussische vervaging
# rekent op pixels die er al zijn.
ALLOWED_ELEMENTS = frozenset({
    # Structuur en vorm
    "svg", "g", "defs", "title", "desc", "symbol", "use", "style", "metadata",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "pattern",
    # Markers: pijlpunten en stippen op een lijn — tekenen, niets meer (#1011).
    "marker",
    # `image` mag, maar alleen met een INGEBEDDE rasterafbeelding — zie
    # `_BRUIKBARE_AFBEELDING` hieronder. Het element zelf is tekenwerk; het is de
    # WAARDE van zijn href die kan ophalen.
    "image",
    # Filters (#1011): een affiche gebruikt schaduw, vervaging en kleurcorrectie.
    # Allemaal rekenwerk op de pixels van het document zelf. `feImage` staat er
    # bewust NIET bij: dat is het enige filterelement dat iets van buiten haalt.
    "filter", "feBlend", "feColorMatrix", "feComponentTransfer", "feComposite",
    "feConvolveMatrix", "feDiffuseLighting", "feDisplacementMap", "feDistantLight",
    "feDropShadow", "feFlood", "feFuncA", "feFuncB", "feFuncG", "feFuncR",
    "feGaussianBlur", "feMerge", "feMergeNode", "feMorphology", "feOffset",
    "fePointLight", "feSpecularLighting", "feSpotLight", "feTile", "feTurbulence",
})

ALLOWED_ATTRIBUTES = frozenset({
    # identity and structure
    "id", "class", "style", "lang", "version", "viewBox", "preserveAspectRatio",
    "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "fx", "fy", "d", "points", "transform", "pathLength",
    # text
    "dx", "dy", "rotate", "textLength", "lengthAdjust", "startOffset", "method",
    "spacing", "text-anchor", "dominant-baseline", "alignment-baseline",
    "baseline-shift", "font-family", "font-size", "font-size-adjust",
    "font-stretch", "font-style", "font-variant", "font-weight",
    "letter-spacing", "word-spacing", "text-decoration", "writing-mode",
    "direction", "unicode-bidi", "white-space",
    # painting
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-dasharray",
    "stroke-dashoffset", "stroke-linecap", "stroke-linejoin",
    "stroke-miterlimit", "stroke-opacity", "stroke-width", "opacity",
    "color", "display", "visibility", "overflow", "clip", "clip-path",
    "clip-rule", "mask", "vector-effect", "paint-order", "shape-rendering",
    "text-rendering", "image-rendering", "color-interpolation",
    "isolation", "mix-blend-mode",
    # gradients, patterns, clips, masks
    "offset", "stop-color", "stop-opacity", "gradientUnits",
    "gradientTransform", "spreadMethod", "patternUnits",
    "patternContentUnits", "patternTransform", "clipPathUnits",
    "maskUnits", "maskContentUnits",
    # references, checked separately
    "href",
    # <style>
    "type", "media",
    # Markers (#1011)
    "marker-start", "marker-mid", "marker-end", "markerUnits", "markerWidth",
    "markerHeight", "refX", "refY", "orient",
    # Filters (#1011): parameters van het rekenwerk hierboven. Geen van deze
    # waarden kan een adres zijn — `in`/`in2`/`result` verwijzen naar een
    # tussenresultaat binnen hetzelfde filter.
    "filter", "filterUnits", "primitiveUnits", "in", "in2", "result",
    "stdDeviation", "mode", "values", "operator", "k1", "k2", "k3", "k4",
    "radius", "flood-color", "flood-opacity", "surfaceScale", "specularConstant",
    "specularExponent", "diffuseConstant", "kernelMatrix", "kernelUnitLength",
    "order", "divisor", "bias", "targetX", "targetY", "edgeMode", "preserveAlpha",
    "xChannelSelector", "yChannelSelector", "scale", "baseFrequency",
    "numOctaves", "seed", "stitchTiles", "tableValues", "slope", "intercept",
    "amplitude", "exponent", "azimuth", "elevation", "pointsAtX", "pointsAtY",
    "pointsAtZ", "limitingConeAngle", "z", "color-interpolation-filters",
})

_LOCAL_REF = re.compile(r"^#[A-Za-z_][\w.\-]*$")
# Een `<image>` die haar beeld meedraagt in plaats van het op te halen (#1011).
# Twee deuren blijven dicht:
#   * `http(s)://` of `file://` — dat is ophalen van buiten, en dat verbiedt de
#     regel van dit bestand;
#   * `data:image/svg+xml` — een SVG ín een SVG. De buitenste wordt opgeschoond,
#     de binnenste niet: deze opschoner kijkt niet in een data-URI. Vandaar dat
#     alleen RASTERformaten erdoor mogen.
_BRUIKBARE_AFBEELDING = re.compile(
    r"^data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)
# Anything in style text that loads or runs something. `url(#id)` stays: that
# is how a fill points at a gradient in the same document.
_UNSAFE_STYLE = re.compile(
    r"@import|expression\s*\(|javascript:|behavior\s*:|-moz-binding"
    r"|url\s*\(\s*(?![\"']?#)", re.I)
_NUMBER = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$")


def _local(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def _clean_attributes(el: ET.Element, *, naam: str = "") -> None:
    for key in list(el.attrib):
        ns, name = _local(key)
        value = el.attrib[key]
        keep = False
        if ns == "" and name in ALLOWED_ATTRIBUTES:
            keep = True
        elif ns == XLINK_NS and name == "href":
            keep = True
        elif ns == XML_NS and name in ("lang", "space"):
            keep = True
        elif ns in (INKSCAPE_NS, SODIPODI_NS):
            # #1011: de eigen aantekeningen van Inkscape (laagnamen, hulplijnen,
            # het type van een vorm). Ze tekenen niets en voeren niets uit; ze
            # laten een bestand een rondgang naar de editor overleven. Ze wegkuisen
            # maakt een affiche onbewerkbaar zonder iets veiliger te maken.
            keep = True
        if keep and name == "href":
            schoon = value.strip()
            keep = bool(_LOCAL_REF.match(schoon)) or (
                naam == "image" and bool(_BRUIKBARE_AFBEELDING.match(schoon)))
        if keep and _UNSAFE_STYLE.search(value):
            keep = False
        if not keep:
            del el.attrib[key]


def _clean(el: ET.Element) -> None:
    for child in list(el):
        ns, name = _local(child.tag)
        if ns in (INKSCAPE_NS, SODIPODI_NS):
            # Zelfde reden als bij de attributen: `sodipodi:namedview` draagt de
            # instellingen van de editor, meer niet.
            _clean_attributes(child, naam=name)
            _clean(child)
            continue
        if ns != SVG_NS or name not in ALLOWED_ELEMENTS:
            el.remove(child)
            continue
        if name == "style" and child.text and _UNSAFE_STYLE.search(child.text):
            el.remove(child)
            continue
        _clean_attributes(child, naam=name)
        _clean(child)
        # Text belongs to text elements and <style>; anywhere else it is noise.
        if name not in ("text", "tspan", "textPath", "title", "desc", "style"):
            child.text = None
        child.tail = None if not (child.tail or "").strip() else child.tail


def _length(value: str | None) -> float | None:
    m = _NUMBER.match(value or "")
    return float(m.group(1)) if m else None


def _size(root: ET.Element) -> tuple[float, float]:
    width, height = _length(root.get("width")), _length(root.get("height"))
    if width and height:
        return width, height
    parts = (root.get("viewBox") or "").replace(",", " ").split()
    if len(parts) == 4:
        try:
            vb_w, vb_h = float(parts[2]), float(parts[3])
        except ValueError:
            vb_w = vb_h = 0
        if vb_w > 0 and vb_h > 0:
            return vb_w, vb_h
    raise ImageError("Het SVG-bestand heeft geen afmetingen (width/height of viewBox)")


def clean_svg(raw: bytes) -> tuple[bytes, float, float]:
    """The cleaned document and its intrinsic size. Raises `ImageError`."""
    if not raw:
        raise ImageError("Leeg bestand")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError("Bestand te groot")
    try:
        root = fromstring(raw)
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise ImageError("Geen geldig SVG-bestand") from exc
    if _local(root.tag) != (SVG_NS, "svg"):
        raise ImageError("Geen geldig SVG-bestand")
    if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
        raise ImageError("Het SVG-bestand is te complex voor een logo")

    _clean_attributes(root)
    _clean(root)
    width, height = _size(root)

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    ET.register_namespace("sodipodi", SODIPODI_NS)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data, width, height


def render_png(svg: bytes, width: float, height: float) -> bytes:
    """The cleaned SVG as PNG, longest side `PNG_MAX_SIDE`, transparency kept."""
    scale = PNG_MAX_SIDE / max(width, height)
    out_w, out_h = max(1, round(width * scale)), max(1, round(height * scale))
    try:
        png = cairosvg.svg2png(bytestring=svg, output_width=out_w, output_height=out_h,
                               unsafe=False)
    except Exception as exc:  # noqa: BLE001 - any renderer failure is an unusable file
        raise ImageError("Het SVG-bestand kon niet weergegeven worden") from exc
    # Through Pillow once more: a PNG that Pillow cannot read is not one to mail.
    with Image.open(BytesIO(png)) as img:
        img.load()
    return png


def process_svg(raw: bytes) -> dict:
    """Same shape as `process_image`: the cleaned SVG as data, the PNG as thumbnail."""
    data, width, height = clean_svg(raw)
    png = render_png(data, width, height)
    return {
        "data": data,
        "content_type": SVG_CONTENT_TYPE,
        "thumbnail": png,
        "thumb_content_type": "image/png",
        "width": round(width),
        "height": round(height),
        "byte_size": len(data),
    }
