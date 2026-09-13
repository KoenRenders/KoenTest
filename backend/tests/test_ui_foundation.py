"""UI-fundament (#396): de shells en macro's renderen — de Jinja-rendertest
uit §19.5.3c (één keer de kit testen verslaat elke pagina testen)."""
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"


def _env():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    # zelfde i18n-machinerie als de echte app-omgeving (#407-T)
    from app.i18n import install_jinja_i18n
    install_jinja_i18n(env)
    # #773: de schillen laden hun assets via `statisch()`. Deze omgeving is met de
    # hand gebouwd en heeft dus niet de globals van `app.ui.templates.env`; zonder
    # deze regel valt elke schil-rendertest om op een ongedefinieerde functie.
    from app.ui import statisch
    env.globals["statisch"] = statisch
    return env


def test_shells_render():
    env = _env()
    for shell in ("public_base.html", "admin_base.html"):
        html = env.get_template(shell).render(
            nav_items=[{"label": None, "items": [{"href": "/x", "label": "X", "active": True}]}])
        assert "htmx.min.js" in html and "alpine.min.js" in html and "app.css" in html


def test_macros_render_and_escape():
    env = _env()
    tpl = env.from_string(
        '{% import "_macros.html" as ui %}'
        '{{ ui.btn_primary("Opslaan") }}{{ ui.badge("Concept") }}'
        '{{ ui.error_banner(msg) }}{{ ui.label("Naam", "f_naam", required=True) }}'
    )
    html = tpl.render(msg="<script>x</script>")
    assert "Opslaan" in html and "Concept" in html
    assert "&lt;script&gt;" in html          # autoescape actief
    assert 'text-red-600">*' in html          # verplicht-veld-conventie


def test_admin_nav_info_onderaan_en_een_tenant_item():
    """#505: 'Info' staat onderaan. #581: één item voor tenants — de aparte
    'Instellingen' is opgegaan in /admin/tenants, dus twee nav-items voor
    hetzelfde object bestaan niet meer."""
    from app.ui import admin_nav

    hrefs = [i["href"] for groep in admin_nav("/admin/werkbank")
             for i in groep["items"]]
    assert "/admin/instellingen" not in hrefs
    assert hrefs.index("/admin/tenants") < hrefs.index("/admin/info")


def test_admin_shell_heeft_uitloggen_en_sticky_sidebar():
    """#526: de admin-schil biedt een Uitloggen-link (→ /afmelden) en een sticky,
    volledige-hoogte zijbalk. Sinds golf 2 (#913, beslissing i) woont Uitloggen
    rechtsboven bij de account-aanwezigheid, niet meer in de zijbalkvoet — de
    link zelf blijft een contract."""
    env = _env()
    html = env.get_template("admin_base.html").render(
        nav_items=[{"label": None, "items": [{"href": "/x", "label": "X", "active": True}]}])
    assert "/afmelden" in html            # logout-link aanwezig (topbalk/mobiel menu)
    assert "Uitloggen" in html
    assert "md:sticky" in html and "md:h-screen" in html  # sticky full-height aside


def test_static_assets_served(client):
    for path in ("/static/app.css", "/static/vendor/htmx.min.js", "/static/vendor/alpine.min.js"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert len(resp.content) > 1000, path
