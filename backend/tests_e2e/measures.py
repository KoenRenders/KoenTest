"""The measurement baseline of the pilot screens (#1605; CR-11 B7 test 11, Q60).

A screen is rendered against a FROZEN clock, and the positions, sizes and counts
of the elements that matter are compared with the numbers in
`tests_e2e/baselines/<screen>.json`. An element that moved by more than
`TOLERANCE` px, changed its size, or appears another number of times makes the
run red, and the message names the screen, the width, the element and the two
numbers. An intended change edits a number, in the same pull request, and the
diff shows which.

**Numbers, no images** (Koen, 5 October 2026). A baseline of pixels is a picture
of people and their payments in a public repository, and it differs between two
machines by tens of thousands of pixels (measured: Debian against Ubuntu, the
same browser). A baseline of measurements carries no data and reads in a diff.
`test_measure_compare.py` refuses an image file under `tests_e2e/`.

**What this cannot see**, and what does: a wrong typeface (`test_one_type_family`),
a wrong colour (`test_site_colours`), a clipped glyph, a missing icon inside an
element whose box stayed the same.

**Every element is named by a stable hook** — a `data-…` attribute, never a
class: a class is styling and changes with it. A hook a screen requires and
does not find FAILS, it does not skip: a baseline that measures nothing is
green forever.

**The stability protocol**, and where each part lives:

| part | where |
|---|---|
| fixed seed data, only read | `scripts/measure-run.sh` (called by `scripts/measure-local.sh` and by one step of the CI job): a database of its own, seeded once — the e2e seed plus `measure_seed.py` — never written by a test |
| the clock frozen | `MEASURE_NOW` below: the seeds and the server run under `faketime` at that moment, and the browser's own clock is set to it (`prepare`) |
| a fixed viewport and device scale | `Screen.widths` and `context_options` (scale 1) |
| fonts self-hosted and loaded, the browser pinned | `prepare`; `requirements-e2e.txt` |
| a tolerance | `TOLERANCE`, 1 px — a rounding step, not a shifted label |
| the baseline-update rule | `scripts/measure-local.sh --write [screen …]`, one command; the new numbers ship in the pull request of the design change |

**Seed data only.** `local_base()` refuses any host but localhost, and that
refusal is tested: against HDEV, UAT or PROD a count would be a real
association's.

**Why the frozen moment lies in the past.** A session cookie carries its own
expiry (`now + SESSION_MAX_AGE`), minted by the test process in real time. For a
server whose clock stands still in the past that expiry is always still ahead;
for one in the future every cookie would have expired.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

#: The frozen moment of the measurement run, Brussels wall time as `faketime`
#: reads it. `scripts/measure-run.sh` reads THIS line.
MEASURE_NOW = "2026-09-15 10:00:00"

BASELINES = Path(__file__).resolve().parent / "baselines"

#: How far a position or a size may be off, in px.
TOLERANCE = 1

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")

# What `tests_e2e/screenshots.py` freezes: nothing may be halfway a movement.
FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
#nprogress { display: none !important; }
"""


class NotLocal(RuntimeError):
    """The measurement run was pointed at something that is not the local server."""


def local_base(url: Optional[str] = None) -> str:
    """The address of the local measurement server, or a refusal."""
    base = url if url is not None else os.environ.get("MEASURE_BASE_URL", "")
    if not base:
        raise NotLocal("MEASURE_BASE_URL is not set — the measurement run has its own server")
    host = urlparse(base).hostname or ""
    if host not in LOCAL_HOSTS:
        raise NotLocal(
            f"refused: MEASURE_BASE_URL points at {host!r} — the measurement run renders "
            "seeded LOCAL screens only, never a live environment"
        )
    return base.rstrip("/")


# ── The elements that matter ─────────────────────────────────────────────────
#
# name → the hook. Of each: how many are visible, and the box of the first.
# The names are what a failure says; the hooks are `data-…` attributes only
# (`test_measure_compare.py` holds that).

