"""A CMS page can show an image: the `page_image` kind and the insert button (#1173).

Koen writes a public how-to page — how to join, how to renew, how to check your
own details — and that needs screenshots. Storage and rendering already existed;
what was missing was the bridge, plus a kind of its own.

**Why a kind of its own, and not an activity photo.** A screenshot is lettering,
and lettering is what JPEG damages. `page_image` therefore joins `LOSSLESS_KINDS`
for the same measured reason as the sponsor logo in #1131 — without making every
activity photo bigger. That half is guarded in
`test_sponsorlogo_blijft_verliesvrij_1131.py`, which owns that list; here we only
check the kind end-to-end.

**The dangerous part is the sanitiser, and the shape of the saved HTML is not
what you would guess.** Trix does not store the `<img>` you insert. Its parser
turns EVERY `<img>` into an attachment — `case "img": e = {url:
t.getAttribute("src"), contentType: "image"}` in `trix.min.js` — keeping only
src, width and height. **An `alt` handed to `insertHTML` is gone before anything
is saved.** Measured in a headless Chromium against the vendored Trix 2.1.15, not
reasoned from the API docs.

So the button puts the alt in the attachment JSON, where Trix does keep it
(measured over two round trips with an edit in between), and
`image_alt_from_attachment()` lifts it onto the `<img>` just before sanitisation.
`nh3` then removes the `<figure>` while keeping its children, so the `<img>`
survives — now with its alt.

The HTML constants below are **literal editor output**, copied from that
measurement. That matters: an invented fixture would prove that the server half
works on HTML nobody produces. `tests_e2e/test_page_image_insert.py`
closes the other half — it drives the real button in a real browser, so the day
Trix changes its serialisation, that test goes red instead of this one going
quietly irrelevant.

Broken on purpose to check these tests can go red. Five proofs, with what each
one actually knocked over — not what it was expected to:
- `image_alt_from_attachment` turned into `return html` → 2 failed
  (`..._carries_its_alt`, `..._survives_a_round_trip`). The img-survives test
  stayed green, which is right: it guards the allowlist, not the alt.
- `"img"` removed from `_ALLOWED_TAGS` → 4 failed. Every test that reads the
  rendered image, the hand-typed-alt one included.
- `page_image` removed from `VALID_KINDS` → 1 failed, only
  `..._offered_by_the_media_library`. The picker test stayed green and that is
  correct: it seeds its asset straight through the ORM, so it depends on the
  kind being filtered, not on the kind being uploadable. Worth knowing before
  reading too much into one red line.
- the `contentType` check dropped → 1 failed, the PDF test ("een bestandsbijlage
  is als afbeelding behandeld").
- `sponsor_options` stripped of its `kind="sponsor"` filter → 1 failed, the
  picker test. That is the proof the picker test needed: the four above never
  touch it.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.cms.render import image_alt_from_attachment, render_cms_content
from app.domains.media.api import MediaAsset, PAGE_IMAGE_KIND
from app.domains.media.images import process_image
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

ALT = "Schermafdruk van het aanmeldformulier"

# ── Literal Trix output ──────────────────────────────────────────────────────
# What the editor writes into the hidden input after
# `insertAttachment(new Trix.Attachment({url, contentType: "image", alt, width,
# height}))`. Copied from the measurement, entity escaping included — the JSON
# sits in a double-quoted attribute, so Trix escapes its quotes as `&quot;`.
INGEVOEGD = (
    '<div><figure data-trix-attachment="{&quot;alt&quot;:&quot;' + ALT + '&quot;,'
    '&quot;contentType&quot;:&quot;image&quot;,&quot;height&quot;:400,'
    '&quot;url&quot;:&quot;/api/v1/media/7&quot;,&quot;width&quot;:640}" '
    'data-trix-content-type="image" '
    'data-trix-attributes="{&quot;presentation&quot;:&quot;gallery&quot;}" '
    'class="attachment attachment--preview">'
    '<img src="/api/v1/media/7" width="640" height="400">'
    '<figcaption class="attachment__caption"></figcaption></figure></div>'
)

# The same page after being reopened and edited: Trix re-parsed its own figure and
# wrote it out again. Kept as a separate constant because this is the state that
# proves the alt does not decay — it is the second save, not the first, where an
# alt stored on the <img> would have been lost.
NA_EEN_RONDGANG = (
    '<div>&nbsp;erbij<figure data-trix-attachment="{&quot;alt&quot;:&quot;' + ALT
    + '&quot;,&quot;contentType&quot;:&quot;image&quot;,&quot;height&quot;:400,'
    '&quot;url&quot;:&quot;/api/v1/media/7&quot;,&quot;width&quot;:640}" '
    'data-trix-content-type="image" class="attachment attachment--preview">'
    '<img src="/api/v1/media/7" width="640" height="400">'
    '<figcaption class="attachment__caption"></figcaption></figure></div>'
)


def _schermafdruk() -> bytes:
    """A screenshot-like image: small lettering and one-pixel rules on white.

    Saved as PNG, which is how a screenshot arrives — so re-encoding it to JPEG
    would be the first compression on this material rather than the second. That
    is enough to damage it: the letters are one pixel wide.
    """
    img = Image.new("RGB", (640, 400), (255, 255, 255))
    tekenaar = ImageDraw.Draw(img)
    for y in range(20, 380, 18):
        tekenaar.line([(20, y), (620, y)], fill=(0, 0, 0), width=1)
        tekenaar.text((26, y + 3), "Lidgeld 35,00 — hoofdlid", fill=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _afwijking(bron: bytes, uit: bytes) -> int:
    a = Image.open(BytesIO(bron)).convert("RGB")
    b = Image.open(BytesIO(uit)).convert("RGB")
    assert a.size == b.size, (a.size, b.size)
    return max(abs(p - q) for pa, pb in zip(a.getdata(), b.getdata())
               for p, q in zip(pa, pb))


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _asset(db, *, kind: str, title: str, activity_id: int | None = None) -> MediaAsset:
    beeld = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    asset = MediaAsset(kind=kind, activity_id=activity_id, title=title, data=beeld,
                       content_type="image/png", thumbnail=beeld,
                       thumb_content_type="image/png", width=640, height=400,
                       byte_size=len(beeld), sort_order=0, is_active=True)
    db.add(asset)
    db.flush()
    return asset


# ── 1. Lossless ──────────────────────────────────────────────────────────────

def test_a_page_image_is_stored_losslessly():
    """The reason the kind exists: the lettering has to stay readable."""
    bron = _schermafdruk()

    uit = process_image(bron, kind=PAGE_IMAGE_KIND)

    assert uit["content_type"] == "image/png", (
        "een schermafdruk is als JPEG bewaard — dan staan de artefacten rond de "
        "letters die #1131 op het MONA-logo liet zien")
    assert uit["thumb_content_type"] == "image/png"
    assert _afwijking(bron, uit["data"]) == 0, (
        "de pixels wijken af van wat er opgeladen werd, dus er is hercodeerd")


# ── 2. The image survives the sanitiser ──────────────────────────────────────

def test_the_inserted_image_survives_sanitisation():
    """The allowlist is where this would die silently: visible in the editor,
    gone on the published page."""
    html = render_cms_content(INGEVOEGD)

    assert '<img src="/api/v1/media/7"' in html, (
        f"de afbeelding is bij het saneren verdwenen:\n{html}")
    assert "<figure" not in html and "data-trix-attachment" not in html, (
        f"de trix-omhulling staat nog in de publieke HTML:\n{html}")
    assert "figcaption" not in html, f"het bijschrift-element staat er nog:\n{html}"


# ── 3. And it carries its alt ────────────────────────────────────────────────

def test_the_inserted_image_carries_its_alt():
    """A how-to page without alternative text is unusable with a screen reader,
    so this is a requirement and not a nicety."""
    html = render_cms_content(INGEVOEGD)

    assert f'alt="{ALT}"' in html, (
        f"de alt uit de bijlage staat niet op de <img>:\n{html}")


def test_the_alt_survives_a_round_trip_through_the_editor():
    """The second save, which is where an alt stored on the <img> would be lost.

    Trix drops an `alt` when it re-parses an `<img>`, so an alt kept on the tag
    would disappear the moment somebody reopens the page and saves again. This
    fixture is the editor's own output after exactly that.
    """
    html = render_cms_content(NA_EEN_RONDGANG)

    assert f'alt="{ALT}"' in html, (
        f"de alt is na een rondgang door de editor verdwenen:\n{html}")
    assert '<img src="/api/v1/media/7"' in html


def test_an_alt_typed_in_the_html_source_wins():
    """Somebody who edits the HTML source by hand made a deliberate choice."""
    eigen = INGEVOEGD.replace('<img src="/api/v1/media/7"',
                              '<img alt="Eigen tekst" src="/api/v1/media/7"')

    html = render_cms_content(eigen)

    assert 'alt="Eigen tekst"' in html, f"de handmatige alt is overschreven:\n{html}"
    assert ALT not in html, f"er staan nu twee alt-teksten op de img:\n{html}"


def test_a_file_attachment_is_not_turned_into_an_image():
    """Trix can also hold a file attachment. That is not an `<img>` and must not
    become one — the rewrite only touches image attachments."""
    pdf = (
        '<div><figure data-trix-attachment="{&quot;alt&quot;:&quot;Verslag&quot;,'
        '&quot;contentType&quot;:&quot;application/pdf&quot;,'
        '&quot;url&quot;:&quot;/api/v1/media/9&quot;}" '
        'class="attachment attachment--file"><img src="/api/v1/media/9">'
        "</figure></div>"
    )

    uit = image_alt_from_attachment(pdf)

    assert 'alt="Verslag"' not in uit, (
        "een bestandsbijlage is als afbeelding behandeld en heeft nu een alt")
    assert uit == pdf, "een niet-beeldbijlage hoort onaangeroerd te blijven"


def test_html_without_an_attachment_is_returned_unchanged():
    """The cheap guard in front of the regex may not alter ordinary content."""
    gewoon = '<p>Gewone tekst met een <a href="/lid-worden">link</a>.</p>'

    assert image_alt_from_attachment(gewoon) == gewoon


# ── 4. The kind stays in its own lane ────────────────────────────────────────

def test_a_page_image_is_offered_by_the_media_library(client, db_session):
    """Uploading is the only way in, so the library has to offer the kind."""
    _login(client, db_session)

    html = client.get(f"/admin/media?kind={PAGE_IMAGE_KIND}").text

    assert "Pagina-afbeelding" in html, "de soort staat niet in het mediascherm"
    nieuw = client.get("/admin/media/nieuw").text
    assert f'value="{PAGE_IMAGE_KIND}"' in nieuw, (
        "de soort staat niet in de keuzelijst van het uploadscherm, dus ze is "
        "niet op te laden")


def test_a_page_image_is_not_offered_as_an_activity_photo_or_a_logo(db_session):
    """It must not surface in the Design Studio's pickers (#1173).

    Both halves are asserted on purpose. That the page image is absent proves
    nothing while the lists could simply be empty — so each list also has to
    contain the kind it is for.
    """
    from app.domains.designstudio.service import image_options, sponsor_options
    from tests.conftest import seed_activity_with_product

    activity, _c, _p = seed_activity_with_product(db_session)
    pagina_beeld = _asset(db_session, kind=PAGE_IMAGE_KIND, title="Schermafdruk")
    foto = _asset(db_session, kind="activity_photo", title="Foto",
                  activity_id=activity.id)
    logo = _asset(db_session, kind="sponsor", title="Sponsorlogo")

    class _Design:
        activity_id = activity.id

    beelden = image_options(db_session, _Design())
    logos = sponsor_options(db_session)

    assert foto.id in [b["id"] for b in beelden], (
        "de activiteitenfoto-keuzelijst is leeg, dus deze test bewijst niets")
    assert logo.id in [m["id"] for m in logos], (
        "de logokiezer is leeg, dus deze test bewijst niets")
    assert pagina_beeld.id not in [b["id"] for b in beelden], (
        "een pagina-afbeelding duikt op in de activiteitenfoto-keuzelijst")
    assert pagina_beeld.id not in [m["id"] for m in logos], (
        "een pagina-afbeelding duikt op in de logokiezer van de Design Studio")


# ── 5. The editor offers the library, and still refuses a dropped file ───────

def test_the_editor_offers_the_library_to_insert_from(client, db_session):
    from app.domains.cms.api import CmsPage

    _login(client, db_session)
    pagina = CmsPage(title="Uitleg", slug="uitleg", content="<p>x</p>")
    db_session.add(pagina)
    db_session.flush()
    beeld = _asset(db_session, kind=PAGE_IMAGE_KIND, title="Schermafdruk")

    html = client.get(f"/admin/paginas/{pagina.id}").text

    assert "insertPageImage" in html, "de invoegknop heeft geen invoegfunctie"
    assert f'data-url="/api/v1/media/{beeld.id}"' in html, (
        "de bibliotheek staat niet in de kiezer, dus er is niets te kiezen")
    assert 'id="cp-alt"' in html, "het alt-veld ontbreekt in de kiezer"


def test_the_editor_still_refuses_a_dropped_file():
    """Deliberate (#1173): dragging a file in would be an unbounded upload path
    to a public page. Inserting goes through the library instead.

    Checked on the shell, where the listener lives, and on the editor fragment,
    which may not smuggle an upload field back in.
    """
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    schil = (app / "ui/templates/admin_base.html").read_text(encoding="utf-8")
    fragment = (app / "domains/cms/templates/_cp_detail.html").read_text(encoding="utf-8")

    assert "trix-file-accept" in schil and "preventDefault" in schil, (
        "de beheerschil onderschept geen bestanden meer in de editor")
    assert 'type="file"' not in fragment, (
        "de pagina-editor heeft een eigen uploadveld gekregen — invoegen hoort "
        "uit de bibliotheek te komen")
