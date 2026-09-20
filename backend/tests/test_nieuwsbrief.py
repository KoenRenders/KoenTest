"""The newsletter (CR-05, #984): who receives it, and how it leaves.

The numbered sections follow CR-05 §7, the test set the build has to prove.
The mail transport is replaced by a mailbox that records what would leave; the
queue is driven by calling the job's own function, the way the scheduler does.
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person
from app.domains.membership.api import Membership
from app.domains.newsletter.models import (
    AUDIENCE_BOTH,
    AUDIENCE_MEMBERS,
    AUDIENCE_NON_MEMBERS,
    DELIVERY_FAILED,
    DELIVERY_MEMBER,
    DELIVERY_QUEUED,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    DELIVERY_SUBSCRIBER,
    LETTER_DRAFT,
    LETTER_SENDING,
    LETTER_SENT,
    SOURCE_IMPORT,
    SUBSCRIBER_CONFIRMED,
    SUBSCRIBER_PENDING,
    SUBSCRIBER_UNSUBSCRIBED,
    Delivery,
    Subscriber,
)
from app.domains.newsletter import service as nb

pytestmark = pytest.mark.ui_serverrendered

BASE = "https://raak.example"
YEAR = date.today().year


# ── Helpers ──────────────────────────────────────────────────────────────────

class _Mailbox:
    """What would have left: one entry per mail, in order."""

    def __init__(self):
        self.sent: list[dict] = []
        self.answer = "sent"
        self.quota_after: int | None = None

    def __call__(self, to_email, subject, body_html, *, email_type,
                 reply_to=None, unsubscribe_url=None, body_text=None):
        from app.domains.mail.api import SendingQuotaReached

        if self.quota_after is not None and len(self.sent) >= self.quota_after:
            raise SendingQuotaReached("550 5.4.5 Daily user sending limit exceeded")
        self.sent.append({"to": to_email, "subject": subject, "body": body_html,
                          "type": email_type, "reply_to": reply_to,
                          "unsubscribe_url": unsubscribe_url,
                          "body_text": body_text})
        return self.answer

    @property
    def addresses(self) -> list[str]:
        return [m["to"] for m in self.sent]


@pytest.fixture
def mailbox(monkeypatch):
    box = _Mailbox()
    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", box)
    return box


@pytest.fixture
def confirmations(monkeypatch):
    sent = []
    monkeypatch.setattr("app.domains.mail.api.send_newsletter_confirmation",
                        lambda to, name, url: sent.append((to, name, url)) or "sent")
    return sent


def _household(db, *people, year=YEAR):
    """A household with a membership for ``year`` (None: no membership).

    ``people`` are (first name, e-mail or None, relation) tuples.
    """
    member = Member()
    db.add(member)
    db.flush()
    for first_name, email, relation in people:
        person = Person(first_name=first_name, last_name="Voorbeeld")
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=person.id,
                            relation_type=relation))
        if email:
            db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                                 value=email))
    if year is not None:
        db.add(Membership(member_id=member.id, year=year, is_active=True,
                          valid_from=date(year, 1, 1), valid_to=date(year, 12, 31)))
    db.flush()
    return member


def _subscriber(db, email, status=SUBSCRIBER_CONFIRMED, source="admin"):
    row = Subscriber(email=email, status=status, source=source,
                     unsubscribe_token=f"tok-{email}")
    db.add(row)
    db.flush()
    return row


def _letter(db, audience=AUDIENCE_MEMBERS, subject="Het najaar",
            body="<div>Beste, er komt veel aan.</div>"):
    letter = nb.create_newsletter(db, created_by="secretaris@example.org")
    nb.update_draft(db, letter, subject=subject, body_html=body, audience=audience)
    return letter


def _run_until_done(db, letter, *, rounds=50):
    outcomes = []
    for _ in range(rounds):
        outcome = nb.send_batch(db, letter.id)
        outcomes.append(outcome)
        if outcome in ("done", "paused", "nothing"):
            break
    return outcomes


# ── 1. The member audience ───────────────────────────────────────────────────

def test_leden_zijn_iedereen_met_een_adres_in_een_gezin_met_lidmaatschap(db_session):
    """Every person with an address, children included; last year's members out;
    a shared address once (CR-05 §3.3).

    Broken on purpose to check this test can fail: `email_addresses_of_members`
    reading only the main member → the partner and the child disappear.
    """
    _household(db_session, ("An", "an@example.org", "HOOFDLID"),
               ("Bert", "bert@example.org", "PARTNER"),
               ("Cas", "cas@example.org", "KIND"),
               ("Dirk", None, "KIND"))
    _household(db_session, ("Els", "gezin@example.org", "HOOFDLID"),
               ("Frank", "Gezin@Example.org", "PARTNER"))
    _household(db_session, ("Gert", "vorigjaar@example.org", "HOOFDLID"), year=YEAR - 1)
    _household(db_session, ("Hilde", "nooit@example.org", "HOOFDLID"), year=None)

    assert nb.member_addresses(db_session) == [
        "an@example.org", "bert@example.org", "cas@example.org", "gezin@example.org"]


# ── 2. "Allebei" deduplicates ────────────────────────────────────────────────

def test_allebei_voegt_samen_zonder_dubbels(db_session):
    """An address on both lists appears once, as a member (CR-05 §3.4)."""
    _household(db_session, ("An", "an@example.org", "HOOFDLID"))
    _subscriber(db_session, "an@example.org")
    _subscriber(db_session, "piet@example.org")
    _subscriber(db_session, "wacht@example.org", status=SUBSCRIBER_PENDING)
    _subscriber(db_session, "weg@example.org", status=SUBSCRIBER_UNSUBSCRIBED)

    both = nb.recipients_for(db_session, AUDIENCE_BOTH)

    assert [(r.email, r.kind) for r in both] == [
        ("an@example.org", DELIVERY_MEMBER), ("piet@example.org", DELIVERY_SUBSCRIBER)]
    counts = nb.audience_counts(db_session)
    assert (counts.members, counts.non_members, counts.both, counts.overlap) == (1, 2, 2, 1)


# ── 3. No audience, no send ──────────────────────────────────────────────────

def test_zonder_gekozen_doelgroep_vertrekt_er_niets(db_session, mailbox):
    """A new letter has no audience, and sending refuses (CR-05 §3.2).

    Broken on purpose: a default audience in `create_newsletter` → the first
    assertion fails.
    """
    _household(db_session, ("An", "an@example.org", "HOOFDLID"))
    # Straight from `create_newsletter`: `_letter` sets the audience itself and
    # would hide a default (measured — with a default, this test stayed green).
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    assert letter.audience is None
    nb.update_draft(db_session, letter, subject="Het najaar",
                    body_html="<div>Beste</div>", audience=letter.audience)

    with pytest.raises(nb.NewsletterError):
        nb.start_sending(db_session, letter, sent_by="s@example.org",
                         reply_to_mode="association", base_url=BASE)
    assert letter.status == LETTER_DRAFT
    assert db_session.query(Delivery).count() == 0


def test_een_kopie_neemt_de_doelgroep_niet_mee(db_session):
    """A copy keeps subject and text and asks the audience again (CR-05 §3.12)."""
    letter = _letter(db_session, audience=AUDIENCE_BOTH, subject="Zomer")
    copy = nb.copy_newsletter(db_session, letter, created_by="s@example.org")

    assert (copy.subject, copy.body_html) == (letter.subject, letter.body_html)
    assert copy.audience is None
    assert copy.copied_from_id == letter.id
    assert copy.status == LETTER_DRAFT


# ── 4. Unsubscribe links only for non-members ────────────────────────────────

def test_alleen_een_niet_lid_krijgt_een_uitschrijflink(db_session, mailbox):
    """A subscriber's mail carries its own token and the header; a member's
    carries neither (CR-05 §3.4, §3.7).

    Broken on purpose: `render_mail` adding the unsubscribe line for every kind
    → the member body contains "Uitschrijven" and the test fails.
    """
    _household(db_session, ("An", "an@example.org", "HOOFDLID"))
    piet = _subscriber(db_session, "piet@example.org")
    letter = _letter(db_session, audience=AUDIENCE_BOTH)

    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)
    assert _run_until_done(db_session, letter)[-1] == "done"

    by_address = {m["to"]: m for m in mailbox.sent}
    member, subscriber = by_address["an@example.org"], by_address["piet@example.org"]
    assert member["unsubscribe_url"] is None
    assert "Uitschrijven" not in member["body"]
    assert subscriber["unsubscribe_url"] == f"{BASE}/nieuwsbrief/uitschrijven/{piet.unsubscribe_token}"
    assert subscriber["unsubscribe_url"] in subscriber["body"]


# ── 6. Double opt-in ─────────────────────────────────────────────────────────

def test_dubbele_bevestiging(db_session, mailbox, confirmations):
    """An unconfirmed address receives nothing; the link confirms exactly one row."""
    nb.subscribe_public(db_session, " Nieuw@Example.org ", "Nora",
                        lambda token: f"{BASE}/nieuwsbrief/bevestigen/{token}")
    _subscriber(db_session, "ander@example.org", status=SUBSCRIBER_PENDING)

    nieuw = nb.subscriber_by_email(db_session, "nieuw@example.org")
    assert nieuw.status == SUBSCRIBER_PENDING
    assert [(to, name) for to, name, _url in confirmations] == [("nieuw@example.org", "Nora")]
    assert nb.recipients_for(db_session, AUDIENCE_NON_MEMBERS) == []

    token = confirmations[0][2].rsplit("/", 1)[1]
    assert nb.confirm(db_session, token).id == nieuw.id
    assert nieuw.status == SUBSCRIBER_CONFIRMED
    assert nb.subscriber_by_email(db_session, "ander@example.org").status == SUBSCRIBER_PENDING
    assert nb.confirm(db_session, token) is None, "een token werkt één keer"


def test_het_formulier_verraadt_niet_wie_al_op_de_lijst_staat(db_session, confirmations):
    """A confirmed address changes nothing and gets no mail; a pending one gets
    at most one mail a day."""
    _subscriber(db_session, "al@example.org")
    nb.subscribe_public(db_session, "al@example.org", "", lambda t: t)
    assert confirmations == []

    nb.subscribe_public(db_session, "twee@example.org", "", lambda t: t)
    nb.subscribe_public(db_session, "twee@example.org", "", lambda t: t)
    assert [to for to, _n, _u in confirmations] == ["twee@example.org"]


def test_een_ongeldig_adres_wordt_geweigerd(db_session, confirmations):
    with pytest.raises(nb.NewsletterError):
        nb.subscribe_public(db_session, "geen-adres", "", lambda t: t)
    assert db_session.query(Subscriber).count() == 0


def test_uitschrijven_en_toch_opnieuw(db_session):
    """The link works without a login, is idempotent, and can be undone."""
    piet = _subscriber(db_session, "piet@example.org")
    assert nb.unsubscribe(db_session, piet.unsubscribe_token).status == SUBSCRIBER_UNSUBSCRIBED
    assert nb.unsubscribe(db_session, piet.unsubscribe_token).status == SUBSCRIBER_UNSUBSCRIBED
    assert nb.unsubscribe(db_session, "onbekend") is None

    assert nb.resubscribe(db_session, piet.unsubscribe_token).status == SUBSCRIBER_CONFIRMED


# ── 7. The import ────────────────────────────────────────────────────────────

def test_de_import_toont_eerst_wat_hij_zal_doen(db_session):
    """New, known, unsubscribed and invalid lines, before anything is written
    (CR-05 §3.6). A repeated line counts once; blank lines are ignored.

    Broken on purpose: `run_import` also resubscribing the unsubscribed ones →
    the last assertion fails.
    """
    _subscriber(db_session, "gekend@example.org")
    _subscriber(db_session, "weg@example.org", status=SUBSCRIBER_UNSUBSCRIBED)
    tekst = "\n".join(["nieuw@example.org", "NIEUW@example.org", "", "gekend@example.org",
                       "weg@example.org", "geen adres", "twee@example.org"])

    preview = nb.preview_import(db_session, tekst)
    assert preview.new == ["nieuw@example.org", "twee@example.org"]
    assert preview.known == ["gekend@example.org"]
    assert preview.unsubscribed == ["weg@example.org"]
    assert preview.invalid == ["geen adres"]
    assert db_session.query(Subscriber).count() == 2, "de voorvertoning schrijft niets"

    nb.run_import(db_session, tekst)
    nieuw = nb.subscriber_by_email(db_session, "nieuw@example.org")
    assert (nieuw.status, nieuw.source) == (SUBSCRIBER_CONFIRMED, SOURCE_IMPORT)
    assert nieuw.imported_at is not None
    assert nb.subscriber_by_email(db_session, "weg@example.org").status == SUBSCRIBER_UNSUBSCRIBED


def test_handmatig_toevoegen_herstelt_geen_uitschrijving(db_session):
    _subscriber(db_session, "weg@example.org", status=SUBSCRIBER_UNSUBSCRIBED)
    with pytest.raises(nb.NewsletterError):
        nb.add_by_admin(db_session, "weg@example.org")
    assert nb.add_by_admin(db_session, "Nieuw@example.org", "Nora").status == SUBSCRIBER_CONFIRMED


def test_verwijderen_wist_het_adres_ook_uit_het_archief(db_session, mailbox):
    """The right to erasure: the row goes, the deliveries keep their counts."""
    piet = _subscriber(db_session, "piet@example.org")
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)
    _run_until_done(db_session, letter)

    nb.erase(db_session, piet.id)

    assert nb.subscriber_by_email(db_session, "piet@example.org") is None
    rows = db_session.query(Delivery).filter(Delivery.newsletter_id == letter.id).all()
    assert len(rows) == 1 and "piet" not in rows[0].email
    assert rows[0].status == DELIVERY_SENT


# ── 8. The queue under a daily cap ───────────────────────────────────────────

def _many_subscribers(db, amount):
    for index in range(amount):
        _subscriber(db, f"lid{index:03d}@example.org")


def test_de_wachtrij_blijft_onder_het_dagplafond(db_session, mailbox, monkeypatch):
    """A send larger than the cap pauses, and never goes above it (CR-05 §3.7).

    Broken on purpose: `send_batch` ignoring `room` → more than the cap leaves
    and the test fails.
    """
    monkeypatch.setattr("app.kernel.tenant_config.tenant_newsletter_daily_cap",
                        lambda db, tenant_id=None: 30)
    _many_subscribers(db_session, 45)
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)

    outcomes = _run_until_done(db_session, letter)

    assert outcomes[-1] == "paused"
    assert len(mailbox.sent) == 30
    assert letter.status == LETTER_SENDING
    assert letter.paused_until is not None
    assert nb.send_batch(db_session, letter.id) == "nothing", "gepauzeerd blijft gepauzeerd"


def test_na_de_pauze_gaat_het_verder_zonder_iemand_twee_keer_te_mailen(db_session, mailbox,
                                                                        monkeypatch):
    """The next day continues with the next address; nobody gets two mails."""
    monkeypatch.setattr("app.kernel.tenant_config.tenant_newsletter_daily_cap",
                        lambda db, tenant_id=None: 30)
    _many_subscribers(db_session, 45)
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)
    _run_until_done(db_session, letter)

    # A day later: yesterday's sends fall out of the window.
    gisteren = datetime.now(timezone.utc) - timedelta(hours=25)
    for row in db_session.query(Delivery).filter(Delivery.status == DELIVERY_SENT):
        row.sent_at = gisteren
    letter.paused_until = gisteren
    db_session.commit()

    assert _run_until_done(db_session, letter)[-1] == "done"
    assert len(mailbox.sent) == 45
    assert len(set(mailbox.addresses)) == 45
    assert letter.status == LETTER_SENT


def test_gmails_quotumfout_pauzeert_en_markeert_niets_als_mislukt(db_session, mailbox):
    """Gmail says the day is full: pause, and nothing counts as failed."""
    _many_subscribers(db_session, 10)
    mailbox.quota_after = 4
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)

    assert _run_until_done(db_session, letter)[-1] == "paused"

    statuses = [d.status for d in db_session.query(Delivery).order_by(Delivery.id)]
    assert statuses.count(DELIVERY_SENT) == 4
    assert statuses.count(DELIVERY_QUEUED) == 6
    assert DELIVERY_FAILED not in statuses
    assert letter.paused_until > datetime.now(timezone.utc) + timedelta(hours=23)


def test_de_job_hervat_na_een_herstart(db_session, mailbox):
    """The scheduler's own path: the pending job carries on where it stopped."""
    from app.kernel.jobs import KernelJob, run_due_jobs

    _many_subscribers(db_session, 25)
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)
    assert db_session.query(KernelJob).filter(KernelJob.name == nb.SEND_JOB).count() == 1

    run_due_jobs(db_session, batch=1)
    assert len(mailbox.sent) == nb.BATCH_SIZE
    # "Restart": the follow-up job is pending, a few seconds ahead.
    for job in db_session.query(KernelJob).filter(KernelJob.status == "pending"):
        job.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    run_due_jobs(db_session, batch=5)
    assert len(mailbox.sent) == 25
    assert len(set(mailbox.addresses)) == 25
    assert letter.status == LETTER_SENT


