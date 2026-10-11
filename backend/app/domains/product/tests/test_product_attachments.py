"""The article's pictures and documents (CR-21, R3): a photo and a document are
uploaded through the record and removed again, the bytes in media and the soft
reference in product.
"""

from __future__ import annotations

from io import BytesIO

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.product.api import attachments_of, create_product
from tests.conftest import SEEDED_ADMIN_EMAIL


def _operator(client, db_session, every_module_on) -> dict[str, str]:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not any(role.role_code.value == "OPERATOR" for role in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.flush()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def _png() -> bytes:
    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def _pdf() -> bytes:
    stroom = b"1 0 0 rg 20 20 160 260 re f\n"
    uit = bytearray(b"%PDF-1.4\n")
    posities = []
    for nummer, body in enumerate(
        [
            b"<</Type/Catalog/Pages 2 0 R>>",
            b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]/Contents 4 0 R>>",
            b"<</Length " + str(len(stroom)).encode() + b">>stream\n" + stroom + b"endstream",
        ],
        start=1,
    ):
        posities.append(len(uit))
        uit += str(nummer).encode() + b" 0 obj" + body + b"endobj\n"
    start = len(uit)
    uit += b"xref\n0 5\n0000000000 65535 f \n"
    for p in posities:
        uit += ("%010d 00000 n \n" % p).encode()
    uit += b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n"
    return bytes(uit)


def test_a_photo_and_a_document_are_uploaded_and_removed(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    photo = client.post(
        f"/admin/producten/{product.id}/fotos",
        files={"file": ("foto.png", _png(), "image/png")},
        headers=headers,
        follow_redirects=False,
    )
    assert photo.status_code == 303
    assert len(attachments_of(db_session, product.id)) == 1

    document = client.post(
        f"/admin/producten/{product.id}/documenten",
        files={"file": ("maattabel.pdf", _pdf(), "application/pdf")},
        headers=headers,
        follow_redirects=False,
    )
    assert document.status_code == 303
    assert len(attachments_of(db_session, product.id)) == 2

    first = attachments_of(db_session, product.id)[0]
    removed = client.post(
        f"/admin/producten/{product.id}/bijlage/{first.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert len(attachments_of(db_session, product.id)) == 1
