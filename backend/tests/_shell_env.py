"""A bare Jinja environment for tests that render a shell directly.

A handful of tests render `site_base.html` or `admin_base.html` without going through the
app — they are about markup (footer branding, the sticky offset of the environment banner)
and do not want a request, a session or a database.

Such an environment does **not** carry the globals of `app.ui.templates.env`, so every
function a shell calls has to be handed over. That went wrong twice with the same shape:
#773 added `statisch()` and every shell test fell over on an undefined function; #889 added
`path_for()` and it happened again, in two files that each carried their own copy of the fix.

Hence one place. A new global is added here once, and no shell test breaks a third time.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"


def bare_shell_env(*extra_dirs) -> Environment:
    """A Jinja environment that can render the shells, with the app's globals."""
    from app.i18n import install_jinja_i18n
    from app.ui import path_for, statisch

    zoekpaden = [str(TEMPLATES), *[str(d) for d in extra_dirs]]
    env = Environment(loader=FileSystemLoader(zoekpaden), autoescape=True)
    install_jinja_i18n(env)
    env.globals["statisch"] = statisch
    # #889: `path_for` geeft een intern pad de tenant-prefix wanneer het verzoek via een
    # prefix binnenkwam. Buiten een verzoek — zoals hier — geeft hij het pad ongewijzigd
    # terug, dus deze tests zien exact wat ze vroeger zagen.
    env.globals["path_for"] = path_for
    return env
