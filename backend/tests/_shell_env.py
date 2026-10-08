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
    # Golf 2 (#913): de beheerschil toont linksboven de tenantnaam via
    # `werkruimte_naam()`. Buiten de app is er geen tenantcontext; de echte
    # functie valt dan óók terug op de default, dus dit is dezelfde waarde
    # langs een DB-loze weg.
    from app.ui import _werkruimte_naam  # noqa: F401 - zelfde bron, zie boven

    env.globals["werkruimte_naam"] = lambda: "Raak Millegem"
    # #1238: de schillen vragen de banner niet te renderen tijdens een opname van de
    # schermafdruk-tool. Dit is de ECHTE functie en geen kopie van de regel: buiten een
    # verzoek vindt ze geen request in de rendercontext en geeft ze False, dus deze
    # tests zien de banner zoals voorheen.
    from app.ui import _is_screenshot

    env.globals["is_screenshot"] = _is_screenshot
    # #1748: the kit's `total_line` formats its amount with `geld`, and a filter is
    # looked up when `_macros.html` is compiled — so every shell needs it, also one
    # that shows no amount. The app's own function, not a copy.
    from app.ui import templates

    env.filters["geld"] = templates.env.filters["geld"]
    # `beheer_account(request)` staat achter `request is defined` in de schil en
    # hoeft hier dus niet.
    return env
