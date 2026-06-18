"""Admin kan een bericht/idee definitief (hard) verwijderen (#279)."""
from app.models.idea import Idea


def _seed_idea(db_session, content="test"):
    idea = Idea(submitter_name="X", submitter_email="x@example.com", content=content)
    db_session.add(idea)
    db_session.commit()
    return idea.id


def test_delete_idea_requires_admin(client, db_session):
    idea_id = _seed_idea(db_session)
    assert client.delete(f"/api/v1/ideas/{idea_id}").status_code in (401, 403)


def test_admin_can_hard_delete_idea(client, db_session, admin_headers):
    idea_id = _seed_idea(db_session, content="weg")

    resp = client.delete(f"/api/v1/ideas/{idea_id}", headers=admin_headers)
    assert resp.status_code == 204

    # Echt weg: directe query vindt niets meer, en de admin-lijst bevat het niet.
    db_session.expire_all()
    assert db_session.query(Idea).filter(Idea.id == idea_id).first() is None
    listed = client.get("/api/v1/ideas", headers=admin_headers).json()
    assert all(i["id"] != idea_id for i in listed)


def test_delete_unknown_idea_returns_404(client, admin_headers):
    assert client.delete("/api/v1/ideas/999999", headers=admin_headers).status_code == 404
