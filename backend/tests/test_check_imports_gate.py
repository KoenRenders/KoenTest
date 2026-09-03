"""Guard on the import smoke test in `check_imports.py` (#583).

`check_imports.py` derives its module list from the `app` package instead of a
hand-written list, because that list rotted: in #581 it still named the removed
`app.ui.settings_ui`, CI stayed green and the HDEV deploy build failed.

Derivation removes that failure mode but introduces another: discovery that
quietly finds nothing, or misses a corner of the tree, would make the whole check
pass vacuously. These tests compare discovery against the files on disk.

Importing the module is safe — the smoke test itself only runs under
`if __name__ == "__main__"`.
"""
from pathlib import Path

import check_imports

APP = Path(check_imports.app.__file__).resolve().parent


def _modules_on_disk() -> set[str]:
    """Every dotted name under `app/` that a `.py` file makes importable."""
    names = set()
    for path in APP.rglob("*.py"):
        parts = path.relative_to(APP.parent).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.add(".".join(parts))
    return names


def test_discovery_finds_every_module_on_disk():
    missing = _modules_on_disk() - set(check_imports.discover()) - set(check_imports.SKIP)
    assert not missing, (
        "check_imports.py would not import these modules, so a broken import in "
        "them reaches the deploy build unseen:\n  " + "\n  ".join(sorted(missing))
    )


def test_discovery_invents_nothing():
    extra = set(check_imports.discover()) - _modules_on_disk()
    assert not extra, "Discovered names without a file on disk: " + ", ".join(sorted(extra))


def test_discovery_is_substantial():
    """A collapsed walk (empty or near-empty) would make the check pass vacuously."""
    found = check_imports.discover()
    assert len(found) > 100, f"Only {len(found)} modules discovered — did the walk collapse?"
    for anchor in ("app.main", "app.ui.tenants_ui", "app.domains.forms.admin_ui"):
        assert anchor in found, f"{anchor} not discovered"


def test_skips_are_documented_and_still_exist():
    """A skip that outlives its module is a blind spot nobody notices."""
    stale = [m for m in check_imports.SKIP if m not in _modules_on_disk()]
    assert not stale, "SKIP names modules that no longer exist: " + ", ".join(stale)
