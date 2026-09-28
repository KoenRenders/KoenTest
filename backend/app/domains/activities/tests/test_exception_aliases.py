"""CR-13 §B4.4 — one English exception class per domain, the Dutch name an alias.

At the first touch of a domain in CR-13, its Dutch `*Fout` becomes an alias of one
English `*Error`: one class, two names. Existing `except ActiviteitFout` keeps
catching, new rules raise `ActivityError`, and the #780 ratchet sees one Dutch
name fewer, not one more. Phase 0a does it for `activities`, the domain phase 1
touches; each later phase does it for its own.

Broken on purpose to check this can go red (run, then restored), additively: a
line `class ActiviteitFout(ActivityError): pass` added under the alias in
`activities/models.py` → all three fail: two classes, the service path points at
the subclass, and `except ActiviteitFout` no longer catches `ActivityError`.
"""

from __future__ import annotations

import pytest

from app.domains.activities import models, service


def test_one_class_two_names():
    assert models.ActiviteitFout is models.ActivityError
    assert models.ActivityError.__name__ == "ActivityError"


def test_the_existing_path_through_the_service_is_the_same_class():
    """Routers import `ActiviteitFout` from the service; that must stay the one class."""
    assert service.ActiviteitFout is models.ActivityError


def test_an_existing_except_clause_still_catches_the_new_name():
    with pytest.raises(models.ActiviteitFout):
        raise models.ActivityError("a rule of activities was violated")
