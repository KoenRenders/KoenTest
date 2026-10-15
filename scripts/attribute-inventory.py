"""Inventory of the business columns of the ORM, per schema (module), with a proposed label and the AI
classification per RULE (CR-33, the attribute register). Appendix: docs/change_request_33_attribute_inventory.md.
Run inside a backend container: `python scripts/attribute-inventory.py /app > docs/change_request_33_attribute_inventory.md`;
re-run on the handover commit of phase 1, and retire with the register (the coverage gate replaces it).
"""

import os
import re
import sys
from collections import Counter

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://u:p@localhost/x")
sys.path.insert(0, sys.argv[1])
import app.models  # noqa: F401
from app.database import Base

TECH_NAMES = re.compile(r"^(tenant_id|created_at|updated_at|deleted_at)$")


def technical(c) -> bool:
    """Technical by what the metadata says, not by the name (build read B3): the primary
    key, a column with a foreign key, tenant_id and the timestamps. `external_id` without a
    key and `created_by` are data."""
    to_code_list = any(k.column.table.name.endswith("_codes") for k in c.foreign_keys)
    return bool(
        c.primary_key
        or (c.foreign_keys and not to_code_list)
        or TECH_NAMES.match(c.name)
    )


BUILD = {"sales", "product", "stock", "pricing"}  # CR-21, in build, not on master

LABELS = {
    "name": "Naam",
    "first_name": "Voornaam",
    "last_name": "Achternaam",
    "birth_date": "Geboortedatum",
    "gender": "Geslacht",
    "email": "E-mail",
    "phone": "Telefoon",
    "mobile": "Mobiel",
    "street": "Straat",
    "house_number": "Huisnummer",
    "box": "Bus",
    "bus": "Bus",
    "postal_code": "Postcode",
    "municipality": "Gemeente",
    "city": "Gemeente",
    "country": "Land",
    "description": "Omschrijving",
    "title": "Titel",
    "slug": "Webadres",
    "location": "Locatie",
    "start_date": "Startdatum",
    "end_date": "Einddatum",
    "start_time": "Beginuur",
    "end_time": "Einduur",
    "price": "Prijs",
    "member_price": "Ledenprijs",
    "amount": "Bedrag",
    "status": "Status",
    "note": "Opmerking",
    "notes": "Opmerkingen",
    "content": "Inhoud",
    "subject": "Onderwerp",
    "body": "Tekst",
    "iban": "IBAN",
    "bic": "BIC",
    "ogm": "Gestructureerde mededeling",
    "structured_communication": "Gestructureerde mededeling",
    "quantity": "Aantal",
    "max_participants": "Maximum aantal deelnemers",
    "is_free": "Gratis",
    "members_only": "Alleen voor leden",
    "contact_name": "Naam",
    "contact_email": "E-mail",
    "contact_mobile": "Mobiel",
    "contact_phone": "Telefoon",
    "team_name": "Ploegnaam",
    "relation_type": "Relatie",
    "contact_type_code": "Soort contact",
    "value": "Waarde",
    "kind": "Soort",
    "code": "Code",
    "label": "Label",
    "role": "Rol",
    "paid_at": "Betaald op",
    "due_date": "Vervaldatum",
    "paid_amount": "Betaald",
    "open_amount": "Openstaand",
    "payment_method": "Betaalwijze",
    "sort_order": "Volgorde",
    "is_active": "Actief",
    "published_at": "Gepubliceerd op",
    "vat_number": "Btw-nummer",
    "enterprise_number": "Ondernemingsnummer",
    "legal_form": "Rechtsvorm",
    "website": "Website",
    "year": "Jaar",
    "valid_from": "Geldig van",
    "valid_until": "Geldig tot",
}

