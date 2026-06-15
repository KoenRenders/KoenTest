"""Belgische gestructureerde mededeling (OGM) — #157.

12 cijfers: 10 cijfers + 2 controlecijfers (= het 10-cijferige getal mod 97,
waarbij 0 → 97), weergegeven als +++DDD/DDDD/DDDDD+++.
"""


def generate_structured_communication(base: int) -> str:
    """Bouw een geldige gestructureerde mededeling uit een basisnummer.

    Het basisnummer (typisch een DB-sequence) wordt op 10 cijfers gehouden; de
    laatste 2 cijfers zijn het mod-97-controlegetal (0 → 97).
    """
    base10 = base % 10_000_000_000
    check = base10 % 97 or 97
    digits = f"{base10:010d}{check:02d}"
    return f"+++{digits[0:3]}/{digits[3:7]}/{digits[7:12]}+++"
