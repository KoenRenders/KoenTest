"""The poster SVG, cleaned on upload (CR-10 §3.6a).

A unit may download the merged SVG, rework it in Inkscape and upload it again;
the upload then replaces the generated file for that layout. An SVG is a
document and can carry code, so the upload goes through the same defence as
the association logo (`media/svg.py`, #989): **an allowlist**, parsed with
`defusedxml`. What is not on the list is dropped, whatever it is called.

The list here is wider than the logo's, on purpose, because a poster is not a
logo: it embeds photos (``<image>`` with a ``data:`` URI of a raster type),
uses filters for its rough edges (``<filter>`` and the ``fe*`` primitives that
Inkscape writes) and carries Inkscape's own layer attributes so the file opens
with its layers intact. It is still a closed list: no ``<script>``,
``<foreignObject>``, ``<a>``, event attributes, external references or
``@import``. A test keeps this list a superset of the logo's, so the two cannot
drift apart in the direction that matters.

Served with the same CSP and ``nosniff`` as every media file.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

#: A poster has a few thousand elements (speckle dots are the bulk).
MAX_ELEMENTS = 200_000
#: An A3 poster with three photos at 300 dpi stays well under this.
MAX_BYTES = 40 * 1024 * 1024


class SvgError(ValueError):
    """An input error the screen shows; no HTTP here."""


ALLOWED_ELEMENTS = frozenset({
    "svg", "g", "defs", "title", "desc", "metadata", "symbol", "use", "style",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "pattern",
    "image",
    "filter", "feTurbulence", "feDisplacementMap", "feGaussianBlur", "feColorMatrix",
    "feComposite", "feOffset", "feMerge", "feMergeNode", "feBlend", "feFlood",
    "feMorphology", "feComponentTransfer", "feFuncA", "feFuncR", "feFuncG", "feFuncB",
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
    "color-interpolation-filters", "isolation", "mix-blend-mode",
    # gradients, patterns, clips, masks
    "offset", "stop-color", "stop-opacity", "gradientUnits",
    "gradientTransform", "spreadMethod", "patternUnits",
    "patternContentUnits", "patternTransform", "clipPathUnits",
    "maskUnits", "maskContentUnits",
    # filters
    "filter", "filterUnits", "primitiveUnits", "in", "in2", "result",
    "type", "baseFrequency", "numOctaves", "seed", "stitchTiles",
    "scale", "xChannelSelector", "yChannelSelector", "stdDeviation",
    "values", "operator", "k1", "k2", "k3", "k4", "mode", "flood-color",
    "flood-opacity", "radius", "tableValues", "slope", "intercept",
    "amplitude", "exponent",
    # references, checked separately
    "href",
    # <style>
    "media",
})

#: Inkscape's own attributes, kept so the layers survive a round trip.
ALLOWED_INKSCAPE = frozenset({"label", "groupmode", "version"})
ALLOWED_SODIPODI = frozenset({"insensitive", "docname"})

_LOCAL_REF = re.compile(r"^#[A-Za-z_][\w.\-]*$")
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg);base64,[A-Za-z0-9+/=\s]+$")
# Anything in style text that loads or runs something. `url(#id)` stays: that
# is how a fill points at a gradient in the same document.
_UNSAFE_STYLE = re.compile(
    r"@import|expression\s*\(|javascript:|behavior\s*:|-moz-binding"
    r"|url\s*\(\s*(?![\"']?#)", re.IGNORECASE)
_NUMBER = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm|px)?\s*$")


def _local(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def _href_ok(el_name: str, value: str) -> bool:
    value = value.strip()
    if el_name == "image":
        return bool(_DATA_IMAGE.match(value))
    return bool(_LOCAL_REF.match(value))


def _clean_attributes(el: ET.Element, el_name: str) -> None:
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
        elif ns == INKSCAPE_NS and name in ALLOWED_INKSCAPE:
            keep = True
        elif ns == SODIPODI_NS and name in ALLOWED_SODIPODI:
            keep = True
        if keep and name == "href":
            keep = _href_ok(el_name, value)
        if keep and name != "href" and _UNSAFE_STYLE.search(value):
            keep = False
        if not keep:
            del el.attrib[key]


def _clean(el: ET.Element) -> None:
    for child in list(el):
        ns, name = _local(child.tag)
        if ns != SVG_NS or name not in ALLOWED_ELEMENTS:
            el.remove(child)
            continue
        if name == "style" and child.text and _UNSAFE_STYLE.search(child.text):
            el.remove(child)
            continue
        _clean_attributes(child, name)
        # An image or a reference whose target was refused is an empty shell:
        # drop it rather than leave a hole that a viewer may still try to load.
        if name in ("image", "use") and not any(_local(k)[1] == "href" for k in child.attrib):
            el.remove(child)
            continue
        _clean(child)
        if name not in ("text", "tspan", "textPath", "title", "desc", "style"):
            child.text = None
        child.tail = None if not (child.tail or "").strip() else child.tail


def _length_mm(value: str | None) -> float | None:
    m = _NUMBER.match(value or "")
    if not m:
        return None
    n = float(m.group(1))
    return n if m.group(2) == "mm" else n * 25.4 / 96


def clean_poster_svg(raw: bytes) -> tuple[bytes, float, float]:
    """The cleaned document and its page size in mm. Raises :class:`SvgError`."""
    if not raw:
        raise SvgError("Leeg bestand")
    if len(raw) > MAX_BYTES:
        raise SvgError("Bestand te groot")
    try:
        root = fromstring(raw)
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise SvgError("Geen geldig SVG-bestand") from exc
    if _local(root.tag) != (SVG_NS, "svg"):
        raise SvgError("Geen geldig SVG-bestand")
    if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
        raise SvgError("Het SVG-bestand is te complex")

    _clean_attributes(root, "svg")
    _clean(root)
    width, height = _length_mm(root.get("width")), _length_mm(root.get("height"))
    if not width or not height:
        raise SvgError("Het SVG-bestand heeft geen paginaformaat (width/height in mm)")

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    ET.register_namespace("sodipodi", SODIPODI_NS)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data, width, height