# Column-name patterns that identify a natural person: never to a model.
IDENTIFYING = re.compile(
    r"(first_name|last_name|birth|email|phone|mobile|iban|bic|ogm|structured_comm|street|house_number"
    r"|^box$|^bus$|bus_number|beneficiary|password|token|secret|encrypted|signature|ip_address|user_agent|national"
    r"|external_id|provider_payment_id|checkout_url|payload|payment_metadata|last_error|error_message"
    r"|^recipient$|^actor$|_by$|extracted_text)"
)
GUEST = re.compile(r"^guest_name$")
PUBLIC_SHOP = re.compile(r"^(intro|name|description|slug)$")
FREE_TEXT = re.compile(
    r"(note|notes|remark|comment|content|body|message|answer|text|reason|question|prompt|reply)"
)
NAME_OF_PERSON = re.compile(
    r"(^name$|_name$|display_name|contact_name|registrant|attendee|author|sender|recipient)"
)
PERSON_TABLES = re.compile(
    r"(person|contact_detail|address|household|member|user|registration|subscriber|recipient|attendee"
    r"|submission|idea|chat_message|conversation|account|login|session|invite)"
)
PUBLIC_SCHEMAS = {"cms", "media"}
PUBLIC_ACTIVITY_COLS = re.compile(
    r"^(name|description|location|start_date|end_date|start_time|end_time|price|member_price|is_free"
    r"|members_only|max_participants|target_audience|slug|title|summary|alt|caption|year|published_at)$"
)


def classify(schema: str, table: str, col: str, type_name: str, fks) -> tuple[str, str]:
    """Return (classification, rule)."""
    personal = bool(PERSON_TABLES.search(table)) or table.startswith("sales_orders")
    flag_or_type = re.search(r"(^(show|has|is)_|_(type|count|kind)$|^tokens_)", col)
    if IDENTIFYING.search(col) and not flag_or_type:
        return (
            "never",
            "K1 identifies a person, names who did it, or is a secret or an opaque payload",
        )
    if GUEST.match(col):
        return "tokenised", "K2 the name of a person: the token stands for it"
    if table in {
        "shop_settings",
        "products",
        "product_variants",
        "product_attachments",
        "prices",
    } and not re.search(r"_id$|sort_order", col):
        return (
            "public",
            "K5 what the public shop page shows: articles, sizes, prices, availability (Koen, 15 October 2026)",
        )
    if table in {"email_log"}:
        return "never", "K3 a mail to a person: its text names the person"
    if table.startswith("meeting") and re.search(
        r"(notes|data|filename|steward|member_id|person_id)", col
    ):
        return (
            "never",
            "K3 the board's meeting: files, notes and the members discussed never go to a model (Koen, 15 October 2026)",
        )
    if (
        (table == "payment_records" and col == "note")
        or (table == "newsletters" and col == "reply_to_address")
        or (table == "deliveries" and col == "error")
        or (table == "stock_movements" and col == "note")
    ):
        return (
            "never",
            "K3 free text or an address beside a person's payment, mail or stock movement (Koen, 15 October 2026)",
        )
    if table == "kernel_tenant_settings" and col == "value":
        return (
            "never",
            "K10 one column, several data: per key; the membership amounts and dates are public, the rest never (Koen, 15 October 2026)",
        )
    if any(k.column.table.name.endswith("_codes") for k in fks):
        return "plain", "K0 a code: the label is the code list's, the value is a code"
    if personal and (NAME_OF_PERSON.search(col)):
        return "tokenised", "K2 the name of a person: the token stands for it"
    if personal and FREE_TEXT.search(col):
        return "never", "K3 free text written about or by a person"
    if schema in PUBLIC_SCHEMAS and not personal:
        return "public", "K4 public content (pages, media)"
    if (
        schema == "activities"
        and table
        in {
            "activities",
            "activity_sub_registrations",
            "activity_dates",
            "activity_products",
            "components",
            "products",
        }
        and PUBLIC_ACTIVITY_COLS.match(col)
    ):
        return "public", "K5 what the public activity page already shows"
    if schema == "chatbot" and "info" in table:
        return "public", "K6 the Raakje content, entered to be answered publicly"
    if FREE_TEXT.search(col):
        return (
            "plain",
            "K7 free text of the organisation, not about a person: intern (Koen, 15 October 2026, Q&A nr. 03)",
        )
    if re.search(
        r"(BOOL|INT|NUM|DATE|TIME|DEC|ENUM)", type_name.upper()
    ) or col.endswith("_code"):
        return "plain", "K8 an amount, a date, a count, a flag or a code"
    if schema == "form" or table.startswith("organization"):
        return (
            "plain",
            "K9 the tenant's own definitions and organisations: internal (Koen, 15 October 2026)",
        )
    return (
        "plain",
        "K9 a label of the organisation no other rule names: intern (Koen, 15 October 2026, Q&A nr. 03)",
    )


