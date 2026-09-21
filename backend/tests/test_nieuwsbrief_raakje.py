"""Raakje drafts the newsletter (CR-05 §3.15–§3.16, #984) — without inventing facts.

A scripted provider stands in for Mistral: it returns prepared answers and keeps
what it received. The real seam guard wraps it, so a name that slips through
blocks the call exactly as it would in production.

The known hallucinations of the public Raakje are fixed cases here (§3.16):
games that are not in the flyer, a function given to a board member, a price
found only in an old letter.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.mdm.api import Person
from app.domains.newsletter import drafting
from app.domains.newsletter import service as nb
from app.domains.newsletter.models import (
    AUDIENCE_MEMBERS,
    LETTER_SENT,
    Newsletter,
)

pytestmark = pytest.mark.ui_serverrendered

BASE = "https://raak.example"


class ScriptedProvider:
    """Answers in order; keeps every message list it was asked."""

    name = "scripted"
    model = "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[list[dict]] = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.asked.append([dict(m) for m in messages])
        answer = self.answers.pop(0) if self.answers else json.dumps({"unsupported": []})
        if isinstance(answer, Exception):
            raise answer
        return AssistantMessage(content=answer)

    def payloads(self) -> str:
        return json.dumps(self.asked, ensure_ascii=False).lower()


@pytest.fixture
def raakje(monkeypatch):
    def install(*answers):
        provider = ScriptedProvider(*answers)
        monkeypatch.setattr("app.domains.chatbot.api.get_provider",
                            lambda model="": provider)
        return provider
    return install


def _draft(paragraphs, reply="Voorstel klaar.", subject="Het najaar"):
    return json.dumps({"reply": reply, "subject": subject, "paragraphs": paragraphs})


def _piece(text, reply="Aangepast."):
    return json.dumps({"reply": reply, "text": text})


def _verdict(*items):
    return json.dumps({"unsupported": [
        {"paragraph": p, "quote": q, "reason": r} for p, q, r in items]})


def _activity(db, name, days_ahead=20, price=None, member_price=None):
    from app.domains.activities.api import ActivitySubRegistration

    activity = Activity(name=name, location="Dorpsplein",
                        slug=name.lower().replace(" ", "-").replace("&", "en"))
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id,
                        start_date=date.today() + timedelta(days=days_ahead)))
    if price is not None:
        db.add(ActivitySubRegistration(activity_id=activity.id, name="Deelname",
                                       price=Decimal(price), is_free=False,
                                       member_price=(Decimal(member_price)
                                                     if member_price else None)))
    db.flush()
    return activity


def _letter(db, body="", audience=AUDIENCE_MEMBERS, activity_ids=()):
    letter = nb.create_newsletter(db, created_by="s@example.org")
    nb.update_draft(db, letter, subject="", body_html=body, audience=audience)
    nb.set_draft_sources(db, letter, activity_ids=list(activity_ids), meeting_ids=[])
    return letter


def _ask(db, letter, instruction="Schrijf de najaarsbrief.", selection="",
         selection_range="", before_cursor=""):
    return drafting.ask(db, letter, instruction=instruction, actor="s@example.org",
                        base_url=BASE, selection=selection,
                        selection_range=selection_range, before_cursor=before_cursor)


def _sent_meeting_with_point(db, notes, activity=None):
    """A sent meeting report with one point, as the composer may tick it."""
    from app.domains.meetings.api import (
        SECTION_EVALUATION, STATUS_SENT, add_item, create_meeting, sections_of)

    meeting = create_meeting(db, meeting_date=date.today() - timedelta(days=10))
    section = next(s for s in sections_of(db, meeting) if s.kind == SECTION_EVALUATION)
    item = add_item(db, meeting, section, title="Vervoer",
                    activity_id=activity.id if activity else None)
    item.notes = notes
    meeting.status = STATUS_SENT
    db.commit()
    return item


# ── 11–12. What leaves ───────────────────────────────────────────────────────

def test_een_naam_uit_het_verslag_vertrekt_niet_en_komt_niet_terug(db_session, raakje):
    """A ticked point "Kris regelt de bus" leaves without the name, and the name
    does not come back (CR-05 §3.15; Koen: individual organisers are never thanked).

    Broken on purpose: `gather_sources` without `scrub` on the points → the
    seam guard blocks the call (the name is in the payload) and the test fails.
    """
    db_session.add(Person(first_name="Kris", last_name="Vermeulen"))
    db_session.flush()
    item = _sent_meeting_with_point(db_session, "<div>Kris regelt de bus voor iedereen.</div>")
    letter = _letter(db_session)
    nb.set_draft_sources(db_session, letter, activity_ids=[], meeting_ids=[item.meeting_id])
    provider = raakje(_draft(["Er rijdt een bus voor iedereen."]), _verdict())

    turn = _ask(db_session, letter)

    assert "kris" not in provider.payloads()
    assert "vermeulen" not in provider.payloads()
    assert "[naam] regelt de bus" in provider.payloads()
    assert "Kris" not in json.dumps(turn.proposal)


def test_een_niet_aangevinkt_verslag_gaat_nooit_mee(db_session, raakje):
    """Whole reports are ticked (Koen, 17 September 2026); the latest one is
    ticked by default, and unticking it keeps the report data out altogether.

    Broken on purpose: `gather_sources` reading every sent report regardless of
    the ticks → the unticked report's text is in the payload and this fails.
    """
    item = _sent_meeting_with_point(db_session, "<div>Geheim punt over de kas.</div>")
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    assert letter.draft_meeting_ids == [item.meeting_id], "het laatste verslag staat aangevinkt"
    nb.set_draft_sources(db_session, letter, activity_ids=[], meeting_ids=[])
    provider = raakje(_draft(["Een brief."]), _verdict())

    _ask(db_session, letter)

    assert "geheim punt" not in provider.payloads()


def test_een_aangevinkt_verslag_gaat_als_geheel_mee(db_session, raakje):
    item = _sent_meeting_with_point(db_session, "<div>Iedereen genoot van de soep.</div>")
    letter = nb.create_newsletter(db_session, created_by="s@example.org")
    provider = raakje(_draft(["Een brief."]), _verdict())

    _ask(db_session, letter)

    assert "iedereen genoot van de soep" in provider.payloads()
    assert "intern" in provider.payloads(), "het model hoort dat een verslag intern is"
    assert item.meeting_id in letter.draft_meeting_ids


def test_niemands_adres_en_geen_ontvangerslijst_in_de_payload(db_session, raakje):
    from app.domains.newsletter.models import Subscriber

    db_session.add(Subscriber(email="piet@example.org", status="confirmed",
                              source="admin", unsubscribe_token="t1"))
    db_session.flush()
    letter = _letter(db_session)
    provider = raakje(_draft(["Een brief."]), _verdict())

    _ask(db_session, letter)

    assert "piet@example.org" not in provider.payloads()
    assert "@" not in provider.payloads()


def test_een_adres_in_de_gegevens_blokkeert_raakje_niet_meer(db_session, raakje):
    """Found on HDEV (17 September 2026): a question without any address was
    refused, because the text of an activity carried one. Everything outbound now
    loses e-mail addresses, phone numbers and account numbers first, with the
    guard's own patterns.

    The carrier here is `description` since #1028: it used to be `notes`, and
    that column is gone — it read as an internal note while going straight to the
    model. The path is the same, because Raakje reads the activity through the
    public read tool.

    Broken on purpose: `scrub` without `redact` → the guard refuses the call
    (SeamBlocked) and this test fails.
    """
    from app.domains.activities.api import Activity

    activiteit = _activity(db_session, "Wandelweekend Eifel")
    db_session.get(Activity, activiteit.id).description = (
        "Inschrijven via info@raak.example of 0473 12 34 56, betalen op BE68539007547034.")
    db_session.commit()
    letter = _letter(db_session, activity_ids=[activiteit.id])
    provider = raakje(_draft(["Een brief."]), _verdict())

    _ask(db_session, letter, instruction="Mail naar info@raak.example voor meer info")

    payload = provider.payloads()
    assert "@" not in payload
    assert "0473" not in payload and "be68" not in payload
    assert "[e-mailadres]" in payload and "[telefoonnummer]" in payload


def test_redact_laat_niets_over_waar_de_wachter_op_weigert():
    """One source for the patterns: after `redact`, the guard finds nothing."""
    from app.domains.chatbot.api import admin_rules, redact
    from app.domains.chatbot.seam import findings

    tekst = "Mail an@example.org, bel +32 473 12 34 56 of stort op BE68 5390 0754 7034."
    rules = admin_rules(lambda: set(), capability="test")
    assert findings([{"role": "user", "content": tekst}], rules)
    assert findings([{"role": "user", "content": redact(tekst)}], rules) == []


def test_de_hele_brief_op_vraag_ook_als_er_al_tekst_staat(db_session, raakje):
    """Koen asked to rewrite the whole letter; with text present that used to
    become a piece at the cursor. A whole letter comes back as a whole letter,
    with the choice to replace or insert."""
    letter = _letter(db_session, body="<div>Beste,</div><div>Oude tekst.</div>")
    raakje(_draft(["# Terugblik", "Nieuwe tekst."]), _verdict())

    turn = _ask(db_session, letter, instruction="Herschrijf de hele nieuwsbrief.")

    assert turn.proposal["kind"] == "letter"


# ── 13–15, 17–18. What comes back ────────────────────────────────────────────

def test_een_zelf_geschreven_datum_wordt_gemarkeerd_de_markering_komt_uit_de_data(
        db_session, raakje):
    """The model writes its own date → marked; the marker line comes from the
    activity data (CR-05 §3.16 layers 1 and 3).

    Broken on purpose: `deterministic_marks` without the number check → the
    invented "12" is not marked.
    """
    brood = _activity(db_session, "Brood & Spelen", days_ahead=30)
    letter = _letter(db_session, activity_ids=[brood.id])
    raakje(_draft(["# In de kijker", f"[[activiteit:{brood.id}]]",
                   "Kom op de 12de naar Brood & Spelen, gezellig!"]), _verdict())

    turn = _ask(db_session, letter)

    marks = turn.proposal["marks"]
    assert any(m["quote"] == "12" for m in marks)
    html = turn.proposal["operations"][0]["html"]
    # The marker becomes the same reference the button inserts; the date, the
    # place and the link come from the data when the letter is sent.
    assert f"[[activiteit:{brood.id}|" in html
    from app.domains.newsletter import service as nb

    mail = nb.expand_blocks(db_session, html, base_url=BASE)
    assert f"{BASE}/activiteiten/brood-en-spelen" in mail
    assert "Dorpsplein" in mail


def test_een_bedrag_dat_geen_prijs_is_wordt_gemarkeerd(db_session, raakje):
    bbq = _activity(db_session, "BBQ", price="15", member_price="12")
    letter = _letter(db_session, activity_ids=[bbq.id])
    raakje(_draft(["Leden betalen € 12 voor de BBQ.", "Niet-leden betalen € 18."]), _verdict())

    turn = _ask(db_session, letter)

    quotes = [m["quote"] for m in turn.proposal["marks"]]
    assert "€ 18" in quotes
    assert "€ 12" not in quotes, "een echte ledenprijs is geen verzinsel"


def test_een_prijs_die_alleen_in_een_oude_brief_staat_telt_als_verzonnen(db_session, raakje):
    """Example letters are style only (CR-05 §3.16)."""
    old = nb.create_newsletter(db_session, created_by="s@example.org")
    nb.update_draft(db_session, old, subject="Vorig jaar",
                    body_html="<div>De BBQ kost € 7 dit jaar.</div>", audience=AUDIENCE_MEMBERS)
    old.status = LETTER_SENT
    db_session.commit()
    bbq = _activity(db_session, "BBQ", price="15")
    letter = _letter(db_session, activity_ids=[bbq.id])
    provider = raakje(_draft(["De BBQ kost € 7."]), _verdict())

    turn = _ask(db_session, letter)

    assert "€ 7 dit jaar" in json.dumps(provider.asked, ensure_ascii=False), "als stijlvoorbeeld mee"
    assert [m["quote"] for m in turn.proposal["marks"]] == ["€ 7"]


def test_een_verzonnen_functie_wordt_gemarkeerd(db_session, raakje):
    """#309: the public Raakje once made a steward a treasurer."""
    letter = _letter(db_session)
    raakje(_draft(["Onze penningmeester heeft alles geregeld."]), _verdict())

    turn = _ask(db_session, letter)

    assert any(m["quote"].lower() == "penningmeester" for m in turn.proposal["marks"])