ADMIN_HOOKS: dict[str, str] = {
    "top bar title": "[data-topbar-title]",
    "page head": "[data-page-header]",
    "head action": "[data-page-action]",
    "toolbar": "[data-toolbar]",
    "toolbar search": "[data-toolbar-search]",
    "key figure": "[data-figure]",
    "table": "[data-table-frame]",
    "content row": "[data-row]",
    "group row": "[data-group-row]",
    "pager": "[data-pager]",
    "record head": "[data-record-head]",
    "summary card": "[data-summary-card]",
    "related tabs": "[data-related-tabs]",
    "form column": "[data-form-column]",
    "form section": "[data-form-section]",
    "field": "[data-field]",
    "action bar": "[data-action-bar]",
    "assistant panel": "[data-context-key]",
}

PUBLIC_HOOKS: dict[str, str] = {
    "brand": "[data-site-brand]",
    "menu button": "[data-menu-button]",
    "account": "[data-site-account]",
    "content": "[data-main]",
    "card title": "[data-card-title]",
    # The public activity and photo pages (pilot C measures against these).
    "year heading": "[data-year-heading]",
    "date tile": "[data-date-tile]",
    "activity dates": "[data-activity-dates]",
    "component actions": "[data-component-actions]",
    "way back": "[data-way-back]",
    "activity columns": "[data-activity-columns]",
    "description": "[data-activity-description]",
    "poster": "[data-activity-poster]",
    "photo card": "[data-photo-card]",
    "photo": "[data-photo]",
    # The album's lightbox, open (#1665).
    "lightbox photo": "[data-lightbox-photo]",
    "lightbox close": "[data-lightbox-close]",
    "lightbox previous": "[data-lightbox-previous]",
    "lightbox next": "[data-lightbox-next]",
    "form page": "[data-public-form-page]",
    "form page head": "[data-form-page-head]",
    "form section": "[data-form-section]",
    "field": "[data-field]",
    "flow card": "[data-flow-card]",
    # The membership card of Mijn gezin and the transfer to make (CR-22: one
    # partial each, shown in more than one place).
    "membership card": "[data-membership-status]",
    # The account pages (CR-22 S3): the menu on the page, its content, the
    # links at the bottom on a phone, and the account items of the drawer.
    "account menu": "[data-account-page-menu]",
    "account content": "[data-account-content]",
    "account links": "[data-account-links]",
    "page title": "[data-page-title]",
    "drawer account": "[data-drawer-account]",
    "account item": "[data-account-item]",
    "transfer due": "[data-transfer-due]",
    # A registration's card and the latest one on the landing page (CR-22 S5).
    "registration": "[data-my-registration]",
    "latest registration": "[data-latest-registration]",
    "hint": "[data-member-nudge]",
    # The step of the sign-in screens (CR-22 S4b): the address, the four
    # fields of a new account, the code.
    "sign-in step": "[data-sign-in-step]",
    "code sent": "[data-code-sent]",
    "action bar": "[data-action-bar]",
    "footer row": "[data-footer-row]",
    "legal line": "[data-footer-line]",
    "bell": "[data-raakje-bell]",
}

WIDE = (1920, 1080)
DESKTOP = (1440, 900)
PHONE = (390, 844)

MEASURE_JS = """(hooks) => {
  const out = {};
  for (const [name, selector] of Object.entries(hooks)) {
    const all = [...document.querySelectorAll(selector)].filter(e => e.checkVisibility());
    if (!all.length) { out[name] = {count: 0}; continue; }
    const r = all[0].getBoundingClientRect();
    out[name] = {count: all.length, x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY),
                 w: Math.round(r.width), h: Math.round(r.height)};
  }
  out['page'] = {count: 1, x: 0, y: 0, w: document.documentElement.scrollWidth,
                 h: document.documentElement.scrollHeight};
  return out;
}"""


@dataclass(frozen=True)
class Screen:
    """One screen of the set: where it is, who looks, at which widths, and which
    of the shell's elements it MUST show."""

    key: str
    path: str
    #: The elements this screen cannot be without (names of its shell's hooks).
    required: tuple[str, ...]
    #: None (nobody signed in), "admin", or a member of the seed ("lid", …) —
    #: the roles of `screenshots._sessiewaarden`.
    session: Optional[str] = None
    widths: tuple[tuple[int, int], ...] = (PHONE, DESKTOP)
    #: Runs after the page has loaded: open a record, a tab, the panel.
    action: Optional[Callable] = None

    @property
    def hooks(self) -> dict[str, str]:
        return ADMIN_HOOKS if self.session == "admin" else PUBLIC_HOOKS


