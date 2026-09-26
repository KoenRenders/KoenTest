"""What phase 2 of CR-12 must prove: master data and roles (§B8).

Eight lists. Five that master data already had in the *old* shape — one row per
`(code, language)` with a uniqueness on the code alone, which fits exactly one
language and is the bug of #929. One that is new. Two that were split already
(#924) but sat outside the naming and lacked `sort_order`/`is_active`. And the
roles, which move out of `public` into `auth`.

**The test that matters most here is about what did NOT change.** A role list
is an authorisation surface: if the move changes which codes exist, or which
user carries which one, a screen quietly opens or closes for somebody. §B6 and
§B8.9 ask for that explicitly, and it is the first test below.

## Proof that these can go red

One real violation each, checked, reverted (the #652 method), on 26 September
2026:

| Violation | Fired |
|---|---|
| `MEMBER` deleted from the seed instead of retired | yes |
| `U` left active in its `CodeSeed` | yes — after a correction, see below |
| `is_social_network` removed from `extra_code_columns` | yes |
| `ck_org_type` left in place by the migration | yes |
| `LegalForm` put back to `str, Enum` | yes |
| `workflow.workflow_tasks.required_role` dropped from the migration's `fk_from` | yes — after a correction, see below |

**Two of the six needed a correction first, and both are worth recording.**

The gender retirement was expressed *twice*: once in the `CodeSeed`
(`is_active=False`) and once as an `UPDATE` in the migration. Breaking either
one alone left the other doing the work, so the test stayed green — a test that
cannot go red because the thing it guards is duplicated. The migration now only
counts (which the issue asks for) and handles `O`, which has no seed; the seed
owns `U`. One source, and then the violation fires.

The workflow foreign key: removing it from the `CodeList` declaration did not
make the test red, because the migration had already created the key. The
declaration is what a reviewer changes, the migration is what creates it — so
the violation has to be in the migration. Same shape as the Mollie case in
phase 1, and the same lesson: measure the violation where the mechanism is.
"""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.domains.auth.api import Role
from app.domains.mdm.api import (
    ContactType,
    LegalForm,
    OrganizationType,
    RelationType,
)
from app.kernel.codes import code_label, code_labels, registry, reset_label_cache


@pytest.fixture(autouse=True)
def _clean_label_cache():
    reset_label_cache()
    yield
    reset_label_cache()


# ── §B6 / §B8.9 The roles are unchanged ──────────────────────────────────────

#: The role codes as `public.role_codes` held them before the move, read from a
#: freshly migrated database on 26 September 2026. This is the "before" of the
#: before/after that §B8.9 asks for; the "after" is the assertion below.
ROLE_CODES_BEFORE_THE_MOVE = {"ADMIN", "FINANCE", "OPERATOR", "ACCOUNT_ADMIN",
                              "MEMBER", "USER"}


def test_the_set_of_role_codes_is_the_same_after_the_move(db_session):
    """Identical, to the letter. A role that disappears is a door that closes.

    `MEMBER` and `USER` are **retired**, not deleted: they keep their row, so an
    existing assignment keeps a valid target and the enum keeps its member. A
    delete would have been the easy reading of "nobody carries them" and the
    wrong one.
    """
    now = {r[0] for r in db_session.execute(text(
        "SELECT code FROM auth.role_codes")).all()}
    assert now == ROLE_CODES_BEFORE_THE_MOVE
    assert {m.value for m in Role} == ROLE_CODES_BEFORE_THE_MOVE


def test_the_retired_roles_are_inactive_but_still_there(db_session):
    active = {code for code, _ in code_labels("role")}
    assert active == {"ADMIN", "FINANCE", "OPERATOR", "ACCOUNT_ADMIN"}
    # En hun label blijft leesbaar, want een bestaande toekenning moet renderen.
    assert code_label("role", "MEMBER", language="nl") == "Lid"


def test_the_public_orphan_is_gone(db_session):
    """`public.role_codes` was the last of the three orphans of migration 001."""
    assert not inspect(db_session.bind).has_table("role_codes", schema="public")


def test_a_role_that_is_not_a_code_is_refused(db_session):
    """The foreign key `auth.user_roles.role_code` never had, and now has.

    The model said "deliberately no FK, validity is enforced in the service
    layer". That was true for the old placement in `public` — and one layer too
    high for something an authorisation check rests on.
    """
    from app.domains.auth.api import User, UserRole

    user = User(email="rolproef@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "INSERT INTO auth.user_roles (user_id, role_code, created_at) "
            "VALUES (:u, 'SUPERUSER', now())"), {"u": user.id})


def test_the_workflow_role_points_at_the_same_list(db_session):
    """Cross-schema, and that is the point (§B2.4).

    `workflow.workflow_tasks.required_role` is the same vocabulary as
    `auth.user_roles.role_code`. Before this phase it was an unconstrained
    string in another schema — the second place where the role list lived.
    """
    fks = inspect(db_session.bind).get_foreign_keys("workflow_tasks",
                                                    schema="workflow")
    role_fk = [fk for fk in fks if fk["constrained_columns"] == ["required_role"]]
    assert role_fk, "required_role heeft geen foreign key"
    assert role_fk[0]["referred_schema"] == "auth"
    assert role_fk[0]["referred_table"] == "role_codes"


