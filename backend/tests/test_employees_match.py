from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import UserRole
from app.services.matching import normalize_name
from tests._helpers import login_as


async def _create_employee(db_session, *, name, aliases=None, department_id=None):
    emp = Employee(name=name, aliases=aliases or [], department_id=department_id)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


def test_normalize_name_strips_fullwidth_space_and_folds_width():
    assert normalize_name("王　小明") == "王小明"
    assert normalize_name(" 王 小明 ") == "王小明"
    assert normalize_name("ABC123") == normalize_name("ＡＢＣ１２３")


async def test_match_requires_admin_or_counter(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    resp = await client.get("/api/v1/employees/match", params={"q": "王小明"})
    assert resp.status_code == 403


async def test_match_exact_with_fullwidth_space_query(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _create_employee(db_session, name="王小明")

    resp = await client.get("/api/v1/employees/match", params={"q": "王　小明"})
    assert resp.status_code == 200
    matches = resp.json()["data"]
    assert matches, "expected at least one match"
    top = matches[0]
    assert top["name"] == "王小明"
    assert top["score"] >= 90
    assert top["tier"] == "exact"


async def test_match_result_uses_department_name_key(client, db_session):
    """M1-R1 suggestion: the response key is `department_name` (matching
    frontend/src/types/api.ts EmployeeMatchCandidate and
    EmployeeMatchChips.vue), not the old, never-consumed `department` key."""
    await login_as(client, db_session, role=UserRole.counter)
    dept = Department(name="Marketing", code="mkt")
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    await _create_employee(db_session, name="王小明", department_id=dept.id)

    resp = await client.get("/api/v1/employees/match", params={"q": "王小明"})
    assert resp.status_code == 200
    top = resp.json()["data"][0]
    assert top["department_name"] == "Marketing"
    assert "department" not in top


async def test_match_candidate_tier_for_partial_name(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _create_employee(db_session, name="王小明")

    # A close-but-not-exact query should still surface as a candidate.
    resp = await client.get("/api/v1/employees/match", params={"q": "王小"})
    assert resp.status_code == 200
    matches = resp.json()["data"]
    assert matches
    assert matches[0]["score"] < 100


async def test_match_uses_aliases(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _create_employee(db_session, name="陳大文", aliases=["David Chen"])

    resp = await client.get("/api/v1/employees/match", params={"q": "David Chen"})
    assert resp.status_code == 200
    matches = resp.json()["data"]
    assert matches
    assert matches[0]["name"] == "陳大文"
    assert matches[0]["score"] >= 90


async def test_match_sorted_by_score_descending(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _create_employee(db_session, name="林志明")
    await _create_employee(db_session, name="林小明")
    await _create_employee(db_session, name="陳大文")

    resp = await client.get("/api/v1/employees/match", params={"q": "林志明"})
    assert resp.status_code == 200
    matches = resp.json()["data"]
    scores = [m["score"] for m in matches]
    assert scores == sorted(scores, reverse=True)
    assert matches[0]["name"] == "林志明"