def _goto_link(page, selector: str) -> None:
    """Load the page behind the first link that matches — a full load, never a
    boosted click: a swap leaves the end state to timing."""
    link = page.locator(selector).first
    link.wait_for(state="attached", timeout=5000)
    href = link.get_attribute("href")
    if not href:
        raise RuntimeError(f"{selector} has no href")
    page.goto(urljoin(page.url, href))
    page.wait_for_load_state("networkidle")


def _activity(tab: Optional[str] = None, edit: bool = False) -> Callable:
    """The seeded activity's record: a tab of it, in read or in edit mode."""

    def action(page) -> None:
        link = page.get_by_role("link", name="E2E-activiteit").first
        link.wait_for(state="visible", timeout=5000)
        page.goto(urljoin(page.url, link.get_attribute("href")))
        page.wait_for_load_state("networkidle")
        if tab:
            _goto_link(
                page,
                f'[data-related-tabs] a:text-is("{tab}"), [data-related-tabs] a:has-text("{tab}")',
            )
        if edit:
            page.goto(page.url.split("?")[0] + "?bewerken=1")
            page.wait_for_load_state("networkidle")

    return action


def _open_the_panel(page) -> None:
    page.locator("[data-raakje-trigger]").click()
    page.locator("[data-context-key]").wait_for(state="visible", timeout=5000)
    page.wait_for_load_state("networkidle")


def _public_activity(name: str, register: bool = False) -> Callable:
    """The public page of the activity with this name — by its card's title,
    the list also links to the archive — or its registration page."""

    def action(page) -> None:
        _goto_link(page, f'[data-card-title] a:text-is("{name}")')
        if register:
            _goto_link(page, '#main a[href*="/inschrijven/"]')

    return action


def _open_the_drawer(page) -> None:
    page.locator("[data-menu-button]").click()
    page.locator("[data-drawer-account]").wait_for(state="visible", timeout=5000)


def _account_code_step(page) -> None:
    """Account aanmaken, sent: the code step of a new account. The address is
    nobody's, so no person is made — a token waits and is never used."""
    form = page.locator("[data-create-account-form]")
    form.locator('input[name="first_name"]').fill("Meting")
    form.locator('input[name="last_name"]').fill("Codestap")
    form.locator('input[name="email"]').fill("meting.codestap@example.com")
    form.locator('input[name="mobile"]').fill("0470 00 00 08")
    form.locator("button").click()
    page.locator("[data-code-sent]").wait_for(state="visible", timeout=5000)


def _album(page) -> None:
    _goto_link(page, "[data-photo-card]")


def _lightbox(page) -> None:
    """The album's first photo, open in the lightbox, the picture loaded."""
    _album(page)
    page.locator("[data-photo-open]").first.click()
    page.locator("[data-lightbox]").wait_for(state="visible", timeout=5000)
    page.wait_for_function(
        "() => { const i = document.querySelector('[data-lightbox-photo]');"
        " return i.complete && i.naturalWidth > 0"
        " && document.querySelector('[data-lightbox-next]').checkVisibility(); }"
    )


ADMIN = (WIDE, DESKTOP, PHONE)

#: The activities the public screens open: the e2e seed's, and the one
#: `measure_seed.py` adds.
SEEDED = "E2E-activiteit"
AHEAD = "Meetbasis zomerfeest met een lange titel voor de kaart"

#: What a list of activity cards and an activity's page cannot be without.
_CARD = ("brand", "content", "card title", "date tile", "activity dates", "component actions")
_PAGE = (
    "brand",
    "content",
    "way back",
    "page title",
    "date tile",
    "activity dates",
    "component actions",
)