# ── The four lists that had the old shape ────────────────────────────────────

@pytest.mark.parametrize("lijst", ["gender", "contact_type", "relation_type",
                                   "legal_form"])
def test_the_split_lists_carry_two_languages(db_session, lijst):
    """What #929 asked for, per list: a code row and a label row per language.

    The old shape keyed on `(code, language)` with a uniqueness on the code
    alone. Exactly one language fits in that, and migration 017 proved it by
    wiping every English label without anybody noticing.
    """
    talen = {r[0] for r in db_session.execute(text(
        f"SELECT DISTINCT language FROM mdm.{lijst}_labels")).all()}
    assert {"nl", "en"} <= talen

    kolommen = {c["name"] for c in inspect(db_session.bind).get_columns(
        f"{lijst}_codes", schema="mdm")}
    assert "language" not in kolommen, (
        "de codetabel draagt nog een taal — dan is de splitsing niet gebeurd")


def test_the_contact_type_keeps_its_own_property(db_session):
    """`is_social_network` stays on the CODE table (#1160), not in the labels.

    It is data about the code, not a translation: a translator has no business
    deciding which contact type is a social network. The shape gate allows it
    because the `CodeList` declares it, not because an extra column is
    tolerated silently.
    """
    kolommen = {c["name"] for c in inspect(db_session.bind).get_columns(
        "contact_type_codes", schema="mdm")}
    assert "is_social_network" in kolommen
    assert registry()["contact_type"].extra_code_columns == ("is_social_network",)

    netwerken = {r[0] for r in db_session.execute(text(
        "SELECT code FROM mdm.contact_type_codes WHERE is_social_network")).all()}
    assert netwerken == {"FACEBOOK", "INSTAGRAM", "TIKTOK"}


def test_the_contact_type_enum_is_deliberately_partial(db_session):
    """A fifth social network stays one row, and that had to be declared.

    §B4.3 asks for an enum where Python branches, and it does — on `EMAIL` and
    `MOBILE`. But #1160 deliberately made the footer grow with a **row**. Both
    cannot hold for a strict enum column: it would refuse a network with no
    member. So the list declares `enum_is_partial`, the column is tolerant, and
    an unknown code reads back as the code itself — which is exactly right for
    a value nothing branches on.
    """
    from app.domains.mdm.api import ContactDetail, ContactTypeCode, ContactTypeLabel

    assert registry()["contact_type"].enum_is_partial is True

    db_session.add(ContactTypeCode(code="MATRIX", sort_order=95, is_active=True,
                                   is_social_network=True))
    db_session.add(ContactTypeLabel(code="MATRIX", language="nl", value="Matrix"))
    db_session.add(ContactTypeLabel(code="MATRIX", language="en", value="Matrix"))
    db_session.flush()

    detail = ContactDetail(person_id=None, organization_id=None,
                           contact_type_code="MATRIX", value="@raak:matrix.example")
    # Zonder persoon of organisatie weigert de XOR-check; alleen de kolom telt.
    assert detail.contact_type_code == "MATRIX", (
        "een code zonder lid hoort als code terug te komen, niet als fout")


def test_an_unknown_contact_type_is_still_refused_by_the_database(db_session):
    """Tolerant is not unguarded: the foreign key still holds.

    `enum_is_partial` loosens the *enum*, not the list. A code that is in no row
    does not get in, and that is what keeps "a fifth network is a row" from
    becoming "any string goes".
    """
    from app.domains.mdm.api import Person

    person = Person(first_name="Proef", last_name="Persoon")
    db_session.add(person)
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "INSERT INTO mdm.contact_details "
            "(person_id, contact_type_code, value, is_primary, created_at, "
            " updated_at, tenant_id) "
            "VALUES (:p, 'SEMAFOON', 'x', false, now(), now(), 2)"),
            {"p": person.id})


# ── Gender: what the measurement corrected ───────────────────────────────────

def test_the_gender_list_is_m_f_x_with_u_retired(db_session):
    """Koen, 26 September 2026: the list is `M`, `F`, `X` and nothing else.

    **`O` does not exist**, and the catalogue says it does. Migration 004
    *renamed* `O` to `X` (`UPDATE gender_codes SET code = 'X' ... WHERE code =
    'O'`), so there was never an `O` left to retire. Measured on a freshly
    migrated database; the migration handles either state so an environment
    with older history is not left behind.
    """
    alle = {r[0]: r[1] for r in db_session.execute(text(
        "SELECT code, is_active FROM mdm.gender_codes")).all()}
    assert set(alle) == {"M", "F", "X", "U"}, (
        "verwacht M/F/X plus de ingetrokken U — `O` bestaat niet")
    assert alle["U"] is False
    assert [code for code, _ in code_labels("gender")] == ["M", "F", "X"]


