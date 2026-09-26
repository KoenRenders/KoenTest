"""master data and roles become code lists

CR-12 phase 2. Eight lists: five that master data already had in the *old*
shape, one that is new, and two that were already split but not quite in the
pattern. Plus the roles, which move out of `public` into `auth`.

**Why the old shape had to go.** `gender_codes`, `contact_type_codes`,
`relation_type_codes` and `legal_form_codes` keyed on `(code, language)` with a
uniqueness on the code alone. That fits exactly one language — it is the bug of
#929, and it is why migration 017 wiped every English label without anybody
noticing. The split is not a preference; it is what a second language needs.

**Two lists only look like they were already done.** `organization_relation_types`
and `identification_schemes` have the split of #924, but their code tables carry
neither `sort_order` nor `is_active`, and their names do not follow
`<list>_codes`. Both are fixed here: renamed and completed. A list that needs a
special case in every gate is not in the pattern.

**What the measurement changed, twice** (read on a freshly migrated database,
26 September 2026):

- **Gender `O` does not exist.** The catalogue says migration 001 seeded it and
  004 added `X`; in fact 004 *renamed* `O` to `X`
  (`UPDATE gender_codes SET code = 'X' ... WHERE code = 'O'`). The list is
  `M`, `F`, `U`, `X`, so only `U` is retired. The retirement below is written to
  tolerate either state, because an environment with older history may differ.
- **`role_codes` holds no relation types.** The catalogue says migrations 004
  and 017 wrongly seeded `HOOFDLID`/`PARTNER`/`KIND` into it; migration 017
  line 70 already *deletes* them. Nothing to drop. The delete below stays as a
  guard and logs what it found, which on a clean chain is zero.

Roles move to `auth` because **master data describes the world and security
vocabulary does not** (§B4.1). That makes `auth` the second foundation domain,
and `workflow.workflow_tasks.required_role` the second allowed cross-schema
foreign key.

`auth.user_roles.role_code` gets a foreign key it never had. The model said
"deliberately no FK, validity is enforced in the service layer" — true for the
old placement in `public`, and one layer too high for something an authorisation
check rests on.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.auth.codes import ROLE_CODES
from app.domains.mdm.codes import (
    CONTACT_TYPE_CODES,
    GENDER_CODES,
    IDENTIFICATION_SCHEME_CODES,
    LEGAL_FORM_CODES,
    ORGANIZATION_RELATION_TYPE_CODES,
    ORGANIZATION_TYPE_CODES,
    RELATION_TYPE_CODES,
    SOCIAL_NETWORKS,
)
from app.kernel.codes import add_code_fk, create_code_list


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '154_2026_09_26_014501'
down_revision = '153_2026_09_26_001941'
branch_labels = None
depends_on = None

#: De vier lijsten die de oude vorm hadden: (lijstnaam, codelengte, zaad).
TE_SPLITSEN = [
    ("gender", 10, GENDER_CODES),
    ("contact_type", 10, CONTACT_TYPE_CODES),
    ("relation_type", 10, RELATION_TYPE_CODES),
    ("legal_form", 30, LEGAL_FORM_CODES),
]

#: De persoonsweergave leest vandaag `gender_codes.value` en
#: `relation_type_codes.value` met een `language = 'nl'`-filter. Na de splitsing
#: staan die teksten in de labeltabellen, dus de weergave moet mee — en ze moet
#: mee vóór de kolommen verdwijnen, anders weigert Postgres de wijziging.
#:
#: `CREATE OR REPLACE` en geen `DROP`: de kolomlijst blijft identiek, alleen de
#: joins veranderen. Daarmee blijft `reporting.f_registrations` — dat op deze
#: weergave staat — onaangeroerd, en blijft ook het commentaar staan dat de
#: schemapoort van elke weergave eist. Een DROP zou beide meenemen en zou deze
#: migratie een tweede kopie van twee weergavedefinities geven, precies de
#: duplicatie die `CLAUDE.md` als de fout benoemt.
D_PERSON = """
CREATE OR REPLACE VIEW reporting.d_person AS
SELECT
    p.tenant_id,
    p.id                                        AS person_id,
    COALESCE(p.gender_code, 'X')                AS gender_code,
    COALESCE(gl.value, 'Onbekend')              AS gender_label,
    EXTRACT(YEAR FROM p.date_of_birth)::int     AS birth_year,
    CASE
        WHEN p.date_of_birth IS NULL THEN 'Onbekend'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 6 THEN '0-5'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 13 THEN '6-12'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 18 THEN '13-17'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 26 THEN '18-25'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 41 THEN '26-40'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 61 THEN '41-60'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 76 THEN '61-75'
        ELSE '76 of ouder'
    END                                         AS age_group,
    COALESCE(mp.relation_type, 'ONBEKEND')      AS relation_type_code,
    COALESCE(rl.value, mp.relation_type, 'Onbekend') AS relation_type_label,
    mp.member_id,
    p.first_name,
    p.last_name,
    TRIM(CONCAT_WS(' ', p.first_name, p.last_name)) AS person_name
