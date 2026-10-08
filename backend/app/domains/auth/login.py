"""De aanmeldstap: magic link en OTP (#635 I).

`start_login` en `check_otp` stonden in `auth/router.py` — geen routes, gewone
functies, maar wél in het bestand dat de JSON-API definieert. Het aanmeldscherm
importeerde ze daar rechtstreeks, en dat is wat #635 punt 3 beschrijft: de router
als servicelaag. Ze dragen de regels die tellen — een onbekend adres krijgt géén
signaal, een adres bij meerdere gezinnen krijgt uitleg in plaats van een link, en
de pogingteller met lockout (#268) — dus ze horen in de service.

**One code mechanism, three purposes** (CR-22 §B1 D2, #1707). Every code the
portal sends comes from the one token here: to sign in, to make an account, to
confirm a new address. The fifteen minutes, the hashed code, the five attempts
and the one live token per address (#268, #395) hold for all three; the token
says what entering it does (`LoginToken.purpose`), and `_consume` does it in
the transaction that spends the token. This module is the only writer of
`auth.login_tokens`.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.auth.member_identity import ACCOUNT, HOUSEHOLD, MULTIPLE, sign_in_identity
from app.domains.auth.models import LoginPurpose, LoginToken, User
from app.domains.mail.api import send_magic_link, send_member_contact_board_notice
from app.i18n import _
from app.kernel.contracts.auth import (
    ACCOUNT_CONFIRMATION,
    ADDRESS_CONFIRMATION,
    AMBIGUOUS_ADDRESS,
    EXISTING_ACCOUNT,
    AccountCodeEntered,
    AddressCodeEntered,
    CodeMailRequested,
)
from app.kernel.events import has_subscribers, publish
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

MAGIC_LINK_EXPIRE_MINUTES = 15
# Brute-force-rem op de 6-cijferige OTP (#268): na zoveel foute codes op één token
# wordt het token geïnvalideerd en moet er een nieuwe code aangevraagd worden.
MAX_OTP_ATTEMPTS = 5


def _generate_otp() -> str:
    """6-cijferige numerieke code (met voorloopnullen)."""
    return str(secrets.randbelow(1_000_000)).zfill(6)


def _hash_otp(code: str) -> str:
    """OTP nooit leesbaar opslaan (#395): SHA-256 met SECRET_KEY als pepper.

    Een gelekte DB-dump geeft zo geen bruikbare codes; zonder pepper zou de
    10^6-ruimte offline triviaal te bruteforcen zijn.
    """
    return hashlib.sha256(f"{settings.secret_key}:{code}".encode()).hexdigest()


logger = logging.getLogger(__name__)


def _tenant() -> int:
    """The active tenant — outside a request the default one, as a row with
    `TenantMixin` gets it (`kernel.tenancy`)."""
    return current_tenant_id.get() or DEFAULT_TENANT_ID


class Consumed(NamedTuple):
    """What entering a code, or following the link, did (CR-22, #1707).

    `refusal` is None when it did its work. It carries the reason when the
    code was right and its purpose could not be carried out — the address of a
    new account got an owner since the form was sent. The token is spent
    either way; the caller shows the reason and signs nobody in.

    `replaced` (#1711): the address a confirmed one took the place of, "" when
    none — a session that was signed in with it has to move to the new one.
    """

    email: str
    purpose: LoginPurpose
    refusal: Optional[str] = None
    replaced: str = ""


@dataclass(frozen=True)
class AccountRequest:
    """What the form "Account aanmaken" asks: four fields, all required (CR-22 R3)."""

    first_name: str
    last_name: str
    email: str
    mobile: str

    def problems(self) -> dict[str, str]:
        """Field → what is wrong with it, in the form's words; empty when the
        request can be sent. The screen shows each under its own field; the
        service refuses a request that has any."""
        found: dict[str, str] = {}
        if not self.first_name.strip():
            found["first_name"] = _("Vul je voornaam in.")
        if not self.last_name.strip():
            found["last_name"] = _("Vul je achternaam in.")
        address = self.email.strip()
        if not address or "@" not in address:
            found["email"] = _("Vul een geldig e-mailadres in.")
        if not self.mobile.strip():
            found["mobile"] = _("Vul je mobiel nummer in.")
        return found


class AccountRequestInvalid(ValueError):
    """`start_account` was handed a request with a missing field. The screen
    checks `AccountRequest.problems()` first and never gets here."""

    def __init__(self, problems: dict[str, str]):
        super().__init__("; ".join(problems.values()))
        self.problems = problems


def _issue(
    db: Session, email: str, *, purpose: LoginPurpose, payload: Optional[dict] = None
) -> tuple[str, str]:
    """A new token for this address: `(token, code)`. Not committed.

    Eén levende OTP per e-mail (#268): invalideer bestaande ongebruikte,
    niet-verlopen tokens vóór we een nieuwe maken, zodat er hoogstens één
    geldige code tegelijk leeft (verkleint de gok-kans) — whatever their
    purpose: a second request replaces the first.
    """
    token = secrets.token_urlsafe(64)
    otp_code = _generate_otp()
    now = datetime.now(timezone.utc)
    # Through the objects and not a bulk UPDATE (CR-13 phase 4): every write goes
    # through the ORM, so the flush sees it. One or two rows at most.
    for living in db.query(LoginToken).filter(
        func.lower(LoginToken.email) == email.lower(),
        LoginToken.used == False,
        LoginToken.expires_at > now,
    ):
        living.used = True
    db.add(
        LoginToken(
            email=email,
            token=token,
            otp_code=_hash_otp(otp_code),
            expires_at=now + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES),
            purpose=purpose,
            payload=payload,
        )
    )
    return token, otp_code


def _link(db: Session, token: str, return_to: str) -> str:
    """The link of the mail. `/login/verify` consumes every purpose (Q36)."""
    from app.kernel.tenant_config import tenant_base_url

    link = f"{tenant_base_url(db)}/login/verify?token={token}"
    if return_to:
        from urllib.parse import quote

        link += f"&terug={quote(return_to, safe='/')}"
    return link


def start_login(db: Session, email: str, return_to: str = "") -> None:
    """De volledige request-login-stap (ook gebruikt door het aanmeldscherm,
    fase 1 #399): gekend adres → magic-link + OTP; meerdere gezinnen → uitleg-
    mail; onbekend → stil. De aanroeper toont ALTIJD dezelfde generieke respons.

    `return_to` (#1437): the page that asked for the sign-in. It rides along in
    the mail link as `terug`, and `/login/verify` checks it again with
    `veilige_terug` when the link is used — a link can be edited, so the check
    belongs where it is used, not here."""
    # Twee onafhankelijke checks: heeft dit adres een account, en/of hangt het
    # aan een persoon (en is dat gezin eenduidig)?
    user = (
        db.query(User)
        .filter(func.lower(User.email) == email.lower(), User.is_active == True)
        .first()
    )
    # CR-22 F2 (#1707): an account — a person without a household — gets a code
    # too. Unknown stays silent; an address that does not say who signs in gets
    # the board notice, as before.
    identity, _person = sign_in_identity(db, email)

    if user is not None or identity in (HOUSEHOLD, ACCOUNT):
        token, otp_code = _issue(db, email, purpose=LoginPurpose.SIGN_IN)
        db.commit()
        magic_link = _link(db, token, return_to)
        if settings.debug:
            logger.warning("[DEBUG] Inloglink voor %s: %s", email, magic_link)
        send_magic_link(to_email=email, magic_link=magic_link, otp_code=otp_code)
    elif identity == MULTIPLE:
        # E-mailadres hangt aan meerdere gezinnen en is geen account: geen link,
        # wel uitleg per mail (we mogen niet gokken welk gezin bedoeld is).
        send_member_contact_board_notice(to_email=email)


def start_account(db: Session, request: AccountRequest, return_to: str = "") -> None:
    """The step behind "Account aanmaken" (CR-22 R3, R4, F4; #1707).

    **The caller answers the same in every case** — "We stuurden een code naar
    dit adres." — and nothing here tells it which case it was: a screen never
    says whether an address is known (Q17). Only the mail differs:

    - the address is free → a code that MAKES the account, and "Bevestig je
      account". No person exists until that code is entered; the four fields
      wait in the token;
    - the address signs in as someone → a plain sign-in code, and "Je hebt al
      een account" — to the owner, the only one who may learn it;
    - the address does not say who signs in → the board notice, as a sign-in
      does.
    """
    problems = request.problems()
    if problems:
        raise AccountRequestInvalid(problems)
    email = request.email.strip()
    identity, _person = sign_in_identity(db, email)
    # The mails leave through an event (CR-13 §B4.9: events, not calls): `mail`
    # queues them in THIS transaction, so a mail exists only with its token.
    if identity in (HOUSEHOLD, ACCOUNT):
        token, otp_code = _issue(db, email, purpose=LoginPurpose.SIGN_IN)
        _request_mail(db, email, EXISTING_ACCOUNT, _link(db, token, return_to), otp_code)
        db.commit()
        return
    if identity == MULTIPLE:
        _request_mail(db, email, AMBIGUOUS_ADDRESS)
        db.commit()
        return
    token, otp_code = _issue(
        db,
        email,
        purpose=LoginPurpose.CREATE_ACCOUNT,
        payload={
            "first_name": request.first_name.strip(),
            "last_name": request.last_name.strip(),
            "mobile": request.mobile.strip(),
            # The token has no tenant of its own (CR-22 C1) and an account is
            # per tenant (R10): the code makes the account where it was asked.
            "tenant_id": _tenant(),
        },
    )
    # No debug line with the link here, unlike the sign-in above: the link IS
    # the secret that makes the account, and a development environment reads
    # the mail from the e-mail log.
    _request_mail(db, email, ACCOUNT_CONFIRMATION, _link(db, token, return_to), otp_code)
    db.commit()


def issue_address_code(
    db: Session,
    *,
    contact_id: int,
    email: str,
    replaces_id: Optional[int] = None,
    replaces_email: str = "",
    make_primary: bool = False,
) -> None:
    """A code that confirms a waiting e-mail address, and its mail (CR-22 R15,
    F6; #1711). Not committed: it runs in the transaction that stored the row.

    The token carries which row it confirms, which one that row replaces and
    whether it was asked for as the primary address. A second code for the
    same row — "Code opnieuw sturen", or a waiting address typed over —
    comes without those: then what the row's earlier code said is kept, so
    asking again never turns a replacement into an extra address.
    """
    if replaces_id is None and not make_primary:
        earlier = (
            db.query(LoginToken)
            .filter(
                LoginToken.purpose == LoginPurpose.CONFIRM_ADDRESS,
                LoginToken.payload["contact_id"].as_integer() == contact_id,
            )
            .order_by(LoginToken.id.desc())
            .first()
        )
        if earlier is not None:
            replaces_id = (earlier.payload or {}).get("replaces_id")
            replaces_email = (earlier.payload or {}).get("replaces_email") or ""
            make_primary = bool((earlier.payload or {}).get("make_primary"))
    token, otp_code = _issue(
        db,
        email,
        purpose=LoginPurpose.CONFIRM_ADDRESS,
        payload={
            "contact_id": contact_id,
            "replaces_id": replaces_id,
            "replaces_email": replaces_email,
            "make_primary": make_primary,
            # As for an account: the token has no tenant of its own (C1).
            "tenant_id": _tenant(),
        },
    )
    _request_mail(db, email, ADDRESS_CONFIRMATION, _link(db, token, ""), otp_code)


def _request_mail(db: Session, email: str, kind: str, link: str = "", otp_code: str = "") -> None:
    """Ask `mail` for one of the account mails. Publishing into silence would
    answer "we sent a code" and send nothing, so somebody must be listening."""
    if not has_subscribers(CodeMailRequested):
        raise RuntimeError(
            "CodeMailRequested has no subscriber: is app.domains.mail.handlers loaded?"
        )
    publish(CodeMailRequested(to_email=email, kind=kind, link=link, otp_code=otp_code), db)


def _consume(db: Session, login_token: LoginToken) -> Consumed:
    """Spend a token whose code or link was right, and do what it is for — in
    one transaction (CR-22 §B3: consuming the token and writing the person
    commit together).

    A refusal — the address got an owner meanwhile — spends the token and
    makes nobody. Logged: the purpose and the outcome, never the code (C5).
    """
    email = login_token.email or ""
    purpose = LoginPurpose(login_token.purpose)
    refusal: Optional[str] = None
    replaced = ""
    if purpose is LoginPurpose.CREATE_ACCOUNT:
        refusal = _make_account(db, login_token)
    elif purpose is LoginPurpose.CONFIRM_ADDRESS:
        refusal = _confirm_address(db, login_token)
        if refusal is None:
            replaced = str((login_token.payload or {}).get("replaces_email") or "")
    elif purpose is not LoginPurpose.SIGN_IN:
        # A purpose this build does not know: never a sign-in by accident.
        refusal = _("Deze code kan hier niet gebruikt worden.")
    login_token.used = True
    db.commit()
    logger.info(
        "code consumed: purpose=%s outcome=%s", purpose.value, "refused" if refusal else "ok"
    )
    return Consumed(email=email, purpose=purpose, refusal=refusal, replaced=replaced)


def _confirm_address(db: Session, login_token: LoginToken) -> Optional[str]:
    """Carry out CONFIRM_ADDRESS; the refusal's words, or None when the
    address counts (CR-22 R15, #1711).

    Events, not calls: master data owns the row and confirms it when told the
    code was entered. Its refusal — the row is gone, or the address got an
    owner while it waited — reaches us as the exception.
    """
    from app.domains.mdm.api import MasterDataError

    payload = login_token.payload or {}
    if payload.get("tenant_id") != _tenant():
        return _("Deze code hoort bij een andere site.")
    if not has_subscribers(AddressCodeEntered):
        raise RuntimeError(
            "AddressCodeEntered has no subscriber: is app.domains.mdm.handlers loaded?"
        )
    try:
        # No savepoint, as for an account: master data refuses BEFORE it
        # writes anything (`confirm_email` checks first).
        publish(
            AddressCodeEntered(
                contact_id=int(payload.get("contact_id") or 0),
                email=login_token.email or "",
                replaces_id=payload.get("replaces_id"),
                make_primary=bool(payload.get("make_primary")),
            ),
            db,
        )
    except MasterDataError as refused:
        return str(refused)
    return None


def _make_account(db: Session, login_token: LoginToken) -> Optional[str]:
    """Carry out CREATE_ACCOUNT; the refusal's words, or None when it is made.

    Events, not calls (CR-13 §B4.9): master data owns persons and makes this
    one when told the code was entered. Its refusal — `EmailAddressInUse`,
    re-checked at this moment (C5) — reaches us as the exception.
    """
    from app.domains.mdm.api import MasterDataError

    payload = login_token.payload or {}
    if payload.get("tenant_id") != _tenant():
        # Asked at one tenant, entered at another: accounts are per tenant.
        return _("Deze code hoort bij een andere site.")
    if not has_subscribers(AccountCodeEntered):
        raise RuntimeError(
            "AccountCodeEntered has no subscriber: is app.domains.mdm.handlers loaded?"
        )
    try:
        # No savepoint: master data refuses BEFORE it writes anything
        # (`create_account_person` checks first), so a refusal leaves nothing
        # of the person behind to undo.
        publish(
            AccountCodeEntered(
                first_name=str(payload.get("first_name") or ""),
                last_name=str(payload.get("last_name") or ""),
                email=login_token.email or "",
                mobile=str(payload.get("mobile") or ""),
            ),
            db,
        )
    except MasterDataError as refused:
        return str(refused)
    return None


def _living_token(db: Session, email: str) -> Optional[LoginToken]:
    """Het levende token voor dit e-mailadres (ongebruikt), ONAFHANKELIJK van de
    ingevoerde code — zo kunnen we ook een foute poging tellen (#268). Door 'één
    levende OTP per e-mail' is dit het enige relevante token."""
    return (
        db.query(LoginToken)
        .filter(
            func.lower(LoginToken.email) == email.strip().lower(),
            LoginToken.used == False,
        )
        .order_by(LoginToken.id.desc())
        .first()
    )


def consume_code(db: Session, email: str, code: str) -> Optional[Consumed]:
    """Enter a code: what it did, or None for a wrong or expired one — generic,
    no detail that would help a guess (#268). Inclusief pogingteller en lockout,
    for every purpose alike."""
    now = datetime.now(timezone.utc)
    login_token = _living_token(db, email)
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        return None

    if login_token.otp_code != _hash_otp(code):
        # Foute code: tel de poging en maak het token dood na MAX_OTP_ATTEMPTS,
        # zodat de 10^6-ruimte niet uitputbaar is zodra de IP-limiet omzeild wordt.
        login_token.attempts += 1
        if login_token.attempts >= MAX_OTP_ATTEMPTS:
            login_token.used = True
        db.commit()
        return None
    return _consume(db, login_token)


def consume_link(db: Session, token: str) -> Optional[Consumed]:
    """Follow the link of a mail: what it did, or None.

    Eenmalig gebruik (#268) — het token wordt meteen als verbruikt gemarkeerd,
    zodat een gedeelde of onderschepte link niet twee keer werkt. Verlopen of
    onbekend geeft None; de aanroeper toont dan dezelfde nette pagina, zonder
    onderscheid dat iets zou verklappen. The link does what the code does (Q36):
    the same token, the same `_consume`.
    """
    nu = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token == token, LoginToken.used.is_(False), LoginToken.email.isnot(None))
        .first()
    )
    if login_token is None:
        return None
    if login_token.expires_at.replace(tzinfo=timezone.utc) < nu:
        return None
    return _consume(db, login_token)


def check_otp(db: Session, email: str, code: str) -> bool:
    """De volledige OTP-controle (ook gebruikt door de JSON-API, fase 1 #399).
    True = code klopt, het token is verbruikt en wat het moest doen is gedaan;
    False = generiek ongeldig (geen detail-onderscheid). Whoever needs the
    reason of a refusal asks `consume_code`."""
    consumed = consume_code(db, email, code)
    return consumed is not None and consumed.refusal is None


def consume_magic_link(db: Session, token: str) -> Optional[str]:
    """Verzilver een magic link: geeft het e-mailadres terug, of None — also
    when the link was right and its purpose was refused. Whoever needs the
    reason asks `consume_link`."""
    consumed = consume_link(db, token)
    if consumed is None or consumed.refusal is not None:
        return None
    return consumed.email
