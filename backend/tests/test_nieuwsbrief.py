"""The newsletter (CR-05, #984): who receives it, and how it leaves.

The numbered sections follow CR-05 §7, the test set the build has to prove.
The mail transport is replaced by a mailbox that records what would leave; the
queue is driven by calling the job's own function, the way the scheduler does.
"""
from datetime import date, datetime, timedelta, timezone

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
                 reply_to=None, unsubscribe_url=None):
        from app.domains.mail.api import SendingQuotaReached

        if self.quota_after is not None and len(self.sent) >= self.quota_after:
            raise SendingQuotaReached("550 5.4.5 Daily user sending limit exceeded")
        self.sent.append({"to": to_email, "subject": subject, "body": body_html,
                          "type": email_type, "reply_to": reply_to,
                          "unsubscribe_url": unsubscribe_url})
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
