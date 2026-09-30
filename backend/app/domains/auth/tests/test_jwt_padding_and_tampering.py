"""A JWT stays what it was signed as, whatever padding is added (#1398).

`pyjwt` went from 2.14.0 to 2.15.0 for CVE-2026-101918. #1343 had kept 2.14.0
because 2.15.x was said to accept `=` padding at the end of a token. The rule
these tests hold, on any version: a changed signature or payload is refused, and
padding a token never yields anything the original did not already give — the
same subject and the same claims, or a refusal.

Measured on both versions before the pin moved (HS256, our own tokens): every
padded signature or payload is refused with `DecodeError`, and a segment whose
length is already a multiple of four has nothing to pad. No difference between
2.14.0 and 2.15.0 in this; the tests keep it so.

Proven red with an additive violation: a pre-step in `decode_token` that gave
any token with a `=` in it the claims `{"sub": "ander@example.com"}` failed the
padding test on the claims assertion ("padding changed what the token says"),
for every padded variant that reached it. Removed again.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domains.auth.service import create_access_token, decode_token


def _flip_middle(segment: str) -> str:
    """Change a character in the middle, where every bit counts (see the
    tamper test in `test_auth_authz.py` on why not the last one)."""
    middle = len(segment) // 2
    other = "A" if segment[middle] != "A" else "B"
    return f"{segment[:middle]}{other}{segment[middle + 1 :]}"


def _refused(token: str) -> bool:
    try:
        decode_token(token)
    except HTTPException as exc:
        assert exc.status_code == 401
        return True
    return False


def test_a_changed_signature_or_payload_is_refused():
    token = create_access_token({"sub": "iemand@example.com"})
    header, payload, signature = token.split(".")

    assert _refused(f"{header}.{payload}.{_flip_middle(signature)}")
    assert _refused(f"{header}.{_flip_middle(payload)}.{signature}")


@pytest.mark.parametrize("segment", [0, 1, 2])
@pytest.mark.parametrize("padding", ["=", "==", "===", "proper"])
def test_padding_yields_nothing_the_original_did_not(segment, padding):
    token = create_access_token({"sub": "iemand@example.com"})
    original = decode_token(token)
    parts = token.split(".")
    extra = "=" * (-len(parts[segment]) % 4) if padding == "proper" else padding
    parts[segment] += extra
    padded = ".".join(parts)

    try:
        claims = decode_token(padded)
    except HTTPException as exc:
        assert exc.status_code == 401
        return
    assert claims == original, f"padding changed what the token says: {claims} vs {original}"
    assert claims["sub"] == "iemand@example.com"
