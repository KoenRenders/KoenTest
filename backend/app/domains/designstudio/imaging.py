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
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.config import settings
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

#: The house style, appended to every prompt. The unit describes the scene
#: and picks one of two looks; the rest is not theirs to change. Round 3
#: (Koen, 19 September 2026): "voeg kleuren toe" was ignored because the one
#: suffix said "black, no shading" — so colour is a style, not a wish.
# Koen, 20 September 2026: "kleuterachtig" — the first wording asked for a
# "friendly hand-drawn style" and got nursery drawings. These ask for a
# modern editorial line illustration with realistic proportions instead.
_BASE = ("realistic proportions, adults look like adults, no cartoon exaggeration, no text, "
         "no background scenery, pure white background, single subject centred, poster illustration")
STYLES = {
    "lijn": (" — clean black ink line illustration in a modern editorial style, confident even lines, "
             "no shading, no colour, " + _BASE),
    "lijnkleur": (" — clean black ink line illustration in a modern editorial style, confident even lines, "
                  "with a few flat colour accents in muted tones, no shading, " + _BASE),
    "kleur": (" — flat vector illustration with bold black outlines and a limited palette of flat colours, "
              "no gradients, no shading, " + _BASE),
}
STYLE_LABELS = {"lijn": "Lijntekening (zwart-wit)", "lijnkleur": "Lijntekening met kleuraccenten",
                "kleur": "Kleurtekening (vlakke kleuren)"}
STYLE_SUFFIX = STYLES["lijn"]

# A scene typed in Dutch is translated before it goes to BFL (the model reads
# English best). The check is a stopword heuristic; a wrong guess only costs
# one cheap Mistral call, and the translation is logged (#978) so it can be
# read back next to the drawing it produced.
_DUTCH = {"de", "het", "een", "en", "met", "van", "voor", "op", "in", "die", "dat", "naar", "twee", "drie",
          "kinderen", "ouders", "mensen", "fiets", "wandelen", "aan", "bij", "zonder", "onder", "over"}


def looks_dutch(text: str) -> bool:
    words = [w.strip(".,!?;:()").lower() for w in (text or "").split()]
    return sum(1 for w in words if w in _DUTCH) >= max(1, len(words) // 6)


def translate_scene(scene: str, *, actor: str = "") -> tuple[str, bool]:
    """The scene in English, and whether it was translated. Without a real
    LLM (mock provider) or without Dutch in it, the text goes through as is."""
    from dataclasses import replace

    from app.domains.chatbot.api import GuardedProvider, admin_rules, get_provider, sink_for

    text = " ".join((scene or "").split())
    if not text or not looks_dutch(text):
        return text, False
    inner = get_provider()
    if inner.name == "mock":
        return text, False
    # Through the seam like every other LLM call (test_ai_log_coverage_gate):
    # the guard logs the call — provider, model, cost, duration — under this
    # component's surface and the capability "translate".
    rules = replace(admin_rules(lambda: set(), capability="translate", scan_prompt_names=False), surface=SURFACE)
    provider = GuardedProvider(inner, rules, sink_for(actor))
    answer = provider.complete([
        {"role": "system", "content": "Translate the user's text from Dutch to English for an image-generation "
                                      "prompt. Reply with the translation only, no quotes, no commentary."},
        {"role": "user", "content": text[:600]},
    ])
    english = " ".join((answer.content or "").split()).strip('"')
    return english or text, bool(english)

# The five settings live on `Settings` (app/config.py) like every other
# per-host setting, so the compose files pass them and the #821/#917 gate sees
# them: `BFL_API_KEY`, `DESIGNSTUDIO_AI_IMAGES_ENABLED`,
# `DESIGNSTUDIO_AI_MONTHLY_BUDGET_EUR`, `DESIGNSTUDIO_AI_PLATFORM_BUDGET_EUR`,
# `BFL_USD_EUR_RATE`. Reading `os.environ` here would have bypassed all three.


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


def enabled() -> bool:
    """The kill switch, and a key to go with it: without a key there is nothing
    to switch on."""
    return bool(settings.designstudio_ai_images_enabled) and bool(settings.bfl_api_key)


def usd_to_eur(usd: Decimal) -> Decimal:
    return (usd * Decimal(str(settings.bfl_usd_eur_rate))).quantize(Decimal("0.0001"))


def expected_cost_eur(*, with_reference: bool) -> Decimal:
    credits = CREDITS_WITH_REFERENCE if with_reference else EXPECTED_CREDITS
    return usd_to_eur(credits * CREDIT_USD)


def budget_for(db, *, tenant_id: int, spent_eur: Decimal, reserved_cents: int) -> Budget:
    return Budget(
        enabled=enabled(),
        monthly_eur=Decimal(str(settings.designstudio_ai_monthly_budget_eur)),
        platform_eur=Decimal(str(settings.designstudio_ai_platform_budget_eur)),
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


def build_prompt(scene: str, style: str = "lijn", change: str = "") -> str:
    """The scene, the change asked on top of a reference ("wat wil je
    anders?") and the style suffix."""
    scene = " ".join((scene or "").split())
    change = " ".join((change or "").split())
    if not scene and change:
        # A redo on a variant made before the scene was kept (round 3): the
        # change is all we have, and with the reference image it is enough.
        scene, change = change, ""
    if len(scene) < 8:
        raise ImagingError("Beschrijf wat op de tekening moet staan (minstens een paar woorden).")
    if style not in STYLES:
        raise ImagingError("Onbekende stijl.")
    text = scene[:600]
    if change:
        text += ". Keep the same composition and characters as the reference image; change only this: " + change[:300]
    return text + STYLES[style]


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
        self.api_key = api_key or settings.bfl_api_key or ""
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
