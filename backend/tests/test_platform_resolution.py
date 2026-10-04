"""#821 — you silently switched afdeling.

`resolve_request` consults the tenant cookie **only on a platform host**. On PROD
`PLATFORM_HOSTS` was empty — the variable was in `.env.prod` but not in the compose
`environment:` block — so that cookie was set and never read.

The navigation of a tenant site consists of absolute paths WITHOUT a prefix. Measured
on the Voorbeeldafdeling: `/aanmelden`, `/archief`, `/lid-worden`, and **zero** links
carrying a prefix. So you entered one afdeling through the prefix and after a single
click you were on another — no error message, and a registration form for the wrong
afdeling.

**These tests check behaviour, not whether the variable appears somewhere in a file.**
That last one was the false reassurance here: the name sat neatly in `.env`.

Broken on purpose to check that these tests can go red: emptied `platform_hosts` (the
exact state measured on PROD) → the first two fall over, the third stays green because
path prefixes do not depend on this variable.

**That counterproof immediately found a bug in this test itself.** The first version
gave the second tenant id 2 — and `DEFAULT_TENANT_ID` IS 2, so "you stay on the same
afdeling" held no matter what happened. With an empty `platform_hosts` it stayed green.
Hence `OTHER_TENANT = 7` below: an id that cannot be anything else.
"""

import pytest

from app.kernel.tenancy import DEFAULT_TENANT_ID, resolve_request

pytestmark = pytest.mark.ui_agnostisch

# MIND THE NUMBER: `DEFAULT_TENANT_ID` is 2, so a second tenant with id 2 makes every
# assertion below true without proving anything. That is exactly what happened in the
# first version of this test — the counterproof left it green, and only then did it
# show. Hence 7: an id that can be nothing other than "the other afdeling".
OTHER_TENANT = 7
CODES = {"raakmillegem": DEFAULT_TENANT_ID, "raakvoorbeeld": OTHER_TENANT}
PLATFORM = {"platform.voorbeeld.test"}


def _resolve(host, path, cookie=None, platform=PLATFORM):
    return resolve_request(host, path, cookie, {}, platform, CODES)


def test_you_stay_on_the_same_afdeling_after_a_path_without_prefix():
    """The worst consequence, and the test that was red today.

    Entering through the prefix sets the tenant cookie; the next request is an absolute
    path without a prefix. That should land on the same afdeling.
    """
    tenant, path = _resolve("platform.voorbeeld.test", "/raakvoorbeeld/activiteiten")
    assert tenant == OTHER_TENANT and path == "/activiteiten"

    # The way the navigation does it: absolute, without a prefix, WITH the cookie.
    tenant_after, _path = _resolve(
        "platform.voorbeeld.test", "/activiteiten", cookie="raakvoorbeeld"
    )

    assert tenant_after == OTHER_TENANT, (
        "after a single click you are on a different afdeling — with a registration "
        "form for the wrong association"
    )


def test_the_root_of_a_platform_host_is_the_landing_page():
    """Without a platform row the root falls to the default tenant; with one it is
    the platform's own home page (#1543), whose flag went with the landing."""
    tenant, path = _resolve("platform.voorbeeld.test", "/")

    assert path is None and tenant == DEFAULT_TENANT_ID


def test_a_path_prefix_works_without_platform_hosts():
    """What was NOT broken, and that deserves to be recorded.

    The prefix is matched before host or cookie are looked at, so that path is
    independent of `PLATFORM_HOSTS`. Without this test a later "simplification" could
    reverse that order without anything failing.
    """
    tenant, path = _resolve("whatever.test", "/raakvoorbeeld/activiteiten", platform=set())

    assert tenant == OTHER_TENANT and path == "/activiteiten"


def test_a_cookie_does_not_apply_on_an_ordinary_host():
    """The counterproof to the first test: the cookie must not apply everywhere.

    On the domain of one afdeling a lingering cookie would otherwise show a DIFFERENT
    afdeling — the same kind of confusion, but in the place where the visitor most
    needs to be certain where they are.
    """
    tenant, _path = _resolve("www.voorbeeld.test", "/activiteiten", cookie="raakvoorbeeld")

    assert tenant == DEFAULT_TENANT_ID


def test_the_landing_page_carries_no_brand_and_points_at_no_afdeling(platform_workspace):
    """#821 — the platform does not belong to one afdeling.

    The entrance for the platform administrator is on it too: the admin screen already
    existed, there simply was no way to reach it.

    Since #1543 the platform's home is an ordinary CMS page in the site shell, so this
    reads the rendered page and not a template: no "Raak" brand in its name, and its
    "Aanmelden" is the platform's own, not one afdeling's (`/<code>/aanmelden`). The
    afdelingen themselves may stand on it now — the sites placeholder lists them.
    """
    html = platform_workspace.get("/").text

    assert "Raak Digital Platform" not in html
    header = html[html.index("<header") : html.index("</header>")]
    assert 'aria-label="Raak"' not in header, "the RaaK wordmark on the platform's header"
    assert 'href="/aanmelden"' in html, "there is no entrance for the platform administrator"
    assert "/raakmillegem/aanmelden" not in html, (
        "the platform sends its administrator to one of its own afdelingen"
    )