def test_een_mislukte_mail_wordt_mislukt_en_de_rest_gaat_door(db_session, mailbox):
    _many_subscribers(db_session, 3)
    mailbox.answer = "failed"
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)

    assert _run_until_done(db_session, letter)[-1] == "done"
    progress = nb.progress_of(db_session, letter)
    assert (progress.sent, progress.failed, progress.queued) == (0, 3, 0)


# ── 9. Unsubscribing during a send; reply address ────────────────────────────

def test_wie_zich_tijdens_het_versturen_uitschrijft_wordt_overgeslagen(db_session, mailbox):
    """Broken on purpose: `send_batch` not re-reading the subscriber → the
    unsubscribed address still receives the letter."""
    _subscriber(db_session, "a@example.org")
    weg = _subscriber(db_session, "b@example.org")
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)

    nb.unsubscribe(db_session, weg.unsubscribe_token)
    _run_until_done(db_session, letter)

    assert mailbox.addresses == ["a@example.org"]
    skipped = db_session.query(Delivery).filter(Delivery.email == "b@example.org").one()
    assert skipped.status == DELIVERY_SKIPPED


def test_antwoorden_gaan_naar_de_vereniging_of_naar_mezelf(db_session, mailbox):
    """*De vereniging*: no Reply-To, so replies go to the sender address from the
    tenant configuration. *Mezelf*: the admin who sends (CR-05 §3.8)."""
    _subscriber(db_session, "a@example.org")
    vereniging = _letter(db_session, audience=AUDIENCE_NON_MEMBERS, subject="Een")
    nb.start_sending(db_session, vereniging, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)
    _run_until_done(db_session, vereniging)
    mezelf = _letter(db_session, audience=AUDIENCE_NON_MEMBERS, subject="Twee")
    nb.start_sending(db_session, mezelf, sent_by="s@example.org",
                     reply_to_mode="sender", base_url=BASE)
    _run_until_done(db_session, mezelf)

    assert [m["reply_to"] for m in mailbox.sent] == [None, "s@example.org"]