#: The set. Pilot A at 1 920, 1 440 and 390 px; pilot B and the public activity
#: and photo pages (what pilot C must not move) at 390 and 1 440 px.
SCREENS: tuple[Screen, ...] = (
    # ── Pilot A: the back office ──
    Screen(
        "betalingen",
        "/admin/betalingen",
        ("top bar title", "toolbar", "key figure", "content row"),
        session="admin",
        widths=ADMIN,
    ),
    # CR-22 S7 (#1712): Personen, on its default view "Zonder gezin" — the one
    # person the measurement seed makes without a household.
    Screen(
        "personen",
        "/admin/personen",
        ("top bar title", "toolbar", "table", "content row"),
        session="admin",
        widths=ADMIN,
    ),
    Screen(
        "betalingen-paneel",
        "/admin/betalingen",
        ("top bar title", "toolbar", "content row", "assistant panel"),
        session="admin",
        widths=ADMIN,
        action=_open_the_panel,
    ),
    Screen(
        "activiteit-gegevens",
        "/admin/activiteiten",
        ("record head", "related tabs", "form column"),
        session="admin",
        widths=ADMIN,
        action=_activity(),
    ),
    Screen(
        "activiteit-gegevens-bewerken",
        "/admin/activiteiten",
        ("record head", "form column", "field", "action bar"),
        session="admin",
        widths=ADMIN,
        action=_activity(edit=True),
    ),
    Screen(
        "activiteit-inschrijvingen",
        "/admin/activiteiten",
        ("record head", "related tabs"),
        session="admin",
        widths=ADMIN,
        action=_activity(tab="Inschrijvingen"),
    ),
    Screen(
        "activiteit-betalingen",
        "/admin/activiteiten",
        ("record head", "related tabs"),
        session="admin",
        widths=ADMIN,
        action=_activity(tab="Betalingen"),
    ),
    Screen(
        "design-system",
        "/admin/design-system",
        ("top bar title", "field", "key figure"),
        session="admin",
        widths=ADMIN,
    ),
    # ── Pilot B: the public shell and its forms ──
    Screen("public-home", "/", ("brand", "content", "card title", "date tile", "legal line")),
    Screen(
        "public-activiteiten",
        "/activiteiten",
        (*_CARD, "year heading", "legal line"),
    ),
    Screen("public-archief", "/archief", (*_CARD, "legal line")),
    # Without a poster: the page is not centred, one component.
    Screen(
        "public-activiteit",
        "/activiteiten",
        (*_PAGE, "legal line"),
        action=_public_activity(SEEDED),
    ),
    # With a poster: the centred block, three dates, two components, a description.
    Screen(
        "public-activiteit-affiche",
        "/activiteiten",
        (*_PAGE, "description", "poster", "legal line"),
        action=_public_activity(AHEAD),
    ),
    Screen("public-fotos", "/fotos", ("brand", "page title", "year heading", "photo card")),
    Screen(
        "public-fotos-album",
        "/fotos",
        ("brand", "way back", "page title", "photo"),
        action=_album,
    ),
    # The first of two photos open: Close and Next show, Previous is hidden.
    Screen(
        "public-fotos-lichtbak",
        "/fotos",
        ("lightbox photo", "lightbox close", "lightbox next"),
        action=_lightbox,
    ),
    Screen(
        "public-inschrijven",
        "/activiteiten",
        ("brand", "form page", "form page head", "field", "action bar"),
        action=_public_activity(SEEDED, register=True),
    ),
    Screen(
        "public-word-lid",
        "/lid-worden",
        ("brand", "form page", "form page head", "field", "action bar"),
    ),
    Screen(
        "public-formulier",
        "/formulier/tok-e2e-open",
        ("brand", "form page", "field", "action bar"),
    ),
    # "Mijn <site>", the landing page of a member (CR-22 S3): the card of Mijn
    # gezin on it; the menu on the left from 768 px, the links at the bottom on
    # a phone.
    Screen(
        "mijn",
        "/mijn",
        ("brand", "account content", "page title", "membership card"),
        session="lid",
    ),
    # The sign-in screens (CR-22 S4b, #1708): the address with the second
    # door, the four fields of a new account, and its code step.
    Screen("public-aanmelden", "/aanmelden", ("brand", "content", "sign-in step")),
    Screen(
        "public-account-aanmaken",
        "/account-aanmaken",
        ("brand", "content", "sign-in step", "field"),
    ),
    Screen(
        "public-account-code",
        "/account-aanmaken",
        ("brand", "content", "sign-in step", "code sent"),
        action=_account_code_step,
    ),
    # Mijn gegevens, read and in edit mode (CR-22 S6a): the person block for
    # oneself, inside the account layout.
    Screen(
        "mijn-gegevens",
        "/mijn/gegevens",
        ("brand", "account content", "form page", "form section"),
        session="lid",
    ),
    Screen(
        "mijn-gegevens-bewerken",
        "/mijn/gegevens?bewerken=1",
        ("brand", "account content", "form page", "field", "action bar"),
        session="lid",
    ),
    # Mijn inschrijvingen (CR-22 S5): a registration's card with the transfer
    # still to make.
    Screen(
        "mijn-inschrijvingen",
        "/mijn/inschrijvingen",
        ("brand", "account content", "page title", "registration", "transfer due"),
        session="lid",
    ),
    # The drawer on a phone, signed in: the site's pages, then the account menu.
    Screen(
        "public-lade",
        "/",
        ("drawer account", "account item"),
        session="lid",
        widths=(PHONE,),
        action=_open_the_drawer,
    ),
    # Mijn gezin as it is READ: the membership card above the household.
    Screen(
        "leden-gezin",
        "/leden/gezin",
        ("brand", "form page", "membership card", "flow card"),
        session="lid",
    ),
    # A renewal that runs, to be paid by transfer: the inset in that card.
    Screen(
        "leden-gezin-overschrijving",
        "/leden/gezin",
        ("brand", "membership card", "transfer due"),
        session="lid-overschrijving",
    ),
    Screen(
        "leden-gezin-bewerken",
        "/leden/gezin?bewerken=1",
        ("brand", "form page", "field", "action bar"),
        session="lid",
    ),
    Screen(
        "leden-verlengen",
        "/leden/gezin/vernieuwen",
        ("brand", "form page", "action bar"),
        session="lid-verlopen",
    ),
)


