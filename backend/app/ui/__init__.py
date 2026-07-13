"""UI-fundament (#396/#398, §21): Jinja-templates + htmx/Alpine, server-rendered.

Elke component levert zijn schermen als ``ui.py`` (routes: view-model bouwen,
template kiezen) + ``templates/`` (dom: alleen tonen). Dit pakket levert de
gedeelde machinerie: de template-omgeving (met de component-template-mappen),
de UI-kit-macro's en de shells (base-layouts).
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates

_UI_DIR = Path(__file__).parent

# Component-template-mappen haken hier in (fase 0+ voegen paden toe).
template_dirs: list[str] = [str(_UI_DIR / "templates")]

templates = Jinja2Templates(directory=template_dirs)