def test_verzonnen_spelletjes_worden_door_de_controleronde_gemarkeerd(db_session, raakje):
    """Brood & Spelen: games that are not in the flyer. No word list finds
    "zaklopen" — the verification pass does (CR-05 §3.16 layer 4).

    Broken on purpose: `verify` not called → no mark, and the test fails.
    """
    brood = _activity(db_session, "Brood & Spelen")
    letter = _letter(db_session, activity_ids=[brood.id])
    zin = "Er is een springkasteel en een zaklopen-wedstrijd."
    provider = raakje(_draft([zin]), _verdict((1, "zaklopen-wedstrijd", "staat niet in de flyer")))

    turn = _ask(db_session, letter)

    assert [(m["quote"], m["sentence"]) for m in turn.proposal["marks"]] == [
        ("zaklopen-wedstrijd", zin)]
    verify_payload = json.dumps(provider.asked[-1], ensure_ascii=False)
    assert "VOORSTEL" in verify_payload and "zaklopen" in verify_payload


def test_een_mislukte_controleronde_laat_het_voorstel_niet_gecontroleerd_lijken(db_session, raakje):
    letter = _letter(db_session)
    raakje(_draft(["Een brief."]), RuntimeError("controle ging stuk"))

    turn = _ask(db_session, letter)

    assert turn.proposal["unverified"] is True