def baseline_path(screen: Screen) -> Path:
    return BASELINES / f"{screen.key}.json"


def pairs(keys: Optional[list[str]] = None) -> list[tuple[Screen, tuple[int, int]]]:
    """Every (screen, width) of the set, or of the screens named."""
    known = {screen.key for screen in SCREENS}
    unknown = sorted(set(keys or []) - known)
    if unknown:
        raise SystemExit(
            f"unknown screen(s): {', '.join(unknown)} — known: {', '.join(sorted(known))}"
        )
    return [(s, w) for s in SCREENS if not keys or s.key in keys for w in s.widths]


def context_options() -> dict:
    """What every rendering shares: the screenshot flag of the shell (no
    environment band), the Dutch locale, no motion, and a device scale of 1."""
    from tests_e2e.screenshots import context_opties

    return {**context_opties(), "device_scale_factor": 1}


def prepare(
    page, screen: Screen, width: tuple[int, int], sessions: dict[str, str], base: str
) -> None:
    """Bring the page to the screen at this width, at rest."""
    from tests_e2e.schermen import login_met_sessie

    page.context.clear_cookies()
    if screen.session:
        login_met_sessie(page, sessions[screen.session], base)
    # The browser's own clock: a page that reads `new Date()` sees the moment
    # the server lives in.
    page.clock.set_fixed_time(datetime.fromisoformat(MEASURE_NOW))
    page.set_viewport_size({"width": width[0], "height": width[1]})
    page.goto(base + screen.path)
    page.wait_for_load_state("networkidle")
    if screen.action:
        screen.action(page)
    page.add_style_tag(content=FREEZE_CSS)
    # Webfonts shift every line when they land late, and `fonts.ready` resolves
    # trivially for a face nobody asked for yet: load the weights first.
    page.evaluate(
        """Promise.all(['400', '500', '600', '700'].map(w => document.fonts.load(w + ' 1em Inter')))
             .then(() => document.fonts.ready).then(() => null)"""
    )
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')"
        " && document.getAnimations().length === 0"
    )
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def measure(
    context, screen: Screen, width: tuple[int, int], sessions: dict[str, str], base: str
) -> dict:
    """The measurements of one screen at one width: per element its count and
    the box of the first, plus the page's own size. An element the screen
    requires and does not show is an error here, at the source.

    A tab of its own per measurement: the back office remembers in the tab's
    session storage that the Assistent panel was open, and the next screen
    would be measured beside a panel nobody opened (measured: so it was)."""
    page = context.new_page()
    try:
        prepare(page, screen, width, sessions, base)
        found = page.evaluate(MEASURE_JS, screen.hooks)
    finally:
        page.close()
    missing = [name for name in screen.required if found[name]["count"] == 0]
    if missing:
        raise AssertionError(
            f"{screen.key} @{width[0]}: required element(s) not on the screen: "
            + ", ".join(f"{name} ({screen.hooks[name]})" for name in missing)
        )
    # An element that is not there is not written: its count is 0 by absence.
    return {name: box for name, box in found.items() if box["count"]}


