"""Refuses a public form that mails a typed address without the guard against automated submissions · hard · since #2039.

One rule for every public form (#1297, #2033, #2039): a form anyone can send, which mails an
address that was typed into it, carries the guard of `kernel/form_guard.py` — a honeypot and a
signed render time — and its service takes the `Proof`, so a route cannot forget it.

The list of public ways in is not typed here: it is read from the recorded reach of every route
(`app/domains/auth/tests/snapshots/who_gets_in.json`, which a test of its own keeps equal to the
running routes), the POST routes that let *everyone* in. Each of them is either `GUARDED` (and
its handler must read a proof — checked on its source) or `NOT_TYPED`, with the reason it needs no
guard: it mails no typed address, or it works on a token somebody already holds, or it asks a
signed-in session first. A new public POST route is in neither list and fails here until somebody
decides which — the form that mails and is not on the first list is the form this gate is for.

Proven red with an ADDITIVE violation (15 October 2026): `test_a_public_post_nobody_classified_is_named`
is the proof as a test — a route added to the list the gate reads is named; and the real rule
(`test_every_guarded_handler_reads_a_proof`) fails when `Proof.from_request` is taken out of
`aanmelden_submit`.
"""

import inspect
import json
import re
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "app/domains/auth/tests/snapshots/who_gets_in.json"

#: What a guarded handler does with the form it received: builds the proof from it.
PROOF_FROM_FORM = re.compile(r"Proof(\.from_(request|values))?\(")
#: ... and hands it on: a keyword argument `proof=` in the call to the service.
PROOF_HANDED_ON = re.compile(r"\bproof\s*=")

#: Public POST routes that mail an address typed into them, and so carry the guard.
GUARDED = {
    "POST /aanmelden": "the sign-in link and code, to the typed address",
    "POST /account-aanmaken": "'Bevestig je account', to the typed address",
    "POST /activiteiten/{activity_id}/inschrijven/{component_id}": "the registration's confirmation",
    "POST /lid-worden": "the sign-up's confirmation",
    "POST /berichten": "the contact form (the forms module)",
    "POST /formulier/{share_token}": "a public form's confirmation (the forms module)",
    "POST /nieuwsbrief": "the newsletter's confirmation request",
    "POST /webshop/bestellen": "places an order, guarded so a shown form is accepted once (#1987)",
}

#: Public POST routes that need no guard, and why.
NOT_TYPED = {
    "POST /aanmelden/code": "checks a code that was mailed; mails nothing",
    "POST /activiteiten/{activity_id}/inschrijven/{component_id}/totaal": "recomputes a total; mails nothing",
    "POST /api/v1/payment-gateway/webhooks/mollie": "the provider's webhook, re-fetched from the provider",
    "POST /api/v1/payment-gateway/webhooks/stub": "the stand-in provider of dev and the browser tests",
    "POST /betaling/stub/{payment_id}/betaal": "the stand-in provider's page, dev and tests only",
    "POST /formulier/{share_token}/edit/{edit_token}": "works on the edit token its owner holds",
    "POST /fotos/{asset_id}/duim": "a thumbs-up; mails nothing",
    "POST /inschrijving/{token}/vragen": "answers of an existing registration, by its token",
    "POST /mijn/e-mailadres/{contact_id}/code": "asks a signed-in session first; the address is the person's own row",
    "POST /mijn/gegevens": "asks a signed-in session first (the address change then mails a code)",
    "POST /mijn/organisatie": "asks a signed-in session first; mails nothing (CR-26 F7)",
    "POST /mijn/organisatie/{organization_id}/ontkoppelen": "asks a signed-in session first; ends a relation, mails nothing (CR-26 F7)",
    "POST /mijn/aankopen/{order_id}/annuleren": "the buyer's own order; the session and ownership gate it, mails nothing",
    "POST /nieuwsbrief/bevestigen/{token}": "works on the token of a mail somebody holds",
    "POST /nieuwsbrief/opnieuw/{token}": "works on the token of a mail somebody holds",
    "POST /nieuwsbrief/uitschrijven/{token}": "works on the token of a mail somebody holds",
    "POST /nieuwsbrief/uitschrijven/d/{link}": "works on the signed link of a mail somebody holds; mails nothing",
    "POST /raakje/vraag": "the public chat; what it passes on goes to the board, not to a typed address",
    "POST /webshop/mandje": "recomputes the basket; mails nothing",
}


def public_posts() -> set[str]:
    routes = json.loads(SNAPSHOT.read_text())
    routes = routes.get("routes", routes)
    return {
        route
        for route, reach in routes.items()
        if route.startswith("POST ")
        and isinstance(reach, dict)
        and reach.get("platform") == "everyone"
        and reach.get("tenant") == "everyone"
    }


def unclassified(public: set[str]) -> list[str]:
    return sorted(public - set(GUARDED) - set(NOT_TYPED))


def test_the_gate_reads_the_public_routes():
    public = public_posts()
    assert len(public) >= 15, f"only {len(public)} public POST routes read — is the gate looking?"
    assert "POST /lid-worden" in public and "POST /aanmelden" in public


def test_every_public_post_is_classified():
    left = unclassified(public_posts())
    assert not left, (
        "a public POST route nobody classified: if it mails an address typed into it, give it the "
        "guard (`ui.form_guard_fields()` in its form, a `Proof` in its service) and put it in "
        "GUARDED; if not, put it in NOT_TYPED with the reason:\n  " + "\n  ".join(left)
    )


def test_a_public_post_nobody_classified_is_named():
    """The gate can go red: a new public form that mails and is on neither list."""
    assert unclassified(public_posts() | {"POST /nieuw-formulier-dat-mailt"}) == [
        "POST /nieuw-formulier-dat-mailt"
    ]


def test_no_list_names_a_route_that_is_gone():
    stale = sorted((set(GUARDED) | set(NOT_TYPED)) - public_posts())
    assert not stale, f"these routes are no longer public POST routes: {stale}"


def _handlers() -> dict[str, object]:
    """`METHOD path` → the endpoint, walking the routers the way the app includes them (a module
    that is switched off still has its router; the walk of `test_who_gets_in_unchanged_1722`)."""
    from app.main import app

    found: dict[str, object] = {}

    def walk(items, prefix: str = "") -> None:
        for item in items:
            context = getattr(item, "include_context", None)
            if context is not None:
                walk(item.original_router.routes, prefix + (context.prefix or ""))
            elif getattr(item, "endpoint", None) is not None:
                for method in (getattr(item, "methods", None) or set()) - {"HEAD", "OPTIONS"}:
                    found[f"{method} {prefix + item.path}"] = item.endpoint

    walk(app.routes)
    return found


def test_every_guarded_handler_reads_a_proof():
    """The handler of a guarded route builds a `Proof` from the form it received
    (`Proof.from_request(...)`, `Proof.from_values(...)` or `Proof(...)`), and hands it to the service that
    checks it; a route that mails and forgot is red."""
    missing, handlers = [], _handlers()
    assert len(handlers) >= 300, f"the walk found only {len(handlers)} routes"
    for route_key in sorted(GUARDED):
        assert route_key in handlers, f"no route {route_key}"
        source = inspect.getsource(handlers[route_key])
        if not (PROOF_FROM_FORM.search(source) and PROOF_HANDED_ON.search(source)):
            missing.append(route_key)
    assert not missing, (
        "these guarded routes build no proof from their form or do not hand it on:\n  "
        + "\n  ".join(missing)
    )
