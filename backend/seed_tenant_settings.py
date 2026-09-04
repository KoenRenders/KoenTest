"""Seed de footer-links van Raak Millegem (#612).

Sinds v2.0.0 zijn de sociale links en de privacyverklaring **tenant-instellingen**
met "leeg = niet tonen" (#519/#493). In v1.14 stonden ze hardgecodeerd in de
React-footer, dus er valt niets te migreren: zonder seed toont elke verse omgeving
een footer zonder iconen en zonder privacylink.

**Waarom een marker en niet gewoon "vul aan wat leeg is".** De vier sleutels bestaan
op een bestaande omgeving al als *lege rijen* — het instellingenscherm schrijft lege
strings — dus "vul aan als de rij ontbreekt" doet niets. En "vul aan als de waarde
leeg is" zou een bewust leeggemaakte waarde bij elke deploy terugzetten: stopt Raak
ooit met TikTok, dan komt dat icoon telkens terug en zoekt iemand zich suf. De marker
``seed_footer_links_v1`` maakt er een eenmalige actie per omgeving van, waarna het
scherm de baas is.

Idempotent en veilig om bij elke opstart te draaien.
"""
from app.database import SessionLocal
from app.domains.registry import load_all_models
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from app.kernel.tenant_config import get_setting, set_setting

load_all_models()

MARKER = "seed_footer_links_v1"

# Publieke profielen van de vereniging; stonden in v1.14 al in deze repo
# (git show v1.14.0:frontend/src/components/Footer.tsx). Geen secrets.
# Bewust ALLEEN tenant Millegem — "Raak Voorbeeldafdeling" krijgt deze links niet.
FOOTER_LINKS = {
    "facebook_url": "https://www.facebook.com/raakmillegem",
    "instagram_url": "https://www.instagram.com/raakmillegem",
    "tiktok_url": "https://www.tiktok.com/@raakmillegem",
    "privacy_url": "/privacy",
}


def seed_footer_links(db) -> list[str] | None:
    """Vult de footer-links van tenant Millegem, precies één keer.

    Geeft ``None`` terug als de marker er al stond (dan is er niets gebeurd), en
    anders de lijst sleutels die deze run gezet zijn — leeg als alles al ingevuld
    bleek. Een waarde die via /admin/tenants is ingesteld, wordt nooit overschreven.
    """
    if get_setting(db, MARKER, tenant_id=TENANT_MILLEGEM_ID):
        return None

    gezet = []
    for key, value in FOOTER_LINKS.items():
        if get_setting(db, key, tenant_id=TENANT_MILLEGEM_ID):
            continue  # al ingevuld via het instellingenscherm — met rust laten
        set_setting(db, key, value, tenant_id=TENANT_MILLEGEM_ID)
        gezet.append(key)

    set_setting(db, MARKER, "1", tenant_id=TENANT_MILLEGEM_ID)
    db.commit()
    return gezet


def main():
    db = SessionLocal()
    try:
        gezet = seed_footer_links(db)
        if gezet is None:
            print("  Footer-links al geseed (marker aanwezig), overslaan.")
        elif gezet:
            print(f"  Footer-links geseed voor tenant {TENANT_MILLEGEM_ID}: {', '.join(gezet)}.")
        else:
            print("  Footer-links stonden al ingevuld; enkel de marker gezet.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
