"""The image-generation job (CR-10 §3.12): one variant per job.

Registered on import from ``app.main`` like the newsletter's send job. The
job owns the slow part — the call to BFL, the polling, the fetch — and writes
three things when it is done: the bytes into media (kind ``design_image``),
the row's state, and the AI-log line with the real cost, which releases the
reservation. ``max_attempts`` is one: a failed generation is a named failure
on the screen, not a retry that spends again.
"""
from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from sqlalchemy.orm import Session
from starlette.datastructures import Headers, UploadFile

from app.domains.designstudio import imaging
from app.domains.designstudio.models import GenerationStatus, ImageGeneration
from app.kernel.jobs import job

logger = logging.getLogger(__name__)

#: Replaced by a test; production uses the real client.
client_factory = imaging.BflClient

#: A FLUX drawing's "white" ground comes back around RGB 253 (iteration 08);
#: on a white poster that shows as a grey slab. Everything above this level
#: becomes pure white; the black lines are untouched.
WHITE_THRESHOLD = 240


def whiten(png: bytes) -> bytes:
    """Push the near-white ground of a line drawing to pure white."""
    from PIL import Image

    with Image.open(BytesIO(png)) as img:
        rgb = img.convert("RGB")
        lut = [255 if v >= WHITE_THRESHOLD else v for v in range(256)] * 3
        out = rgb.point(lut)
        buf = BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


@job("designstudio.generate")
def generate_image(db: Session, payload: dict) -> None:
    from app.domains.chatbot.api import AiStatus, sink_for
    from app.domains.media.api import MediaAsset, upload_media

    row = db.query(ImageGeneration).filter(ImageGeneration.id == payload["generation_id"]).first()
    if row is None:
        return
    tenant_id = payload.get("tenant_id")
    prompt = payload["prompt"]
    log = sink_for(row.requested_by)
    reference = None
    if payload.get("reference_asset_id"):
        asset = db.query(MediaAsset).filter(MediaAsset.id == payload["reference_asset_id"]).first()
        reference = bytes(asset.data) if asset is not None else None

    try:
        result = client_factory().generate(prompt, width=row.width, height=row.height, seed=row.seed,
                                           reference_png=reference)
    except imaging.ModerationRefused as exc:
        row.status, row.failure_reason = GenerationStatus.REFUSED, str(exc)
        log(surface=imaging.SURFACE, capability=imaging.CAPABILITY, model=imaging.MODEL, payload=prompt,
            provider=imaging.PROVIDER, endpoint=imaging.ENDPOINT, status=AiStatus.BLOCKED,
            blocked_reason="moderation", tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001 - every failure becomes a named row state
        logger.warning("designstudio: generation %s failed: %s", row.id, exc)
        row.status, row.failure_reason = GenerationStatus.FAILED, str(exc)[:500]
        log(surface=imaging.SURFACE, capability=imaging.CAPABILITY, model=imaging.MODEL, payload=prompt,
            provider=imaging.PROVIDER, endpoint=imaging.ENDPOINT, status=AiStatus.ERROR,
            blocked_reason=str(exc)[:200], tenant_id=tenant_id)
    else:
        upload = UploadFile(file=BytesIO(whiten(result.image)), filename=f"ai-{row.id}.png",
                            headers=Headers({"content-type": "image/png"}))
        stored = asyncio.run(upload_media(db, files=[upload], kind="design_image",
                                          activity_id=row.design.activity_id))
        row.media_asset_id = stored[0]["id"]
        row.seed = result.seed
        row.status = GenerationStatus.FETCHED
        usd = result.credits * imaging.CREDIT_USD
        log(surface=imaging.SURFACE, capability=imaging.CAPABILITY, model=imaging.MODEL, payload=prompt,
            provider=imaging.PROVIDER, endpoint=imaging.ENDPOINT, provider_request_id=result.provider_request_id,
            status=AiStatus.OK, duration_ms=result.duration_ms, cost_credits=result.credits, cost_amount=usd,
            cost_currency="USD", output_megapixels=round(row.width * row.height / 1_000_000, 2),
            tenant_id=tenant_id)
    row.reserved_cents = 0
    row.finished_at = imaging.utc_now()
    db.flush()