# ── 10. The test mail ────────────────────────────────────────────────────────

def test_de_testmail_gaat_alleen_naar_mezelf(db_session, mailbox):
    _subscriber(db_session, "a@example.org")
    letter = _letter(db_session, audience=AUDIENCE_BOTH)

    nb.send_test(db_session, letter, to_email="s@example.org", base_url=BASE)

    assert mailbox.addresses == ["s@example.org"]
    assert mailbox.sent[0]["subject"].startswith("[TEST]")
    assert "Uitschrijven" in mailbox.sent[0]["body"], "toont de niet-ledenversie"
    assert letter.status == LETTER_DRAFT
    assert db_session.query(Delivery).count() == 0


# ── 11. A placeholder stops the real send, not the test mail ────────────────

VERGETEN = ("<div>Beste,</div><div>Inschrijven kan via [e-mailadres]. "
            "Tot dan!</div><div>Vragen? Bel [telefoonnummer].</div>")


def test_een_plaatshouder_houdt_het_versturen_tegen_en_noemt_de_zin(db_session, mailbox):
    """Koen, 17 September 2026. Broken on purpose: the `placeholder_refusal`
    check taken out of `start_sending` → the queue fills and this test fails."""
    _subscriber(db_session, "a@example.org")
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS, body=VERGETEN)

    with pytest.raises(nb.NewsletterError) as refused:
        nb.start_sending(db_session, letter, sent_by="s@example.org",
                         reply_to_mode="association", base_url=BASE)

    assert "«Inschrijven kan via [e-mailadres].»" in str(refused.value)
    assert "«Bel [telefoonnummer].»" in str(refused.value)
    assert "Tot dan" not in str(refused.value), "alleen de zinnen met een plaatshouder"
    assert letter.status == LETTER_DRAFT
    assert db_session.query(Delivery).count() == 0


