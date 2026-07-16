"""Fuzzy employee-name matching for OCR-confirmation / manual lookup.

01-REQUIREMENTS.md section 5: normalize (full/half-width, strip whitespace)
then score with rapidfuzz; score >= 90 is "exact", 70-89 is "candidate",
< 70 is left for the counter clerk to type manually. This module implements
normalization + scoring; the >=90 auto-fill / 70-89 candidate-list split is
a UI concern that consumes the `tier` field this returns.

Traditional/simplified Chinese conversion ("繁簡") is *not* implemented --
that needs an OpenCC-style conversion table, which is a materially bigger
dependency than rapidfuzz alone provides. This is a known, documented gap
(see the M1 completion report), not an oversight.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeStatus

EXACT_THRESHOLD = 90
CANDIDATE_THRESHOLD = 70

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Full/half-width normalization (NFKC folds U+3000 ideographic space and
    full-width alnum/punctuation to their half-width forms) followed by
    stripping all whitespace, per 01-REQUIREMENTS.md section 5."""
    if not raw:
        return ""
    folded = unicodedata.normalize("NFKC", raw)
    return _WHITESPACE_RE.sub("", folded).strip()


def _tier(score: float) -> str:
    if score >= EXACT_THRESHOLD:
        return "exact"
    if score >= CANDIDATE_THRESHOLD:
        return "candidate"
    return "low"


async def match_employees(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 20,
    min_score: float = 0.0,
    include_inactive: bool = False,
) -> list[dict]:
    normalized_query = normalize_name(query)
    if not normalized_query:
        return []

    stmt = select(Employee, Department.name).outerjoin(
        Department, Employee.department_id == Department.id
    )
    if not include_inactive:
        stmt = stmt.where(Employee.status == EmployeeStatus.active)

    result = await session.execute(stmt)
    rows = result.all()

    scored: list[dict] = []
    for employee, department_name in rows:
        candidates = [employee.name, *(employee.aliases or [])]
        best_score = 0.0
        for candidate in candidates:
            normalized_candidate = normalize_name(candidate)
            if not normalized_candidate:
                continue
            score = fuzz.ratio(normalized_query, normalized_candidate)
            if score > best_score:
                best_score = score
        if best_score < min_score:
            continue
        scored.append(
            {
                "employee_id": employee.id,
                "name": employee.name,
                # M1-R1 suggestion: rename to match the documented/frontend
                # contract (frontend/src/types/api.ts EmployeeMatchCandidate
                # and EmployeeMatchChips.vue both read `department_name`;
                # the old `department` key was never actually consumed).
                "department_name": department_name,
                "department_id": employee.department_id,
                "score": round(best_score, 2),
                "tier": _tier(best_score),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


async def match_departments(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 10,
    min_score: float = 0.0,
    include_inactive: bool = False,
) -> list[dict]:
    """Fuzzy-match a recipient string against `departments` (name + code), for
    the "部門件" routing path (A): mail addressed to a company/department, not a
    specific person, is routed to that department's contact person
    (`Department.manager_employee_id`). Same normalization/tier scheme as
    `match_employees`. A department name that appears *inside* a longer
    recipient string (e.g. "◯◯公司 採購部 收") is boosted, since the
    recipient block often embeds the unit name in surrounding text.
    """
    normalized_query = normalize_name(query)
    if not normalized_query:
        return []

    stmt = select(Department)
    if not include_inactive:
        stmt = stmt.where(Department.is_active.is_(True))
    departments = list((await session.execute(stmt)).scalars().all())

    scored: list[dict] = []
    for dept in departments:
        best_score = 0.0
        for candidate in (dept.name, dept.code):
            normalized_candidate = normalize_name(candidate)
            if not normalized_candidate:
                continue
            score = float(fuzz.ratio(normalized_query, normalized_candidate))
            # Containment either way (dept name inside the recipient string, or
            # a short recipient string inside a longer dept name) is a strong
            # signal even when the overall ratio is diluted by extra words.
            # Only boost on a reasonably long candidate: a 1-2 char dept code
            # would substring-match almost any recipient text and mint a
            # spurious high-score "candidate" (review SHOULD-FIX #2).
            if len(normalized_candidate) >= 3 and (
                normalized_candidate in normalized_query
                or normalized_query in normalized_candidate
            ):
                score = max(score, 88.0)
            if score > best_score:
                best_score = score
        if best_score < min_score:
            continue
        scored.append(
            {
                "department_id": dept.id,
                "name": dept.name,
                "code": dept.code,
                "manager_employee_id": dept.manager_employee_id,
                "score": round(best_score, 2),
                "tier": _tier(best_score),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]
