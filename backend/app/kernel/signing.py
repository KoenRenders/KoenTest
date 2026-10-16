"""Signed values that carry their own proof: a link whose address names a row and
whose signature says the portal made it (CR-36 #2026, CR-37 #2027; Koen, 15 October
2026: "we gaan dan voor kernel").

`sign(context, *parts)` answers a signature for the parts, `verify(context, *parts,
signature=…)` says whether a signature is the portal's own for them. Nothing is stored:
a bad signature and a row that does not exist answer the same, so the address is no
oracle.

The key is derived from the portal's secret **with the context as its own label**, so a
signature made for one use cannot be passed off for another (a code of the newsletter
is no unsubscribe link). The secret is the one that signs sessions: rotating it ends
every signature made before, which is said wherever a signature outlives the day.
"""

from __future__ import annotations

import hashlib
import hmac

#: The length of a signature, in hex characters: 128 bits, enough against guessing and
#: short enough for an address.
LENGTH = 32

_SEPARATOR = "\x1f"


def _key(context: str) -> bytes:
    from app.config import settings

    return hmac.new(
        settings.secret_key.encode(), b"signing/1:" + context.encode(), hashlib.sha256
    ).digest()


def _message(parts: tuple[object, ...]) -> bytes:
    return _SEPARATOR.join(str(part) for part in parts).encode()


def sign(context: str, *parts: object) -> str:
    """The signature of these parts for this use."""
    return hmac.new(_key(context), _message(parts), hashlib.sha256).hexdigest()[:LENGTH]


def verify(context: str, *parts: object, signature: str) -> bool:
    """Whether `signature` is the portal's own for these parts and this use."""
    if not isinstance(signature, str) or len(signature) != LENGTH:
        return False
    return hmac.compare_digest(sign(context, *parts), signature)