@pytest.mark.parametrize("placeholder", ["[e-mailadres]", "[telefoonnummer]",
                                         "[rekeningnummer]", "[naam]"])
def test_elke_plaatshouder_telt(placeholder):
    """The list comes from the redaction itself; a new placeholder there is
    caught here without a second list to keep in step."""
    assert nb.unfilled_placeholders(f"<div>Met dank aan {placeholder}.</div>")
    assert nb.unfilled_placeholders("<div>Met dank aan iedereen [x].</div>") == []


def test_de_testmail_mag_met_een_plaatshouder(db_session, mailbox):
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS, body=VERGETEN)

    nb.send_test(db_session, letter, to_email="s@example.org", base_url=BASE)

    assert mailbox.addresses == ["s@example.org"]
    assert "[e-mailadres]" in mailbox.sent[0]["body"]


# ── Sent letters stay as they went out ───────────────────────────────────────

def test_een_verstuurde_brief_is_niet_meer_te_wijzigen(db_session, mailbox):
    _subscriber(db_session, "a@example.org")
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS, subject="Zo vertrok hij")
    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)

    with pytest.raises(nb.NewsletterError):
        nb.update_draft(db_session, letter, subject="Anders", body_html="x",
                        audience=AUDIENCE_NON_MEMBERS)
    with pytest.raises(nb.NewsletterError):
        nb.delete_draft(db_session, letter)
    assert letter.subject == "Zo vertrok hij"


