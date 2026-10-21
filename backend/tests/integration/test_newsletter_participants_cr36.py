"""CR-36 (#2026): the newsletter to the people registered for earlier activities.

Proven red (15 October 2026), each by an additive or reversing edit:
- the precedence member → subscriber → participant swapped in `participant_recipients`
  → the precedence test fails;
- the re-check at the send removed from `send_batch` → T11 fails (a participant who
  unsubscribed during the send is mailed);
- `erase` deleting the row of an unsubscribed address → T5's erased-address test fails;
- the registration's address not normalised → T12 fails (a mixed-case address is mailed).
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.domains.newsletter import service as nb
from app.domains.newsletter.models import (
    Audience,
    Delivery,
    DeliveryKind,
    DeliveryStatus,
    LetterStatus,
    Newsletter,
    Subscriber,
    SubscriberSource,
    SubscriberStatus,
)
from app.kernel.clock import belgian_today
from tests._newsletter_world import (
    Mailbox,
    household,
    past_activity,
    register,
    subscriber,
)
from tests._sites import new_site

pytestmark = pytest.mark.ui_serverrendered

BASE = "https://raak.example"


@pytest.fixture
def mailbox(monkeypatch):
    box = Mailbox()
    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", box)
    return box


def _letter(db, *activities, audience=Audience.PARTICIPANTS) -> Newsletter:
    letter = nb.create_newsletter(db, created_by="secretaris@example.org")
    nb.update_draft(
        db,
        letter,
        subject="Het is terug",
        body_html="<div>Beste, tot dan.</div>",
        audience=audience,
    )
    for activity in activities:
        nb.set_participant_activity(db, letter, activity.id, chosen=True)
    return letter


def _send(db, letter) -> int:
    return nb.start_sending(
        db, letter, sent_by="secretaris@example.org", reply_to_mode="association", base_url=BASE
    )


def _kinds(db, letter) -> dict[str, DeliveryKind]:
    return {d.email: d.kind for d in db.query(Delivery).filter(Delivery.newsletter_id == letter.id)}


# ── Who is in it ─────────────────────────────────────────────────────────────


def test_a_person_on_two_chosen_activities_gets_one_delivery(db_session):
    """T1."""
    quiz, bbq = past_activity(db_session, "Quiz"), past_activity(db_session, "BBQ", days_ago=100)
    register(db_session, quiz, "een@example.org")
    register(db_session, bbq, "een@example.org")
    register(db_session, bbq, "twee@example.org")
    letter = _letter(db_session, quiz, bbq)
    assert _send(db_session, letter) == 2
    assert sorted(_kinds(db_session, letter)) == ["een@example.org", "twee@example.org"]


def test_a_deleted_registration_and_a_cancelled_activity_add_nobody_an_unpaid_one_does(db_session):
    """T2."""
    from app.soft_delete import soft_delete

    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "blijft@example.org")
    gone = register(db_session, quiz, "weg@example.org")
    soft_delete(gone)
    db_session.flush()
    cancelled = past_activity(db_session, "Afgelast", cancelled=True)
    register(db_session, cancelled, "afgelast@example.org")
    letter = _letter(db_session, quiz)
    assert [r.email for r in nb.recipients_of(db_session, letter)] == ["blijft@example.org"]
    # A cancelled activity is not offered at all.
    with pytest.raises(nb.NewsletterError):
        nb.set_participant_activity(db_session, letter, cancelled.id, chosen=True)


def test_the_precedence_is_member_then_subscriber_then_participant(db_session):
    """T3, T4 and the gate of C7: the order is a rule, and a test names it."""
    quiz = past_activity(db_session, "Quiz")
    household(db_session, "lid@example.org")
    subscriber(db_session, "abonnee@example.org")
    for address in ("lid@example.org", "abonnee@example.org", "gast@example.org"):
        register(db_session, quiz, address)
    # A member who is also a confirmed subscriber is a member.
    subscriber(db_session, "lid@example.org")
    letter = _letter(db_session, quiz)
    kinds = {r.email: r.kind for r in nb.recipients_of(db_session, letter)}
    assert kinds == {
        "lid@example.org": DeliveryKind.MEMBER,
        "abonnee@example.org": DeliveryKind.SUBSCRIBER,
        "gast@example.org": DeliveryKind.PARTICIPANT,
    }


def test_an_unsubscribed_address_is_left_out_unless_it_is_a_member(db_session):
    """T5."""
    quiz = past_activity(db_session, "Quiz")
    household(db_session, "lid@example.org")
    subscriber(db_session, "weg@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    subscriber(db_session, "lid@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    for address in ("weg@example.org", "lid@example.org", "gast@example.org"):
        register(db_session, quiz, address)
    letter = _letter(db_session, quiz)
    assert {r.email for r in nb.recipients_of(db_session, letter)} == {
        "lid@example.org",
        "gast@example.org",
    }
    # A mixed-case registration against a lower-case row (T12).
    register(db_session, quiz, "WEG@Example.org")
    assert "weg@example.org" not in {r.email for r in nb.recipients_of(db_session, letter)}


def test_an_address_erased_after_its_opt_out_is_still_left_out(db_session):
    """T5, the second half: the erasure keeps the opt-out, and clears the rest. Broken
    on purpose: `erase` deleting the row → the address is mailed again."""
    quiz = past_activity(db_session, "Quiz")
    row = subscriber(db_session, "weg@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    row.first_name = "Weggegaan"
    old_token = row.unsubscribe_token
    register(db_session, quiz, "weg@example.org")
    nb.erase(db_session, row.id)
    db_session.expire_all()
    kept = nb.subscriber_by_email(db_session, "weg@example.org")
    assert kept is not None and kept.status == SubscriberStatus.UNSUBSCRIBED
    assert kept.first_name is None and kept.unsubscribe_token != old_token
    assert nb.recipients_of(db_session, _letter(db_session, quiz)) == []


def test_another_tenants_registrations_never_appear(db_session):
    """T7."""
    from app.domains.mdm.api import TenantKind
    from app.kernel.tenancy import TENANT_MILLEGEM_ID, current_tenant_id

    # The filter is the session's: it needs the tenant the screen would be in.
    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        _the_isolation(db_session, TenantKind)
    finally:
        current_tenant_id.reset(token)


def _the_isolation(db_session, TenantKind):
    other = new_site(
        db_session, name="Andere afdeling", code="cr36-other", kind=TenantKind.ASSOCIATION
    )
    foreign = past_activity(db_session, "Elders", tenant_id=other.id)
    register(db_session, foreign, "vreemd@example.org", tenant_id=other.id)
    mine = past_activity(db_session, "Hier")
    register(db_session, mine, "eigen@example.org")
    letter = _letter(db_session, mine)
    assert [r.email for r in nb.recipients_of(db_session, letter)] == ["eigen@example.org"]
    with pytest.raises(nb.NewsletterError):
        nb.set_participant_activity(db_session, letter, foreign.id, chosen=True)


def test_an_address_that_fails_the_check_is_skipped_and_counted(db_session):
    """T13."""
    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "goed@example.org")
    broken = register(db_session, quiz, "later@example.org")
    # An old registration that predates the validator: written past it.
    db_session.execute(
        text("UPDATE activities.registrations SET contact_email = 'geen adres' WHERE id = :i"),
        {"i": broken.id},
    )
    db_session.expire_all()
    letter = _letter(db_session, quiz)
    recipients, said = nb.participant_recipients(db_session, letter)
    assert [r.email for r in recipients] == ["goed@example.org"] and said.skipped == 1


def test_the_offered_activities_are_the_last_three_working_years(db_session):
    """Q3 and C4.6: published, not cancelled, a date, all dates before today; newest first."""
    recent = past_activity(db_session, "Recent", days_ago=30)
    old = past_activity(db_session, "Oud", days_ago=400)
    ancient = past_activity(db_session, "Antiek", days_ago=365 * 4)
    coming = past_activity(db_session, "Komend", days_ago=-20)
    letter = _letter(db_session, audience=Audience.PARTICIPANTS)
    offered = [o.name for o in nb.offered_activities(db_session, letter)]
    assert offered.index("Recent") < offered.index("Oud")
    assert "Antiek" not in offered and "Komend" not in offered
    del recent, old, ancient, coming


# ── What is said ─────────────────────────────────────────────────────────────


def test_the_sentence_counts_the_union_not_the_sum(db_session):
    """T9."""
    from app.domains.newsletter.admin_ui import _participant_said

    quiz, bbq = past_activity(db_session, "Quiz"), past_activity(db_session, "BBQ", days_ago=100)
    household(db_session, "lid@example.org")
    for address in ("lid@example.org", "een@example.org", "twee@example.org"):
        register(db_session, quiz, address)
    for address in ("een@example.org", "drie@example.org"):
        register(db_session, bbq, address)
    letter = _letter(db_session, quiz, bbq)
    lines, notes, count = _participant_said(db_session, letter)
    assert count == 4, "four people, not five registrations"
    assert "4 adressen van mensen die waren ingeschreven op" in lines[0].sentence
    assert "Quiz" in lines[0].sentence and "BBQ" in lines[0].sentence
    assert "1 krijgt hem al als lid" in lines[0].sentence
    assert notes == []


def test_an_activity_deleted_before_the_send_is_dropped_and_said(db_session):
    from app.domains.newsletter.admin_ui import _participant_said
    from app.soft_delete import soft_delete

    quiz, bbq = past_activity(db_session, "Quiz"), past_activity(db_session, "BBQ", days_ago=100)
    register(db_session, quiz, "een@example.org")
    register(db_session, bbq, "twee@example.org")
    letter = _letter(db_session, quiz, bbq)
    soft_delete(bbq)
    db_session.flush()
    _lines, notes, count = _participant_said(db_session, letter)
    assert count == 1 and any("BBQ" in n for n in notes)


# ── The send ─────────────────────────────────────────────────────────────────


def test_the_participants_mail_carries_a_signed_unsubscribe_link_and_a_member_none(
    db_session, mailbox
):
    """T3, T10 and C4.2."""
    quiz = past_activity(db_session, "Quiz")
    household(db_session, "lid@example.org")
    register(db_session, quiz, "lid@example.org")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    while nb.send_batch(db_session, letter.id) == "continue":
        pass
    by = {m["to"]: m for m in mailbox.sent}
    assert by["lid@example.org"]["unsubscribe_url"] is None
    link = by["gast@example.org"]["unsubscribe_url"]
    assert link.startswith(f"{BASE}/nieuwsbrief/uitschrijven/d/") and "." in link
    assert "Uitschrijven" in by["gast@example.org"]["body"]
    assert "Uitschrijven" not in by["lid@example.org"]["body"]


def test_the_test_mail_of_a_participants_letter_has_the_unsubscribe_line(db_session):
    """T10."""
    letter = _letter(db_session)
    rendered = nb.render_test(db_session, letter, base_url=BASE)
    assert "Uitschrijven" in rendered.body_html


def test_a_participant_who_unsubscribed_during_the_send_is_skipped_a_member_is_not(
    db_session, mailbox
):
    """T11. Broken on purpose: the re-check removed from `send_batch` → both are mailed."""
    quiz = past_activity(db_session, "Quiz")
    household(db_session, "lid@example.org")
    for address in ("lid@example.org", "gast@example.org", "andere@example.org"):
        register(db_session, quiz, address)
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    # Through this letter's link, and — for the other address — through another letter's.
    deliveries = {d.email: d for d in db_session.query(Delivery).filter_by(newsletter_id=letter.id)}
    link = nb.unsubscribe_link_of(deliveries["gast@example.org"], BASE).rsplit("/d/", 1)[1]
    assert nb.unsubscribe_participant(db_session, link) is not None
    subscriber(db_session, "andere@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    # A member who unsubscribed somewhere still gets the member letter.
    subscriber(db_session, "lid@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    while nb.send_batch(db_session, letter.id, batch_size=50) == "continue":
        pass
    assert mailbox.addresses == ["lid@example.org"]
    skipped = {
        d.email
        for d in db_session.query(Delivery).filter_by(
            newsletter_id=letter.id, status=DeliveryStatus.SKIPPED
        )
    }
    assert skipped == {"gast@example.org", "andere@example.org"}


# ── The unsubscribe link ─────────────────────────────────────────────────────


def _delivery_link(db, letter, email) -> str:
    delivery = db.query(Delivery).filter_by(newsletter_id=letter.id, email=email).one()
    return nb.unsubscribe_link_of(delivery, BASE).rsplit("/d/", 1)[1]


def test_the_link_makes_one_unsubscribed_row_with_source_participant_called_twice(
    client, db_session
):
    """T6: a GET shows and changes nothing; a POST (the button, and the mail client's
    one-click) makes the row; a second letter skips the address."""
    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    db_session.commit()
    link = _delivery_link(db_session, letter, "gast@example.org")

    page = client.get(f"/nieuwsbrief/uitschrijven/d/{link}")
    assert page.status_code == 200 and "gast@example.org" in page.text
    assert nb.subscriber_by_email(db_session, "gast@example.org") is None, "opening is no click"

    done = client.post(f"/nieuwsbrief/uitschrijven/d/{link}")
    assert "Je bent uitgeschreven" in done.text
    one_click = client.post(
        f"/nieuwsbrief/uitschrijven/d/{link}", data={"List-Unsubscribe": "One-Click"}
    )
    assert one_click.text == "ok"
    db_session.expire_all()
    rows = db_session.query(Subscriber).filter_by(email="gast@example.org").all()
    assert len(rows) == 1
    assert rows[0].status == SubscriberStatus.UNSUBSCRIBED
    assert rows[0].source == SubscriberSource.PARTICIPANT and rows[0].consented_at is None

    second = _letter(db_session, quiz)
    assert nb.recipients_of(db_session, second) == []


def test_a_link_that_does_not_check_out_answers_like_a_dead_one(client, db_session):
    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    db_session.commit()
    good = _delivery_link(db_session, letter, "gast@example.org")
    number = good.split(".")[0]
    # "²" and the Arabic-Indic "٣" pass `str.isdigit()` and make `int()` raise: a 500 on a
    # public route (review of 16 October 2026).
    for bad in (
        f"{number}.{'0' * 32}",
        f"{number}.kort",
        "12.abc",
        f"99999.{good.split('.')[1]}",
        f"²{number}.{good.split('.')[1]}",
        "٣.abcd",
        # More than 4300 digits: `int()` refuses the string (Python's limit) before the
        # signature is looked at.
        f"{'9' * 5000}.{good.split('.')[1]}",
    ):
        page = client.get(f"/nieuwsbrief/uitschrijven/d/{bad}")
        assert "Deze link werkt niet meer" in page.text, bad
        assert client.post(f"/nieuwsbrief/uitschrijven/d/{bad}").status_code == 200
    assert nb.subscriber_by_email(db_session, "gast@example.org") is None


def test_toch_opnieuw_makes_a_confirmed_subscriber_and_the_page_says_so(client, db_session):
    """T15."""
    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    db_session.commit()
    link = _delivery_link(db_session, letter, "gast@example.org")
    unsubscribed = client.post(f"/nieuwsbrief/uitschrijven/d/{link}")
    assert "Toch opnieuw inschrijven" in unsubscribed.text
    row = nb.subscriber_by_email(db_session, "gast@example.org")
    again = client.post(f"/nieuwsbrief/opnieuw/{row.unsubscribe_token}")
    assert "Je ontvangt vanaf nu onze nieuwsbrief." in again.text
    db_session.expire_all()
    row = nb.subscriber_by_email(db_session, "gast@example.org")
    assert row.status == SubscriberStatus.CONFIRMED and row.consented_at is not None


def test_a_participant_who_then_signs_up_follows_the_double_opt_in(db_session, monkeypatch):
    """T14: `subscribe_public` on an unsubscribed row makes it pending, source public_form."""
    from app.kernel.form_guard import TRUSTED

    monkeypatch.setattr(
        "app.domains.mail.api.send_newsletter_confirmation", lambda to, name, url: "sent"
    )
    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    link = _delivery_link(db_session, letter, "gast@example.org")
    nb.unsubscribe_participant(db_session, link)
    nb.subscribe_public(db_session, "gast@example.org", "Gast", lambda t: f"/b/{t}", proof=TRUSTED)
    row = nb.subscriber_by_email(db_session, "gast@example.org")
    assert row.status == SubscriberStatus.PENDING and row.source == SubscriberSource.PUBLIC_FORM


def test_the_unsubscribed_count_grows_when_a_participant_unsubscribes(db_session):
    """T16: a deliberate effect (Koen, B9)."""
    quiz = past_activity(db_session, "Quiz")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    before = nb.subscriber_counts(db_session)["unsubscribed"]
    nb.unsubscribe_participant(db_session, _delivery_link(db_session, letter, "gast@example.org"))
    assert nb.subscriber_counts(db_session)["unsubscribed"] == before + 1


# ── The letter itself ────────────────────────────────────────────────────────


def test_a_copy_has_no_audience_and_no_activities_and_deleting_a_draft_deletes_them(db_session):
    """T8."""
    quiz = past_activity(db_session, "Quiz")
    letter = _letter(db_session, quiz)
    copy = nb.copy_newsletter(db_session, letter, created_by="s@example.org")
    assert copy.audience is None and nb.chosen_activities(db_session, copy) == []
    nb.delete_draft(db_session, letter)
    assert nb.chosen_activities(db_session, letter) == []


def test_the_archive_keeps_the_activitys_name_after_it_is_deleted(client, db_session):
    """T18 and R6."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.soft_delete import soft_delete
    from tests.conftest import SEEDED_ADMIN_EMAIL

    quiz = past_activity(db_session, "Quiz van vorig jaar")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    _send(db_session, letter)
    soft_delete(quiz)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert "Quiz van vorig jaar" in page.text and "data-audience-activities" in page.text
    assert letter.status in (LetterStatus.SENDING, LetterStatus.SENT)


