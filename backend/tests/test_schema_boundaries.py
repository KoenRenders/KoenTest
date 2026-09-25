"""Geen cross-schema FK's (#396/#397, §8-handhaving 2): een FK die twee schema's
koppelt zou onafhankelijk deployen breken én de merge-redirect onmogelijk maken.

**Eén benoemde uitzondering sinds CR-12 (§B2.4):** een FK naar een codetabel van
een *fundamentdomein*. Dat zijn er twee, `mdm` (masterdata) en `auth`
(beveiligingsvocabularium). Ze hangen van geen enkel businessdomein af — `auth`
hangt enkel van `mdm` af — dus er kan geen cyclus ontstaan, en elk domein
importeert `mdm.api` toch al.

Zonder die uitzondering zou een lijst die in `mdm` hoort (taal, betaalwijze) haar
databankcontrole verliezen, en precies die controle is waarom de lijst bestaat:
een label met taal `nl_BE` of `NL` is anders een rij die niemand ooit leest,
zonder dat iets klaagt. De uitzondering is smal met opzet: **alleen** naar
`<fundament>.<lijst>_codes`, nooit naar een gewone tabel van die schema's.
"""
from sqlalchemy import text

#: De schema's waarvan een codetabel het doel van een cross-schema FK mag zijn.
FOUNDATION_SCHEMAS = ("mdm", "auth")


def _is_code_table_of_a_foundation(ref_schema: str, ref_table: str) -> bool:
    return ref_schema in FOUNDATION_SCHEMAS and ref_table.endswith("_codes")


def test_no_cross_schema_foreign_keys(db_session):
    rows = db_session.execute(text("""
        SELECT tc.table_schema, tc.table_name, ccu.table_schema AS ref_schema, ccu.table_name AS ref_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.constraint_schema = ccu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema != ccu.table_schema
    """)).fetchall()
    verboden = [r for r in rows
                if not _is_code_table_of_a_foundation(r.ref_schema, r.ref_table)]
    assert verboden == [], f"Cross-schema FK's gevonden: {verboden}"


def test_de_uitzondering_dekt_alleen_codetabellen():
    """De uitzondering is smal, en dat moet ze blijven.

    Gemeten door overtreding (5 september-werkwijze, #652): een FK naar
    `mdm.persons` — een gewone tabel van een fundamentdomein — hoort nog altijd
    verboden te zijn. Zonder deze test zou iemand `_is_code_table_of_a_foundation`
    kunnen verruimen tot "alles in mdm" en dan bewaakt de poort niets meer.
    """
    assert _is_code_table_of_a_foundation("mdm", "language_codes")
    assert _is_code_table_of_a_foundation("auth", "role_codes")
    assert not _is_code_table_of_a_foundation("mdm", "persons")
    assert not _is_code_table_of_a_foundation("payment", "payment_status_codes")
