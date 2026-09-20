"""Taalbeleid-fundament (#407-T, §22): gettext-catalogus + ``_()``-helper.

Beleid: nieuwe code/DB/tests in het Engels; gebruikersteksten door ``_()``,
met ``nl_BE`` als standaardtaal. Zolang een string niet in de catalogus
staat, is de msgid zelf de weergavetekst (passthrough) — bestaande
Nederlandse teksten blijven dus letterlijk werken terwijl nieuwe code
Engelse msgids gebruikt en die via de catalogus vertaald worden.

De actieve taal komt per tenant uit de tenant-config (sleutel
``language``, default ``nl_BE``) en wordt door de tenant-middleware in
``current_locale`` gezet. Extract/compile: ``scripts/i18n.sh``.
"""
from __future__ import annotations

import gettext as _gettext
from contextvars import ContextVar
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LOCALE = "nl_BE"

current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)

_cache: dict[str, _gettext.NullTranslations] = {}


def _translations(locale: str) -> _gettext.NullTranslations:
    if locale not in _cache:
        _cache[locale] = _gettext.translation(
            "messages", localedir=str(LOCALES_DIR), languages=[locale], fallback=True)
    return _cache[locale]


def _(text: str) -> str:
    """Vertaal een gebruikerstekst naar de actieve taal (passthrough als de
    msgid niet in de catalogus staat)."""
    return _translations(current_locale.get()).gettext(text)


def install_jinja_i18n(env) -> None:
    """Hang gettext aan de Jinja-omgeving zodat templates ``{{ _("...") }}``
    kunnen gebruiken; volgt dezelfde actieve taal als de Python-kant."""
    env.add_extension("jinja2.ext.i18n")
    env.install_gettext_callables(
        gettext=_, ngettext=lambda s, p, n: _(s) if n == 1 else _(p), newstyle=True)


def long_date(d) -> str:
    """A long date in the active locale, e.g. 'zaterdag 29 augustus 2026' (#451).

    Lives here and not in `app.ui` since #974: a domain needed the same wording in a
    refusal message ("afgesloten sinds zaterdag 29 augustus 2026"), and a domain may
    not import the UI layer. A second copy of these two lines in the domain would be
    two places that decide how a date reads — so the one copy moved down to where
    both can reach it, and the Jinja filter points here.
    """
    if d is None:
        return ""
    from babel.dates import format_date

    return format_date(d, format="full", locale=current_locale.get())


def long_date_no_year(d) -> str:
    """The same long date without the year, e.g. 'zondag 8 november' (#1051).

    Next to `long_date` and not in the UI layer for the same reason: it is the
    wording of a date, and the deadline line on the public card sits directly under
    the activity's own dates — which already carry the year.
    """
    if d is None:
        return ""
    from babel.dates import format_date

    return format_date(d, format="EEEE d MMMM", locale=current_locale.get())
