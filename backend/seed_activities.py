"""Seed all Raak Millegem activities from historical data."""
import sys
from datetime import date, datetime
from app.database import SessionLocal
from app.models.activity import Activity, Registration
from app.models.activity_sub_registration import ActivitySubRegistration

db = SessionLocal()

if "--reset" in sys.argv:
    print("Resetting activities...")
    db.query(ActivitySubRegistration).delete()
    db.query(Registration).delete()
    db.query(Activity).delete()
    db.commit()
    print("Done.")

def add_activity(
    name, date_start, location=None, time=None,
    poster_url=None, members_only=False, is_cancelled=False,
    is_archived=True, date_end=None, notes=None,
    sub_registrations=None
):
    existing = db.query(Activity).filter(Activity.name == name, Activity.date == date_start).first()
    if existing:
        return existing

    activity = Activity(
        name=name,
        date=date_start,
        date_end=date_end,
        time=time,
        location=location or "Millegem",
        poster_url=poster_url,
        members_only=members_only,
        is_cancelled=is_cancelled,
        is_archived=is_archived,
        registration_type_code="INDIVIDUAL",
        price=0,
        notes=notes,
    )
    db.add(activity)
    db.flush()

    if sub_registrations:
        for i, sub in enumerate(sub_registrations):
            db.add(ActivitySubRegistration(
                activity_id=activity.id,
                name=sub.get("name"),
                description=sub.get("description"),
                external_register_url=sub.get("register_url"),
                external_registrations_url=sub.get("registrations_url"),
                registration_type_code="INDIVIDUAL",
                is_free=sub.get("is_free", True),
                price=sub.get("price", 0),
                sort_order=i,
            ))

    return activity

