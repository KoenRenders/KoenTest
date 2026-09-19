"""A PDF poster gets a picture of its first page (#1019).

Why it matters: the newsletter block of CR-05 (#984) needs an image, and for an
activity that still has to happen the poster is the only source. Posters arrive
as PDF, and no mail client shows a PDF.

Broken on purpose while writing these: `first_page_png` left out of
`_process_document` → the upload test fails; the lazy branch removed from
`serve_thumb` → the third test fails and `/thumb` answers with the PDF itself.
"""
from app.domains.activities.api import Activity  # noqa: F401  (registers the mapper)
from app.domains.media.api import MediaAsset
from app.domains.media.pdf import first_page_png
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

# A real one-page PDF: a red rectangle on 200x300 points. Hand-built because the
# image has no PDF writer — and a stub like `%PDF-1.4 … %%EOF` is exactly the
# unreadable case of the second test.
def _pdf() -> bytes:
    objecten = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]/Contents 4 0 R>>",
        None,
    ]
    stroom = b"1 0 0 rg 20 20 160 260 re f\n"
    objecten[3] = b"<</Length " + str(len(stroom)).encode() + b">>stream\n" + stroom + b"endstream"
    uit = bytearray(b"%PDF-1.4\n")
    posities = []
    for nummer, body in enumerate(objecten, start=1):
        posities.append(len(uit))
        uit += str(nummer).encode() + b" 0 obj" + body + b"endobj\n"
    start = len(uit)
    uit += b"xref\n0 " + str(len(objecten) + 1).encode() + b"\n0000000000 65535 f \n"
    for p in posities:
        uit += ("%010d 00000 n \n" % p).encode()
    uit += (b"trailer<</Size " + str(len(objecten) + 1).encode() + b"/Root 1 0 R>>\nstartxref\n"
            + str(start).encode() + b"\n%%EOF\n")
    return bytes(uit)


_ONLEESBAAR = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def test_een_opgeladen_pdf_affiche_krijgt_een_afbeelding(client, db_session, admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)

    resp = client.post(f"/api/v1/admin/activities/{activity.id}/poster",
                       files={"file": ("affiche.pdf", _pdf(), "application/pdf")},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text

    asset = (db_session.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_poster",
                     MediaAsset.activity_id == activity.id).one())
    assert asset.content_type == "application/pdf", "het document zelf blijft bewaard"
    assert asset.thumbnail, "de eerste bladzijde hoort als afbeelding bewaard te zijn"
    assert asset.thumb_content_type == "image/png"

    getoond = client.get(f"/api/v1/media/{asset.id}/thumb")
    assert getoond.status_code == 200
    assert "image/png" in getoond.headers.get("content-type", "")


def test_een_onleesbare_pdf_levert_geen_afbeelding_en_geen_fout(client, db_session,
                                                                admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)

    resp = client.post(f"/api/v1/admin/activities/{activity.id}/poster",
                       files={"file": ("kapot.pdf", _ONLEESBAAR, "application/pdf")},
                       headers=admin_headers)
    assert resp.status_code == 200, "de upload slaagt; een affiche zonder beeld blijft een affiche"

    asset = (db_session.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_poster",
                     MediaAsset.activity_id == activity.id).one())
    assert asset.thumbnail is None
    assert client.get(f"/api/v1/media/{asset.id}/thumb").status_code == 200


def test_een_oudere_pdf_krijgt_zijn_afbeelding_bij_de_eerste_opvraging(client, db_session):
    """Alles wat vóór deze release opgeladen is, heeft nog geen afbeelding —
    daarvoor is geen eenmalig script nodig."""
    activity, _comp, _p = seed_activity_with_product(db_session)
    asset = MediaAsset(kind="activity_poster", activity_id=activity.id,
                       title="Affiche", content_type="application/pdf",
                       data=_pdf(), byte_size=len(_pdf()))
    db_session.add(asset)
    db_session.commit()

    antwoord = client.get(f"/api/v1/media/{asset.id}/thumb")
    assert antwoord.status_code == 200
    assert "image/png" in antwoord.headers.get("content-type", "")

    db_session.expire_all()
    assert db_session.get(MediaAsset, asset.id).thumbnail, "de afbeelding is bewaard"


def test_het_beheerscherm_toont_de_affiche(client, db_session):
    activity, _comp, _p = seed_activity_with_product(db_session)
    db_session.add(MediaAsset(kind="activity_poster", activity_id=activity.id,
                              title="Affiche", content_type="application/pdf",
                              data=_pdf(), byte_size=len(_pdf())))
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    scherm = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "/thumb" in scherm, "de affiche hoort als voorbeeld op het scherm te staan"


def test_de_renderer_geeft_none_in_plaats_van_een_fout():
    assert first_page_png(b"") is None
    assert first_page_png(b"dit is geen pdf") is None
    assert first_page_png(_ONLEESBAAR) is None
    assert first_page_png(_pdf())