def test_de_tekst_wordt_ontsmet(db_session):
    letter = _letter(db_session, body='<div>Hallo<script>alert(1)</script></div>')
    assert "<script" not in letter.body_html
    assert "Hallo" in letter.body_html


def test_de_afsluiting_draagt_geen_persoonsnamen(db_session):
    """CR-05 §3.10: the closing names the association, never people."""
    tekst = nb.closing_html(db_session)
    assert "Het bestuur van" in tekst


# ── The example subscribers ──────────────────────────────────────────────────

def test_voorbeeldabonnees_nooit_op_prod(db_session):
    """CR-05 §3.6: the real list only on PROD, examples everywhere else.

    Broken on purpose: `prod` added to `EXAMPLE_ENVIRONMENTS` → this test fails.
    """
    import seed_newsletter

    assert seed_newsletter.seed(db_session, "prod") == 0
    assert db_session.query(Subscriber).count() == 0

    assert seed_newsletter.seed(db_session, "hdev") == len(seed_newsletter.EXAMPLES)
    assert seed_newsletter.seed(db_session, "hdev") == 0, "niet twee keer"
    assert all(s.email.endswith(("@example.org", ".example.org"))
               for s in db_session.query(Subscriber))


# ── The activity line, as the board wrote it by hand (Koen, 17 September 2026) ─

def _dated_activity(db, name, start, end=None, *, start_time=None, end_time=None,
                    location=None, members_only=False, component=True,
                    external_register=None, external_list=None, capacity=None):
    from app.domains.activities.api import Activity, ActivityDate, ActivitySubRegistration

    activity = Activity(name=name, location=location, members_only=members_only,
                        slug=name.lower().replace(" ", "-"))
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=start, end_date=end,
                        start_time=start_time, end_time=end_time))
    if component:
        db.add(ActivitySubRegistration(activity_id=activity.id, name="Deelname",
                                       external_register_url=external_register,
                                       external_registrations_url=external_list,
                                       max_participants=capacity))
    db.flush()
    return activity


