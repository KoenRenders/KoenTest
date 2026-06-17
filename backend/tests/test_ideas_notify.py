"""Het contactformulier (/ideas) verwittigt het bestuur per e-mail (#260)."""


def test_ideas_endpoint_notifies_board(client, monkeypatch):
    import app.routers.ideas as ideas

    seen: dict = {}
    monkeypatch.setattr(ideas, "send_idea_acknowledgement", lambda **kw: None)
    monkeypatch.setattr(ideas, "send_idea_board_notification", lambda **kw: seen.update(kw))

    resp = client.post(
        "/api/v1/ideas",
        json={"submitter_name": "Mie", "submitter_email": "mie@example.com", "content": "Hallo bestuur"},
    )
    assert resp.status_code == 200
    assert seen.get("message") == "Hallo bestuur"
    assert seen.get("email") == "mie@example.com"


def test_ideas_endpoint_notifies_board_without_submitter_email(client, monkeypatch):
    """Ook zonder e-mail van de indiener wordt het bestuur verwittigd."""
    import app.routers.ideas as ideas

    seen: dict = {}
    monkeypatch.setattr(ideas, "send_idea_board_notification", lambda **kw: seen.update(kw))

    resp = client.post(
        "/api/v1/ideas",
        json={"submitter_name": "Anoniem", "content": "Vraagje"},
    )
    assert resp.status_code == 200
    assert seen.get("message") == "Vraagje"