def test_een_naam_in_het_antwoord_wordt_gemarkeerd(db_session, raakje):
    db_session.add(Person(first_name="Wannes", last_name="Fabriekx"))
    db_session.flush()
    letter = _letter(db_session)
    raakje(_draft(["Bedankt Fabriekx voor het vele werk."]), _verdict())

    turn = _ask(db_session, letter)

    assert any(m["quote"] == "Fabriekx" for m in turn.proposal["marks"])


def test_een_fotolink_alleen_als_er_een_album_is(db_session, raakje, monkeypatch):
    zonder = _activity(db_session, "Wandeling", days_ahead=-10)
    met = _activity(db_session, "Comedy Festival", days_ahead=-20)
    monkeypatch.setattr("app.domains.media.api.activity_photo_covers",
                        lambda db: [{"activity_id": met.id, "thumb_url": "/x"}])
    letter = _letter(db_session, activity_ids=[zonder.id, met.id])
    raakje(_draft([f"[[fotos:{zonder.id}]]", f"[[fotos:{met.id}]]"]), _verdict())

    turn = _ask(db_session, letter)

    html = turn.proposal["operations"][0]["html"]
    assert "/activiteiten/comedy-festival/fotos" in html
    assert "/activiteiten/wandeling/fotos" not in html


# ── Applying ─────────────────────────────────────────────────────────────────

