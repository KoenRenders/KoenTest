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
<h2>Vergadering</h2>
<p>De KWB vergadert iedere eerste donderdag van de maand om 20u in zaal 1 van het Miloheem. Iedereen is hierop uitgenodigd, mannen en vrouwen.</p>
<p>Voor 2024 is dit op 4 januari, 1 februari, 7 maart, 4 april, 2 mei, 6 juni, 4 juli, 1 augustus, 5 september, 3 oktober, 7 november en 5 december.</p>
<p>De agenda is steeds als volgt:</p>
<ul>
<li>Evaluatie activiteiten die plaatsvonden</li>
<li>Bespreking activiteiten in de nabije toekomst</li>
<li>Leden</li>
<li>Programma aanbod (toekomstig te organiseren activiteiten)</li>
<li>Varia</li>
</ul>
<h2>Activiteiten</h2>
<p>KWB Millegem wil mensen in Millegem de gelegenheid bieden om activiteiten voor Millegemnaren te organiseren. KWB Millegem zorgt dan voor communicatie, verzekering, eventuele dekking financieel risico of bijdrage, eventuele lokalen enz.</p>
<p>Alle KWB leden kunnen dus activiteiten organiseren, mits volgende regels gevolgd worden:</p>
<ul>
<li>Een activiteit kent minstens 2 "trekkers", mensen die verantwoordelijkheid nemen om de activiteit te organiseren. Zij kunnen uiteraard andere personen aanspreken om te helpen.</li>
<li>Elke activiteit wordt voordat de activiteit gecommuniceerd wordt op de KWB vergadering toegelicht. Onze ervaring leert dat daar steeds goede ideeën en tips worden gegeven. Op die manier is ook iedereen van het bestuur op de hoogte van toekomstige activiteiten, komen deze op website, sociale media, nieuwsbrief,...</li>
<li>We organiseren geen twee KWB-activiteiten op hetzelfde moment, ook al zijn ze voor verschillende doelpublieken.</li>
</ul>
<p>Volgende zijn de steeds in beweging zijnde activiteitenkalenders, met hun trekkers, locatie, financiële afspraken,... voor de volgende jaren:</p>
<ul>
<li><a href="https://docs.google.com/spreadsheets/d/1bASRBfFLg5UrceUpSlulEAzJNbI6v5_G/edit?usp=sharing&ouid=111908879404264522870&rtpof=true&sd=true">Activiteiten 2024</a></li>
<li><a href="https://docs.google.com/spreadsheets/d/1yx1KNOfHrYcGyqMz8gKCYLAcF6GSWpXv/edit?usp=sharing&ouid=111908879404264522870&rtpof=true&sd=true">Activiteiten 2025</a></li>
</ul>
<h2>Bestuur</h2>
<p>KWB Millegem kent volgende rollen in haar "bestuur":</p>
<ul>
<li><strong>Wijkmeesters</strong> (brengen het maandkrantje "Raak" naar onze leden en zijn het eerste aanspreekpunt voor onze leden): Paul Bens, Mon Essers, Steven Paepen, Paul Lommelen, Bart Ouderits, Wim Paepen, Joost Van Braband, Herman Sannen, Ludo Vermeir, Ivo Verwimp, Frank Mertens</li>
<li><strong>Voorzitter:</strong> Mon Essers</li>
<li><strong>Secretaris en ondervoorzitter:</strong> Koen Renders</li>
<li><strong>Penningmeester:</strong> Steven Paepen</li>
<li><strong>Cultuurraad:</strong> Steven Paepen, Mon Essers</li>
<li><strong>Nieuwsbrief:</strong> Steven Paepen</li>
<li><strong>Website, Facebook en Instagram:</strong> Koen Renders</li>
<li><strong>Leden administratie:</strong> Koen Renders</li>
<li><strong>Trekkers van activiteiten:</strong> zie hoger bij Activiteiten, en wie weet ook u!</li>
</ul>
""",
    },
    {
        "title": "Kerstradio",
        "slug": "kerstradio",
        "sort_order": 2,
        "is_published": True,
        "content": """\
<h2>Kerstradio</h2>
<p><strong>Luister op zaterdag 27 december van 10u tot 22u naar onze kerstradio via de frequentie van Radio Gompel op 105.6 FM, via <a href="http://www.radiogompel.be">www.radiogompel.be</a> of zoek Radio Gompel in de app op je smartphone</strong>.</p>
<ul>
<li>Heb je technische uitdagingen? Bel of chat met onze hotline op 0496 59 20 17</li>
</ul>
<h3>Verzoekjesformulier</h3>
<p>Heb jij een verzoeknummer met een kerstboodschap?</p>
<ul>
<li>Vraag aan via <a href="https://forms.gle/kj93xiUqLuPhKLr89">https://forms.gle/kj93xiUqLuPhKLr89</a></li>
</ul>
<h3>Interviews</h3>
<ul>
<li>10u45: GoGoLorrie - Jolien Geenen</li>
<li>13u-13u30: Rozanne en Marie maken radio</li>
<li>15u-16u: Chiro Millegem neemt de radio over</li>
<li>15u30: Kinderburgemeester Saar Renders</li>
<li>16u30: Miloplein en Koen Mariën (nieuwe VB Chiro Millegem)</li>
</ul>
<h3>Raad de RODE DRAAD</h3>
<p>Ieder uur wordt er een vraag gesteld waarvan het antwoord leidt tot hét antwoord op onze Rode Draad. Win jij die prijs?</p>
<ul>
<li>10u15 - vraag 1</li>
<li>11u15 - vraag 2</li>
<li>12u30 - vraag 3</li>
<li>13u55 - vraag 4</li>
<li>14u50 - vraag 5</li>
<li>16u15 - vraag 6</li>
<li>17u50 - vraag 7</li>
<li>19u05 - vraag 8</li>
</ul>
<h3>Raad HET GELUID</h3>
<p>Ieder uur spelen we het geluid dat jullie moeten raden. Vanaf de tweede keer geven we ook telkens een tip. Jullie kunnen langskomen aan de Kerstherberg voor een gokje.</p>
<ul>
<li>10u30 - geluid: langskomen van 11u tot 11u15</li>
<li>11u35 - geluid + tip 1: langskomen van 12u30 tot 12u45</li>
<li>13u40 - geluid + tip 2: langskomen van 14u tot 14u15</li>
<li>14u20 - geluid + tip 3: langskomen van 14u45 tot 15u</li>
<li>15u45 - geluid + tip 4: langskomen van 16u tot 16u15</li>
<li>17u20 - geluid + tip 5: langskomen van 17u30 tot 17u45</li>
<li>18u45 - geluid + tip 6: langskomen van 19u tot 19u15</li>
</ul>
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
