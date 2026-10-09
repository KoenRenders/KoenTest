from sqlalchemy import func
from sqlalchemy.orm import Session

# ── One identity; what someone may is derived per request ────────────────────
#
# The session carries only who someone is (an e-mail address). What they may is
# asked of the data at every request — never kept beside the identity — so a role
# that is withdrawn or a link that lapsed works at once, and two domains stay
# apart: back-office roles live in users/user_roles; being a member is derived
# from ContactDetail (the address hangs on a Person). The one bridge between
# them is the value of the address, no foreign key.


#: The account page of whoever is signed in (CR-22): the landing of everyone
#: who is no board user. The page itself lives in `app/ui/account_ui.py`.
ACCOUNT_HOME = "/mijn"


def landing_for(db: Session, email: str) -> str:
    """Where someone lands after signing in on the site when no page asked for
    them: their account page, "Mijn <tenant>" — for everyone, whatever their
    role (#1740; Koen, 8 October 2026: "waar men aanlogt komt men terecht").

    A page that asked comes first — the caller passes this as the fallback of
    `veilige_terug` — so the renewal link in a mail opens the renewal, and an
    admin screen that sent its visitor to sign in gets him back: that is how
    the back office is the door.

    The account page is a person's page. A session that signs in as no person
    here — a board account without a person, an address that does not say who
    signs in — has none (that route answers 404), so it lands on the site.
    """
    from app.domains.auth.member_identity import login_person_for_email

    return ACCOUNT_HOME if login_person_for_email(db, email) is not None else "/"


def get_user_roles(db: Session, email: str) -> set:
    """Backoffice-rollen voor dit e-mailadres in de ACTIEVE werkruimte (#963):
    de platformbrede rijen (tenant_id NULL, vandaag alleen OPERATOR) plus de
    rijen van de werkruimte waar dit request in draait. Leeg als er geen
    actief account is — en dus ook wanneer iemand enkel rollen in een
    ándere werkruimte heeft: ADMIN in A is geen ADMIN in B."""
    from sqlalchemy import or_

    from app.domains.auth.models import User, UserRole
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    actief = current_tenant_id.get() or DEFAULT_TENANT_ID
    rows = (
        db.query(UserRole.role_code)
        .join(User, User.id == UserRole.user_id)
        .filter(func.lower(User.email) == email.strip().lower(), User.is_active == True)
        .filter(or_(UserRole.tenant_id.is_(None), UserRole.tenant_id == actief))
        .all()
    )
    # CR-12 phase 2: since this phase the COLUMN carries a `Role` member; this
    # function returns the codes. That is a deliberate boundary, not an
    # oversight.
    #
    # This is the authorisation surface: thirty-nine places ask it "which roles
    # do I have here", and compare the answer with sets such as
    # `{"ADMIN", "OPERATOR"} & rollen`. Converting those in the same change is
    # exactly the half migration this CR itself warns against, in the one
    # place where a half migration is a permission leak. What the code list
    # gains here is that the value is guaranteed to be in the list — the
    # database now refuses a role that does not exist, which it could not do
    # before this phase.
    return {r[0].value for r in rows}


def rights_of(db: Session, email: str) -> set:
    """The rights this address holds in the ACTIVE workspace (CR-24 §B1, #1722):
    every right one of its roles here bundles. The workspace rule is that of
    `get_user_roles` (#963) — the platform-wide rows plus those of this
    workspace — so a right in workspace A is no right in B.

    One query, and the whole set: a caller that asks several rights in one
    request — a menu — asks once and keeps the answer. Nothing is cached, so a
    role that is given or withdrawn counts at the next request.

    Empty for an address without an active account and for a role whose bundle
    holds nothing.
    """
    from sqlalchemy import String, cast

    from app.domains.auth.models import Right, RoleRight

    # One row, the codes gathered: the menu asks this on every page, and a row
    # per right was some thirty rows beside whatever the page itself reads.
    gathered = func.array_agg(func.distinct(cast(RoleRight.right_code, String)))
    return {Right(code) for code in _held(db, email).with_entities(gathered).scalar() or ()}


def _held(db: Session, email: str):
    """The rows of the bundles this address holds here — the one definition of
    "holds", for the set (`rights_of`) and for the question (`may`)."""
    from sqlalchemy import or_

    from app.domains.auth.models import RoleRight, User, UserRole
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    active = current_tenant_id.get() or DEFAULT_TENANT_ID
    return (
        db.query(RoleRight.right_code)
        .join(UserRole, UserRole.role_code == RoleRight.role_code)
        .join(User, User.id == UserRole.user_id)
        .filter(func.lower(User.email) == email.strip().lower(), User.is_active == True)
        .filter(or_(UserRole.tenant_id.is_(None), UserRole.tenant_id == active))
    )


def may(db: Session, email: str, right) -> bool:
    """Does this address hold the right here? The one condition `require_right`
    admits on, and the question of a place that shows a way in or an action
    only to who may use it (CR-24 §C2).

    It asks for this one right and reads one row: a gate runs on every request
    and a screen asks a few times more, so neither fetches a whole bundle. True
    only when a row says so — no account, no role here, an empty bundle and a
    right no bundle holds are all "no" (C4.2).
    """
    from app.domains.auth.models import RoleRight

    return _held(db, email).filter(RoleRight.right_code == right).first() is not None


def get_user_role_rows(db: Session, email: str) -> list:
    """Alle (role_code, tenant_id)-paren van dit account, over de werkruimtes
    heen (#963) — voor Mijn profiel en het accountmenu. tenant_id None is de
    platformbrede rij. Autorisatie blijft bij get_user_roles: dat is de enige
    functie die 'wat mag ik HIER' beantwoordt."""
    from app.domains.auth.models import User, UserRole

    rows = (
        db.query(UserRole.role_code, UserRole.tenant_id)
        .join(User, User.id == UserRole.user_id)
        .filter(func.lower(User.email) == email.strip().lower(), User.is_active == True)
        .all()
    )
    # Codes, for the same reason as in `get_user_roles` above.
    return [(r[0].value, r[1]) for r in rows]


def has_login(db: Session, email: str) -> bool:
    """Whether a login exists for this address."""
    from app.domains.auth.models import User

    return db.query(User).filter(User.email == email).first() is not None


def give_board_member_a_login(db: Session, email: str) -> None:
    """A login with the role ADMIN for a board member the member report names —
    only a new one; a login that exists is never overwritten. Flushed, not
    committed. A login is tied to a person by its address alone (no person id on
    a user): that is the separation auth keeps on purpose (#226)."""
    from app.domains.auth.models import User, UserRole
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    if has_login(db, email):
        return
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(
        UserRole(
            user_id=user.id,
            role_code="ADMIN",
            tenant_id=current_tenant_id.get() or DEFAULT_TENANT_ID,
        )
    )
    db.flush()
