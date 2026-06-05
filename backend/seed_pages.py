"""Seed CMS pages: Werking and Kerstradio."""
from app.database import SessionLocal
from app.models.cms import CmsPage

db = SessionLocal()

PAGES = [
    {
        "title": "Werking",
        "slug": "werking",
        "sort_order": 1,
        "is_published": True,
        "content": """\
## Vergadering

De KWB vergadert iedere eerste donderdag van de maand om 20u in zaal 1 van het Miloheem. Iedereen is hierop uitgenodigd, mannen en vrouwen.

Voor 2024 is dit op 4 januari, 1 februari, 7 maart, 4 april, 2 mei, 6 juni, 4 juli, 1 augustus, 5 september, 3 oktober, 7 november en 5 december.

De agenda is steeds als volgt:

- Evaluatie activiteiten die plaatsvonden
- Bespreking activiteiten in de nabije toekomst
- Leden
- Programma aanbod (toekomstig te organiseren activiteiten)
- Varia

## Activiteiten

KWB Millegem wil mensen in Millegem de gelegenheid bieden om activiteiten voor Millegemnaren te organiseren. KWB Millegem zorgt dan voor communicatie, verzekering, eventuele dekking financieel risico of bijdrage, eventuele lokalen enz.

Alle KWB leden kunnen dus activiteiten organiseren, mits volgende regels gevolgd worden:

- Een activiteit kent minstens 2 "trekkers", mensen die verantwoordelijkheid nemen om de activiteit te organiseren. Zij kunnen uiteraard andere personen aanspreken om te helpen.
- Elke activiteit wordt voordat de activiteit gecommuniceerd wordt op de KWB vergadering toegelicht. Onze ervaring leert dat daar steeds goede ideeën en tips worden gegeven. Op die manier is ook iedereen van het bestuur op de hoogte van toekomstige activiteiten, komen deze op website, sociale media, nieuwsbrief,...
- We organiseren geen twee KWB-activiteiten op hetzelfde moment, ook al zijn ze voor verschillende doelpublieken.

Volgende zijn de steeds in beweging zijnde activiteitenkalenders, met hun trekkers, locatie, financiële afspraken,... voor de volgende jaren:

- [Activiteiten 2024](https://docs.google.com/spreadsheets/d/1bASRBfFLg5UrceUpSlulEAzJNbI6v5_G/edit?usp=sharing&ouid=111908879404264522870&rtpof=true&sd=true)
- [Activiteiten 2025](https://docs.google.com/spreadsheets/d/1yx1KNOfHrYcGyqMz8gKCYLAcF6GSWpXv/edit?usp=sharing&ouid=111908879404264522870&rtpof=true&sd=true)

## Bestuur

KWB Millegem kent volgende rollen in haar "bestuur":

- **Wijkmeesters** (brengen het maandkrantje "Raak" naar onze leden en zijn het eerste aanspreekpunt voor onze leden): Paul Bens, Mon Essers, Steven Paepen, Paul Lommelen, Bart Ouderits, Wim Paepen, Joost Van Braband, Herman Sannen, Ludo Vermeir, Ivo Verwimp, Frank Mertens
- **Voorzitter:** Mon Essers
- **Secretaris en ondervoorzitter:** Koen Renders
- **Penningmeester:** Steven Paepen
- **Cultuurraad:** Steven Paepen, Mon Essers
- **Nieuwsbrief:** Steven Paepen
- **Website, Facebook en Instagram:** Koen Renders
- **Leden administratie:** Koen Renders
- **Trekkers van activiteiten:** zie hoger bij Activiteiten, en wie weet ook u!
""",
    },
    {
        "title": "Kerstradio",
        "slug": "kerstradio",
        "sort_order": 2,
        "is_published": True,
        "content": """\
## Kerstradio

**Luister op zaterdag 27 december van 10u tot 22u naar onze kerstradio via de frequentie van Radio Gompel op 105.6 FM, via [www.radiogompel.be](http://www.radiogompel.be) of zoek Radio Gompel in de app op je smartphone**.

- Heb je technische uitdagingen? Bel of chat met onze hotline op 0496 59 20 17

### Verzoekjesformulier

Heb jij een verzoeknummer met een kerstboodschap?

- Vraag aan via [https://forms.gle/kj93xiUqLuPhKLr89](https://forms.gle/kj93xiUqLuPhKLr89)

### Interviews

- 10u45: GoGoLorrie - Jolien Geenen
- 13u-13u30: Rozanne en Marie maken radio
- 15u-16u: Chiro Millegem neemt de radio over
- 15u30: Kinderburgemeester Saar Renders
- 16u30: Miloplein en Koen Mariën (nieuwe VB Chiro Millegem)

### Raad de RODE DRAAD

Ieder uur wordt er een vraag gesteld waarvan het antwoord leidt tot hét antwoord op onze Rode Draad. Win jij die prijs?

- 10u15 - vraag 1
- 11u15 - vraag 2
- 12u30 - vraag 3
- 13u55 - vraag 4
- 14u50 - vraag 5
- 16u15 - vraag 6
- 17u50 - vraag 7
- 19u05 - vraag 8

### Raad HET GELUID

Ieder uur spelen we het geluid dat jullie moeten raden. Vanaf de tweede keer geven we ook telkens een tip. Jullie kunnen langskomen aan de Kerstherberg voor een gokje.

- 10u30 - geluid: langskomen van 11u tot 11u15
- 11u35 - geluid + tip 1: langskomen van 12u30 tot 12u45
- 13u40 - geluid + tip 2: langskomen van 14u tot 14u15
- 14u20 - geluid + tip 3: langskomen van 14u45 tot 15u
- 15u45 - geluid + tip 4: langskomen van 16u tot 16u15
- 17u20 - geluid + tip 5: langskomen van 17u30 tot 17u45
- 18u45 - geluid + tip 6: langskomen van 19u tot 19u15
""",
    },
]

for p in PAGES:
    existing = db.query(CmsPage).filter(CmsPage.slug == p["slug"]).first()
    if existing:
        print(f"  Page '{p['slug']}' already exists, skipping.")
        continue
    db.add(CmsPage(
        title=p["title"],
        slug=p["slug"],
        content=p["content"],
        is_published=p["is_published"],
        sort_order=p["sort_order"],
    ))
    print(f"  Created page '{p['slug']}'.")

db.commit()
db.close()
print("Done.")