def _line(db, activity, today):
    facts = nb.activity_facts(db, [activity.id], base_url="https://raak.example", today=today)
    return nb.activity_line_html(facts[activity.id])


def test_de_regel_van_een_activiteit_zoals_het_bestuur_ze_schreef(db_session):
    """Naam (enkel leden) | datum uur plaats | inschrijven — the name links to
    the activity. No participant list (Koen, 20 September 2026): that is for the
    board, and in a letter it is a second link to the same page.

    Broken on purpose: `members_only` not passed into the facts → the
    "(enkel leden)" assertion fails.
    """
    from datetime import time

    vandaag = date.today()
    dag = vandaag + timedelta(days=10)
    kroeg = _dated_activity(db_session, "Mannenkroegentocht", dag, start_time=time(20, 0),
                            location="Miloheem", members_only=True)

    regel = _line(db_session, kroeg, vandaag)

    link = 'href="https://raak.example/activiteiten/mannenkroegentocht"'
    assert regel.startswith(f'<a {link}>Mannenkroegentocht</a> (enkel leden) | ')
    assert " 20u Miloheem | " in regel
    assert regel.endswith(f'<a {link}>inschrijven</a>')
    assert "inschrijvingen" not in regel, "de deelnemerslijst hoort niet in een brief"


def test_de_datum_leest_zoals_het_bestuur_ze_schrijft():
    from datetime import time

    def facts(start, end=None, start_time=None, end_time=None):
        return nb.ActivityFacts(id=1, name="x", start=start, end=end or start,
                                start_time=start_time, location="", url="",
                                photos_url=None, is_full=False, prices=(),
                                end_time=end_time)

    assert nb.when_text(facts(date(2026, 6, 12), start_time=time(20, 0))) == "vrijdag 12 juni 20u"
    assert nb.when_text(facts(date(2026, 8, 16), start_time=time(7, 45),
                              end_time=time(19, 45))) == "zondag 16 augustus 7u45-19u45"
    assert nb.when_text(facts(date(2026, 11, 27), date(2026, 11, 28))) == \
        "vrijdag 27 en zaterdag 28 november"
    assert nb.when_text(facts(date(2026, 9, 18), date(2026, 9, 20))) == \
        "vrijdag 18 september - zondag 20 september"
    assert nb.when_text(facts(date(2026, 6, 1), date(2026, 9, 30))) == "juni-september"


def test_extern_inschrijven_en_zonder_inschrijving(db_session):
    vandaag = date.today()
    dag = vandaag + timedelta(days=10)
    brood = _dated_activity(db_session, "Brood en Spelen", dag, component=False)
    comedy = _dated_activity(db_session, "Comedy Festival", dag,
                             external_register="https://tickets.example/comedy")

    assert _line(db_session, brood, vandaag).count(" | ") == 1, "geen inschrijving, geen links"
    comedy_regel = _line(db_session, comedy, vandaag)
    assert '<a href="https://tickets.example/comedy">inschrijven</a>' in comedy_regel
    assert "inschrijvingen" not in comedy_regel, "extern inschrijven zonder externe lijst"


def test_volzet_vervangt_inschrijven():
    facts = nb.ActivityFacts(id=1, name="Bowlen", start=date(2026, 11, 15), end=date(2026, 11, 15),
                             start_time=None, location="", url="https://raak.example/a",
                             photos_url=None, is_full=True, prices=(),
                             register_url="https://raak.example/a",
                             registrations_url="https://raak.example/a")
    regel = nb.activity_line_html(facts)
    assert "<em>volzet</em>" in regel
    assert ">inschrijven<" not in regel
    assert "inschrijvingen" not in regel


def test_de_kalender_is_een_opsomming_met_een_bolletje_per_activiteit(db_session):
    """Koen, 20 September 2026: zeven regels onder elkaar lezen als één blok
    tekst; met een bolletje per activiteit tel je ze in één oogopslag.

    Broken on purpose: de `<li>` terug naar een `<div>` → deze test faalt.
    """
    vandaag = date.today()
    _dated_activity(db_session, "Eerste", vandaag + timedelta(days=3))
    _dated_activity(db_session, "Tweede", vandaag + timedelta(days=6))

    html = nb.calendar_html(db_session, base_url="https://raak.example", today=vandaag)

    assert html.startswith("<ul>") and html.endswith("</ul>")
    assert html.index("Eerste") < html.index("Tweede")
    regels = [r for r in html.replace("<ul>", "").replace("</ul>", "").split("</li>") if r]
    assert all(r.startswith("<li><a ") and " | " in r for r in regels)


# ── The activity block (Koen, 19 September 2026) ─────────────────────────────

