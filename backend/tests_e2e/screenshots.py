"""Reproducible screenshot set for the design track (#785 step 0).

Captures a FIXED set of screens at two widths against a live backend with the
e2e seed — the same environment as the e2e CI job. Two runs on the same commit
must produce the same images; a sha256 manifest is written so that claim can
be checked instead of felt.

Not collected by pytest (no ``test_`` prefix): this is a tool, not a test.

Run, from ``backend/`` with a seeded backend on ``E2E_BASE_URL``::

    python seed_e2e.py                      # once, dev/test only
    python -m tests_e2e.screenshots [outdir]

or via the repo-root wrapper ``./scripts/screenshots.sh [outdir]``.
Default output: ``./screenshots/``. Seed data ONLY — never point this at
UAT or PROD (the admin session is minted locally, so it would not work
there anyway; the rule stands regardless).
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright

from tests_e2e.schermen import BASE, login_met_sessie

# The audience decides the primary width (CR-08): public screens are judged on
# a phone, admin screens on a desktop. Both widths are captured for every
# screen; the order in the filename makes the primary one sort first.
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

# Animations and blinking carets are the enemy of "two runs, same bytes".
FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
/* The hx-boost progress bar is mid-flight state, not design. */
#nprogress { display: none !important; }
"""


@dataclass(frozen=True)
class Screen:
    """One entry of the fixed set."""

    key: str
    path: str
    admin: bool
    # Runs after navigation, e.g. to open a modal or click through to a
    # seeded record. Receives the page; raises to signal a missing target.
    action: Optional[Callable] = None


def _open_first_link(page, text: str, url_glob: str) -> None:
    """Navigate to the record behind the first link named ``text``.

    Deliberately goto(href) instead of click(): a click goes through hx-boost,
    whose swap leaves bistable end states (progress bar, focus, swap timing)
    that made these two screens the only irreproducible ones. A full page
    load renders the same target screen the boring, deterministic way.
    """
    link = page.get_by_role("link", name=text).first
    link.wait_for(state="visible", timeout=5000)
    href = link.get_attribute("href")
    if not href:
        raise RuntimeError(f"link {text!r} has no href")
    page.goto(href)
    page.wait_for_url(url_glob, timeout=5000)
    page.wait_for_load_state("networkidle")


def _open_register_modal(page) -> None:
    """Open the public registration modal on the activities list."""
    button = page.get_by_role("button", name="Inschrijven").first
    button.wait_for(state="visible", timeout=5000)
    button.click()
    # The htmx swap fills an #inschrijf-* container; wait for the form.
    page.wait_for_selector("form >> text=Inschrijven", timeout=5000)


SCREENS: tuple[Screen, ...] = (
    # Public — judged phone-first.
    Screen("public-home", "/", admin=False),
    Screen("public-activiteiten", "/activiteiten", admin=False),
    Screen("public-inschrijfmodal", "/activiteiten", admin=False,
           action=_open_register_modal),
    Screen("public-word-lid", "/lid-worden", admin=False),
    Screen("public-formulier", "/formulier/tok-e2e-open", admin=False),
    # Admin — judged desktop-first.
    Screen("admin-dashboard", "/admin", admin=True),
    Screen("admin-betalingen", "/admin/betalingen", admin=True),
    Screen("admin-leden", "/admin/leden", admin=True),
    Screen("admin-activiteit-detail", "/admin/activiteiten", admin=True,
           action=lambda page: _open_first_link(
               page, "E2E-activiteit", "**/admin/activiteiten/*")),
    Screen("admin-formulierbouwer", "/admin/formulieren", admin=True,
           action=lambda page: _open_first_link(
               page, "E2E-formulier", "**/admin/formulieren/*")),
    # The living component kit — review-round material.
    Screen("admin-design-system", "/admin/design-system", admin=True),
)


def _admin_session_value() -> str:
    """Mint a session for the seeded admin, exactly as the e2e tests do."""
    from app.domains.auth.api import make_session_value

    email = os.environ.get("E2E_ADMIN_EMAIL")
    if not email:
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = SEEDED_ADMIN_EMAIL
    return make_session_value(email)


def _capture(page, screen: Screen, width: dict, out_dir: Path) -> Path:
    page.set_viewport_size(width)
    page.goto(screen.path)
    page.wait_for_load_state("networkidle")
    if screen.action:
        screen.action(page)
    page.add_style_tag(content=FREEZE_CSS)
    # Webfonts shift every line height when they land late — one run rendered
    # the builder in the fallback font and nothing hashed the same. fonts.ready
    # alone resolves trivially when the face was not requested yet, so load the
    # families explicitly before waiting.
    page.evaluate(
        """Promise.all([
             document.fonts.load('1em Inter'),
             document.fonts.load('700 1em Inter'),
             document.fonts.load('1em "Radio Canada Big"'),
           ]).then(() => document.fonts.ready).then(() => null)"""
    )
    # #997: until no htmx swap is still running or settling, instead of one
    # guessed "settle beat". Without htmx on the page there is nothing to wait for.
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')")
    name = f"{screen.key}-{width['width']}.png"
    target = out_dir / name
    page.screenshot(path=str(target), full_page=True)
    return target


def main(argv: list[str]) -> int:
    # Hard stop, not a docstring: against HDEV/UAT/PROD these images would show
    # real members and addresses. Localhost is the only target this tool has.
    from urllib.parse import urlparse

    host = urlparse(BASE).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        print(f"refused: E2E_BASE_URL points at {host!r} — this tool captures "
              "seeded LOCAL screens only, never a live environment.",
              file=sys.stderr)
        return 2

    out_dir = Path(argv[1]) if len(argv) > 1 else Path("screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    session_value = _admin_session_value()
    captured: list[Path] = []
    missing: list[str] = []

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        context = browser.new_context(base_url=BASE, reduced_motion="reduce")
        page = context.new_page()
        login_met_sessie(page, session_value)

        for screen in SCREENS:
            # Primary width first: phone for public, desktop for admin.
            widths = (DESKTOP, PHONE) if screen.admin else (PHONE, DESKTOP)
            for width in widths:
                try:
                    captured.append(_capture(page, screen, width, out_dir))
                except Exception as exc:  # noqa: BLE001 - report, don't die mid-set
                    missing.append(f"{screen.key} @ {width['width']}: {exc}")
        browser.close()

    manifest = out_dir / "manifest.txt"
    lines = []
    for path in sorted(captured):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(captured)} screenshots -> {out_dir}/ (manifest: {manifest.name})")
    if missing:
        # The #644 lesson: with the seed loaded, a missing screen is a
        # finding, not a footnote.
        for entry in missing:
            print(f"MISSING: {entry}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
