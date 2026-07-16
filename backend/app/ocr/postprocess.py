"""Post-extraction cross-validation (04-AI-OCR.md section 3, "後處理"):

    "tracking_no 對 carriers 表的 regex 驗證(不符 -> 降信心並標警示);
    carrier_guess 與 regex 判斷交叉驗證"

`recipient_name` -> employee fuzzy-matching candidates is *not* done here --
it is computed on demand by `GET /ocr/jobs/{id}/draft` (app/api/v1/ocr_jobs.py)
instead of being baked into `result_json` at extraction time, so the
candidate list always reflects the current employee directory rather than a
stale snapshot from whenever the OCR job happened to run.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.carrier import Carrier
from app.ocr.schema import OCRResult


async def cross_validate_tracking(session: AsyncSession, result: OCRResult) -> dict:
    """Returns `{"carrier_id": str|None, "confidence": float, "warnings": [str]}`."""
    warnings: list[str] = []
    carrier_id: str | None = None
    carrier_row: Carrier | None = None
    confidence = result.confidence

    if result.carrier_guess:
        stmt = select(Carrier).where(Carrier.slug == result.carrier_guess)
        carrier_row = (await session.execute(stmt)).scalar_one_or_none()
        if carrier_row is None:
            warnings.append(f"unknown_carrier_guess:{result.carrier_guess}")
        else:
            carrier_id = carrier_row.id

    if result.tracking_no:
        if carrier_row is not None and carrier_row.tracking_pattern:
            try:
                pattern_ok = re.match(carrier_row.tracking_pattern, result.tracking_no) is not None
            except re.error:
                pattern_ok = True  # a malformed seed pattern must never crash a job
            if not pattern_ok:
                warnings.append("tracking_no_pattern_mismatch")
                confidence = min(confidence, 0.5)
        elif carrier_row is None:
            # No (usable) carrier_guess -- best-effort: if exactly one active
            # carrier's tracking_pattern matches, suggest it.
            stmt = select(Carrier).where(
                Carrier.is_active.is_(True), Carrier.tracking_pattern.is_not(None)
            )
            rows = (await session.execute(stmt)).scalars().all()
            matches = []
            for row in rows:
                try:
                    if re.match(row.tracking_pattern, result.tracking_no):
                        matches.append(row)
                except re.error:
                    continue
            if len(matches) == 1:
                carrier_id = matches[0].id

    return {"carrier_id": carrier_id, "confidence": confidence, "warnings": warnings}