def _block(db, activity, today):
    facts = nb.activity_facts(db, [activity.id], base_url="https://raak.example", today=today)
    return nb.activity_block_html(facts[activity.id])


def _poster(db, activity, *, content_type="image/png"):
    from app.domains.media.api import MediaAsset

    asset = MediaAsset(kind="activity_poster", activity_id=activity.id, title="Affiche",
                       content_type=content_type, data=b"x", byte_size=1)
    db.add(asset)
    db.flush()
    return asset


def test_het_blok_draagt_titel_beeld_omschrijving_en_een_inschrijflink(db_session):
    """The shape of the Raak nationaal letter, built by the server so that what
    Raakje inserts and what the button inserts are the same thing.

    Broken on purpose: `description` left off `ActivityFacts` → the sentence
    disappears from the block and this test fails.
    """
    vandaag = date.today()
    activity = _dated_activity(db_session, "Rumproefavond", vandaag + timedelta(days=10),
                               start_time=time(20, 0), location="Miloheem")
    activity.description = "We proeven acht rums uit het Caribisch gebied."
    asset = _poster(db_session, activity)
    db_session.flush()

    blok = _block(db_session, activity, vandaag)

    assert 'class="nb-blok-titel"' in blok and "Rumproefavond" in blok
    assert "https://raak.example/activiteiten/rumproefavond" in blok
    assert "We proeven acht rums uit het Caribisch gebied." in blok
    assert " 20u · Miloheem" in blok
    assert f'src="https://raak.example/api/v1/media/{asset.id}"' in blok
    assert "Schrijf je in!" in blok


def test_een_blok_zonder_beeld_of_omschrijving_houdt_geen_lege_plek_over(db_session):
    vandaag = date.today()
    activity = _dated_activity(db_session, "Wandeling", vandaag + timedelta(days=20))

    blok = _block(db_session, activity, vandaag)

    assert "nb-blok-beeld" not in blok, "geen kolom voor een beeld dat er niet is"
    assert "nb-blok-omschrijving" not in blok
    assert "nb-blok-titel" in blok


def test_een_pdf_affiche_zonder_afbeelding_levert_geen_gebroken_beeld(db_session):
    """`/thumb` van een PDF zonder rendering antwoordt met de PDF zelf — dat zou
    in een mail een gebroken beeld geven. Media beslist dat, niet de brief."""
    vandaag = date.today()
    activity = _dated_activity(db_session, "Quiz", vandaag + timedelta(days=25))
    _poster(db_session, activity, content_type="application/pdf")
    db_session.flush()

    assert "nb-blok-foto" not in _block(db_session, activity, vandaag)


def test_een_voorbije_activiteit_vraagt_geen_inschrijving(db_session):
    vandaag = date.today()
    voorbij = vandaag - timedelta(days=20)
    activity = _dated_activity(db_session, "Zomerbar", voorbij)

    blok = _block(db_session, activity, vandaag)

    assert "Schrijf je in!" not in blok
    assert str(voorbij.day) in blok, "de datum van toen staat er wel"


def test_de_brief_draagt_een_verwijzing_en_de_mail_het_blok(db_session):
    """Measured on 19 September 2026: Trix keeps no table and no class, and
    turns an inserted image into an attachment of its own at full width — Koen
    saw the picture spill out of the letter. So the letter carries the activity
    NUMBER and the server builds the block when it sends.

    Broken on purpose: `expand_blocks` taken out of `render_mail` → the mail
    arrives with the bare reference and this test fails.
    """
    vandaag = date.today()
    activity = _dated_activity(db_session, "Zo vader zo zoon", vandaag + timedelta(days=10),
                               location="Miloheem")
    activity.description = "Een avond over vaderschap."
    db_session.flush()
    facts = nb.activity_facts(db_session, [activity.id], base_url="https://raak.example")
    kaart = nb.activity_card_html(facts[activity.id])
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS, body=kaart)

    assert f"[[activiteit:{activity.id}|" in letter.body_html, "overleeft de ontsmetting"
    assert "<table" not in letter.body_html, "de brief draagt geen blok"

    mail = nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER, unsubscribe_url=None,
                          base_url="https://raak.example")
    assert "Zo vader zo zoon" in mail and "Een avond over vaderschap." in mail
    assert "Schrijf je in!" in mail
    assert "[[activiteit:" not in mail, "de markering zelf gaat niet mee"


def test_een_verwijzing_naar_een_verdwenen_activiteit_laat_niets_achter(db_session):
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS,
                     body="<div>[[activiteit:99999|Weggehaalde activiteit]]</div>")

    mail = nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER, unsubscribe_url=None,
                          base_url="https://raak.example")

    assert "Weggehaalde activiteit" not in mail
    assert "[[activiteit:" not in mail


