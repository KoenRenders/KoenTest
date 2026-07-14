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
