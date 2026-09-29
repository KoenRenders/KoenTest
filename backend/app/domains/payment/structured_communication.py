"""Belgische gestructureerde mededeling (OGM) — #157.

12 cijfers: 10 cijfers + 2 controlecijfers (= het 10-cijferige getal mod 97,
waarbij 0 → 97), weergegeven als +++DDD/DDDD/DDDDD+++.
(verhuisd uit app/services/structured_communication.py, #444)
"""


def generate_structured_communication(base: int) -> str:
    """Bouw een geldige gestructureerde mededeling uit een basisnummer.

    Het basisnummer (typisch een DB-sequence) wordt op 10 cijfers gehouden; de
    laatste 2 cijfers zijn het mod-97-controlegetal (0 → 97).
    """
    from app.kernel.structured_communication import StructuredCommunication

    # CR-13 phase 1: the check digits and the +++…+++ form live in the kernel's
    # value object, which can also read one back; this stays for its callers.
    return str(StructuredCommunication.from_base(base))