# ── The comparison ───────────────────────────────────────────────────────────


def differences(baseline: dict, actual: dict, tolerance: int = TOLERANCE) -> list[str]:
    """What two measurements of one screen at one width differ in, one line per
    element and number: "<element>: <what> <baseline> → <now>"."""
    lines: list[str] = []
    for name in sorted(set(baseline) | set(actual)):
        old, new = baseline.get(name), actual.get(name)
        if old is None or new is None:
            was, now = (old or {"count": 0})["count"], (new or {"count": 0})["count"]
            lines.append(f"{name}: count {was} → {now}")
            continue
        if old["count"] != new["count"]:
            lines.append(f"{name}: count {old['count']} → {new['count']}")
        for part in ("x", "y", "w", "h"):
            if abs(old[part] - new[part]) > tolerance:
                lines.append(f"{name}: {part} {old[part]} → {new[part]}")
    return lines


def largest(baseline: dict, actual: dict) -> int:
    """The largest difference, in px, between two measurements of one screen at
    one width, over the elements both hold — 0 where the two machines agree to
    the pixel, at most `TOLERANCE` where the comparison is green."""
    return max(
        (
            abs(baseline[name][part] - actual[name][part])
            for name in set(baseline) & set(actual)
            for part in ("x", "y", "w", "h")
        ),
        default=0,
    )


def read_baseline(screen: Screen) -> dict:
    path = baseline_path(screen)
    return json.loads(path.read_text()) if path.exists() else {}


def launch(playwright):
    """The pinned browser, started in Dutch (`screenshots.launch_opties`)."""
    from tests_e2e.screenshots import launch_opties

    options = dict(launch_opties())
    exe = os.environ.get("E2E_CHROMIUM_PATH")
    if exe:
        options["executable_path"] = exe
    return playwright.chromium.launch(**options)


def sessions() -> dict[str, str]:
    from tests_e2e.screenshots import _sessiewaarden

    return _sessiewaarden()


def measure_all(base: str, keys: Optional[list[str]] = None) -> dict:
    """{screen: {width: measurements}} for the set, or the screens named."""
    from playwright.sync_api import sync_playwright

    out: dict = {}
    with sync_playwright() as pw:
        browser = launch(pw)
        context = browser.new_context(base_url=base, **context_options())
        values = sessions()
        for screen, width in pairs(keys):
            out.setdefault(screen.key, {})[str(width[0])] = measure(
                context, screen, width, values, base
            )
        browser.close()
    return out


# ── Writing the baselines: a deliberate act ──────────────────────────────────


def write(keys: list[str]) -> int:
    """Measure the screens (all, or the ones named) and write their baselines.

    Each screen is measured twice and written only when the two agree to the
    pixel: a baseline the same machine cannot reproduce would be red on its
    first comparison."""
    try:
        base = local_base()
    except NotLocal as refusal:
        print(refusal, file=sys.stderr)
        return 2
    BASELINES.mkdir(parents=True, exist_ok=True)
    first, second = measure_all(base, keys), measure_all(base, keys)
    unstable = 0
    for key, widths in first.items():
        drift = [
            f"@{width}: {line}"
            for width in widths
            for line in differences(widths[width], second[key][width], tolerance=0)
        ]
        if drift:
            unstable += 1
            print(
                f"NOT WRITTEN, two measurements differ — {key} " + "; ".join(drift), file=sys.stderr
            )
            continue
        target = BASELINES / f"{key}.json"
        text = json.dumps(widths, indent=1, sort_keys=True) + "\n"
        changed = not target.exists() or target.read_text() != text
        target.write_text(text)
        print(f"{'wrote' if changed else 'same '} {target.name}")
    return 1 if unstable else 0


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments or arguments[0] != "--write":
        print("usage: python -m tests_e2e.measures --write [screen ...]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(write(arguments[1:]))
