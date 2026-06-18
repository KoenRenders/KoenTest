"""De rate-limiter mag X-Forwarded-For niet blind vertrouwen (#268). Bij precies
één Caddy-hop is enkel het meest rechtse (door Caddy gezette) adres betrouwbaar;
het meest linkse is client-gestuurd en dus spoofbaar."""
from app.limiter import _client_ip


class _FakeRequest:
    def __init__(self, xff=None, client_host="10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}
        self.client = type("C", (), {"host": client_host})()


def test_client_ip_takes_rightmost_xff():
    assert _client_ip(_FakeRequest(xff="9.9.9.9, 203.0.113.7")) == "203.0.113.7"


def test_spoofed_leftmost_does_not_create_new_bucket():
    a = _client_ip(_FakeRequest(xff="1.1.1.1, 203.0.113.7"))
    b = _client_ip(_FakeRequest(xff="2.2.2.2, 203.0.113.7"))
    assert a == b == "203.0.113.7"


def test_client_ip_falls_back_to_peer_without_xff():
    assert _client_ip(_FakeRequest(xff=None, client_host="10.0.0.5")) == "10.0.0.5"
