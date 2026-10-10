"""The shop's screens answer 404 while the module is off (CR-21, T3).

The shop is off by default for every kind of tenant (Q49), so its screens are
not found for a tenant that has not switched it on. The rights that gate the
screens once the module is on are walked by the who-gets-in snapshot
(`test_who_gets_in_unchanged_1722.py`).
"""

from __future__ import annotations


def test_the_shop_being_off_makes_its_screens_404(client):
    assert client.get("/admin/producten", follow_redirects=False).status_code == 404
    assert client.get("/admin/producten/nieuw", follow_redirects=False).status_code == 404
    assert client.get("/admin/voorraad", follow_redirects=False).status_code == 404
