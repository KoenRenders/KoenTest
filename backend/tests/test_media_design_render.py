"""A way in for `design_render`, and one SVG list for every kind (#1011).

Koen, 19 September 2026: one machine, one list, and nobody gets a profile of
their own. The dividing line is not "logo against poster" but **drawing against
doing**: what can execute or fetch goes, whatever the kind; what only describes
shape and colour stays, in a logo as much as in a poster.

So these tests check two things at once: that a poster keeps what it needs
(gradient, clip, filter, markers, Inkscape annotations, text), and that the four
refusals of #989 still refuse — on the STORED bytes, because a message on a
screen says nothing about what reached the database.

`<image>` is the sharp edge of that rule: the element draws, but its href can
fetch — and a `data:image/svg+xml` would smuggle an UNCLEANED svg inside a
cleaned one, because this cleaner does not look inside a data URI. Hence:
embedded raster only.

Broken to see them red (measured):
- `filter` out of ALLOWED_ELEMENTS → the poster test fails on the lost filter;
- the Inkscape namespaces out of `_clean_attributes` → the round-trip test fails;
- `process_svg` replaced by storing the raw bytes → all four refusal cases fail;
- the SVG check on `kind` removed → an SVG is stored as a newsletter file;
- `image` accepted without checking its value → the external and the svg-in-a-
  data-uri cases fail;
- the data-uri allowed on any element → the `use` test fails;
- the raster check widened to any `image/*` → the svg-in-a-data-uri case fails;
- `image` out of the list → the embedded raster is dropped.
"""
import pytest

from app.domains.media.api import MediaAsset, MediaFout, add_document
from app.domains.media.svg import INKSCAPE_NS, SODIPODI_NS

pytestmark = pytest.mark.ui_serverrendered

SVG = "http://www.w3.org/2000/svg"

# Wat een affiche nodig heeft: verloop, uitsnijding, filter, marker, tekst en de
# aantekeningen van Inkscape.
AFFICHE = f'''<svg xmlns="{SVG}" xmlns:inkscape="{INKSCAPE_NS}"
     xmlns:sodipodi="{SODIPODI_NS}" viewBox="0 0 420 594" width="420" height="594">
  <sodipodi:namedview pagecolor="#ffffff" inkscape:zoom="0.7"/>
  <defs>
    <linearGradient id="lucht"><stop offset="0" stop-color="#0051a4"/></linearGradient>
    <clipPath id="kader"><rect width="420" height="300"/></clipPath>
    <filter id="schaduw"><feGaussianBlur stdDeviation="3"/><feOffset dx="2" dy="2"/>
      <feDropShadow dx="1" dy="1" flood-color="#000000"/></filter>
    <marker id="punt" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 z"/></marker>
  </defs>
  <g inkscape:label="Achtergrond" inkscape:groupmode="layer" sodipodi:insensitive="true"
     clip-path="url(#kader)">
    <rect width="420" height="300" fill="url(#lucht)" filter="url(#schaduw)"/>
    <line x1="10" y1="320" x2="410" y2="320" stroke="#000" marker-end="url(#punt)"/>
  </g>
  <text x="40" y="380" font-size="40" inkscape:label="Titel">Quiz van Raak</text>
</svg>'''

GEVAARLIJK = {
    "script": f'<svg xmlns="{SVG}" viewBox="0 0 10 10"><script>alert(1)</script>'
              '<rect width="10" height="10"/></svg>',
    "onload": f'<svg xmlns="{SVG}" viewBox="0 0 10 10" onload="alert(1)">'
              '<rect width="10" height="10" onclick="alert(2)"/></svg>',
    "foreignObject": f'<svg xmlns="{SVG}" viewBox="0 0 10 10"><foreignObject>'
                     '<body xmlns="http://www.w3.org/1999/xhtml">hallo</body>'
                     '</foreignObject><rect width="10" height="10"/></svg>',
    "externe href": f'<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink" '
                    'viewBox="0 0 10 10"><use xlink:href="https://evil.example/x.svg#a"/>'
                    '<image href="https://evil.example/foto.png"/>'
                    '<rect width="10" height="10"/></svg>',
}
VERBODEN = [b"script", b"alert", b"onload", b"onclick", b"foreignObject",
            b"evil.example"]


def _render(db, svg=AFFICHE, *, naam="affiche.svg", kind="design_render", **extra):
    return add_document(db, kind=kind, filename=naam,
                        content_type="image/svg+xml", data=svg.encode(), **extra)


# ── De ingang ────────────────────────────────────────────────────────────────

def test_a_render_can_be_stored_as_pdf_png_and_svg(db_session):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2000, 2800), (255, 255, 255)).save(buf, format="PNG")

    pdf = add_document(db_session, kind="design_render", filename="v1.pdf",
                       content_type="application/pdf", data=b"%PDF-1.7\n%aap\n")
    png = add_document(db_session, kind="design_render", filename="v1.png",
                       content_type="image/png", data=buf.getvalue())
    svg = _render(db_session, naam="v1.svg")

    assert pdf.content_type == "application/pdf" and pdf.data.startswith(b"%PDF")
    assert png.content_type == "image/png"
    assert svg.content_type == "image/svg+xml"
    assert all(a.kind == "design_render" for a in (pdf, png, svg))