def _proposal_message(db, letter, turn):
    return drafting.record(db, letter, author_text="vraag", turn=turn)


def test_een_gemarkeerde_zin_blijft_weg_tenzij_je_hem_behoudt(db_session, raakje):
    """Koen, 17 September 2026: choice A — left out unless "klopt, behouden".

    Broken on purpose: `apply` ignoring the marks → the invented sentence ends up
    in the letter, and the test fails.
    """
    brood = _activity(db_session, "Brood & Spelen")
    zin = "Er is ook een zaklopen-wedstrijd."
    for keep, expected in ((set(), False), ({1}, True)):
        letter = _letter(db_session, activity_ids=[brood.id])
        raakje(_draft(["Kom naar Brood & Spelen!", zin]),
               _verdict((1, "zaklopen", "staat niet in de flyer")))
        turn = _ask(db_session, letter)
        message = _proposal_message(db_session, letter, turn)
        assert letter.body_html == "", "niets in de brief vóór Toepassen"

        html = drafting.apply(db_session, letter, message, keep=keep,
                              body_html="", base_url=BASE).html

        assert ("zaklopen" in html) is expected
        assert "Kom naar Brood &amp; Spelen!" in html
        assert "Het bestuur van" in html, "de afsluiting zet het portaal er zelf onder"
        assert message.proposal["status"] == "applied"


def test_zonder_selectie_komt_het_stuk_waar_de_cursor_staat(db_session, raakje):
    """Koen, 17 September 2026: Raakje does not choose the place — the author
    does. Without a selection the piece goes to the cursor, the letter itself is
    not rewritten by the server, and the model gets the text before the cursor.
    """
    body = "<div>Beste,</div><div>Eerste alinea.</div>"
    letter = _letter(db_session, body=body)
    provider = raakje(_piece("Een nieuw stuk."), _verdict())

    turn = _ask(db_session, letter, instruction="Een stuk over de BBQ.",
                before_cursor="Eerste alinea.")
    message = _proposal_message(db_session, letter, turn)
    applied = drafting.apply(db_session, letter, message, keep=set(),
                             body_html=body, base_url=BASE)

    assert turn.proposal["kind"] == "insert"
    assert "TEKST VLAK VOOR DE CURSOR" in provider.asked[0][-1]["content"]
    assert "Eerste alinea." in provider.asked[0][-1]["content"]
    assert (applied.placement, applied.html) == ("cursor", "<div>Een nieuw stuk.</div>")
    assert letter.body_html == body, "de server herschrijft de brief niet zelf"


def test_een_selectie_wordt_vervangen(db_session, raakje):
    body = "<div>Beste,</div><div>Een te lange zin die korter mag.</div>"
    letter = _letter(db_session, body=body)
    provider = raakje(_piece("Een korte zin."), _verdict())

    turn = _ask(db_session, letter, instruction="Korter.",
                selection="Een te lange zin die korter mag.", selection_range="7,39")
    message = _proposal_message(db_session, letter, turn)
    applied = drafting.apply(db_session, letter, message, keep=set(),
                             body_html=body, base_url=BASE)

    assert turn.proposal["kind"] == "replace"
    assert "Een te lange zin die korter mag." in provider.asked[0][-1]["content"]
    assert (applied.placement, applied.range, applied.html) == (
        "selection", [7, 39], "<div>Een korte zin.</div>")


