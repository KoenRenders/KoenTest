from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from app.domains.forms.api import AnswerIn

# ── Products ──────────────────────────────────────────────────────────────────


class ProductResponse(BaseModel):
    id: int
    component_id: int
    name: str
    price: Decimal
    member_price: Optional[Decimal] = None
    is_free: bool
    pay_on_site: bool = False
    is_active: bool = True
    max_participants: Optional[int] = None
    sort_order: int

    model_config = {"from_attributes": True}


# ── Components (Onderdelen) ───────────────────────────────────────────────────


class ComponentResponse(BaseModel):
    id: int
    name: str
    team_name_required: bool
    sort_order: int
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    info_asset_url: Optional[str] = None
    info_asset_is_pdf: bool = False
    max_participants: Optional[int] = None
    is_full: bool = False
    # #1053: per onderdeel, zodat de kaart kan tonen wat er werkelijk geldt.
    registration_closes_on: Optional[Date] = None
    # #1053: de toestand van DIT onderdeel, beslist door `registration_state`.
    # De kaart rekent niet zelf uit of een deadline voorbij is — dat was precies
    # de duplicatie die #974 wegnam, en ze mag niet per onderdeel terugkomen.
    registration_state: Optional[str] = None

    # CR-12 phase 4: what the card needs, derived here so the template compares
    # no codes (§B4.7). `registration_state` stays the code, for the API.
    @property
    def registration_open(self) -> bool:
        from app.domains.activities.api import RegistrationState

        return self.registration_state == RegistrationState.OPEN.value

    @property
    def registration_closed(self) -> bool:
        from app.domains.activities.api import RegistrationState

        return self.registration_state == RegistrationState.CLOSED.value

    # #1051: binnen de laatste week kleurt de regel oranje (attentietint, §1.1).
    deadline_near: bool = False
    products: List[ProductResponse] = []

    model_config = {"from_attributes": True}


# ── Activity dates ────────────────────────────────────────────────────────────


class ActivityDateResponse(BaseModel):
    id: int
    activity_id: int
    start_date: Date
    end_date: Optional[Date] = None
    start_time: Optional[Time] = None
    end_time: Optional[Time] = None

    model_config = {"from_attributes": True}


# ── Activities ────────────────────────────────────────────────────────────────


class ActivityResponse(BaseModel):
    id: int
    name: str
    # #884: de vriendelijke URL hoort bij de activiteit, dus ook in haar antwoord — het
    # beheerscherm leest hem hieruit, en een externe aanroeper moet het adres kunnen
    # kennen dat hij deelt.
    slug: Optional[str] = None
    sort_date: Optional[Date] = None
    dates: List[ActivityDateResponse] = []
    location: Optional[str] = None
    description: Optional[str] = None
    poster_url: Optional[str] = None
    poster_asset_url: Optional[str] = None
    # Feedbackronde 2 golf 8 (#913): de leeslink toont de documenttitel.
    poster_asset_title: Optional[str] = None
    poster_asset_is_pdf: bool = False
    members_only: bool = False
    is_cancelled: bool = False
    created_at: datetime
    status: Optional[str] = None
    registration_count: Optional[int] = None
    # #1053: de ene uiterste inschrijfdatum die voor élk open onderdeel geldt —
    # None zodra ze verschillen, want dan hoort elke datum bij haar onderdeel.
    # Afgeleid, zoals `is_full` en `registration_state`, en pas ingevuld als de
    # bezetting bekend is.
    shared_deadline: Optional[Date] = None
    # #1051: idem, voor de ene regel bovenaan de kaart.
    shared_deadline_near: bool = False
    # #974: `registration_state` as the service decides it — open, past, closed or
    # cancelled. The card reads THIS and does not work it out again; two places that
    # each decide "open" is how the deadline would have been forgotten in one.
    registration_state: Optional[str] = None
    sub_registrations: List[ComponentResponse] = []

    # CR-12 phase 4: see `ComponentResponse` — the same two, for the activity.
    @property
    def registration_open(self) -> bool:
        from app.domains.activities.api import RegistrationState

        return self.registration_state == RegistrationState.OPEN.value

    @property
    def registration_closed(self) -> bool:
        from app.domains.activities.api import RegistrationState

        return self.registration_state == RegistrationState.CLOSED.value

    model_config = {"from_attributes": True}


# ── Registrations ─────────────────────────────────────────────────────────────


class RegistrationItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class RegistrationRemarksUpdate(BaseModel):
    """Admin bewerkt enkel de opmerking van de inschrijver (#283).

    Sinds #624 aanvaardt de route `RegistrationContactUpdate`, dat dit veld omvat;
    dit schema blijft staan omdat een externe API-client het nog kan versturen — een
    JSON-body met enkel `remarks` valideert nog steeds tegen beide vormen.
    """

    remarks: Optional[str] = None


class RegistrationContactUpdate(BaseModel):
    """Admin corrigeert de contactgegevens van een inschrijving (#624).

    Een tikfout in het e-mailadres betekent dat de bevestiging en elke verdere
    communicatie niet aankomen; dat was alleen recht te zetten door de inschrijving
    te verwijderen en opnieuw in te voeren — met een nieuwe betaling en OGM tot
    gevolg.

    Vorm hoort in het schema (§ validatielagen): `EmailStr` weigert een ongeldig
    adres met een leesbare 422 i.p.v. het stil te bewaren. Leeg of enkel witruimte
    wordt server-side NULL, zoals de opmerking dat al doet — and since CR-13 phase 1
    the registration refuses a NULL e-mail address itself (Koen, 29 September 2026).

    Los van de gekoppelde `Person`: deze velden zijn een momentopname van wat de
    inschrijver invulde. Het ledenbestand corrigeer je op /admin/leden.
    """

    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    team_name: Optional[str] = None
    remarks: Optional[str] = None


class RegistrationCreate(BaseModel):
    contact_name: str
    contact_email: EmailStr
    phone: Optional[str] = None
    team_name: Optional[str] = None
    payment_method: Optional[str] = None
    component_id: Optional[int] = None
    items: List[RegistrationItemCreate] = []
    remarks: Optional[str] = None
    #: CR-14 phase 2 (§B1.1 F6, §B4.8): the answers to the component's questions.
    #: A list — even an empty one — means "now": validated by the form's rules,
    #: refused as a whole. None means "later": the registration gets an answer link.
    answers: Optional[List[AnswerIn]] = None


class RegistrationItemResponse(BaseModel):
    id: Optional[int] = None  # registratie-item-id, nodig om regels te bewerken (#84)
    product_id: int
    quantity: int
    product_name: Optional[str] = None
    component_name: Optional[str] = None

    model_config = {"from_attributes": True}


class RegistrationResponse(BaseModel):
    id: int
    activity_id: int
    component_id: Optional[int] = None
    person_id: Optional[int] = None
    registered_at: datetime
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    team_name: Optional[str] = None
    payment_method: Optional[str] = None
    checkout_url: Optional[str] = None
    remarks: Optional[str] = None
    items: List[RegistrationItemResponse] = []

    model_config = {"from_attributes": True}


# Keep for backwards compat in router imports
SubRegistrationResponse = ComponentResponse
