import pytest

from app.models.department import Department
from app.models.employee import Employee
from app.services.matching import match_departments


@pytest.mark.asyncio
async def test_match_departments_by_name_and_contains(db_session):
    mgr = Employee(name="王主管")
    db_session.add(mgr)
    await db_session.flush()
    dept = Department(name="採購部", code="PUR", manager_employee_id=mgr.id, is_active=True)
    db_session.add(dept)
    await db_session.commit()

    exact = await match_departments(db_session, "採購部")
    assert exact and exact[0]["department_id"] == dept.id
    assert exact[0]["manager_employee_id"] == mgr.id
    assert exact[0]["tier"] == "exact"

    # dept name embedded in a longer recipient string -> still matched
    embedded = await match_departments(db_session, "噢買尬有限公司 採購部 收")
    assert embedded and embedded[0]["department_id"] == dept.id


@pytest.mark.asyncio
async def test_match_departments_skips_inactive_and_blank(db_session):
    dept = Department(name="停用部", code="OLD", is_active=False)
    db_session.add(dept)
    await db_session.commit()
    assert await match_departments(db_session, "停用部") == []
    assert await match_departments(db_session, "   ") == []