def test_een_selectie_op_een_intussen_veranderde_brief_wordt_geweigerd(db_session, raakje):
    """The remembered selection would point at other text.

    Broken on purpose: the snapshot check removed from `apply` → the stale
    replacement goes through and this test fails.
    """
    body = "<div>Een.</div><div>Twee.</div>"
    letter = _letter(db_session, body=body)
    raakje(_piece("Drie."), _verdict())
    turn = _ask(db_session, letter, instruction="Anders.", selection="Twee.",
                selection_range="4,9")
    message = _proposal_message(db_session, letter, turn)

    with pytest.raises(drafting.DraftingError):
        drafting.apply(db_session, letter, message, keep=set(),
                       body_html="<div>Nul.</div>" + body, base_url=BASE)
    assert message.proposal["status"] == "open"


def test_de_brief_splitsen_in_alineas():
    html = ("<div>Een <strong>vet</strong> woord.<br>Tweede regel.</div>"
            "<ul><li>a</li><li>b</li></ul><h1>Kop</h1><div>Laatste</div>")
    assert drafting.paragraphs(html) == [
        "<div>Een <strong>vet</strong> woord.<br>Tweede regel.</div>",
        "<ul><li>a</li><li>b</li></ul>", "<h1>Kop</h1>", "<div>Laatste</div>"]


def test_de_systeemprompt_draagt_geen_opgeslagen_inhoud(db_session, raakje):
    """`SCAN_PROMPT_NAMES = False` is only allowed for a prompt built from code
    (CR-07's rule). Everything stored — sources, house style, examples — goes in
    a user message, which the guard does scan.

    Broken on purpose: the house style appended to the system prompt → the
    system message differs from the constant and this test fails.
    """
    from app.kernel.tenant_config import set_setting

    set_setting(db_session, "newsletter_house_style", "Warm en kort.")
    db_session.commit()
    letter = _letter(db_session)
    provider = raakje(_draft(["Een brief."]), _verdict())

    _ask(db_session, letter)

    system = provider.asked[0][0]
    assert system["role"] == "system"
    assert system["content"] == drafting.SYSTEM_PROMPT
    assert "Warm en kort." in provider.asked[0][1]["content"]


# ── 19. The switch ───────────────────────────────────────────────────────────

def _login(client) -> dict:
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


def _switch(db, monkeypatch, on: bool):
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr("app.config.settings.admin_chat_enabled", on)
    set_setting(db, "admin_chat_enabled", "1" if on else None)
    db.commit()


def test_met_raakje_uit_is_er_geen_paneel_en_werkt_de_rest(client, db_session, monkeypatch):
    headers = _login(client)
    _switch(db_session, monkeypatch, False)
    letter = _letter(db_session)

    scherm = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert 'id="nb-raakje"' not in scherm.text
    assert 'id="nb-trix"' in scherm.text
    vraag = client.post(f"/admin/nieuwsbrieven/{letter.id}/raakje/vraag", headers=headers,
                        data={"instruction": "x", "body_html": ""})
    assert vraag.status_code == 404


def test_het_gesprek_via_het_scherm(client, db_session, monkeypatch, raakje):
    """Ask → the proposal shows with its mark → apply → the editor gets the text."""
    headers = _login(client)
    _switch(db_session, monkeypatch, True)
    brood = _activity(db_session, "Brood & Spelen")
    letter = _letter(db_session)

    kies = client.post(f"/admin/nieuwsbrieven/{letter.id}/raakje/activiteit",
                       headers=headers, data={"activity_id": str(brood.id)})
    assert "Brood &amp; Spelen" in kies.text
    raakje(_draft(["Kom naar Brood & Spelen!", "Er is een zaklopen-wedstrijd."]),
           _verdict((1, "zaklopen", "staat niet in de flyer")))

    antwoord = client.post(f"/admin/nieuwsbrieven/{letter.id}/raakje/vraag",
                           headers=headers, data={"instruction": "Een feestelijke brief",
                                                  "body_html": ""})
    assert "staat niet in de flyer" in antwoord.text
    assert "klopt, behouden" in antwoord.text
    assert "bg-yellow-100" in antwoord.text

    message = [m for m in nb.messages_of(db_session, letter) if m.proposal][-1]
    toegepast = client.post(f"/admin/nieuwsbrieven/{letter.id}/raakje/{message.id}/toepassen",
                            headers=headers, data={"body_html": "", "placement": "replace"})
    assert 'id="nb-toepassen"' in toegepast.text
    sjabloon = toegepast.text.split('id="nb-toepassen"')[1].split("</template>")[0]
    assert "Kom naar Brood" in sjabloon
    assert "zaklopen" not in sjabloon
    assert "toegepast" in toegepast.text