def test_de_opmaak_komt_er_pas_bij_het_versturen_op(db_session, mailbox):
    """The sanitiser drops `style` on every autosave, so the block travels as
    classes and `render_mail` inlines them.

    Broken on purpose: `with_inline_styles` taken out of `render_mail` → the
    block arrives without styling and this test fails.
    """
    vandaag = date.today()
    activity = _dated_activity(db_session, "Rumproefavond", vandaag + timedelta(days=12))
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS,
                     body=_block(db_session, activity, vandaag))

    bewaard = letter.body_html
    assert "style=" not in bewaard, "de ontsmetting laat geen style toe"

    mail = nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER, unsubscribe_url=None)
    assert 'class="nb-blok-titel" style="font-size:20px' in mail
    assert "@media only screen and (max-width:480px)" in mail, "op een telefoon onder elkaar"


# ── The inbox line and the text part (Koen, 19 September 2026) ───────────────

def test_de_voorbeeldtekst_staat_in_de_mail_en_valt_terug_op_de_eerste_zin(db_session):
    """Raak nationaal zet er "Ontdek onze webinars…"; bij ons las het postvak
    "Beste,".

    Broken on purpose: the fallback in `preview_text_of` removed → the letter
    without a typed line carries nothing and the second half fails.
    """
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS,
                     body="<div>Beste,</div><div>Het najaar zit vol activiteiten.</div>")

    mail = nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER, unsubscribe_url=None)
    assert "Het najaar zit vol activiteiten." in mail
    assert nb.preview_text_of(letter) == "Het najaar zit vol activiteiten."

    nb.update_draft(db_session, letter, subject=letter.subject, body_html=letter.body_html,
                    audience=AUDIENCE_MEMBERS, preview_text="Ontdek ons najaar!")
    assert nb.preview_text_of(letter) == "Ontdek ons najaar!"
    assert "Ontdek ons najaar!" in nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER,
                                                  unsubscribe_url=None)


def test_de_mail_draagt_ook_een_tekstversie(db_session, mailbox):
    """A mail announcing itself as multipart/alternative with only an HTML part
    is a blank page in a reader that strips HTML.

    Broken on purpose: `body_text` not passed in `send_test` → the mail leaves
    without its text part and this test fails.
    """
    vandaag = date.today()
    activity = _dated_activity(db_session, "Rumproefavond", vandaag + timedelta(days=10))
    facts = nb.activity_facts(db_session, [activity.id], base_url=BASE)
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS,
                     body=f"<div>Beste,</div><div>{nb.activity_card_html(facts[activity.id])}</div>")

    nb.send_test(db_session, letter, to_email="s@example.org", base_url=BASE)

    tekst = mailbox.sent[0]["body_text"]
    assert "Rumproefavond" in tekst
    assert "<div" not in tekst and "&nbsp;" not in tekst
    # Links as the letter of Raak nationaal writes them: the text, then the URL.
    assert f"Schrijf je in! ({BASE}/activiteiten/rumproefavond)" in tekst


def test_de_tekstversie_van_een_abonnee_draagt_de_uitschrijflink(db_session):
    letter = _letter(db_session, audience=AUDIENCE_NON_MEMBERS, body="<div>Dag!</div>")

    tekst = nb.render_text(db_session, letter, unsubscribe_url=f"{BASE}/nieuwsbrief/uit/tok",
                           base_url=BASE)

    assert f"{BASE}/nieuwsbrief/uit/tok" in tekst


def test_een_kop_krijgt_de_merkkleur_bij_het_versturen(db_session):
    """Koen, 20 September 2026, after reading a sent letter: "Dit is onze
    kalender:" arrived as a mail client's own `h1` — huge, black, fighting with
    the block title under it. The minimum of the national letter: brand colour,
    one step up in size, no colour picker anywhere.

    Broken on purpose: the heading branch removed from `with_inline_styles` →
    the heading leaves unstyled and this test fails.
    """
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS,
                     body="<div>Beste,</div><h1>Dit is onze kalender:</h1><div>…</div>")

    mail = nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER, unsubscribe_url=None)

    assert 'style="font-size:20px;font-weight:700;line-height:1.3;color:#0051a4' in mail
    assert "<h1>" not in mail, "elke kop draagt opmaak"


def test_elke_kop_krijgt_ze_en_de_tekstversie_blijft_tekst(db_session):
    """Een brief heeft meer dan één onderwerp; en de opmaak hoort niet in de
    tekstversie te lekken."""
    letter = _letter(db_session, audience=AUDIENCE_MEMBERS,
                     body="<h1>Terugblik</h1><div>a</div><h1>Vooruitblik</h1><div>b</div>")

    mail = nb.render_mail(db_session, letter, kind=DELIVERY_MEMBER, unsubscribe_url=None)
    # Op de kopstijl tellen, niet op de kleur alleen: zonder logo draagt de
    # briefkop diezelfde merkkleur.
    assert mail.count(nb.HEADING_STYLE) == 2

    tekst = nb.render_text(db_session, letter, unsubscribe_url=None)
    assert "Terugblik" in tekst and "Vooruitblik" in tekst
    assert "style=" not in tekst and "#0051a4" not in tekst