FROM mdm.persons p
LEFT JOIN mdm.gender_labels gl
       ON gl.code = p.gender_code AND gl.language = 'nl'
LEFT JOIN LATERAL (
    SELECT mp2.member_id, mp2.relation_type
    FROM mdm.member_persons mp2
    WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
    ORDER BY (mp2.relation_type = 'HOOFDLID') DESC, mp2.id
    LIMIT 1
) mp ON TRUE
LEFT JOIN mdm.relation_type_labels rl
       ON rl.code = mp.relation_type AND rl.language = 'nl'
WHERE p.deleted_at IS NULL AND p.superseded_by_id IS NULL
"""


def _heeft_tabel(schema, naam: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(naam, schema=schema)


def _kolommen(schema: str, tabel: str) -> set:
    return {c["name"]
            for c in sa.inspect(op.get_bind()).get_columns(tabel, schema=schema)}


def _maak_labeltabel(naam: str, lengte: int, codes) -> None:
    """De labeltabel naast een bestaande codetabel, gevuld uit de declaratie.

    **De teksten komen uit de declaratie en niet uit de oude tabel**, want dat
    zijn de door Koen goedgekeurde labels van §B5.3. Eén verschil is echt en
    het is de moeite het te noemen: de oude tabel schreef
    `(Meerderjarig) kind` met een hoofdletter, `ui/__init__.py:_RELATIE_LABELS`
    schreef `(meerderjarig) kind` met een kleine. Twee plaatsen, twee
    spellingen; het CR koos die van de keuzelijst (#779), en dat is wat een
    scherm vandaag toont.
    """
    bind = op.get_bind()
    if not _heeft_tabel("mdm", f"{naam}_labels"):
        op.create_table(
            f"{naam}_labels",
            sa.Column("code", sa.String(lengte), primary_key=True),
            sa.Column("language", sa.String(5), primary_key=True),
            sa.Column("value", sa.String(150), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["language"], ["mdm.language_codes.code"],
                                    name=f"fk_{naam}_labels_language"),
            schema="mdm",
        )
    for seed in codes:
        for taal in ("nl", "en"):
            bind.execute(sa.text(
                f"INSERT INTO mdm.{naam}_labels "
                f"(code, language, value, description, created_at, updated_at) "
                f"VALUES (:c, :l, :v, :d, now(), now()) "
                f"ON CONFLICT (code, language) "
                f"DO UPDATE SET value = EXCLUDED.value"),
                {"c": seed.code, "l": taal, "v": seed.label(taal),
                 "d": seed.description(taal)})


def _inkomende_fks(naam: str) -> list[tuple[str, str, str, str]]:
    """(schema, tabel, kolom, constraintnaam) van elke FK naar deze codetabel.

    Opgezocht in plaats van opgesomd: de namen verschillen per migratie die ze
    gelegd heeft (`persons_gender_code_fkey` tegenover
    `fk_member_persons_relation_type`), en een lijst met de hand is precies
    waar er één ontbreekt.
    """
    return [tuple(rij) for rij in op.get_bind().execute(sa.text("""
        SELECT n.nspname, c.relname, a.attname, con.conname
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = con.conrelid
                           AND a.attnum = con.conkey[1]
        WHERE con.contype = 'f'
          AND con.confrelid = to_regclass(:doel)
    """), {"doel": f"mdm.{naam}_codes"}).all()]


def _hervorm_codetabel(naam: str, lengte: int, codes) -> None:
    """De codetabel naar de vorm van §B4.2, ter plekke.

    Ter plekke en niet droppen-en-opnieuw-maken: er hangen foreign keys aan
    (`persons.gender_code`, `contact_details.contact_type_code`,
    `member_persons.relation_type`) en een weergave. Droppen zou die allemaal
    meenemen, en ze daarna opnieuw aanleggen betekent hun definitie hier
    overschrijven — een tweede kopie van iets dat elders al staat.
    """
    bind = op.get_bind()
    tabel = f"mdm.{naam}_codes"
    kolommen = _kolommen("mdm", f"{naam}_codes")
    if "language" in kolommen:
        # Eén rij per code overhouden. De oude vorm had er één per (code, taal);
        # welke rij blijft maakt niet uit, want alles behalve `code` verdwijnt.
        bind.execute(sa.text(
            f"DELETE FROM {tabel} a USING {tabel} b "
            f"WHERE a.code = b.code AND a.language > b.language"))
        for constraint in (f"{naam}_codes_pkey", f"uq_{naam}_codes_code"):
            bind.execute(sa.text(
                f"ALTER TABLE {tabel} DROP CONSTRAINT IF EXISTS {constraint}"))
        for kolom in ("language", "value", "description", "updated_at"):
            if kolom in kolommen:
                op.drop_column(f"{naam}_codes", kolom, schema="mdm")
        bind.execute(sa.text(
            f"ALTER TABLE {tabel} ADD CONSTRAINT {naam}_codes_pkey "
            f"PRIMARY KEY (code)"))
    for kolom, type_, default in (("sort_order", sa.Integer(), "0"),
                                  ("is_active", sa.Boolean(), sa.true())):
        if kolom not in _kolommen("mdm", f"{naam}_codes"):
            op.add_column(f"{naam}_codes",
                          sa.Column(kolom, type_, nullable=False,
                                    server_default=default), schema="mdm")
    for seed in codes:
        bind.execute(sa.text(
            f"INSERT INTO {tabel} (code, sort_order, is_active, created_at) "
            f"VALUES (:c, :s, :a, now()) ON CONFLICT (code) DO UPDATE SET "
            f"sort_order = EXCLUDED.sort_order, is_active = EXCLUDED.is_active"),
            {"c": seed.code, "s": seed.sort_order, "a": seed.is_active})


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. De twee lijsten die de vorm bijna hadden (#924) ───────────────────
    for oud, nieuw in (("organization_relation_types",
                        "organization_relation_type_codes"),
                       ("identification_schemes", "identification_scheme_codes")):
        if _heeft_tabel("mdm", oud):
            op.rename_table(oud, nieuw, schema="mdm")
        for kolom, type_, default in (("sort_order", sa.Integer(), "0"),
                                      ("is_active", sa.Boolean(), sa.true())):
            if kolom not in _kolommen("mdm", nieuw):
                op.add_column(nieuw, sa.Column(kolom, type_, nullable=False,
                                               server_default=default),
                              schema="mdm")

    # De helper vult aan wat ontbreekt: de `en`-labels van de
    # identificatieschema's, die er nooit geweest zijn.
    for naam, codes, lengte in (
            ("organization_relation_type", ORGANIZATION_RELATION_TYPE_CODES, 30),
            ("identification_scheme", IDENTIFICATION_SCHEME_CODES, 20)):
        create_code_list(op, schema="mdm", name=naam, codes=codes,
                         code_length=lengte)
        for seed in codes:
            bind.execute(sa.text(
                f"UPDATE mdm.{naam}_codes SET sort_order = :s WHERE code = :c"),
                {"s": seed.sort_order, "c": seed.code})
        # De taal-FK ontbrak op deze twee: ze zijn van vóór de taallijst. Zonder
        # hem kan er elke spelling van een taalcode in een labelrij staan, en
        # dat is precies wat de taallijst uitsluit.
        naam_fk = f"fk_{naam}_labels_language"
        if naam_fk not in {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(
                f"{naam}_labels", schema="mdm")}:
            op.create_foreign_key(naam_fk, f"{naam}_labels", "language_codes",
                                  ["language"], ["code"],
                                  source_schema="mdm", referent_schema="mdm")

    # ── 2. De labeltabellen, vóór de codetabellen ────────────────────────────
    # In deze volgorde omdat de persoonsweergave hieronder de labeltabellen
    # nodig heeft, en zij op haar beurt vóór de codekolommen moet wijken.
    for naam, lengte, codes in TE_SPLITSEN:
        _maak_labeltabel(naam, lengte, codes)

    # ── 3. De weergave gaat over op de labels ────────────────────────────────
    op.execute(D_PERSON)

    # ── 4. Nu pas de codetabellen zelf ───────────────────────────────────────
    sociaal = {}
    if "is_social_network" in _kolommen("mdm", "contact_type_codes"):
        sociaal = {r.code: r.is_social_network for r in bind.execute(sa.text(
            "SELECT code, is_social_network FROM mdm.contact_type_codes")).all()}

    for naam, lengte, codes in TE_SPLITSEN:
        # De inkomende foreign keys hangen aan de uniciteit die we vervangen,
        # dus ze gaan er eerst af en daarna weer op — met de wacht van
        # `add_code_fk`, die eerst telt of de data past.
        inkomend = _inkomende_fks(naam)
        for schema, tabel, _kolom, constraint in inkomend:
            op.drop_constraint(constraint, tabel, schema=schema,
                               type_="foreignkey")
        _hervorm_codetabel(naam, lengte, codes)
        op.create_foreign_key(f"fk_{naam}_labels_code", f"{naam}_labels",
                              f"{naam}_codes", ["code"], ["code"],
                              source_schema="mdm", referent_schema="mdm")
        for schema, tabel, kolom, _constraint in inkomend:
            add_code_fk(op, f"{schema}.{tabel}.{kolom}", "mdm", naam)

    if "is_social_network" not in _kolommen("mdm", "contact_type_codes"):
        op.add_column("contact_type_codes",
                      sa.Column("is_social_network", sa.Boolean(), nullable=True),
                      schema="mdm")
    # De bewaarde eigenschap terug (#1160), en voor een verse omgeving de
    # waarde uit de declaratie — zodat beide dezelfde uitkomst krijgen.
    for seed in CONTACT_TYPE_CODES:
        waarde = sociaal.get(seed.code, seed.code in SOCIAL_NETWORKS)
        bind.execute(sa.text(
            "UPDATE mdm.contact_type_codes SET is_social_network = :v "
            "WHERE code = :c"), {"v": bool(waarde), "c": seed.code})

    # ── 5. Gender: intrekken wat er niet meer bij hoort ──────────────────────
    # `U` is ingetrokken via zijn CodeSeed. `O` bestaat niet — migratie 004
    # hernoemde hem naar `X`, anders dan §B5.3 note 2 zegt — maar een omgeving
    # met oudere geschiedenis kan hem nog dragen, dus dit is tolerant
    # geschreven in plaats van voorwaardelijk.
    # `U` wordt ingetrokken door zijn eigen `CodeSeed` (`is_active=False`) —
    # één bron, en de declaratie is de plek waar een lezer ernaar zoekt. Wat
    # hier gebeurt is het TELLEN, wat het issue vraagt, plus het ene geval dat
    # geen zaad heeft: `O`. Die bestaat niet meer (migratie 004 hernoemde hem
    # naar `X`), maar een omgeving met oudere geschiedenis kan hem nog dragen.
    for code in ("U", "O"):
        aantal = bind.execute(sa.text(
            "SELECT count(*) FROM mdm.persons WHERE gender_code = :c"),
            {"c": code}).scalar_one()
        bestaat = bind.execute(sa.text(
            "SELECT count(*) FROM mdm.gender_codes WHERE code = :c"),
            {"c": code}).scalar_one()
        print(f"[CR-12 §B5.3 note 2] gender {code!r}: {bestaat} rij in de "
              f"codetabel, {aantal} perso(o)n(en) dragen hem")
    bind.execute(sa.text(
        "UPDATE mdm.gender_codes SET is_active = false WHERE code = 'O'"))

    # ── 6. De organisatiesoort, nieuw ────────────────────────────────────────
    create_code_list(op, schema="mdm", name="organization_type",
                     codes=ORGANIZATION_TYPE_CODES,
                     fk_from=("mdm.organizations.org_type",), code_length=20)
    # Dezelfde reden als bij `ck_payment_records_type` in fase 1: de CHECK zegt
    # wat de FK zegt, en met hem erbij kost een vierde soort een rij én een
    # migratie.
    if "ck_org_type" in {c["name"] for c in sa.inspect(bind).get_check_constraints(
            "organizations", schema="mdm")}:
        op.drop_constraint("ck_org_type", "organizations", schema="mdm",
                           type_="check")

    # ── 7. De rechtsvorm krijgt eindelijk haar FK ────────────────────────────
    add_code_fk(op, "mdm.organizations.legal_form", "mdm", "legal_form")

    # ── 8. De rollen naar auth ───────────────────────────────────────────────
    weg = bind.execute(sa.text(
        "DELETE FROM role_codes WHERE code IN ('HOOFDLID','PARTNER','KIND') "
        "RETURNING code")).all() if _heeft_tabel(None, "role_codes") else []
    print(f"[CR-12 §B5.3 note 4] relatietypes in public.role_codes: "
          f"{len(weg)} verwijderd")

    create_code_list(op, schema="auth", name="role", codes=ROLE_CODES,
                     fk_from=("auth.user_roles.role_code",
                              "workflow.workflow_tasks.required_role"),
                     code_length=20)

    if _heeft_tabel(None, "role_codes"):
        op.drop_table("role_codes")


def downgrade() -> None:
    # Schema, niet data. De labels die deze migratie schrijft zijn de
    # goedgekeurde teksten van §B5.3; teruggaan zet de oude, enkeltalige vorm
    # terug maar niet de oude Engelse labels, want die waren er niet meer —
    # migratie 017 had ze al gewist. Dat is precies de reden dat deze migratie
    # bestaat, dus een "volledige" omkering zou een toestand herstellen die
    # niemand wil.
    raise NotImplementedError(
        "CR-12 fase 2 is niet omkeerbaar zonder de eentalige vorm terug te "
        "zetten die #929 als fout benoemt. Rol terug naar de tag vóór de "
        "release en zet de databank terug uit de back-up.")