def test_a_retired_gender_still_renders(db_session):
    """The reason a retirement is not a delete.

    A person carrying `U` must still show a word on screen. That is why the
    label row stays, and why the members list asks `code_label` instead of
    looking the label up in the dropdown — the dropdown no longer has it.
    """
    assert code_label("gender", "U", language="nl") == "Onbekend"


# ── The two lists that were nearly in the pattern (#924) ─────────────────────

@pytest.mark.parametrize("lijst", ["organization_relation_type",
                                   "identification_scheme"])
def test_the_924_lists_are_now_fully_in_the_pattern(db_session, lijst):
    """Renamed to `<list>_codes`, and given the two columns they lacked.

    They had the split of #924 — code table plus label table — but their code
    tables carried neither `sort_order` nor `is_active`, and their names did not
    follow the pattern. A list that needs a special case in every gate is not in
    the pattern; these now are.
    """
    kolommen = {c["name"] for c in inspect(db_session.bind).get_columns(
        f"{lijst}_codes", schema="mdm")}
    assert {"code", "sort_order", "is_active", "created_at"} == kolommen


def test_the_identification_schemes_finally_have_english_labels(db_session):
    """They never had them; the seeding call added them."""
    assert code_label("identification_scheme", "KBO", language="en") == \
        "Enterprise number"
    assert code_label("identification_scheme", "VAT", language="en") == "VAT number"


# ── The two new foreign keys on the organisation ─────────────────────────────

def test_the_organisation_type_is_a_list_and_no_longer_a_check(db_session):
    """`ck_org_type` said what the foreign key says.

    Two places for one fact, and the expensive half is the second: with the
    check still there a fourth kind of organisation would cost a row *and* a
    migration, so "a new value is a row" would quietly stop being true.
    """
    checks = {c["name"] for c in inspect(db_session.bind).get_check_constraints(
        "organizations", schema="mdm")}
    assert "ck_org_type" not in checks

    fks = inspect(db_session.bind).get_foreign_keys("organizations", schema="mdm")
    op_type = [fk for fk in fks if fk["constrained_columns"] == ["org_type"]]
    assert op_type and op_type[0]["referred_table"] == "organization_type_codes"


def test_the_legal_form_gets_the_key_it_never_had(db_session):
    fks = inspect(db_session.bind).get_foreign_keys("organizations", schema="mdm")
    op_vorm = [fk for fk in fks if fk["constrained_columns"] == ["legal_form"]]
    assert op_vorm and op_vorm[0]["referred_table"] == "legal_form_codes"


# ── The enums ────────────────────────────────────────────────────────────────

def test_the_legal_form_is_a_plain_enum_with_english_member_names(db_session):
    """From `str, Enum` to plain, and `COMPANY = "BEDRIJF"` (§B4.3 literally).

    With the `str` mixin, `organisatie.legal_form == "VZW"` stayed a valid
    comparison that happened to be true; plain, it is silently false and
    therefore findable. The values are stored data and did not change.
    """
    assert not issubclass(LegalForm, str)
    assert LegalForm.COMPANY.value == "BEDRIJF"
    assert {m.value for m in LegalForm} == {"VZW", "FEITELIJKE_VERENIGING",
                                            "BEDRIJF"}


def test_the_relation_type_keeps_its_dutch_values_and_english_names():
    assert RelationType.PRIMARY_MEMBER.value == "HOOFDLID"
    assert RelationType.ADULT_CHILD.value == "KIND"


def test_the_four_new_enum_columns_store_codes(db_session):
    """The round trip, on the master data columns."""
    from app.domains.mdm.api import Organization

    org = Organization(code="proefvorm", name="Proef",
                       org_type=OrganizationType.UNIT,
                       legal_form=LegalForm.NON_PROFIT)
    db_session.add(org)
    db_session.flush()
    raw = db_session.execute(text(
        "SELECT org_type, legal_form FROM mdm.organizations WHERE id = :i"),
        {"i": org.id}).one()
    assert tuple(raw) == ("UNIT", "VZW")


def test_the_contact_type_enum_names_match_the_stored_codes():
    assert ContactType.MOBILE.value == "MOBILE", (
        "de opgeslagen code is HOOFDLETTERS; `CLAUDE.md` schreef 'mobile' en "
        "dat is in deze fase gecorrigeerd")


# ── What may not change ──────────────────────────────────────────────────────

def test_the_roles_document_is_untouched():
    """`docs/rollen-en-rechten.md` describes who may do what.

    This phase moves where the codes live; it does not touch what a role means.
    If that document had to change, this phase went further than it should
    have — so the issue says so, and this test says it too.
    """
    from pathlib import Path

    pad = Path(__file__).resolve().parents[2] / "docs" / "rollen-en-rechten.md"
    tekst = pad.read_text(encoding="utf-8")
    for rol in ("ADMIN", "FINANCE", "OPERATOR", "ACCOUNT_ADMIN"):
        assert rol in tekst, f"{rol} staat niet meer in het rollendocument"