def test_versturen_ruimt_het_gesprek_op(db_session, raakje, monkeypatch):
    from app.domains.newsletter.models import DraftingMessage, Subscriber

    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail",
                        lambda *a, **k: "sent")
    db_session.add(Subscriber(email="a@example.org", status="confirmed", source="admin",
                              unsubscribe_token="t"))
    db_session.flush()
    letter = _letter(db_session, audience="non_members")
    raakje(_draft(["Een brief."]), _verdict())
    turn = _ask(db_session, letter)
    _proposal_message(db_session, letter, turn)
    nb.update_draft(db_session, letter, subject="Onderwerp", body_html="<div>Tekst</div>",
                    audience="non_members")
    assert db_session.query(DraftingMessage).count() == 2

    nb.start_sending(db_session, letter, sent_by="s@example.org",
                     reply_to_mode="association", base_url=BASE)

    assert db_session.query(DraftingMessage).count() == 0


# ── The shape of a whole letter (Koen, 17 September 2026) ────────────────────

def test_een_volledige_brief_krijgt_aanhef_witregels_en_afsluiting(db_session, raakje):
    """A greeting at the top, a blank line before every topic but the first, and
    a blank line before the closing — all set by the portal, not the model.

    Broken on purpose: the blank line before a heading left out of
    `_paragraph_html` → the second assertion fails.
    """
    wandel = _activity(db_session, "Wandelweekend Eifel")
    letter = _letter(db_session, activity_ids=[wandel.id])
    raakje(_draft(["# Vooruitblik", "De komende maanden zitten vol.", f"[[activiteit:{wandel.id}]]",
                   "# Terugblik", "Het was gezellig."]), _verdict())
    turn = _ask(db_session, letter)
    message = drafting.record(db_session, letter, author_text="vraag", turn=turn)

    html = drafting.apply(db_session, letter, message, keep=set(), body_html="",
                          base_url=BASE).html

    # Sinds 20 september 2026 is een kopje een echte titel (`h1`), zodat ze bij
    # het versturen dezelfde merkkleur krijgt als de rest van de brief.
    assert html.startswith("<div>Beste,</div><div><br></div><h1>Vooruitblik</h1>")
    assert "<div><br></div><h1>Terugblik</h1>" in html
    assert "Het was gezellig.</div><div><br></div><div>Tot binnenkort!" in html
    assert html.count("<div><br></div>") == 3


def test_een_naam_in_een_zin_komt_er_een_keer_en_vet_in(db_session, raakje):
    """`[[naam:ID]]` inside a sentence becomes the name in bold, exactly once —
    the model builds the sentence around it and never writes the name itself."""
    sint = _activity(db_session, "Sint komt naar onze gezinnen")
    letter = _letter(db_session, activity_ids=[sint.id])
    raakje(_draft([f"Tijdens [[naam:{sint.id}]] beleven groot en klein magische momenten."]),
           _verdict())

    turn = _ask(db_session, letter)

    html = turn.proposal["operations"][0]["html"]
    assert "Tijdens <strong>Sint komt naar onze gezinnen</strong> beleven" in html
    assert "[[" not in html
    assert html.count("Sint komt naar onze gezinnen") == 1


def test_de_prompt_vraagt_correct_nederlands_en_laat_aanhef_en_groet_aan_het_portaal():
    prompt = drafting.SYSTEM_PROMPT
    assert "[[naam:ID]]" in prompt
    assert "geen aanhef" in prompt
    assert "correct Nederlands" in prompt


# ── What a new letter starts with (Koen, 17 September 2026) ──────────────────

def test_een_nieuwe_brief_start_met_voorbije_en_volgende_activiteiten(db_session, monkeypatch):
    """Past: what took place since the previous letter went out. Coming: the
    next three months. Older and further activities are left for the picker.

    Broken on purpose: `default_sources` ignoring the previous letter (always
    three months back) → the activity from before that letter is included and
    this test fails.
    """
    from datetime import datetime, timezone

    vorige = nb.create_newsletter(db_session, created_by="s@example.org")
    nb.update_draft(db_session, vorige, subject="Vorige", body_html="<div>x</div>",
                    audience=AUDIENCE_MEMBERS)
    vorige.status = LETTER_SENT
    vorige.send_started_at = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.commit()

    voor_de_vorige = _activity(db_session, "Voor de vorige brief", days_ahead=-45)
    sindsdien = _activity(db_session, "Sinds de vorige brief", days_ahead=-10)
    binnenkort = _activity(db_session, "Binnenkort", days_ahead=40)
    te_ver = _activity(db_session, "Te ver", days_ahead=120)

    letter = nb.create_newsletter(db_session, created_by="s@example.org")

    assert sindsdien.id in letter.draft_activity_ids
    assert binnenkort.id in letter.draft_activity_ids
    assert voor_de_vorige.id not in letter.draft_activity_ids
    assert te_ver.id not in letter.draft_activity_ids