rows_by_schema: dict[str, list[tuple]] = {}
tech_by_schema: Counter = Counter()
for t in Base.metadata.sorted_tables:
    if re.search(r"_(codes|labels|history)$", t.name):
        continue
    schema = t.schema or "public"
    for c in t.columns:
        if technical(c):
            tech_by_schema[schema] += 1
            continue
        fk = ", ".join(f"→ {k.column.table.fullname}" for k in c.foreign_keys)
        type_name = str(c.type)
        cls, rule = classify(schema, t.name, c.name, type_name, c.foreign_keys)
        label = LABELS.get(c.name, "")
        if rule.startswith("K0"):
            label = "(label of the code list)"
        if t.name == "contact_details" and c.name == "value":
            label, rule = (
                "(label of the contact type: Mobiel, Telefoon, E-mail)",
                "K10 one column, several data: the label comes from the code",
            )
        rows_by_schema.setdefault(schema, []).append(
            (
                t.name,
                c.name,
                type_name,
                "" if c.nullable else "required",
                fk,
                label,
                cls,
                rule,
            )
        )

total = sum(len(v) for v in rows_by_schema.values())
print("# CR-33 appendix — the inventory of the data model, per module\n")
print(
    "Generated from the ORM metadata by `scripts/attribute-inventory.py`; re-generated on master at the handover of phase 1 of CR-33 (15 October 2026), "
    "which carries no webshop schema yet (sales, product, stock and pricing arrive with CR-21; their columns are registered by whichever of the two lands second, Q9). The classification per row follows the rules K0–K10 below; every rule and every exception was decided by Koen on 15 October 2026 (the Q&A log of the change request, Q10 and Q12).\n"
)
print(
    f"Business columns: **{total}**; "
    f"technical columns by the metadata (primary key, foreign key to a table that is no code list, tenant_id, timestamps): {sum(tech_by_schema.values())}, "
    "covered by one rule (never shown, to a model only as the token they already are).\n"
)
print(
    "**Reading:** the label is a proposal where the column name has a fixed word, empty where the build chooses it with the screen that shows the datum. "
    "The classification comes from a RULE (K0–K10), named per row. Levels: public (the public assistant may say it) · plain = **intern** (the back-office assistant only) · tokenised (the back-office assistant sees persoon-90) · never. "
    "Every row is decided (Koen, 15 October 2026).\n"
)
summary = Counter()
for rows in rows_by_schema.values():
    for r in rows:
        summary[r[6]] += 1
print("| Classification (plain = intern) | Rows |\n|---|---|")
for k, v in summary.most_common():
    print(f"| {k} | {v} |")
print("\n| Rule | Rows |\n|---|---|")
rules = Counter(r[7] for rows in rows_by_schema.values() for r in rows)
for k, v in sorted(rules.items()):
    print(f"| {k} | {v} |")
print()
for schema in sorted(rows_by_schema, key=lambda s: -len(rows_by_schema[s])):
    rows = rows_by_schema[schema]
    mark = " — **CR-21, in build, not on master**" if schema in BUILD else ""
    print(
        f"\n## {schema}{mark} — {len(rows)} business columns, {tech_by_schema[schema]} technical\n"
    )
    print("| Table | Column | Type | | FK | Label (proposal) | Classification | Rule |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
