"""Events the auth component publishes (CR-22, #1707).

`auth` owns the codes that are sent by mail; `mdm` owns persons and their
addresses. When a code is entered that makes an account, `auth` says so and
`mdm` does it — events, not calls (CR-13 §B4.9): a command of one domain is
not called from another.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class AccountCodeEntered(KernelEvent):
    """The code of a new account was entered (CR-22 R3, F4).

    Published by `auth.login` when a token with the purpose CREATE_ACCOUNT is
    consumed, in that transaction: the account exists only once the code from
    the mail has been entered, so the person is made here and not when the
    form was sent. The four fields are what the form asked.

    `mdm` subscribes and makes the person with its confirmed address. **A
    subscriber that refuses raises, and the refusal reaches the publisher**:
    the address may have been taken between the form and the code, and then
    there is one owner, not two (C5). Publishing into silence would spend the
    code and make nobody, so the publisher checks that somebody listens.
    """

    first_name: str
    last_name: str
    email: str
    mobile: str


#: The kinds of `CodeMailRequested`.
ACCOUNT_CONFIRMATION = "account_confirmation"
EXISTING_ACCOUNT = "existing_account"
AMBIGUOUS_ADDRESS = "ambiguous_address"


@dataclass(frozen=True)
class CodeMailRequested(KernelEvent):
    """A mail about an account must leave (CR-22 R3, R4).

    Published by `auth.login.start_account` in the transaction that issues the
    token. `mail` subscribes, words the message by `kind` and queues it as a
    job in that transaction: it leaves only if the token was stored, and a
    handler never reaches the network (CR-13 §B4.1).

    `kind`: `ACCOUNT_CONFIRMATION` ("Bevestig je account", with the link and
    the code that make it), `EXISTING_ACCOUNT` ("Je hebt al een account", with
    a link and a code to sign in — the only place that says so, to the owner),
    `AMBIGUOUS_ADDRESS` (the address does not say who signs in: the board
    notice, without a link or a code).
    """

    to_email: str
    kind: str
    link: str = ""
    otp_code: str = ""