def test_the_chosen_activities_reach_raakje_with_name_and_date_and_no_address(db_session):
    """T19."""
    from app.domains.newsletter import drafting

    quiz = past_activity(db_session, "Quiz van vorig jaar", days_ago=300)
    register(db_session, quiz, "geheim@example.org")
    letter = _letter(db_session, quiz)
    sources = drafting.gather_sources(db_session, letter, instruction="Schrijf.", names=set())
    from app.domains.newsletter import service as nb

    day = nb.short_date(belgian_today() - timedelta(days=300))
    assert sources.earlier == [f"Quiz van vorig jaar ({day})"]
    text = "\n".join(text for text, _place in drafting._sections(sources))
    assert "Quiz van vorig jaar" in text and "geheim@example.org" not in text
    assert sources.examples == [], "no example letters for this audience"


# ── The gate (C7) ────────────────────────────────────────────────────────────


def test_every_audience_has_its_entries(db_session):
    """C7: a new audience must choose its place in `recipients_of` and in the kind of
    its sample mail. Proven by an additive violation: a fifth value not in the map fails
    `sample_kind_of` with a KeyError, and `recipients_of` refuses it by name."""
    from types import SimpleNamespace

    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    for audience in Audience:
        letter.audience = audience
        assert isinstance(nb.recipients_of(db_session, letter), list)
        assert isinstance(nb.sample_kind_of(audience), DeliveryKind)
    assert set(nb._SAMPLE_KIND) == set(Audience)
    with pytest.raises(nb.NewsletterError):
        nb.recipients_of(db_session, SimpleNamespace(audience="fantasy"))  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        nb.sample_kind_of("fantasy")  # type: ignore[arg-type]