def test_een_voorbije_activiteit_krijgt_geen_inschrijflink(db_session):
    voorbij = _activity(db_session, "Raak Café", days_ahead=-5, price="5")
    komt = _activity(db_session, "Zo vader zo zoon", days_ahead=5, price="5")
    facts = nb.activity_facts(db_session, [voorbij.id, komt.id], base_url=BASE)

    assert "inschrijven" not in nb.activity_line_html(facts[voorbij.id])
    assert "inschrijven" in nb.activity_line_html(facts[komt.id])


def test_de_prompt_vraagt_eerst_terugblik_dan_vooruitblik():
    prompt = drafting.SYSTEM_PROMPT
    assert "TERUGBLIK" in prompt and "VOORUITBLIK" in prompt
    assert prompt.index("TERUGBLIK") < prompt.index("VOORUITBLIK")
    assert "INTERN" in prompt


def test_de_nieuwste_beurt_staat_bovenaan(client, db_session, monkeypatch, raakje):
    """Koen, 17 September 2026: older conversations move down; within a turn the
    question stays above its answer."""
    headers = _login(client)
    _switch(db_session, monkeypatch, True)
    letter = _letter(db_session)
    raakje(_draft(["Eerste voorstel."], reply="Antwoord een."), _verdict(),
           _piece("Tweede stuk.", reply="Antwoord twee."), _verdict())

    client.post(f"/admin/nieuwsbrieven/{letter.id}/raakje/vraag", headers=headers,
                data={"instruction": "Vraag een", "body_html": ""})
    html = client.post(f"/admin/nieuwsbrieven/{letter.id}/raakje/vraag", headers=headers,
                       data={"instruction": "Vraag twee",
                             "body_html": "<div>Er staat al tekst.</div>"}).text

    assert html.index("Vraag twee") < html.index("Antwoord twee") < html.index("Vraag een") \
        < html.index("Antwoord een")
    assert html.index("Gesprek met Raakje") < html.index("Vraag twee")


# ── Raakje kan alles wat de knoppen kunnen (Koen, 19 September 2026) ─────────

def test_raakje_zet_de_kalender_en_de_afsluiting(db_session, raakje):
    """"Raakje zou alles moeten kunnen (muv bijlagen invoegen)." De markeringen
    zonder nummer worden door het portaal gevuld, net als de knoppen.

    Broken on purpose: `_PLAIN_MARKER` niet meer herkend in `_paragraph_html` →
    de kalenderregel en de afsluiting verdwijnen en deze test faalt.
    """
    fuif = _activity(db_session, "Herfstfuif", days_ahead=14)
    letter = _letter(db_session, activity_ids=[fuif.id])
    raakje(_draft(["# Wat komt er aan", "[[kalender]]", "[[afsluiting]]"]), _verdict())

    turn = _ask(db_session, letter)

    html = turn.proposal["operations"][0]["html"]
    assert "Herfstfuif" in html, "de kalender staat er als compacte regel"
    assert "[[kalender]]" not in html and "[[afsluiting]]" not in html
    assert "Tot binnenkort!" in html


def test_een_markering_zonder_nummer_wordt_niet_als_verzonnen_gemarkeerd(db_session, raakje):
    """Een markering is geen proza: ze mag de feitencontrole niet triggeren."""
    fuif = _activity(db_session, "Herfstfuif", days_ahead=14)
    letter = _letter(db_session, activity_ids=[fuif.id])
    raakje(_draft(["# Wat komt er aan", "[[kalender]]"]), _verdict())

    turn = _ask(db_session, letter)

    quotes = [m["quote"] for m in turn.proposal["marks"]]
    assert not [q for q in quotes if "kalender" in q]


def test_een_kopje_met_twee_hekjes_is_ook_een_kopje(db_session, raakje):
    """Koen, 20 september 2026: Raakje schreef "## Spel en plezier" en dat kwam
    letterlijk in de brief terecht.

    Broken on purpose: `_HEADING` terug naar `line.startswith("# ")` → de regel
    met twee hekjes wordt gewone tekst en deze test faalt.
    """
    letter = _letter(db_session)
    raakje(_draft(["## Spel en plezier", "Er valt veel te beleven."]), _verdict())

    turn = _ask(db_session, letter)

    html = turn.proposal["operations"][0]["html"]
    assert "<h1>Spel en plezier</h1>" in html
    assert "#" not in html, "geen hekjes in de brief"


