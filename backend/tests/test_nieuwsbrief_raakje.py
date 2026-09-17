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


def _edit(operations, reply="Aangepast."):
    return json.dumps({"reply": reply, "subject": None, "operations": operations})


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
    nb.set_draft_sources(db, letter, activity_ids=list(activity_ids), meeting_item_ids=[])
    return letter


def _ask(db, letter, instruction="Schrijf de najaarsbrief.", selection=""):
    return drafting.ask(db, letter, instruction=instruction, actor="s@example.org",
                        base_url=BASE, selection=selection)


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
    nb.set_draft_sources(db_session, letter, activity_ids=[], meeting_item_ids=[item.id])
    provider = raakje(_draft(["Er rijdt een bus voor iedereen."]), _verdict())

    turn = _ask(db_session, letter)

    assert "kris" not in provider.payloads()
    assert "vermeulen" not in provider.payloads()
    assert "[naam] regelt de bus" in provider.payloads()
    assert "Kris" not in json.dumps(turn.proposal)


def test_een_niet_aangevinkt_punt_gaat_nooit_mee(db_session, raakje):
    item = _sent_meeting_with_point(db_session, "<div>Geheim punt over de kas.</div>")
    letter = _letter(db_session)
    assert item.id not in letter.draft_meeting_item_ids
    provider = raakje(_draft(["Een brief."]), _verdict())

    _ask(db_session, letter)

    assert "geheim punt" not in provider.payloads()


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


def test_een_geblokkeerde_oproep_wordt_een_melding_en_geen_voorstel(db_session, raakje):
    """Names are scrubbed before the guard sees them; an e-mail address is not,
    and the guard refuses the call — visibly, as a message for the screen."""
    from app.domains.chatbot.api import SeamBlocked

    letter = _letter(db_session)
    raakje(_draft(["Een brief."]))
    with pytest.raises(SeamBlocked):
        _ask(db_session, letter, instruction="Mail iedereen via info@example.org")


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
    assert f"{BASE}/activiteiten/brood-en-spelen" in html
    assert "Dorpsplein" in html


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
                              body_html="", base_url=BASE)

        assert ("zaklopen" in html) is expected
        assert "Kom naar Brood &amp; Spelen!" in html
        assert "Het bestuur van" in html, "de afsluiting zet het portaal er zelf onder"
        assert message.proposal["status"] == "applied"


def test_een_wijziging_raakt_precies_haar_alinea(db_session, raakje):
    body = "<div>Eerste alinea.</div><div>Tweede alinea.</div><div>Derde alinea.</div>"
    letter = _letter(db_session, body=body)
    raakje(_edit([{"op": "replace", "paragraph": 2, "text": "Nieuwe tweede."},
                  {"op": "insert_after", "paragraph": 3, "text": "Een vierde."},
                  {"op": "remove", "paragraph": 1}]), _verdict())
    turn = _ask(db_session, letter, instruction="Pas aan.")
    message = _proposal_message(db_session, letter, turn)

    html = drafting.apply(db_session, letter, message, keep=set(),
                          body_html=letter.body_html, base_url=BASE)

    assert html == "<div>Nieuwe tweede.</div><div>Derde alinea.</div><div>Een vierde.</div>"


def test_een_wijziging_op_een_intussen_veranderde_brief_wordt_geweigerd(db_session, raakje):
    letter = _letter(db_session, body="<div>Een.</div><div>Twee.</div>")
    raakje(_edit([{"op": "remove", "paragraph": 2}]), _verdict())
    turn = _ask(db_session, letter, instruction="Schrap de tweede.")
    message = _proposal_message(db_session, letter, turn)

    with pytest.raises(drafting.DraftingError):
        drafting.apply(db_session, letter, message, keep=set(),
                       body_html="<div>Nul.</div><div>Een.</div><div>Twee.</div>",
                       base_url=BASE)
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
