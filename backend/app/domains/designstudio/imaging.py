"""AI illustrations for a design: Black Forest Labs FLUX.2 [pro] (CR-10 §3.12).

Europe First: BFL is a German company and the EU endpoint
(``api.eu.bfl.ai``) keeps the request in the EU. The alternative — Mistral,
already in the stack — has no image model; self-hosting a diffusion model is
out of reach for an association. The choice and the trade-off are recorded in
CR-10 B1.3.

What this module guards, in order:

1. **Kill switch and budget before any call.** ``DESIGNSTUDIO_AI_IMAGES_ENABLED``
   must be on; the month's spend plus the open *reservations* must stay under
   the unit's monthly budget and under the platform cap. A click reserves its
   expected cost first (four variants, ``EXPECTED_CREDITS`` each) so two clicks
   in the same second cannot both pass the check.
2. **One click, four variants, one request key.** Each variant is a row in
   ``image_generations`` with a state machine — requested → fetched → picked or
   discarded, or refused (moderation) / failed. The prompt, the provider, the
   cost and the duration go to the AI log (#978) with ``surface="designstudio"``,
   which is where the monthly spend is read back from.
3. **The job does the waiting.** A generation takes 10–40 s and the result URL
   expires after ten minutes; the request runs as a kernel job that polls,
   fetches the bytes into media (kind ``design_image``) and releases the
   reservation by writing the real cost. The screen polls the design.

Prompts are English (the model reads English best; "football" and "torch"
mistranslate — iteration 08) and always end with the house style suffix, so
the drawing sits on a white ground in the Raak line-art look.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.kernel.clock import belgian_today

logger = logging.getLogger(__name__)

PROVIDER = "bfl"
ENDPOINT = "https://api.eu.bfl.ai/v1/flux-2-pro"
MODEL = "flux-2-pro"
SURFACE = "designstudio"
CAPABILITY = "image"

#: FLUX.2 [pro] prices per image: 4.5 credits up to 2 MP, 6 with a reference
#: image (measured in iteration 08; a credit is USD 0.01 at list price).
EXPECTED_CREDITS = Decimal("4.5")
CREDITS_WITH_REFERENCE = Decimal("6")
CREDIT_USD = Decimal("0.01")
VARIANTS_PER_CLICK = 4
POLL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 180

#: The house style, appended to every prompt. The unit describes the scene;
#: the look is not theirs to change.
STYLE_SUFFIX = (" — simple black line drawing in a friendly hand-drawn style, thick even lines, "
                "no shading, no text, no background scenery, pure white background, "
                "single subject centred, poster illustration")

ENV_ENABLED = "DESIGNSTUDIO_AI_IMAGES_ENABLED"
ENV_BUDGET = "DESIGNSTUDIO_AI_MONTHLY_BUDGET_EUR"
ENV_PLATFORM_BUDGET = "DESIGNSTUDIO_AI_PLATFORM_BUDGET_EUR"
ENV_KEY = "BFL_API_KEY"
ENV_RATE = "BFL_USD_EUR_RATE"


class ImagingError(RuntimeError):
    """A refusal the screen can show as it is."""


@dataclass(frozen=True)
class Budget:
    enabled: bool
    monthly_eur: Decimal
    platform_eur: Decimal
    spent_eur: Decimal
    reserved_eur: Decimal

    @property
    def left_eur(self) -> Decimal:
        return self.monthly_eur - self.spent_eur - self.reserved_eur

    def line(self) -> str:
        if not self.enabled:
            return "AI-beelden staan uit op deze server."
        return (f"Deze maand: € {self.spent_eur:.2f} gebruikt van € {self.monthly_eur:.2f}"
                + (f" (€ {self.reserved_eur:.2f} gereserveerd)" if self.reserved_eur else ""))


def _env_decimal(name: str, fallback: str) -> Decimal:
    try:
        return Decimal(os.environ.get(name) or fallback)
    except ArithmeticError:
        return Decimal(fallback)


def enabled() -> bool:
    return (os.environ.get(ENV_ENABLED) or "").strip().lower() in ("1", "true", "yes", "on") \
        and bool(os.environ.get(ENV_KEY))


def usd_to_eur(usd: Decimal) -> Decimal:
    return (usd * _env_decimal(ENV_RATE, "0.92")).quantize(Decimal("0.0001"))


def expected_cost_eur(*, with_reference: bool) -> Decimal:
    credits = CREDITS_WITH_REFERENCE if with_reference else EXPECTED_CREDITS
    return usd_to_eur(credits * CREDIT_USD)


def budget_for(db, *, tenant_id: int, spent_eur: Decimal, reserved_cents: int) -> Budget:
    return Budget(
        enabled=enabled(),
        monthly_eur=_env_decimal(ENV_BUDGET, "50"),
        platform_eur=_env_decimal(ENV_PLATFORM_BUDGET, "150"),
        spent_eur=spent_eur,
        reserved_eur=Decimal(reserved_cents) / 100,
    )


def check_budget(budget: Budget, *, platform_spent_eur: Decimal, cost_eur: Decimal) -> None:
    """Refuse before any call. Named reasons, because "het lukte niet" sends
    the unit to the board and the board to the logs."""
    if not budget.enabled:
        raise ImagingError("AI-beelden staan uit op deze server (kill switch).")
    if budget.left_eur - cost_eur < 0:
        raise ImagingError(
            f"Het maandbudget voor AI-beelden is op: € {budget.spent_eur:.2f} gebruikt en "
            f"€ {budget.reserved_eur:.2f} gereserveerd van € {budget.monthly_eur:.2f}.")
    if platform_spent_eur + budget.reserved_eur + cost_eur > budget.platform_eur:
        raise ImagingError("Het platformplafond voor AI-beelden is bereikt; vraag het aan de beheerder.")


def build_prompt(scene: str) -> str:
    scene = " ".join((scene or "").split())
    if len(scene) < 8:
        raise ImagingError("Beschrijf wat op de tekening moet staan (minstens een paar woorden).")
    return scene[:600] + STYLE_SUFFIX


def new_request_key() -> str:
    return secrets.token_hex(12)


# ── The HTTP client ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Generated:
    image: bytes
    mime: str
    seed: int | None
    provider_request_id: str
    duration_ms: int
    credits: Decimal


class BflClient:
    """Thin, synchronous, retry-free: the job around it decides what to do
    with a failure. Separate class so a test can replace it."""

    def __init__(self, api_key: str | None = None, *, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get(ENV_KEY, "")
        self.timeout = timeout

    def generate(self, prompt: str, *, width: int, height: int, seed: int | None,
                 reference_png: bytes | None = None) -> Generated:
        if not self.api_key:
            raise ImagingError("Geen BFL-sleutel op deze server.")
        body: dict = {"prompt": prompt, "width": width, "height": height,
                      "output_format": "png", "safety_tolerance": 2}
        if seed is not None:
            body["seed"] = seed
        if reference_png:
            body["input_image"] = base64.b64encode(reference_png).decode()
        headers = {"x-key": self.api_key, "accept": "application/json"}
        t0 = time.monotonic()
        with httpx.Client(timeout=self.timeout) as client:
            first = client.post(ENDPOINT, json=body, headers=headers)
            if first.status_code >= 400:
                raise ImagingError(f"BFL weigerde de aanvraag ({first.status_code}).")
            task = first.json()
            request_id = str(task.get("id", ""))
            polling_url = task.get("polling_url") or f"https://api.eu.bfl.ai/v1/get_result?id={request_id}"
            deadline = t0 + POLL_TIMEOUT_SECONDS
            while True:
                if time.monotonic() > deadline:
                    raise ImagingError("BFL antwoordde niet binnen de tijd.")
                time.sleep(POLL_SECONDS)
                poll = client.get(polling_url, headers=headers, params={"id": request_id})
                data = poll.json() if poll.status_code < 400 else {}
                status = data.get("status", "")
                if status == "Ready":
                    result = data.get("result") or {}
                    url = result.get("sample")
                    if not url:
                        raise ImagingError("BFL gaf geen beeld terug.")
                    image = client.get(url)
                    image.raise_for_status()
                    return Generated(
                        image=image.content, mime="image/png",
                        seed=result.get("seed") if isinstance(result.get("seed"), int) else seed,
                        provider_request_id=request_id,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        credits=CREDITS_WITH_REFERENCE if reference_png else EXPECTED_CREDITS,
                    )
                if status in ("Content Moderated", "Request Moderated"):
                    raise ModerationRefused("De aanvraag werd door de moderatie van BFL geweigerd.")
                if status in ("Error", "Failed", "Task not found"):
                    raise ImagingError(f"BFL meldde een fout ({status}).")


class ModerationRefused(ImagingError):
    """Moderation is a named outcome, not a failure: the row becomes `refused`
    and nothing is retried."""


def month_bounds_now() -> tuple[datetime, datetime]:
    from app.domains.chatbot.api import month_period

    return month_period(belgian_today())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
