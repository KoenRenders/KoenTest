"""Reporting (#901): elke datum bij haar onderwerp, en de klasse Tijd verdwijnt.

Koen, na de hiërarchie van #899: de gewone *Datum* betekende per feit iets anders.
`date_day` stond op de eigen sleuteldatum van het feit dat je bevraagt — bij
inschrijvingen de inschrijfdatum, bij betalingen de aanmaakdatum. De omschrijving
van het buurobject gaf het zelf toe: *"kalenderjaar van de gebeurtenis
(inschrijfdatum of aanmaakdatum van de betaling)"*.

**Eén object met twee betekenissen is erger dan #894.** Daar stond de fout
zichtbaar in de lijst: twee objecten met bijna dezelfde naam. Hier klopt het
rapport, en weet alleen wie het feit eronder kent wat er geteld is. Dat is precies
de "of" die nergens meer in een omschrijving hoort te staan.

De oplossing is dezelfde als bij *Betaaldetail* in #871: **indelen naar onderwerp
en niet naar soort ding.** De datums verhuizen naar de klasse van hun feit —
*Inschrijfdatum* bij Activiteiten, *Betaaldatum* bij Betalingen, *Afhandeldatum*
bij Taken — en dan blijft er van de klasse *Tijd* niets over. Ze was de laatste die
naar een soort genoemd was.

Elke sleuteldatum krijgt daarbij de naam van haar onderwerp, via dezelfde
alias-machinerie als de rollen van #895: `d_payment_created` en
`d_registration_date` lezen allebei uit `reporting.d_date`, maar heten naar wat ze
betekenen. Er verandert dus **niets aan de weergaven** — dit is een migratie van
data, niet van schema.

**Twee dingen die onderweg boven water kwamen.**

*Maand voluit* is geschrapt. Het was een erfenis van vóór het rollenwerk, bestond
alleen op de gedeelde datum en niet op de vier rollen, en sinds #852 kan je er niet
op groeperen. `2026-03` sorteert al chronologisch en leest even goed — drie kopieën
erbij maken was het alternatief, en dat is geen keuze.

En `f_activities` joinde de gedeelde datum op zijn `date_key`, die **de einddatum
is**. Sinds #895 heeft die kolom al een eigen rol (*Einddatum*), dus dat waren twee
namen voor dezelfde kolom. De join is weg; *Startdatum* en *Einddatum* blijven.

**De sleutels wijzigen wél**, anders dan bij #899 — een object verandert van klasse
én van betekenis. De bewaarde selecties gaan hieronder mee, en de gate van #880 is
het net eronder: een rapport dat naar een verdwenen sleutel wijst, valt daar om.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "117"
down_revision = "116"
branch_labels = None
depends_on = None


# Per meegeleverd rapport: welke datumsleutel het nu moet noemen. De vertaling
# hangt af van het FEIT dat het rapport bevraagt — en dat was nu net het probleem:
# uit de oude sleutel alleen was het niet af te leiden.
HERSCHREVEN: dict[str, dict[str, str]] = {
    "revenue_per_month": {"date_month": "payment_created_month"},
    "payment_method_per_month": {"date_month": "payment_created_month"},
    "form_usage": {"date_month": "submission_date_month"},
    "members_per_year": {"date_year": "membership_year"},
    "membership_flow_per_year": {"date_year": "membership_year"},
    "member_demographics": {"date_year": "membership_year"},
    "dashboard_active_members": {"date_year": "membership_year"},
    "households_per_board_member": {"date_year": "membership_year"},
}


def upgrade() -> None:
    bind = op.get_bind()
    for sleutel, vertaling in HERSCHREVEN.items():
        rijen = bind.execute(sa.text(
            "SELECT id, selection::text FROM reporting.saved_reports "
            "WHERE builtin_key = :k AND deleted_at IS NULL"), {"k": sleutel})
        for rij_id, ruw in rijen:
            selectie = json.loads(ruw)
            gewijzigd = False
            for oud, nieuw in vertaling.items():
                vervangen = json.loads(
                    json.dumps(selectie).replace(f'"{oud}"', f'"{nieuw}"'))
                if vervangen != selectie:
                    selectie, gewijzigd = vervangen, True
            if gewijzigd:
                bind.execute(sa.text(
                    "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
                    "WHERE id = :id"), {"s": json.dumps(selectie), "id": rij_id})

    # Wat iemand zelf bouwde kan hier niet vertaald worden: welke datum bedoeld is,
    # hangt af van het feit, en dat is precies wat uit de oude sleutel niet af te
    # leiden viel. Melden dus, in plaats van gokken.
    resterend = bind.execute(sa.text(
        "SELECT id, name FROM reporting.saved_reports "
        "WHERE deleted_at IS NULL AND builtin_key IS NULL "
        "  AND selection::text LIKE '%\"date_%'"
    )).fetchall()
    for rij in resterend:
        print(f"  #901: bewaard rapport {rij[0]} ({rij[1]}) gebruikt de oude "
              f"gedeelde datum; open het en kies de datum van zijn onderwerp.")


def downgrade() -> None:
    pass
