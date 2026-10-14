import json

import pytest
from fastapi.testclient import TestClient

from auth import auth_required
from main import app


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("FORMA_AUTH_REQUIRED", "true")
    monkeypatch.setenv("FORMA_AUTH_SECRET", "test-only-secret-with-at-least-32-bytes")
    monkeypatch.setenv("FORMA_TEACHER_USERNAME", "instructor")
    monkeypatch.setenv("FORMA_TEACHER_PASSWORD", "teacher-password")
    monkeypatch.setenv(
        "FORMA_STUDENT_CREDENTIALS_JSON",
        json.dumps({
            "demo-student-001": "student-password",
            "other-student-002": "another-password",
        }),
    )
    with TestClient(app) as client:
        yield client


def _login(client: TestClient, role: str, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"role": role, "username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_api_routes_require_bearer_auth(auth_client: TestClient):
    assert auth_client.get("/api/health").status_code == 200
    assert auth_client.get("/assignments").status_code == 401
    assert auth_client.get("/academic/student/grades").status_code == 401
    preflight = auth_client.options(
        "/assignments",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert auth_client.get(
        "/assignments", headers={"Authorization": "Bearer malformed.token"}
    ).status_code == 401


def test_student_cannot_access_teacher_routes_or_impersonate_teacher(auth_client: TestClient):
    token = _login(auth_client, "student", "demo-student-001", "student-password")
    headers = {"Authorization": f"Bearer {token}"}
    assert auth_client.get("/assignments", headers=headers).status_code == 403
    assert auth_client.get(
        "/academic/courses?role=teacher", headers=headers
    ).status_code == 403


def test_teacher_access_preserves_teacher_data_and_blocks_student_routes(auth_client: TestClient):
    token = _login(auth_client, "teacher", "instructor", "teacher-password")
    headers = {"Authorization": f"Bearer {token}"}
    assert auth_client.get("/assignments", headers=headers).status_code == 200
    assert auth_client.get(
        "/academic/student/grades", headers=headers
    ).status_code == 403
    response = auth_client.get(
        "/academic/offerings/phy101-fall-2024?role=teacher",
        headers=headers,
    )
    assert response.status_code == 200
    questions = [
        question
        for assignment in response.json()["assignments"]
        for question in assignment["questions"]
    ]
    assert questions and any("reference_solution" in question for question in questions)


def test_student_records_are_isolated_and_reference_solutions_redacted(auth_client: TestClient):
    own_token = _login(auth_client, "student", "demo-student-001", "student-password")
    other_token = _login(auth_client, "student", "other-student-002", "another-password")

    own = auth_client.get(
        "/academic/student/assignments",
        headers={"Authorization": f"Bearer {own_token}"},
    )
    other = auth_client.get(
        "/academic/student/assignments",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert own.status_code == 200
    assert other.status_code == 200
    own_items = own.json()["items"]
    assert own_items
    assert other.json()["items"] == []
    assert all(
        "reference_solution" not in question
        for assignment in own_items
        for question in assignment["questions"]
    )


def test_student_cannot_read_unenrolled_offering(auth_client: TestClient):
    token = _login(auth_client, "student", "other-student-002", "another-password")
    response = auth_client.get(
        "/academic/offerings/phy101-fall-2024?role=student",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_login_rejects_invalid_password(auth_client: TestClient):
    response = auth_client.post(
        "/api/auth/login",
        json={"role": "teacher", "username": "instructor", "password": "incorrect"},
    )
    assert response.status_code == 401


def test_auth_enabled_requires_complete_server_configuration(monkeypatch):
    monkeypatch.setenv("FORMA_AUTH_REQUIRED", "true")
    monkeypatch.delenv("FORMA_AUTH_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="FORMA_AUTH_SECRET"):
        with TestClient(app):
            pass


def test_auth_required_rejects_invalid_boolean(monkeypatch):
    monkeypatch.setenv("FORMA_AUTH_REQUIRED", "enabled-ish")
    with pytest.raises(RuntimeError, match="must be a boolean"):
        auth_required()