def test_geen_kopje_dat_de_titel_van_het_blok_herhaalt(db_session, raakje):
    """Koen, 20 september 2026: boven élk blok stond een kopje met precies de
    naam die het blok zelf al als titel draagt.

    Broken on purpose: `_without_duplicate_headings` uit `_paragraph_html` → het
    dubbele kopje staat er weer en deze test faalt.
    """
    brood = _activity(db_session, "Brood en Spelen")
    letter = _letter(db_session, activity_ids=[brood.id])
    raakje(_draft(["# Wat er aankomt", "Het najaar zit vol.",
                   "# Brood en Spelen", "Een middag vol spel.",
                   f"[[activiteit:{brood.id}]]"]), _verdict())

    turn = _ask(db_session, letter)

    html = turn.proposal["operations"][0]["html"]
    assert "<h1>Wat er aankomt</h1>" in html, "een kopje over een ONDERDEEL blijft"
    assert "<h1>Brood en Spelen</h1>" not in html, "het dubbele kopje is weg"
    assert "Een middag vol spel." in html, "de zin eronder blijft staan"


def test_een_naam_plakt_niet_tegen_het_leesteken(db_session, raakje):
    brood = _activity(db_session, "Brood en Spelen")
    letter = _letter(db_session, activity_ids=[brood.id])
    raakje(_draft([f"We proostten tijdens [[naam:{brood.id}]] ."]), _verdict())

    turn = _ask(db_session, letter)

    assert "</strong>." in turn.proposal["operations"][0]["html"]


def test_de_groet_staat_maar_een_keer_onder_een_volledige_brief(db_session, raakje):
    """Koen, 20 september 2026: hij vroeg Raakje uitdrukkelijk om de afsluiting
    en kreeg ze twee keer — het portaal zet er onder élke volledige brief al een.

    Broken on purpose: `_CLOSING_MARKER.sub` uit `apply` → de groet staat er
    weer twee keer en deze test faalt.
    """
    letter = _letter(db_session)
    raakje(_draft(["# Wat er aankomt", "Het najaar zit vol.", "[[afsluiting]]"]), _verdict())
    turn = _ask(db_session, letter)
    message = drafting.record(db_session, letter, author_text="schrijf de brief", turn=turn)

    html = drafting.apply(db_session, letter, message, keep=set(), body_html="",
                          base_url=BASE).html

    assert html.count("Tot binnenkort!") == 1
    assert "[[afsluiting]]" not in html


def test_een_verkeerd_gespelde_markering_wordt_toch_ingevuld(db_session, raakje):
    """Koen, 20 september 2026: Raakje schreef "[[nam:7]]" en dat kwam
    letterlijk in de brief terecht, want alleen het exacte woord telde.

    Broken on purpose: `_kind_of` terug naar een vaste woordenlijst in `_MARKER`
    → de markering blijft letterlijk staan en deze test faalt.
    """
    comedy = _activity(db_session, "Comedy Festival")
    letter = _letter(db_session, activity_ids=[comedy.id])
    raakje(_draft([f"We genoten van een hilarisch [[nam:{comedy.id}]] in Miloheem."]),
           _verdict())

    turn = _ask(db_session, letter)

    html = turn.proposal["operations"][0]["html"]
    assert "<strong>Comedy Festival</strong>" in html
    assert "[[" not in html, "geen rauwe markering voor de lezer"


def test_een_markering_die_niets_betekent_laat_niets_achter(db_session, raakje):
    letter = _letter(db_session)
    raakje(_draft(["Een zin.", "[[onzin]]", "Nog een zin."]), _verdict())

    turn = _ask(db_session, letter)

    assert "[[" not in turn.proposal["operations"][0]["html"]


def test_elke_markering_toont_de_zin_waarover_ze_gaat(db_session, client, raakje,
                                                      monkeypatch):
    """Koen, 21 september 2026: met vier vinkjes onder elkaar wist hij niet meer
    welk vinkje bij welke bewering hoorde.

    Broken on purpose: de regel met `mark.sentence` uit `_nb_raakje.html` → het
    vinkje staat er weer zonder zijn zin en deze test faalt.
    """
    _switch(db_session, monkeypatch, True)  # zonder de schakelaar is er geen paneel
    letter = _letter(db_session)
    raakje(_draft(["We verwachten 250 deelnemers.", "Het wordt gezellig."]), _verdict())
    turn = _ask(db_session, letter)
    drafting.record(db_session, letter, author_text="schrijf de brief", turn=turn)
    _login(client)

    scherm = client.get(f"/admin/nieuwsbrieven/{letter.id}").text

    zinnen = [m["sentence"] for m in turn.proposal["marks"]]
    assert zinnen, "de controle hoort hier iets te markeren"
    for zin in zinnen:
        assert f"«{zin}»" in scherm, zin
    assert 'name="keep"' in scherm