try:
    # === 2026 (upcoming) ===
    add_activity("Mannenkroegentocht", date(2026, 6, 12), time="20:00", location="Millegem",
        poster_url="https://drive.google.com/file/d/1DyYBCYugRl8ygTdMnifQeAuzGX_xsAKz/view",
        members_only=True, is_archived=False,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/TXEVZXNL2GPEiyYx7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vR9RmgeoyuM2deAC_5ylhCqUY9kZsC-zHZ5tT4Md8I5Aggb_iwLKFOsQ3yOjxuWZqDgPwFookDzEEYE/pubhtml?gid=1101066722&single=true"}])

    add_activity("Fotozoektocht", date(2026, 6, 1), location="Millegem", is_archived=False, notes="juni-september")

    add_activity("Ledenfeest", date(2026, 6, 27), location="Chiro Millegem",
        poster_url="https://drive.google.com/file/d/1ih62JEP6vowgTfKdtc6MPwohZyvPvjzM/view",
        members_only=True, is_archived=False,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/erYgq7yWyh3EQJrF6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vR6AK7Ka3kATzeKi34Rb0hJHoTTrd-Gies-f-WB6ERlcn9BopmaayTNvxfpIEiiOK0rcG_Y-52ondrr/pubhtml?gid=2037320537&single=true"}])

    add_activity("Gezinsuitstap Irrland", date(2026, 8, 16), time="07:45", location="Lindeplein (vertrek)",
        poster_url="https://drive.google.com/file/d/1DJUbe9LkJvmASEgtQxwKWYapFDspr7kF/view",
        is_archived=False,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/E4XYUEWFsDhrhEV99", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRPa7U-ImQmV8qAuACy2vT6bTsdtOum-s9B_hJLiJ9GwwVRZwLl3uG7dVSMPlqWqQkRgBDNMbeGJohf/pubhtml?gid=2030255716&single=true"}])

    add_activity("Brood en Spelen", date(2026, 8, 29), time="14:00", location="Chiro",
        poster_url="https://drive.google.com/file/d/1ZAQUQa8_OngLP9th2etPKON-6TZGkw4p/view",
        is_archived=False)

    add_activity("Bezoek wijndomein Aldeneyck", date(2026, 9, 5), time="09:00", location="Kerk (vertrek, eigen vervoer)", is_archived=False)

    add_activity("Comedy Festival", date(2026, 9, 11), time="20:00", location="Miloheem",
        poster_url="https://drive.google.com/file/d/1t48_DsOjFZ6V-3xb4SPnI_DuDJBmdnrO/view",
        is_archived=False,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://shop.stamhoofd.be/comedy-raak-millegem"}])

    add_activity("Wandelweekend Eifel", date(2026, 9, 18), date_end=date(2026, 9, 20), location="Eifel",
        poster_url="https://drive.google.com/file/d/19E8CKprHDhPjMZRkCViI7ZcDi7CwZ3bN/view",
        is_archived=False,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/3CTvybCkt8QcGxcq6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRKYFtlTL5I_JYf2kk4UIL6gRRSlXunCGE_-plyMhpCF8baOfxiAX0akIzX3OT7DR4G1a_4dgUT_srm/pubhtml?gid=989683599&single=true"}])

    add_activity("Zo vader zo zoon", date(2026, 9, 25), time="20:00", location="Miloheem", is_archived=False)
    add_activity("Raak Café", date(2026, 10, 18), time="13:00", location="Miloheem", is_archived=False, notes="13u-16u30")
    add_activity("Bowlen", date(2026, 11, 15), time="09:45", location="Bowling Bruul", is_archived=False, notes="10u start")
    add_activity("Zettersprijskamp", date(2026, 11, 20), time="20:00", location="Miloheem", is_archived=False)
    add_activity("Sint komt naar onze gezinnen", date(2026, 11, 27), date_end=date(2026, 11, 28), location="Bij de gezinnen", members_only=True, is_archived=False)
    add_activity("Kerststal", date(2026, 12, 6), date_end=date(2027, 1, 7), location="Millegem", is_archived=False)
    add_activity("Kerstherberg", date(2026, 12, 25), date_end=date(2026, 12, 30), location="Kerk & Lindeplein", is_archived=False)

    # === 2027 (upcoming) ===
    add_activity("Fietsweekend Grubbenvorst", date(2027, 5, 7), date_end=date(2027, 5, 9), location="Witte Dame, Grubbenvorst (Venlo)", members_only=True, is_archived=False)

    # === 2026 (archived) ===
    add_activity("Bierproefavond", date(2026, 2, 13), time="20:00", location="Miloheem",
        poster_url="https://drive.google.com/file/d/1p-0ncE4Lwwamg7vvReFcPKP1Nbqedu-D/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/Jfk6JMLFFLx2uzqg7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTXnCXXuEMhK7cEPqazJZi9ekxzWaB60CyBXFnP5eMGRD13btZhjjbVpP7lIL_nxi0_hvkFzf/pubhtml"}])

    add_activity("Helpersdrink", date(2026, 2, 20), time="20:00", location="Miloheem", members_only=True, notes="enkel helpers")

    add_activity("Dartstornooi", date(2026, 3, 7), time="19:00", location="Miloheem",
        poster_url="https://drive.google.com/file/d/11M2Y4UYLZz5XqSaBlPTJ9sFyJfXYsOuF/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/grMnWQ2e41eZ63Ph9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTQ7f9b2V-2zMnJ_9ULU8pseaLF3qAAp8BBpxH4VRdXeG_CfDKUzhtNFR7Jjf2fSglvzKVY9cNJe1sj/pubhtml?gid=1853566764&single=true"}])

    add_activity("Kookworkshop Surinaamse keuken", date(2026, 3, 12), time="19:00", location="Miloheem",
        poster_url="https://drive.google.com/file/d/1hTe50sCRmvddCkDYa-2yKRvddCkDYa-2/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/9CL1X4ZMLBa4R6Wz7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRa-2fKSHsz2rXPEds3y7w-_c9ZGo70qRUKZ6tE9sIhl4V2XkqrpLwOw0jxlO_731mEU1rI7U86M9qK/pubhtml?gid=2038422098&single=true"}])

    add_activity("Millegem Kwist! Quizt Millegem?", date(2026, 3, 14), time="19:30", location="Miloheem",
        poster_url="https://drive.google.com/file/d/15kWMsSGmmlUUmGsDFL_eT-I7CGS_b2zB/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/83r3t7F9c46QUvpk7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRqgXoynXzcH33DzrC-jCh1b8NTyKdo_52ixSREwVKg-FCACmTfQnw2utzghsUZZqTSgDdWzq3LdZZK/pubhtml?gid=857377081&single=true"}])

    add_activity("Kookworkshop Indische keuken", date(2026, 3, 26), time="19:00", location="Miloheem",
        poster_url="https://drive.google.com/file/d/1nziIPrl03g8EhSSLCECTNrQ4w4LBB6qY/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/dAZDEfQNjU3F63UT9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRUv0vnVSXO_bYGDrM2p3foKfkyKBvP9HYPGJkkfKSXkH0i85pgKhRHcIPsHKtW9lpXHco2XHVAoHsO/pubhtml?gid=260985097&single=true"}])

    add_activity("Bunkerwandeling", date(2026, 4, 18), time="09:00", location="SAS4",
        poster_url="https://drive.google.com/file/d/1_PRkUl9CTSECk4yriveHCOV56yKWfrs7/view",
        notes="9u-11u30",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/wuEuz7mEfroJPQoJ7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vS8XjF9g5wfYcBUi6ficyE1nuu6Hry1t0wRJ3BcZk6FMq2kxCaucJV9Ohu7LfFZL4U5cNKa1Rfkikwi/pubhtml?gid=1221495790&single=true"}])

    add_activity("Fietsweekend Wintelre", date(2026, 5, 1), date_end=date(2026, 5, 3), location="Wintelre (NL)",
        poster_url="https://drive.google.com/file/d/1ORD79tv2bczRSZH8csB2fG0URRtXHqeG/view",
        members_only=True, notes="inschrijven tot 24 december",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/Neo526PhRJHBmVVg9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRZimk4CBW2MbSfCS5QzehN5hL-9L-jdMkGsH7zRXHFsRJBM6OAUH1qb_2FMRAa51tW0Ch7bZHmF7j4/pubhtml?gid=1984299190&single=true"}])

    add_activity("Gezinsweekend Reigersnest Koksijde", date(2026, 5, 1), date_end=date(2026, 5, 3), location="Koksijde",
        poster_url="https://drive.google.com/file/d/1u8DRNA1FpBOUowyqJd7VP1Io5kBCHVt-/view",
        members_only=True, notes="inschrijven tot 4 januari",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/gLnC5USbmafPAEuM8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQlGRKG171C3iMSaVt9RYBJXcCdXZDlsy3P8LwbrHmLlD5QfVoq04rW7O4KzgR824OV73Vn0OClBimD/pubhtml?gid=402355748&single=true"}])

    add_activity("Te voet of Te Fiets naar Scherpenheuvel", date(2026, 5, 9), time="05:00", location="Lindeplein",
        poster_url="https://drive.google.com/file/d/177vYUlZIrav7gTFsz1bPYcBp8JZLudEt/view",
        notes="5u te voet of 9u te fiets",
        sub_registrations=[
            {"name": "Inschrijven wandelen en fietsen", "register_url": "https://forms.gle/Vj2iAQAp48RuvGeTA", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTb4q9UNu0dRl_Ezi1DvSGEDpKzsCT65sVj_5zSN2WNhKydyNt97ERNAh63Bt-uUB-bSXzHopeXV8cq/pubhtml?gid=358458357&single=true"},
            {"name": "Inschrijven eten (foodtrucks Raak nationaal)", "register_url": "https://shop.stamhoofd.be/stappen-klappen-trappen-naar-scherpenheuvel/"},
        ])

    add_activity("Zotte 50 van Gheel", date(2026, 5, 30), location="Gheel")

    # === 2025 (archived) ===
    add_activity("Bezoek Tabloo Expo", date(2025, 2, 2), time="10:00", location="Tabloo Dessel",
        poster_url="https://drive.google.com/file/d/14ei2QcSXtwDLbKGRoT6Dz-JIolyPUbyM/view",
        notes="10u-12u",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/szyAgSJL6Q15mXtRA", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTejnMIfeDKINVzJecOaOJ4rSjbjqhbcQrHwpsbgcgQHVifMzJ8WA4ekb2ngU5hkOD9mMFLUU9krqH7/pubhtml?gid=445607477&single=true"}])

    add_activity("Helpersdrink", date(2025, 2, 21), time="20:00", location="Miloheem", members_only=True, notes="enkel helpers")

    add_activity("Op Stap in Gent: de 7 werken van barmhartigheid", date(2025, 3, 9), time="07:30", location="Station Mol (vertrek)",
        poster_url="https://drive.google.com/file/d/1ACYV8XJUt3vSB0swt-U4aCatX0HYRAPw/view")

    add_activity("Millegem Kwist! Quizt Millegem?", date(2025, 3, 15), time="19:30", location="Miloheem",
        poster_url="https://drive.google.com/file/d/18KHkpdk_C5lUKFq8kpdk_C5lUKFq/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/BNZ1Gi2qn16W48yT9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTlAiJTCiR9TFGJBqTW0M1uiKW_EyrUFrvKJiaKJzLZZl6LNPj5LR3_15kTjkS93HNvR4lJFkLn4q34/pubhtml?gid=946762086&single=true"}])

    add_activity("Ledenfeest", date(2025, 3, 29), time="12:30", location="Scouts Ezaart",
        poster_url="https://drive.google.com/file/d/1OQrmtCWK_ah20S_5ZoARAYuif/view",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/PuMn4yLyQBV2h7Pv9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTCQ4JGaTkPDKi5gPta5-o-tgQva2l8dlNeiYgOGdfIeTlXWDCOjyrROPp0hzeyCJ0PCJh1LZqidN-v/pubhtml?gid=1147485884&single=true"}])

    add_activity("Bezoek Mokapi Koffie Laakdal", date(2025, 4, 11), time="13:30", location="Laakdal",
        poster_url="https://drive.google.com/file/d/18sJtu38b1trKxgpZBe7Cpf92fhb_wylV/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/Bvwo9ZJ7LooqcrcDA", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSWyTClJEog6Ng8p-7ainOtJSovpDvIGBnpv5BpUh7vCUBhmgcYyLwjX3Z7voTfTkMgsvYJmirKaKG-/pubhtml?gid=781551902&single=true"}])

    add_activity("Te voet of Te Fiets naar Scherpenheuvel", date(2025, 5, 1), time="06:00", location="Lindeplein",
        poster_url="https://drive.google.com/file/d/1kfweMJJ5pOyUBPGFtpV3ejDy4EPNXf1J/view",
        notes="6u te voet of 9u te fiets",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/rGaphkr8TJsDSnbm6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRouCnmnQQp2-sdQvbmO51Lw2hpAX36_J59c26np6QqbVKDNFBCWFetZjt8Q1OkHvZ1tY6jt9bKahku/pubhtml?gid=1930666359&single=true"}])

    add_activity("Fietsweekend Arcen", date(2025, 5, 2), date_end=date(2025, 5, 4), location="Arcen (NL)", members_only=True, notes="inschrijven tot 29 december")

    add_activity("Infoavond brandwonden bij kinderen", date(2025, 5, 15), time="19:00", location="MillekeMol",
        poster_url="https://drive.google.com/file/d/1H2CYguHQPwRf7jJ1cOkkK_V71fsnuA67/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/ntSMUAVEgtQgwm1e9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSuNEcPsYKry0_eiBHlRORFMH7_dVLYvx4xDIi21tg8KSRi9GEDb7Cb6Poh9vXYtoDjwGnflFJKePDt/pubhtml?gid=175044806&single=true"}])

    add_activity("Fiets- en Gezinsweekend Maasmechelen Fabiola", date(2025, 5, 23), date_end=date(2025, 5, 25), time="18:30", location="Maasmechelen",
        poster_url="https://drive.google.com/file/d/1pxgQRqpZVNmSC7aovlsRvwQ9HLyOnYfn/view",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/mEzjxkuWYviMepd59", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQjFYUmCpjgmOqKq7aaqsgwBEKj1__e58tZUfItDto1zz2M4VMbigoz2mEVlC5HITUC1urnBw3ORfO3/pubhtml?gid=1215941626&single=true"}])

    add_activity("Zotte 50 van Gheel", date(2025, 5, 31), location="Gheel")

    add_activity("Wandeling Landschap de Liereman", date(2025, 6, 21), time="09:00", location="Oud-Turnhout",
        poster_url="https://drive.google.com/file/d/19Zh3Qw-v6aLqpa8u45a9WhTg-ipvptTz/view",
        notes="9u-12u",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/h5MAttfRaggdZMHq8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vScdTXeUiJo39DsX_RiTaDFYh7CF6DNSKWkxz0y7ztmux50xrhXSkJtc18Wi9SRzASjhE7WKXbQ7U2M/pubhtml?gid=587656731&single=true"}])

    add_activity("Soldaat voor één dag", date(2025, 6, 25), time="13:00", location="Lindeplein",
        poster_url="https://drive.google.com/file/d/1jcIy9rXZL9tbUgmdc-9UV9vJcIy9rXZL9tbUgmdc/view",
        notes="6de leerjaar - 6de middelbaar",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/MhBTwTtgXTnCrghW6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vR8piJt0GNt90pcRdKT4HiDKgYUGKIszLma1S-9vijVY7PnS9IMW5ZD6A-oH6HNApEWo-msO5pFlLxj/pubhtml?gid=1939080127&single=true"}])

    add_activity("Brood en Spelen", date(2025, 8, 30), time="14:00", location="Chiro",
        poster_url="https://drive.google.com/file/d/13J4GM9OsswOrE_EjWBsMhRPzNC8v9agI/view",
        sub_registrations=[
            {"name": "Barbecue", "register_url": "https://forms.gle/2ChSwo8BmJMaUt2t6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQb3cIqNBqmguqvZTFX8Z9wamD3GCYxmoL-P0nZ5FQm61IQ-m7l77AmmQ8SumfyQBEhMGWmaXly7p9j/pubhtml?gid=254633452&single=true", "is_free": False},
            {"name": "Cornhole toernooi (ploeg 2 of 4 personen)", "register_url": "https://forms.gle/nSxqWVTtBmwih84V6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vR1ZmuuhoYyr9P9-7PuTQ5AVPBeru0cb7oIdepOBsRQGscpgSvlJkXiy7sWfMp6LTwclGg3w7OjAQXd/pubhtml?gid=1451593528&single=true"},
            {"name": "Wereldkampioenschap Raakpong", "register_url": "https://forms.gle/r8BQCnFpmghUjayT7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vS79E8NawK2xba1eaYU9Ql9wy5lrfNyCOCii5PipvwfYvpDd7L00IQG-eSfx42xuP2o9VsJOGUeIXG0/pubhtml?gid=335029383&single=true"},
            {"name": "Helpers", "register_url": "https://forms.gle/aEwQJadc3Fxe8Pqq6"},
        ])

    add_activity("Aquapark Zilvermeer", date(2025, 9, 13), time="10:25", location="Zilvermeer",
        poster_url="https://drive.google.com/file/d/1KYd9xJN_w8r0Ii9rlHYwdHUb2Tg-LiEN/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/XVqjVze5J24admKR8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSiIJu8BLKQvMHtJOGBSvHFiCW6QlE1pQxyX-o4GtDSa-yrjYJUWgMxulWnwsMzNQ9THIvPBnUhgv3q/pubhtml?gid=1485566172&single=true"}])

    add_activity("Wandelweekend", date(2025, 9, 19), date_end=date(2025, 9, 21), location="Wandelweekend",
        poster_url="https://drive.google.com/file/d/1TLFas16YdMmC_ijpozrrwOwQMKp4S4R7/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/eKotbtcubbTXrvMp8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQXGQv7CCf9-ggu3Mv1f3B8BiN9Ep9PI1rfjK9FR383tj9iBjfzg/pubhtml"}])

    add_activity("Speeltuin Kinderweelde", date(2025, 9, 27), time="09:30", location="Kinderweelde",
        poster_url="https://drive.google.com/file/d/1GTcl2Q3KZ-GjShX33RWHyRgmt52h9QXy/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/mPJ8R8gP52eycSyr9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRzKfusxHYMTULgmDaGouBJBzl2_0_dqokWJV8dNKLe6AcaylEyrH24uCEqWbh5gss1Lexkys0BPmaf/pubhtml?gid=554080093&single=true"}])

    add_activity("RAAK opent Millegem Kermis", date(2025, 10, 24), time="20:00", location="Miloheem", members_only=True)

    add_activity("Infoavond Cybersecurity", date(2025, 11, 13), time="20:00", location="Miloheem",
        poster_url="https://drive.google.com/file/d/1luOQtopv-HOdrbeFYEQdX1rqweNVLoyQ/view",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/KAM5Mc11W3JKVGzF8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTIaoSwGwH8EDPWwUSOvkam0nYUztOkWwOz9LdMG-rbaPoKTot0TWjDdLVsPVzoV00Sk4x17hx4fAoP/pubhtml?gid=1807764513&single=true"}])

    add_activity("Bowlen", date(2025, 11, 16), time="09:45", location="Bowling Bruul",
        poster_url="https://drive.google.com/file/d/1eHFTM1qdYm1RuShtiDEkVGDBx5nCzNNW/view",
        notes="10u start",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/Zbju3XJ9aH7Ch5Eq8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTw8OLXPRbZQF6CTPNyOV47n2K_QxAxYQM9FGQ-bDnKDj1kUn9KPEMeJNUHHwzVKcTJ5ONQgUIMwfxj/pubhtml?gid=315769761&single=true"}])

    add_activity("Sint komt naar onze gezinnen", date(2025, 11, 28), date_end=date(2025, 11, 29), location="Bij de gezinnen",
        poster_url="https://drive.google.com/file/d/1Nzdr_t8c24DO_AGg4qX-Kt6Gm9YIDU2Z/view",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/QjuHEndWQhJU1uQHA", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTP3YqA0yeCXxb6iQCE1HU8WlECKAtHfoAa3Xn0jH2GLNU-QDPCECUFc1jDuSk-6QjA98Eq89hLl7XI/pubhtml?gid=1383442225&single=true"}])

    add_activity("Kerststal", date(2025, 12, 7), date_end=date(2026, 1, 8), location="Millegem")
    add_activity("Kerstherberg", date(2025, 12, 25), date_end=date(2025, 12, 30), location="Kerk & Lindeplein",
        poster_url="https://drive.google.com/file/d/18X2bZwqXimYURShpeAcM18B-phdI3EO0/view")
    add_activity("Kerstradio", date(2025, 12, 27), time="10:00", location="Lindeplein (voor kerk)", notes="10u tot 20u")
    add_activity("Lichtjeswandeling", date(2025, 12, 28), time="17:00", location="Kerstherberg, Lindeplein",
        poster_url="https://drive.google.com/file/d/10uZrPsYHUQYQEZY1Jz-V9-Rv2pr0ZUKB/view")

    # === 2024 (archived) ===
    add_activity("Millegem Kwist! Quizt Millegem?", date(2024, 3, 9), time="19:30", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/UvGVFh98etTVgWZs9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRPml6LDA2veq6kVnnkeMCmDfqCTYZjBacvvevnsuLEDUwpB5EnLNpy0zNM_Hjc8RIbRMrdY_IhgHzj/pubhtml?gid=811564582&single=true"}])
    add_activity("Helpersdrink", date(2024, 3, 15), time="20:00", location="Miloheem", members_only=True, notes="enkel helpers")
    add_activity("Infosessie Veilig op de fiets", date(2024, 3, 22), time="19:30", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/YZygwq8fcx9JeSQR8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQAtNA6Dp4LYjhivONsBqIOfkCwYOc1lETyTB_gmhlpfE5A2uxhNzaBk6mCTXr4uBdVRqa7Fn0t7RC0/pubhtml?gid=859709733&single=true"}])
    add_activity("Moordspel Gotcha", date(2024, 3, 31), notes="inschrijven tot 22 maart, materiaaldag 27 maart",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/6BcVo4CSyBw1utFy9"}])
    add_activity("Met KWB naar Toneel 'De Madammen van de Macadam'", date(2024, 4, 12), time="20:00", location="MollekeMil",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/3u6GDoLfkThcsfeCA", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSLRgedXntqmoqYiScdrUIQ41qTz2JchWv7z3oLzXv8htmNWTXTJBx1e0lqMbyKTEK-fqqTZFpJO-pI/pubhtml?gid=1738207638&single=true"}])
    add_activity("Te voet of Te Fiets naar Scherpenheuvel", date(2024, 5, 1), time="06:00", location="Lindeplein",
        notes="6u te voet of 9u te fiets",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/eonhEoD4vUxcuVWx5", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTM7UA1J21Bt1fERMcycZzWRSgyIR6ty1vZMD12aG07qt2EDNZfypMavG9BYT7ZmQdsVZ5KKPRRnG2E/pubhtml?gid=137546810&single=true"}])
    add_activity("Fietsweekend De Spaenjerd Kinrooi", date(2024, 5, 3), date_end=date(2024, 5, 5), location="Kinrooi", members_only=True)
    add_activity("Fiets- en Gezinsweekend Voeren De Veurs", date(2024, 5, 17), date_end=date(2024, 5, 19), time="18:30", location="Voeren",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/1cFxivoLMA8Uhdsx5", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTvfSEA6mthWllMQIM6xatlhKC_L8v0gm9YlIpzjFfqqu0IZSGL8OLuqRYMeJfBzz1awjSCYLv5d-xe/pubhtml?gid=1496878476&single=true"}])
    add_activity("Zotte 50 van Gheel", date(2024, 5, 25), location="Gheel")
    add_activity("Ledenfeest", date(2024, 6, 1), time="12:00", location="Chirolokaal Millegem", members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/ndsYj9gimVhtZeqz9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vThorWrEE2Yq0EcNJjpfD_Lj896PCrsBUH0Nqs9iQhGe77aDvsCAUdz3vUPOvVUy8RqdgOaz9xI3tTx/pubhtml?gid=182181313&single=true"}])
    add_activity("Aquapark Zilvermeer", date(2024, 6, 8), time="10:20", location="Zilvermeer",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/22Nmi8G63SZpd24Q6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ8gvkxCHHR2-VkhKpqVKwXZCqyOagsh3LoqrXdSYNEyBc92OcAhsHrRrsh9yFv6HTMkNxmA0vD-dpN/pubhtml?gid=376892800&single=true"}])
    add_activity("Suppen Sas4toren Dessel", date(2024, 6, 26), time="14:00", location="Lindeplein (vertrek)",
        notes="voor jongeren van 2004-2012",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/yX47nQptNbZTy7DC6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vR4ddL3LRVHq1fKKP-I2k2hndeaCGQkq8iWxrak2xsFMEIWlU3tYZBuf9k7jW-r7-FeaWdUl1QGDFfB/pubhtml"}])
    add_activity("Bezoek Kabouterberg", date(2024, 8, 18), time="13:15", location="Kabouterstraat Kasterlee")
    add_activity("Brood en Spelen", date(2024, 8, 31), time="14:00", location="Chiro",
        sub_registrations=[
            {"name": "Cornhole toernooi (ploeg 2 of 4 personen)", "register_url": "https://forms.gle/5RgqZ7zJn1GDCJvK8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEa172nXKQpVoqaF5hd8PX3Zltc7f8xW2Ro7LpjpLVbFxnnp3I3QMlJVb8AICpLIXCkKIB1qpZEF5S/pubhtml?gid=1805961499&single=true"},
            {"name": "Barbecue", "register_url": "https://forms.gle/vaXYvEXfBVLG7Hpn8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMSUaX32lDg8q8y1ueaFyPaZQ3yBzDh1OnzJ29cD10_BsjwhaVJ8wl9n6OnYlmRuxE0GR58JI98KXE/pubhtml?gid=670827743&single=true", "is_free": False},
            {"name": "Helpers", "register_url": "https://forms.gle/Ys8JUVYd9m4CAZPF9"},
        ])
    add_activity("Wandeling Gebeten door De Zegge", date(2024, 9, 7), time="09:00", location="Millegem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/LEv7LMok4nLn8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTmBS3c52I5IS3VQoYe9kId-10R0lhDL1tYN32Sa4dy2oQBzkkI_G1UumZshn1ecnN324uAck3Yw0EV/pubhtml?gid=1108753390&single=true"}])
    add_activity("Wijngaard ten Gaerde Begijnendijk", date(2024, 9, 14), time="14:00", location="Lindeplein (vertrek)",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/C8ShE8S5Uv7v31cU7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vTbSW5Momd2Yn4URS3HHITTWWzdrEQCMT5cZN-2-rwlKRrRs60-rjQMPARsaEVbRziD_QhziOeuyUns/pubhtml?gid=240782374&single=true"}])
    add_activity("Wandelweekend Hotel Seemöwe Simmerath", date(2024, 9, 20), date_end=date(2024, 9, 22), location="Simmerath (DE)", members_only=True)
    add_activity("Tequila en Mezcal tasting", date(2024, 10, 4), time="20:00", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/YmCup2pftBD5FH988"}])
    add_activity("Infosessie Opfrissing wegcode", date(2024, 10, 10), time="20:00", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/PsmCiaZVvWGVDzebA"}])
    add_activity("KWB opent Millegem Kermis", date(2024, 10, 25), time="20:30", location="Café Christiane", members_only=True)
    add_activity("Bowlen", date(2024, 11, 17), time="09:45", location="Bowling Bruul",
        notes="10u start",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/4TgjAPxYGpimw56d9", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQburYNFEdkvg1pe_0tXPPrqiRsYzF6L5vUmR9ekCUJTBaQlfHmy2TEwkqr7rtpyh3DeUWVATBSpPrb/pubhtml?gid=811148801&single=true"}])
    add_activity("Dartstornooi", date(2024, 11, 22), time="19:00", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/zyHsopA8LuRZXb4f8", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSU8M23utO0axr22y_510Y_EdO8dD61P_H4BzlX21uEW6ehkb_7ndvpIEUNZV5GOi1QD3wUiW4_QLKD/pubhtml?gid=857448136&single=true"}])
    add_activity("Sint komt naar onze gezinnen", date(2024, 11, 29), date_end=date(2024, 11, 30), location="Bij de gezinnen",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/x2DxErTREDL4SsLK6", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRlzdrXki0fK1TfOBf7EFgqkMqSD63-Lct4vRPyRYvGrMKEXiAQqiNhGN9GWeI0s9IeLjAhg9mlKBMw/pubhtml?gid=1475980686&single=true"}])
    add_activity("Schaatsen", date(2024, 12, 15), time="09:15", location="Lindeplein (vertrek naar Herentals)",
        sub_registrations=[
            {"name": "Inschrijven op lijst Raak (groepstarief)", "register_url": "https://forms.gle/5rzZDEpyukwFx8My7", "registrations_url": "https://docs.google.com/spreadsheets/d/e/2PACX-1vR8ITURRunJwJb3m9jkJhlGtn9mUeR1xxF77qtFsW46v3YS1uCk0-N6FFbXQ-x3SldG478OwX-mcWnI/pubhtml?gid=1428387968&single=true"},
            {"name": "Tickets kopen Sport Vlaanderen Herentals", "register_url": "https://www.sport.vlaanderen/waar-sporten/onze-centra/sport-vlaanderen-herentals/tickets/"},
        ])
    add_activity("Kerststal", date(2024, 12, 8), date_end=date(2025, 1, 2), location="Millegem")
    add_activity("Kerstherberg", date(2024, 12, 25), date_end=date(2024, 12, 30), time="14:00", location="Kerk & Lindeplein",
        poster_url="https://drive.google.com/file/d/1-WCea0MjRhe6ppSXQA07ibWE_XS-FH03/view",
        notes="14u tot 23u")
    add_activity("Kerstradio", date(2024, 12, 28), time="10:00", location="Lindeplein (voor kerk)", notes="10u tot 18u")
    add_activity("Lichtjeswandeling", date(2024, 12, 29), time="16:00", location="Kerstherberg, Lindeplein",
        poster_url="https://drive.google.com/file/d/16GC1wHgWOqFxXKTuDkHensVzkIcVSk/view")

    # === 2023 (archived) ===
    add_activity("Avondwandeling", date(2023, 2, 3), time="19:30", location="Miloheem (vertrek)",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/H2BDob7hqnyyd1F39"}])
    add_activity("Binnenspeeltuin Tarzan & Jane", date(2023, 2, 11), time="13:00", location="Kerkplein (vertrek)",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/KwY5is4kBnDKt6eP9"}])
    add_activity("Millegems Bal", date(2023, 2, 11), time="20:00", location="Miloheem")
    add_activity("Clip n Climb Alpamayo Beringen", date(2023, 2, 18), time="13:45", location="Lindeplein (vertrek)",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/j99S5oq686K5aRxU6"}])
    add_activity("Wijnbeurs Wijnfocus", date(2023, 3, 4), time="13:30", location="Lindeplein (vertrek) / Elsum",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/FXnE2guTgCWkisrC8"}])
    add_activity("Millegem Kwist! Quizt Millegem?", date(2023, 3, 18), time="19:30", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/9eykCQNdEKvXH6VM8"}])
    add_activity("Met KWB naar Toneel 'Onweer op komst!!'", date(2023, 4, 14), time="20:00", location="MollekeMil",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/MYuQVeLCqTAzR41Y7"}])
    add_activity("Ledenfeest 2023", date(2023, 4, 15), time="13:00", location="Chirolokaal Millegem",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/taFunqwPs9Q4qVuD6"}])
    add_activity("Te voet of met de fiets naar Scherpenheuvel", date(2023, 5, 1), time="06:00", location="Lindeplein",
        notes="6u te voet of 9u met fiets",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/tmhqeYUZCnKtR6Lb7"}])
    add_activity("Fietsweekend Nieuwe Berk Essen", date(2023, 5, 5), date_end=date(2023, 5, 7), location="Essen",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/VA3n4eaQ6aWzmJsW9"}])
    add_activity("Fiets- en Gezinsweekend Bosberg Houthalen", date(2023, 5, 12), date_end=date(2023, 5, 14), time="18:30", location="Houthalen",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/Y7YWPk5kGgjMwxvh6"}])
    add_activity("Zotte 50 van Gheel", date(2023, 5, 20), location="Gheel",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/HwxrJcmCGc1ti4w9u9"}])
    add_activity("Muziek-kien for ladies", date(2023, 6, 23), time="20:00", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/UAD33kShkExtav1W9"}])
    add_activity("Boogschieten Olympia", date(2023, 6, 24), time="09:15", location="Lindeplein (fiets vertrek)",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/VQfCyvCnR2kfCy7w8"}])
    add_activity("Aquapark Zilvermeer", date(2023, 8, 26), time="10:00", location="Lindeplein (vertrek)",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/pemp6D7JRBH6VD1b9"}])
    add_activity("Brood en Spelen", date(2023, 9, 2), time="14:00", location="Chiro",
        sub_registrations=[
            {"name": "Cornhole toernooi (ploeg 2 of 4 personen)", "register_url": "https://forms.gle/4fKUYjZwiiFyXw8X7"},
            {"name": "Barbecue", "register_url": "https://forms.gle/PzaAxC3gKnvbmNc97", "is_free": False},
            {"name": "Darts tornooi", "register_url": "https://forms.gle/s2zKChDgEeZmnGsH6"},
            {"name": "Helpers", "register_url": "https://forms.gle/RoBCbofy4r5dqqES8"},
        ])
    add_activity("Wandelweekend Irrhausen Duitsland", date(2023, 9, 15), date_end=date(2023, 9, 17), location="Irrhausen (DE)", members_only=True)
    add_activity("KWB opent Millegem Kermis", date(2023, 10, 27), time="20:30", location="Café Christiane", members_only=True)
    add_activity("Bowlen", date(2023, 11, 12), time="09:45", location="Bowling Bruul",
        notes="10u start",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/48L6U26DWn3YeXV49"}])
    add_activity("Infoavond Mona", date(2023, 11, 15), time="19:30", location="Millekemol",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/RoMtxqMvEgX1rs5P9"}])
    add_activity("Sint komt naar onze gezinnen", date(2023, 12, 1), date_end=date(2023, 12, 2), location="Bij de gezinnen",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/qbByZhtu9FBhsNkx9"}])
    add_activity("Kerstherberg", date(2023, 12, 25), date_end=date(2023, 12, 30), location="Kerk & Lindeplein")
    add_activity("KWB Kerstradio", date(2023, 12, 27), time="10:00", location="Lindeplein (voor kerk)", notes="10u tot 20u")

    # === 2022 (archived) ===
    add_activity("Avond Bowling", date(2022, 3, 4), time="20:00", location="Bowling Bruul", members_only=True)
    add_activity("Millegem Kwist! Quizt Millegem?", date(2022, 3, 19), time="19:30", location="Miloheem", notes="VOLZET")
    add_activity("Mijn Fitte Fiets workshop", date(2022, 3, 24), time="19:30", location="Miloheem", members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/Ps2VJBtaN5dfTUke8"}])
    add_activity("Paaswandeling", date(2022, 4, 2), date_end=date(2022, 4, 24), location="Millegem")
    add_activity("Millegem Bloeit", date(2022, 4, 18), time="10:00", location="Miloheem", notes="10u-18u")
    add_activity("Ledenfeest", date(2022, 4, 23), time="13:00", location="Scoutslokaal Ezaart", members_only=True, notes="inschrijven via overschrijving vóór 15 april")
    add_activity("Fietsweekend Bree Mussenburghof", date(2022, 5, 6), date_end=date(2022, 5, 8), location="Bree", members_only=True)
    add_activity("Fiets- en Gezinsweekend Voeren", date(2022, 5, 20), date_end=date(2022, 5, 22), time="18:30", location="Voeren", members_only=True)
    add_activity("Zotte 50 van Gheel", date(2022, 5, 28), location="Gheel", members_only=True)
    add_activity("Initiatie Padel", date(2022, 6, 11), time="09:30", location="Tennis en Padelclub Field, Rauw",
        notes="9u30-12u30",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/5neJ8gaYnUz4U1uG7"}])
    add_activity("Bezoek wijndomein Kitsberg Heers", date(2022, 6, 12), time="09:00", location="Lindeplein",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/tnFRu8vGMaEZVE6B7"}])
    add_activity("Familiefietstocht en picknick Kinderweelde Meerhout", date(2022, 8, 7), time="13:00", location="Lindeplein",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/PxyhahTUSuNmhJty8"}])
    add_activity("Brood en Spelen", date(2022, 9, 3), time="14:00", location="Chiro",
        sub_registrations=[
            {"name": "Muziek-kien voor kinderen", "register_url": "https://forms.gle/KoEvTQRne27p46fy5"},
            {"name": "Barbecue", "register_url": "https://forms.gle/MiXyb6DHf1BHpVJp7", "is_free": False},
            {"name": "Dartstornooi", "register_url": "https://forms.gle/xWuSP6fSEKomvKMn7"},
            {"name": "Helper worden", "register_url": "https://forms.gle/whqMxbxbeJ1CKRg79"},
        ])
    add_activity("Wandelweekend Deudesfeld Eifel", date(2022, 9, 16), date_end=date(2022, 9, 18), location="Deudesfeld Eifel")
    add_activity("Whisky proefavond", date(2022, 10, 21), time="20:00", location="Miloheem",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/FxPduarUn9Pqyyrg9"}])
    add_activity("KWB opent Millegem Kermis", date(2022, 10, 28), time="20:30", location="Miloheem", members_only=True)
    add_activity("Bowlen", date(2022, 11, 13), time="10:00", location="Bowling Bruul",
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/9G6VNUjrvc5Kvn9B8"}])
    add_activity("Sint komt naar onze gezinnen", date(2022, 12, 2), date_end=date(2022, 12, 3), location="Bij de gezinnen",
        members_only=True,
        sub_registrations=[{"name": "Inschrijven", "register_url": "https://forms.gle/eKS4HPjp9MtuxmJ67"}])
    add_activity("Schaatsen", date(2022, 12, 18), time="09:15", location="Lindeplein (vertrek)",
        sub_registrations=[
            {"name": "Inschrijven op lijst KWB (groepstarief)", "register_url": "https://forms.gle/nmrTFSFzRJksJL2HA"},
            {"name": "Tickets kopen Sport Vlaanderen Herentals", "register_url": "https://www.sport.vlaanderen/waar-sporten/onze-centra/sport-vlaanderen-herentals/tickets/"},
        ])
    add_activity("Kerstherberg", date(2022, 12, 25), date_end=date(2022, 12, 30), time="13:00", location="Kerk & Lindeplein", notes="13u tot 23u")
    add_activity("Millegem Gloeit", date(2022, 12, 26), date_end=date(2022, 12, 29), time="14:00", location="Lindeplein", notes="14u tot 00u")
    add_activity("KWB Kerstradio", date(2022, 12, 30), time="12:00", location="Lindeplein (voor kerk)", notes="12u tot 20u")

    # === 2021 (archived) ===
    add_activity("Brood en Spelen", date(2021, 8, 28), location="Chiroplein")
    add_activity("Ledenfeest", date(2021, 9, 25), time="10:00", location="Chirolokaal", notes="10u-18u", members_only=True)
    add_activity("KWB opent Millegem Kermis", date(2021, 10, 29), time="20:30", location="Miloheem", members_only=True, notes="2 consumpties")
    add_activity("Bowlen", date(2021, 11, 7), time="09:00", location="Lindeplein (vertrek)")
    add_activity("Sint komt naar onze gezinnen", date(2021, 11, 26), date_end=date(2021, 11, 27), location="Bij de gezinnen", members_only=True)
    add_activity("UW GELD door Pascal Paepen", date(2021, 11, 18), time="19:30", location="Miloheem")
    add_activity("Infoavond Stroom op je dak", date(2021, 11, 25), time="20:00", location="Miloheem")
    add_activity("KWB Kerstradio", date(2021, 12, 29), time="11:00", location="ONLINE", notes="11u tot 19u")

    # === 2020 (archived) ===
    add_activity("Binnenspeeltuin", date(2020, 1, 25), time="13:00", location="Kerkplein (vertrek)")
    add_activity("Avondwandeling", date(2020, 1, 31), time="19:30", location="Miloheem (vertrek)")
    add_activity("Millegems Bal", date(2020, 2, 15), time="20:00", location="Miloheem")
    add_activity("Opfrissing wegcode", date(2020, 2, 24), time="19:30", location="Miloheem")
    add_activity("Kanovaren", date(2020, 6, 27), time="09:00", location="Lindeplein")
    add_activity("Bezoek Belgische wijnbouwer", date(2020, 7, 11), location="Millegem")
    add_activity("Bierdegustatie", date(2020, 10, 16), time="20:30", location="Miloheem")
    add_activity("Sint komt naar onze gezinnen", date(2020, 11, 28), date_end=date(2020, 11, 29), location="Bij de gezinnen", members_only=True)
    add_activity("KWB Kerst Radio", date(2020, 12, 26), time="10:00", location="ONLINE", notes="10u tot 18u")

    # === 2019 (archived) ===
    add_activity("Binnenspeeltuin", date(2019, 1, 26), time="13:00", location="Lindeplein kerk (vertrek)")
    add_activity("Avondwandeling", date(2019, 2, 1), time="19:30", location="Miloheem (vertrek)")
    add_activity("Millegems Bal", date(2019, 2, 16), time="20:00", location="Miloheem")
    add_activity("Millegem Kwist! Quizt Millegem?", date(2019, 3, 9), time="19:30", location="Miloheem")
    add_activity("Gezinsuitstap be-MINE Beringen", date(2019, 3, 30), time="13:00", location="Kerk (vertrek)")
    add_activity("Ledenfeest", date(2019, 4, 20), time="10:00", location="Chirolokaal Millegem", members_only=True)
    add_activity("Fiets- en Gezinsweekend", date(2019, 5, 10), date_end=date(2019, 5, 12), location="Millegem", members_only=True)
    add_activity("Kinderwandeling Grote Netewoud", date(2019, 5, 30), time="14:00", location="Meerhout")
    add_activity("Kanovaren op de Dommel in Valkenswaard", date(2019, 6, 15), time="09:00", location="Lindeplein")
    add_activity("Kids Zwerfvuilactie", date(2019, 6, 23), time="10:00", location="Zwanenhof")
    add_activity("Bezoek wijndomein ALDENEYCK", date(2019, 7, 13), time="09:00", location="Kerk (vertrek, eigen vervoer)")
    add_activity("Familiefietstocht en picknick Ark van Noé Kasterlee", date(2019, 8, 11), time="13:00", location="Lindeplein (aan Kerk)")
    add_activity("Brood en Spelen", date(2019, 8, 31), time="14:00", location="Chiroplein",
        notes="kubb-tornooi")
    add_activity("Wandelweekend 2019", date(2019, 9, 13), date_end=date(2019, 9, 15), location="Wandelweekend", members_only=True)
    add_activity("Casino avond", date(2019, 9, 28), time="20:00", location="Chirolokaal Millegem")
    add_activity("Schaatsen", date(2019, 11, 10), time="09:00", location="Lindeplein (vertrek naar Herentals)")
    add_activity("Zettersprijskamp", date(2019, 11, 22), time="20:00", location="Miloheem")
    add_activity("Sint komt naar onze gezinnen", date(2019, 11, 29), date_end=date(2019, 11, 30), location="Bij de gezinnen", members_only=True)
    add_activity("Kerstherberg", date(2019, 12, 25), date_end=date(2019, 12, 30), time="13:00", location="Kerk & Lindeplein")

    # === 2018 (archived) ===
    add_activity("Brood en spelen", date(2018, 9, 1), location="Chiroplein")

    db.commit()
    print("Activities seeded successfully.")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
    raise
finally:
    db.close()