# ── The screens ──────────────────────────────────────────────────────────────


def _login(client):
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def test_the_list_appears_for_the_audience_ticks_follow_and_the_sentence_says_who(
    client, db_session
):
    """AC1, AC2, AC3: the fragment is asked for with the audience ticked on the page
    (not yet saved); a tick puts the activity in the letter; the sentence counts once."""
    quiz, bbq = past_activity(db_session, "Quiz"), past_activity(db_session, "BBQ", days_ago=100)
    register(db_session, quiz, "een@example.org")
    register(db_session, quiz, "twee@example.org")
    register(db_session, bbq, "twee@example.org")
    letter = _letter(db_session, audience=None)
    db_session.commit()
    headers = _login(client)

    other = client.get(f"/admin/nieuwsbrieven/{letter.id}/deelnemers?audience=members")
    assert "Kies één of meer activiteiten" not in other.text, "only for the audience"
    shown = client.get(f"/admin/nieuwsbrieven/{letter.id}/deelnemers?audience=participants")
    assert "Kies één of meer activiteiten" in shown.text
    assert "Quiz" in shown.text and "2 adressen" in shown.text and "1 adres" in shown.text

    # The ticks are part of the record form (#2183): Opslaan stores them with the audience.
    saved = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bewaren",
        headers={**headers, "HX-Request": "true"},
        data={"subject": "x", "audience": "participants", "chosen": [str(quiz.id), str(bbq.id)]},
    )
    assert saved.status_code == 204
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    assert "2 adressen van mensen die waren ingeschreven op" in page, "the union, not the sum"
    assert page.count('name="chosen"') == 2
    assert 'value="participants"' in page

    client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bewaren",
        headers={**headers, "HX-Request": "true"},
        data={"subject": "x", "audience": "participants", "chosen": [str(quiz.id)]},
    )
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    sentence = [r for r in page.splitlines() if "van mensen die waren ingeschreven op" in r]
    assert sentence and "BBQ" not in sentence[0] and "Quiz" in sentence[0]
    assert [a.activity_id for a in nb.chosen_activities(db_session, letter)] == [quiz.id]


def test_the_send_screen_says_who_it_goes_to_in_words(client, db_session):
    quiz = past_activity(db_session, "Quiz")
    household(db_session, "lid@example.org")
    register(db_session, quiz, "lid@example.org")
    register(db_session, quiz, "gast@example.org")
    letter = _letter(db_session, quiz)
    db_session.commit()
    _login(client)
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen").text
    assert "2 adressen van mensen die waren ingeschreven op Quiz" in page
    assert "1 krijgt hem al als lid" in page
    assert "Verstuur naar 2 ontvangers" in page
