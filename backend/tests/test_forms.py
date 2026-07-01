"""Tests voor de form engine (#327)."""
from app.database import SessionLocal
from app.models.email_log import EmailLog
from app.models.form import FormSubmission, FormSubmissionAnswer


def _form_payload(**overrides):
    payload = {
        "title": "Helpers Brood en Spelen",
        "description": "Geef je op als helper",
        "status": "open",
        "send_confirmation": False,
        "allow_edit": False,
        "fields": [
            {"field_type": "email", "label": "Email", "required": True, "position": 0},
            {"field_type": "text", "label": "Naam", "required": True, "position": 1},
            {
                "field_type": "checkbox", "label": "Zaterdag namiddag", "position": 2,
                "options": [
                    {"label": "Bonnekes 14u", "position": 0},
                    {"label": "BBQ bakken", "position": 1},
                    {"label": "Sjoelbak", "position": 2},
                ],
            },
            {"field_type": "rating", "label": "Tevredenheid", "position": 3},
            {"field_type": "textarea", "label": "Opmerking", "position": 4},
        ],
    }
    payload.update(overrides)
    return payload


def _create_form(client, admin_headers, **overrides):
    resp = client.post("/api/v1/forms", json=_form_payload(**overrides), headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _field_id(form, label):
    return next(f["id"] for f in form["fields"] if f["label"] == label)


def _option_id(form, field_label, opt_label):
    field = next(f for f in form["fields"] if f["label"] == field_label)
    return next(o["id"] for o in field["options"] if o["label"] == opt_label)


# ── CRUD + autorisatie ──────────────────────────────────────────────────────────

def test_create_requires_admin(client):
    assert client.post("/api/v1/forms", json=_form_payload()).status_code == 401


def test_create_generates_unique_share_token(client, admin_headers):
    f1 = _create_form(client, admin_headers)
    f2 = _create_form(client, admin_headers)
    assert f1["share_token"] and f2["share_token"]
    assert f1["share_token"] != f2["share_token"]


def test_invalid_field_type_rejected(client, admin_headers):
    bad = _form_payload(fields=[{"field_type": "date", "label": "Wanneer", "position": 0}])
    assert client.post("/api/v1/forms", json=bad, headers=admin_headers).status_code == 422


# ── Publieke render ─────────────────────────────────────────────────────────────

def test_draft_form_not_public(client, admin_headers):
    form = _create_form(client, admin_headers, status="draft")
    assert client.get(f"/api/v1/forms/by-token/{form['share_token']}").status_code == 404


def test_unknown_token_404(client):
    assert client.get("/api/v1/forms/by-token/onbestaand").status_code == 404


def test_public_form_hides_internals(client, admin_headers):
    form = _create_form(client, admin_headers)
    pub = client.get(f"/api/v1/forms/by-token/{form['share_token']}").json()
    assert pub["title"] == form["title"]
    assert "share_token" not in pub  # PublicForm lekt de token niet terug


# ── Inzending + validatie ───────────────────────────────────────────────────────

def test_submit_missing_required_422(client, admin_headers):
    form = _create_form(client, admin_headers)
    token = form["share_token"]
    body = {"answers": [{"field_id": _field_id(form, "Naam"), "text": "Jan"}]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 422


def test_submit_valid_and_checkbox_creates_multiple_answers(client, admin_headers, db_session):
    form = _create_form(client, admin_headers)
    token = form["share_token"]
    body = {
        "submitter_name": "Jan",
        "submitter_email": "jan@example.com",
        "answers": [
            {"field_id": _field_id(form, "Email"), "text": "jan@example.com"},
            {"field_id": _field_id(form, "Naam"), "text": "Jan"},
            {"field_id": _field_id(form, "Zaterdag namiddag"), "option_ids": [
                _option_id(form, "Zaterdag namiddag", "Bonnekes 14u"),
                _option_id(form, "Zaterdag namiddag", "BBQ bakken"),
            ]},
            {"field_id": _field_id(form, "Tevredenheid"), "rating": 5},
        ],
    }
    resp = client.post(f"/api/v1/forms/by-token/{token}/submit", json=body)
    assert resp.status_code == 200, resp.text
    sub_id = resp.json()["id"]
    # Checkbox met 2 vinkjes → 2 antwoordrijen.
    opt_rows = (
        db_session.query(FormSubmissionAnswer)
        .filter(FormSubmissionAnswer.submission_id == sub_id)
        .filter(FormSubmissionAnswer.value_option_id.isnot(None))
        .count()
    )
    assert opt_rows == 2
    rating_row = (
        db_session.query(FormSubmissionAnswer)
        .filter(FormSubmissionAnswer.submission_id == sub_id)
        .filter(FormSubmissionAnswer.value_rating.isnot(None))
        .one()
    )
    assert rating_row.value_rating == 5


def test_invalid_email_rejected(client, admin_headers):
    form = _create_form(client, admin_headers)
    token = form["share_token"]
    body = {"answers": [
        {"field_id": _field_id(form, "Email"), "text": "geen-email"},
        {"field_id": _field_id(form, "Naam"), "text": "Jan"},
    ]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 422


def test_rating_out_of_range_rejected(client, admin_headers):
    form = _create_form(client, admin_headers)
    token = form["share_token"]
    body = {"answers": [
        {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
        {"field_id": _field_id(form, "Naam"), "text": "Jan"},
        {"field_id": _field_id(form, "Tevredenheid"), "rating": 9},
    ]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 422


def test_submit_on_closed_form_rejected(client, admin_headers):
    form = _create_form(client, admin_headers, status="closed")
    token = form["share_token"]
    body = {"answers": [
        {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
        {"field_id": _field_id(form, "Naam"), "text": "Jan"},
    ]}
    # Closed is publiek zichtbaar maar weigert inzendingen.
    assert client.get(f"/api/v1/forms/by-token/{token}").status_code == 200
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 403


def test_max_submissions_enforced(client, admin_headers):
    form = _create_form(client, admin_headers, max_submissions=1)
    token = form["share_token"]
    body = {"answers": [
        {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
        {"field_id": _field_id(form, "Naam"), "text": "Jan"},
    ]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 200
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 403


# ── Resultaten-aggregatie ───────────────────────────────────────────────────────

def test_results_aggregation(client, admin_headers):
    form = _create_form(client, admin_headers)
    token = form["share_token"]

    def submit(rating, opt_labels):
        body = {"answers": [
            {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
            {"field_id": _field_id(form, "Naam"), "text": "Jan"},
            {"field_id": _field_id(form, "Tevredenheid"), "rating": rating},
            {"field_id": _field_id(form, "Zaterdag namiddag"),
             "option_ids": [_option_id(form, "Zaterdag namiddag", l) for l in opt_labels]},
        ]}
        assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 200

    submit(5, ["Bonnekes 14u"])
    submit(3, ["Bonnekes 14u", "BBQ bakken"])

    res = client.get(f"/api/v1/forms/{form['id']}/results", headers=admin_headers).json()
    assert res["submission_count"] == 2
    rating = next(f for f in res["fields"] if f["label"] == "Tevredenheid")
    assert rating["average"] == 4.0
    assert sum(d["count"] for d in rating["distribution"]) == 2
    checkbox = next(f for f in res["fields"] if f["label"] == "Zaterdag namiddag")
    counts = {o["label"]: o["count"] for o in checkbox["options"]}
    assert counts["Bonnekes 14u"] == 2
    assert counts["BBQ bakken"] == 1
    assert counts["Sjoelbak"] == 0


# ── Export ──────────────────────────────────────────────────────────────────────

def test_export_csv_and_ods(client, admin_headers):
    form = _create_form(client, admin_headers)
    token = form["share_token"]
    client.post(f"/api/v1/forms/by-token/{token}/submit", json={"answers": [
        {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
        {"field_id": _field_id(form, "Naam"), "text": "Jan"},
    ]})
    csv_resp = client.get(f"/api/v1/forms/{form['id']}/export?format=csv", headers=admin_headers)
    assert csv_resp.status_code == 200
    assert b"Naam" in csv_resp.content and b"Jan" in csv_resp.content
    ods_resp = client.get(f"/api/v1/forms/{form['id']}/export?format=ods", headers=admin_headers)
    assert ods_resp.status_code == 200
    assert ods_resp.headers["content-type"] == "application/vnd.oasis.opendocument.spreadsheet"


# ── Bevestigingsmail + wijzig-flow ──────────────────────────────────────────────

def test_confirmation_email_logged_when_enabled(client, admin_headers):
    form = _create_form(client, admin_headers, send_confirmation=True)
    token = form["share_token"]
    recipient = "confirm-flow@example.com"
    client.post(f"/api/v1/forms/by-token/{token}/submit", json={
        "submitter_email": recipient,
        "answers": [
            {"field_id": _field_id(form, "Email"), "text": recipient},
            {"field_id": _field_id(form, "Naam"), "text": "Jan"},
        ],
    })
    s = SessionLocal()
    try:
        rows = s.query(EmailLog).filter(EmailLog.recipient == recipient).all()
    finally:
        s.close()
    assert any(r.email_type == "form_confirmation" for r in rows)


def test_no_edit_token_without_allow_edit(client, admin_headers):
    form = _create_form(client, admin_headers)
    token = form["share_token"]
    resp = client.post(f"/api/v1/forms/by-token/{token}/submit", json={"answers": [
        {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
        {"field_id": _field_id(form, "Naam"), "text": "Jan"},
    ]})
    assert resp.json()["edit_token"] is None


def test_edit_flow(client, admin_headers):
    form = _create_form(client, admin_headers, allow_edit=True)
    token = form["share_token"]
    resp = client.post(f"/api/v1/forms/by-token/{token}/submit", json={
        "submitter_name": "Jan",
        "answers": [
            {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
            {"field_id": _field_id(form, "Naam"), "text": "Jan"},
            {"field_id": _field_id(form, "Tevredenheid"), "rating": 2},
        ],
    })
    edit_token = resp.json()["edit_token"]
    assert edit_token

    got = client.get(f"/api/v1/forms/edit/{edit_token}")
    assert got.status_code == 200
    assert got.json()["submitter_name"] == "Jan"

    upd = client.put(f"/api/v1/forms/edit/{edit_token}", json={
        "submitter_name": "Jan Aangepast",
        "answers": [
            {"field_id": _field_id(form, "Email"), "text": "a@b.be"},
            {"field_id": _field_id(form, "Naam"), "text": "Jan"},
            {"field_id": _field_id(form, "Tevredenheid"), "rating": 4},
        ],
    })
    assert upd.status_code == 200
    again = client.get(f"/api/v1/forms/edit/{edit_token}").json()
    rating_answer = next(a for a in again["answers"] if a["rating"] is not None)
    assert rating_answer["rating"] == 4


def test_edit_unknown_token_404(client):
    assert client.get("/api/v1/forms/edit/onbestaand").status_code == 404


# ── Secties + info + "Andere…" (#335, #337) ─────────────────────────────────────

def _sectioned_payload():
    return {
        "title": "Enquête met secties",
        "status": "open",
        "sections": [
            {"title": "Intro", "description": "Welkom", "position": 0},
            {"title": "Vragen", "description": None, "position": 1},
        ],
        "fields": [
            {"field_type": "info", "label": "Beste families", "help_text": "Korte uitleg",
             "required": True, "position": 0, "section_index": 0},
            {"field_type": "text", "label": "Naam", "required": True, "position": 1, "section_index": 1},
            {"field_type": "checkbox", "label": "Waarom niet?", "position": 2, "section_index": 1,
             "options": [
                 {"label": "Geen tijd", "position": 0},
                 {"label": "Andere", "position": 1, "is_other": True},
             ]},
        ],
    }


def test_sections_returned_and_fields_linked(client, admin_headers):
    form = client.post("/api/v1/forms", json=_sectioned_payload(), headers=admin_headers).json()
    assert len(form["sections"]) == 2
    naam = next(f for f in form["fields"] if f["label"] == "Naam")
    intro_section = next(s for s in form["sections"] if s["title"] == "Intro")
    vragen_section = next(s for s in form["sections"] if s["title"] == "Vragen")
    assert naam["section_id"] == vragen_section["id"]
    info = next(f for f in form["fields"] if f["field_type"] == "info")
    assert info["section_id"] == intro_section["id"]
    # Publiek formulier geeft secties + is_other mee.
    pub = client.get(f"/api/v1/forms/by-token/{form['share_token']}").json()
    assert len(pub["sections"]) == 2
    checkbox = next(f for f in pub["fields"] if f["label"] == "Waarom niet?")
    assert any(o["is_other"] for o in checkbox["options"])


def test_info_field_never_required(client, admin_headers):
    # Een 'info'-veld met required=true mag een inzending nooit blokkeren.
    form = client.post("/api/v1/forms", json=_sectioned_payload(), headers=admin_headers).json()
    token = form["share_token"]
    naam_id = next(f["id"] for f in form["fields"] if f["label"] == "Naam")
    resp = client.post(f"/api/v1/forms/by-token/{token}/submit", json={
        "answers": [{"field_id": naam_id, "text": "Jan"}],
    })
    assert resp.status_code == 200, resp.text


def test_other_option_stores_free_text(client, admin_headers, db_session):
    form = client.post("/api/v1/forms", json=_sectioned_payload(), headers=admin_headers).json()
    token = form["share_token"]
    naam_id = next(f["id"] for f in form["fields"] if f["label"] == "Naam")
    checkbox = next(f for f in form["fields"] if f["label"] == "Waarom niet?")
    other_opt = next(o for o in checkbox["options"] if o["is_other"])
    resp = client.post(f"/api/v1/forms/by-token/{token}/submit", json={
        "answers": [
            {"field_id": naam_id, "text": "Jan"},
            {"field_id": checkbox["id"], "option_ids": [other_opt["id"]], "other_text": "Op reis"},
        ],
    })
    assert resp.status_code == 200, resp.text
    row = (
        db_session.query(FormSubmissionAnswer)
        .filter(FormSubmissionAnswer.submission_id == resp.json()["id"])
        .filter(FormSubmissionAnswer.value_option_id == other_opt["id"])
        .one()
    )
    assert row.value_text == "Op reis"
    # Export toont "Andere: Op reis".
    csv = client.get(f"/api/v1/forms/{form['id']}/export?format=csv", headers=admin_headers)
    assert "Op reis".encode() in csv.content


def test_loose_coupling_no_person_fk():
    # Inzending bewaart enkel vrije naam/e-mail — geen koppeling naar het ledendomein.
    cols = {c.name for c in FormSubmission.__table__.columns}
    assert "person_id" not in cols and "member_id" not in cols


# ── Branching / secties + skip-logica (#336) ─────────────────────────────────────

def _branching_payload():
    """Enquête met sectie-sprongen: Start → (Ja) Wel / (Nee) Niet → Slot.
    Wel springt over Niet naar Slot; Niet valt lineair door naar Slot."""
    return {
        "title": "Ledenfeest-enquête",
        "status": "open",
        "sections": [
            {"title": "Start", "position": 0},
            {"title": "Wel aanwezig", "position": 1, "next_section_index": 3},
            {"title": "Niet aanwezig", "position": 2},
            {"title": "Slot", "position": 3},
        ],
        "fields": [
            {"field_type": "radio", "label": "Aanwezig?", "required": True, "position": 0,
             "section_index": 0, "options": [
                 {"label": "Ja", "position": 0, "skip_to_section_index": 1},
                 {"label": "Nee", "position": 1, "skip_to_section_index": 2},
             ]},
            {"field_type": "text", "label": "Wat was leuk?", "required": True, "position": 1, "section_index": 1},
            {"field_type": "text", "label": "Waarom niet?", "required": True, "position": 2, "section_index": 2},
            {"field_type": "text", "label": "Slotopmerking", "required": True, "position": 3, "section_index": 3},
        ],
    }


def _mk(client, admin_headers, payload):
    r = client.post("/api/v1/forms", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_branching_skips_other_branch(client, admin_headers):
    form = _mk(client, admin_headers, _branching_payload())
    token = form["share_token"]
    ja = _option_id(form, "Aanwezig?", "Ja")
    # Ja-tak: Wel + Slot ingevuld, "Waarom niet?" (Niet-tak) overgeslagen → OK.
    body = {"answers": [
        {"field_id": _field_id(form, "Aanwezig?"), "option_ids": [ja]},
        {"field_id": _field_id(form, "Wat was leuk?"), "text": "De sfeer"},
        {"field_id": _field_id(form, "Slotopmerking"), "text": "Top"},
    ]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 200


def test_branching_required_in_taken_branch_enforced(client, admin_headers):
    form = _mk(client, admin_headers, _branching_payload())
    token = form["share_token"]
    ja = _option_id(form, "Aanwezig?", "Ja")
    # Ja-tak maar "Wat was leuk?" (verplicht, in doorlopen sectie) ontbreekt → 422.
    body = {"answers": [
        {"field_id": _field_id(form, "Aanwezig?"), "option_ids": [ja]},
        {"field_id": _field_id(form, "Slotopmerking"), "text": "Top"},
    ]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 422


def test_branching_nee_branch(client, admin_headers):
    form = _mk(client, admin_headers, _branching_payload())
    token = form["share_token"]
    nee = _option_id(form, "Aanwezig?", "Nee")
    body = {"answers": [
        {"field_id": _field_id(form, "Aanwezig?"), "option_ids": [nee]},
        {"field_id": _field_id(form, "Waarom niet?"), "text": "Op reis"},
        {"field_id": _field_id(form, "Slotopmerking"), "text": "Volgend jaar wel"},
    ]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 200


def test_skip_to_end_ignores_later_sections(client, admin_headers):
    payload = {
        "title": "Skip-to-end",
        "status": "open",
        "sections": [
            {"title": "Start", "position": 0},
            {"title": "Vervolg", "position": 1},
        ],
        "fields": [
            {"field_type": "radio", "label": "Stoppen?", "required": True, "position": 0,
             "section_index": 0, "options": [
                 {"label": "Stop nu", "position": 0, "skip_to_end": True},
                 {"label": "Ga door", "position": 1, "skip_to_section_index": 1},
             ]},
            {"field_type": "text", "label": "Vervolgvraag", "required": True, "position": 1, "section_index": 1},
        ],
    }
    form = _mk(client, admin_headers, payload)
    token = form["share_token"]
    stop = _option_id(form, "Stoppen?", "Stop nu")
    # "Stop nu" → einde; de verplichte "Vervolgvraag" wordt niet afgedwongen.
    body = {"answers": [{"field_id": _field_id(form, "Stoppen?"), "option_ids": [stop]}]}
    assert client.post(f"/api/v1/forms/by-token/{token}/submit", json=body).status_code == 200


def test_branching_only_on_choice_fields(client, admin_headers):
    payload = _branching_payload()
    # Zet een skip op een checkbox-optie → moet geweigerd worden.
    payload["fields"][0]["field_type"] = "checkbox"
    assert client.post("/api/v1/forms", json=payload, headers=admin_headers).status_code == 422


def test_backward_section_jump_rejected(client, admin_headers):
    payload = _branching_payload()
    payload["sections"][3]["next_section_index"] = 1  # Slot terug naar Wel = lus
    assert client.post("/api/v1/forms", json=payload, headers=admin_headers).status_code == 422


def test_empty_label_rejected(client, admin_headers):
    bad = _form_payload(fields=[{"field_type": "text", "label": "   ", "position": 0}])
    assert client.post("/api/v1/forms", json=bad, headers=admin_headers).status_code == 422


def test_branch_config_persisted_on_form_and_sections(client, admin_headers):
    """De branch-config (sectie-sprong + keuze-sprong) wordt bewaard en correct
    teruggegeven met de juiste sectie-ids."""
    form = _mk(client, admin_headers, _branching_payload())
    fetched = client.get(f"/api/v1/forms/{form['id']}", headers=admin_headers).json()
    secs = sorted(fetched["sections"], key=lambda s: s["position"])
    slot_id = secs[3]["id"]
    wel_id = secs[1]["id"]
    niet_id = secs[2]["id"]
    # Sectie-sprong: "Wel aanwezig" (index 1) springt naar "Slot" (index 3).
    assert secs[1]["next_section_id"] == slot_id
    assert secs[1]["next_is_end"] is False
    # Keuze-sprong: Ja → Wel, Nee → Niet.
    radio = next(f for f in fetched["fields"] if f["label"] == "Aanwezig?")
    by_label = {o["label"]: o for o in radio["options"]}
    assert by_label["Ja"]["skip_to_section_id"] == wel_id
    assert by_label["Nee"]["skip_to_section_id"] == niet_id