def test_a_render_png_keeps_its_print_size(db_session):
    """Terugbrengen tot 1600 px zou het beeld vernietigen (#1011)."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (5000, 3000), (255, 255, 255)).save(buf, format="PNG")

    png = add_document(db_session, kind="design_render", filename="groot.png",
                       content_type="image/png", data=buf.getvalue())
    assert max(png.width, png.height) == 4096


def test_a_render_may_hang_on_an_activity(db_session):
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Affiche-activiteit")
    db_session.add(activiteit)
    db_session.flush()

    asset = _render(db_session, activity_id=activiteit.id)
    assert asset.activity_id == activiteit.id


@pytest.mark.parametrize("kind", ["activity_poster", "sponsor", "design_image"])
def test_only_a_render_comes_in_through_this_door(db_session, kind):
    with pytest.raises(MediaFout):
        _render(db_session, kind=kind)


def test_a_newsletter_file_may_not_be_an_svg(db_session):
    """De ingang blijft voor de nieuwsbrief wat ze was (#984)."""
    with pytest.raises(MediaFout) as fout:
        _render(db_session, kind="newsletter_file")
    assert "Design Studio" in str(fout.value)


# ── Tekenen mag ──────────────────────────────────────────────────────────────

def test_a_poster_keeps_everything_it_draws_with(db_session):
    bewaard = _render(db_session).data.decode()

    for onderdeel in ("linearGradient", "clipPath", "filter", "feGaussianBlur",
                      "feDropShadow", "marker", "marker-end", "url(#lucht)",
                      "url(#kader)", "url(#schaduw)", "Quiz van Raak"):
        assert onderdeel in bewaard, f"{onderdeel} overleefde het opschonen niet"


def test_the_round_trip_stays_editable_in_inkscape(db_session):
    """De rondgang: opslaan en weer ophalen laat een bewerkbaar bestand achter.

    Getoetst op wat een editor nodig heeft om het als zíjn bestand te herkennen:
    de naamruimten, de laagaantekeningen, de `namedview` en de tekstobjecten.
    Een render die als platte vormen terugkomt, is geen bron meer.
    """
    eerste = _render(db_session).data.decode()

    for kenmerk in (INKSCAPE_NS, SODIPODI_NS, "namedview",
                    'inkscape:label="Achtergrond"', "groupmode", "<text",
                    # De vergrendeling van de huisstijllaag (#1011, nagelezen door
                    # de designstudio-CLI): verdwijnt dat slotje, dan versleept
                    # iemand na een rondgang per ongeluk het logo.
                    'sodipodi:insensitive="true"'):
        assert kenmerk in eerste, f"{kenmerk} is weg na het opslaan"

    # Tweede rondgang: wat bewaard werd, moet opnieuw bewaard kunnen worden
    # zonder verder te eroderen — anders slijt een affiche bij elke bewerking.
    tweede = _render(db_session, svg=eerste, naam="ronde2.svg").data.decode()
    for kenmerk in (INKSCAPE_NS, SODIPODI_NS, "namedview", "groupmode",
                    'sodipodi:insensitive="true"', "feDropShadow", "Quiz van Raak"):
        assert kenmerk in tweede, f"{kenmerk} is weg na de tweede rondgang"


# ── Doen mag niet, en dat leest de databank ──────────────────────────────────

@pytest.mark.parametrize("soort", sorted(GEVAARLIJK))
def test_a_dangerous_construct_is_not_stored(db_session, soort):
    asset = _render(db_session, svg=GEVAARLIJK[soort], naam=f"{soort}.svg")

    gevonden = [v for v in VERBODEN if v in asset.data]
    assert not gevonden, (soort, gevonden, asset.data)
    assert b"<rect" in asset.data, "het onschuldige deel hoort te blijven"


def test_the_stored_bytes_are_not_the_bytes_that_came_in(db_session):
    """Media schoont zelf op — ook als de aanroeper dat al deed (#1011)."""
    binnen = GEVAARLIJK["script"]
    asset = _render(db_session, svg=binnen)

    assert asset.data.decode() != binnen
    assert "script" not in asset.data.decode()


def test_an_external_reference_in_style_is_refused_too(db_session):
    svg = (f'<svg xmlns="{SVG}" viewBox="0 0 10 10">'
           '<style>@import url(https://evil.example/x.css);</style>'
           '<rect width="10" height="10" style="fill:url(https://evil.example/p)"/></svg>')

    asset = _render(db_session, svg=svg)
    assert b"evil.example" not in asset.data and b"@import" not in asset.data


# ── Bij het uitserveren verandert er niets (#989) ────────────────────────────

def test_the_served_render_still_carries_the_security_headers(client, db_session):
    asset = _render(db_session)
    db_session.commit()

    resp = client.get(f"/api/v1/media/{asset.id}")

    assert resp.status_code == 200
    assert resp.headers.get("content-security-policy") == (
        "default-src 'none'; style-src 'unsafe-inline'")
    assert resp.headers.get("x-content-type-options") == "nosniff"


# ── `<image>`: meedragen mag, ophalen niet (#1011) ───────────────────────────

RASTER = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
          "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
SVG_IN_EEN_DATA_URI = ("data:image/svg+xml;base64,"
                       "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxzY3Jp"
                       "cHQ+YWxlcnQoMSk8L3NjcmlwdD48L3N2Zz4=")


def _met_image(href: str) -> str:
    return ('<svg xmlns="%s" viewBox="0 0 10 10">'
            '<image x="0" y="0" width="10" height="10" href="%s"/>'
            '<rect width="10" height="10"/></svg>' % (SVG, href))


def test_an_embedded_raster_image_stays(db_session):
    """De affiche draagt haar QR-code en foto's als data-URI mee."""
    bewaard = _render(db_session, svg=_met_image(RASTER)).data.decode()

    assert "<image" in bewaard and "data:image/png;base64," in bewaard


@pytest.mark.parametrize("href,waarom", [
    ("https://evil.example/foto.png", "ophalen van buiten"),
    ("file:///etc/passwd", "een bestand van de server"),
    (SVG_IN_EEN_DATA_URI, "een SVG in een data-URI wordt niet opgeschoond"),
])
def test_an_image_that_fetches_or_hides_an_svg_is_refused(db_session, href, waarom):
    bewaard = _render(db_session, svg=_met_image(href)).data.decode()

    assert href not in bewaard, waarom
    for spoor in ("evil.example", "file://", "svg+xml", "script"):
        assert spoor not in bewaard, (waarom, spoor)
    assert "<rect" in bewaard, "het onschuldige deel hoort te blijven"


def test_a_data_uri_is_only_allowed_on_an_image(db_session):
    """Een `use` die een data-URI binnenhaalt, is dezelfde omweg (#1011)."""
    svg = ('<svg xmlns="%s" viewBox="0 0 10 10">'
           '<use href="%s"/><rect width="10" height="10"/></svg>' % (SVG, RASTER))

    bewaard = _render(db_session, svg=svg).data.decode()
    assert "data:image" not in bewaard


# Wat de affiche-sjabloon van CR-10 echt gebruikt, opgesomd door de
# designstudio-CLI. Als één test, zodat een latere wijziging aan de opschoner die
# hier iets van wegneemt, opvalt vóór ze in de studio opvalt.
SJABLOON = '''<svg xmlns="%s" xmlns:inkscape="%s" xmlns:sodipodi="%s"
     viewBox="0 0 420 594">
  <defs>
    <pattern id="ruit" patternUnits="userSpaceOnUse" width="8" height="8">
      <path d="M0 0 h8" stroke="#eee"/></pattern>
    <mask id="verloop" maskUnits="userSpaceOnUse" filter="url(#ruis)">
      <rect width="420" height="594" fill="#fff"/></mask>
    <filter id="ruis">
      <feTurbulence baseFrequency="0.8" numOctaves="2" seed="7" result="t"/>
      <feDisplacementMap in="SourceGraphic" in2="t" scale="4"
                         xChannelSelector="R" yChannelSelector="G"/>
      <feGaussianBlur stdDeviation="1"/></filter>
  </defs>
  <g inkscape:label="Laag" inkscape:groupmode="layer" sodipodi:insensitive="true">
    <path d="M0 0 h10 v10 z" fill-rule="evenodd" fill-opacity="0.4"
          transform="translate(4,4)" stroke-dasharray="2 2" stroke-linecap="round"/>
    <rect width="420" height="594" fill="url(#ruit)" mask="url(#verloop)"/>
    <text x="20" y="80" paint-order="stroke" letter-spacing="1.5" font-weight="700">
      <tspan x="20" dy="0">Raak</tspan></text>
    <svg x="300" y="480" width="90" height="90" viewBox="0 0 21 21">
      <rect width="21" height="21" fill="#000"/></svg>
  </g>
  <script>alert(1)</script>
</svg>''' % (SVG, INKSCAPE_NS, SODIPODI_NS)

SJABLOON_ONDERDELEN = (
    "pattern", "patternUnits", "mask", "maskUnits", "feTurbulence",
    "baseFrequency", "numOctaves", "seed", "feDisplacementMap",
    "xChannelSelector", "yChannelSelector", "feGaussianBlur", "stdDeviation",
    "paint-order", "letter-spacing", "font-weight", "fill-rule", "fill-opacity",
    "stroke-dasharray", "stroke-linecap", "inkscape:label", "groupmode",
    "insensitive", 'viewBox="0 0 21 21"',
)


def test_the_poster_template_of_the_design_studio_survives(db_session):
    bewaard = _render(db_session, svg=SJABLOON, naam="sjabloon.svg").data.decode()

    for onderdeel in SJABLOON_ONDERDELEN:
        assert onderdeel in bewaard, f"{onderdeel} overleefde het opschonen niet"
    assert "script" not in bewaard and "alert" not in bewaard
