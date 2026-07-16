from app.models.department import Department
from app.models.enums import UserRole
from tests._helpers import login_as


async def _make_department(db_session, code="eng") -> Department:
    dept = Department(name="Engineering", code=code)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


def _csv_file(content: str, filename: str = "employees.csv"):
    return {"file": (filename, content.encode("utf-8"), "text/csv")}


async def test_import_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    csv_content = "name,aliases,department_code,ext,email,phone\n王小明,David;David Wang,,101,,\n"
    resp = await client.post("/api/v1/employees/import", files=_csv_file(csv_content))
    assert resp.status_code == 403


async def test_import_success_rows(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    dept = await _make_department(db_session, code="eng")

    csv_content = (
        "name,aliases,department_code,ext,email,phone\n"
        f"王小明,David;David Wang,{dept.code},101,david@example.com,0912345678\n"
        "陳小華,,,,,\n"
    )
    resp = await client.post("/api/v1/employees/import", files=_csv_file(csv_content))
    assert resp.status_code == 200
    body = resp.json()["data"]
    # M1-R1 blocking #7: response shape unified with the frontend contract
    # (frontend/src/types/api.ts EmployeeImportResult) --
    # { total, succeeded, failed, errors: [{ row, message }] } -- instead of
    # the old success_count/failure_count/created/failures[].error shape.
    assert body["total"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert body["errors"] == []

    list_resp = await client.get("/api/v1/employees")
    assert list_resp.json()["meta"]["total"] == 2

    wang = next(e for e in list_resp.json()["data"] if e["name"] == "王小明")
    assert wang["aliases"] == ["David", "David Wang"]
    assert wang["department_id"] == dept.id
    assert wang["email"] == "david@example.com"


async def test_import_bad_rows_reported_without_aborting_good_rows(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    csv_content = (
        "name,aliases,department_code,ext,email,phone\n"
        ",no-name-here,,,,\n"  # missing required name
        "OK Employee,,,,,\n"  # valid
        "Bad Dept Employee,,does-not-exist,,,\n"  # unknown department_code
    )
    resp = await client.post("/api/v1/employees/import", files=_csv_file(csv_content))
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 3
    assert body["succeeded"] == 1
    assert body["failed"] == 2

    failure_rows = {e["row"] for e in body["errors"]}
    assert failure_rows == {1, 3}
    assert any("name is required" in e["message"] for e in body["errors"])
    assert any("department_code" in e["message"] for e in body["errors"])


async def test_import_no_header_positional_columns(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    csv_content = "李四,;,,,,\n"
    resp = await client.post("/api/v1/employees/import", files=_csv_file(csv_content))
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["succeeded"] == 1


async def test_import_neutralizes_csv_formula_injection(client, db_session):
    """M1-R1 blocking #2: a name/alias/email/phone cell starting with
    =/+/-/@ must be neutralized (leading `'`) before being stored, so it
    can't later detonate as a formula if pasted into (or exported to) a
    spreadsheet."""
    await login_as(client, db_session, role=UserRole.admin)

    csv_content = (
        'name,aliases,department_code,ext,email,phone\n=SUM(A1:A9),"@evil;+123",,,=cmd|test,-9\n'
    )
    resp = await client.post("/api/v1/employees/import", files=_csv_file(csv_content))
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["succeeded"] == 1

    list_resp = await client.get("/api/v1/employees")
    emp = list_resp.json()["data"][0]
    assert emp["name"] == "'=SUM(A1:A9)"
    assert emp["aliases"] == ["'@evil", "'+123"]
    assert emp["email"] == "'=cmd|test"
    assert emp["phone"] == "'-9"
