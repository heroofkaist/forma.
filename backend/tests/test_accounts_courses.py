"""Synthetic public account lifecycle and independent course isolation."""
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
import persistence
import accounts
import ai_budget
import account_models
import courses
import permissions
import academic_api
import assignment_api
import email_delivery
import institutions
import document_processing
from main import app
from migrations import apply_migrations
from persistence import Base, now_utc

@pytest.fixture
def platform(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'platform.db'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    for module in (persistence, accounts, ai_budget, courses, permissions, academic_api, assignment_api, email_delivery, institutions, document_processing):
        monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(persistence, "engine", engine)
    monkeypatch.setenv("FORMA_AUTH_REQUIRED", "true")
    monkeypatch.setenv("FORMA_AUTH_SECRET", "a-long-test-secret-at-least-thirty-two-bytes")
    monkeypatch.setenv("FORMA_LEGACY_LOGIN_ENABLED", "false")
    monkeypatch.setenv("FORMA_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("FORMA_EMAIL_WORKER_ENABLED", "false")
    from cryptography.fernet import Fernet
    monkeypatch.setenv("FORMA_EMAIL_TOKEN_KEY", Fernet.generate_key().decode())
    for key in ("FORMA_SMTP_HOST", "FORMA_SMTP_USERNAME", "FORMA_SMTP_PASSWORD", "FORMA_EMAIL_FROM"):
        monkeypatch.setenv(key, "test-only")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://forma.example")
    monkeypatch.setattr(academic_api, "DEMO_MODE", False)
    monkeypatch.setattr(assignment_api, "DEMO_MODE", False)
    sent = []
    original_enqueue = accounts.enqueue_action
    def record_queue(db, account, purpose, token):
        sent.append((account.email, purpose, token))
        original_enqueue(db, account, purpose, token)
    monkeypatch.setattr(accounts, "enqueue_action", record_queue)
    monkeypatch.setattr(institutions, "enqueue_action", record_queue)
    with TestClient(app) as client:
        yield client, factory, sent
    engine.dispose()


def registration_age(client):
    response = client.post('/api/accounts/age-check', json={'age_band': '18_or_over'})
    assert response.status_code == 200 and response.json()['eligible']
    return response.json()['age_check_token']


def register(client, sent, email):
    response = client.post("/api/accounts/register", json={"email": email, "display_name": email.split("@")[0], "password": "correct-password-123", "age_check_token": registration_age(client)})
    assert response.status_code == 202, response.text
    return next(token for address, purpose, token in reversed(sent) if address == email and purpose == "verify")


def identity(client, sent, email):
    token = register(client, sent, email)
    assert client.post("/api/accounts/verify-email", json={"token": token}).status_code == 200
    response = client.post("/api/auth/login", json={"role": "teacher", "username": email, "password": "correct-password-123"})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def create_course(client, headers, **extras):
    from institution_models import AccountRole, Institution, InstitutionMembership
    identity_id = client.get('/api/auth/me', headers=headers).json()['account_id']
    with accounts.SessionLocal() as db:
        institution = Institution(name='Synthetic approved institution'); db.add(institution); db.flush()
        access = db.get(AccountRole, identity_id)
        access.role = 'teacher'
        db.add(InstitutionMembership(institution_id=institution.id, account_id=identity_id, role='teacher'))
        db.commit(); institution_id = institution.id
    payload = {"institution_id": institution_id, "title": "General Science", "code": "SCI101", "subject": "Science", "academic_year": "2026", "term": "Fall", **extras}
    response = client.post("/api/courses", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_verification_password_reset_session_revocation(platform):
    client, factory, sent = platform
    email = "student@example.com"
    token = register(client, sent, email)
    login = {"role": "student", "username": email, "password": "correct-password-123"}
    assert client.post("/api/auth/login", json=login).status_code == 401
    assert client.post("/api/accounts/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/accounts/verify-email", json={"token": token}).status_code == 400
    assert client.post("/api/auth/login", json={**login, "password": "wrong"}).status_code == 401
    headers = {"Authorization": "Bearer " + client.post("/api/auth/login", json=login).json()["access_token"]}
    with factory() as db:
        user = db.scalar(select(account_models.Account))
        assert user.password_hash.startswith("$argon2id$")
        assert "correct-password-123" not in user.password_hash
        assert user.verified
    before = len(sent)
    assert client.post("/api/accounts/register", json={"email": email, "display_name": "Attacker", "password": "different-password", "age_check_token": registration_age(client)}).status_code == 202
    assert len(sent) == before  # Duplicate cannot replace the password or enumerate accounts.
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "student"
    assert client.post("/api/accounts/forgot-password", json={"email": email}).status_code == 202
    reset = sent[-1][2]
    assert client.post("/api/accounts/reset-password", json={"token": reset, "password": "new-secure-password"}).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/accounts/reset-password", json={"token": reset, "password": "another-password"}).status_code == 400
    assert client.post("/api/auth/login", json=login).status_code == 401
    new = client.post("/api/auth/login", json={**login, "password": "new-secure-password"})
    new_headers = {"Authorization": "Bearer " + new.json()["access_token"]}
    assert client.post("/api/accounts/logout", headers=new_headers).status_code == 200
    assert client.get("/api/auth/me", headers=new_headers).status_code == 401


def test_email_dependency_expiry_and_rate_limits(platform, monkeypatch):
    client, factory, sent = platform
    monkeypatch.delenv("FORMA_SMTP_HOST")
    assert client.post("/api/accounts/register", json={"email": "missing@example.com", "display_name": "Missing", "password": "correct-password-123", "age_check_token": registration_age(client)}).status_code == 503
    assert client.post("/api/accounts/forgot-password", json={"email": "missing@example.com"}).status_code == 503
    assert sent == []
    monkeypatch.setenv("FORMA_SMTP_HOST", "test")
    headers = identity(client, sent, "expiry@example.com")
    with factory() as db:
        session = db.scalar(select(account_models.AccountSession))
        session.expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    for _ in range(10):
        assert client.post("/api/auth/login", json={"role": "teacher", "username": "unknown@example.com", "password": "invalid"}).status_code == 401
    assert client.post("/api/auth/login", json={"role": "teacher", "username": "unknown@example.com", "password": "invalid"}).status_code == 429
    token = register(client, sent, "expired-link@example.com")
    with factory() as db:
        action = db.get(account_models.AccountAction, accounts.digest(token))
        action.expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/accounts/verify-email", json={"token": token}).status_code == 400


def test_course_isolation_code_lifecycle_and_duplicate_join(platform):
    client, factory, sent = platform
    teacher = identity(client, sent, "teacher-a@example.com")
    other = identity(client, sent, "teacher-b@example.com")
    student = identity(client, sent, "student@example.com")
    a = create_course(client, teacher, institution="Institution A")
    b = create_course(client, other, institution="Institution B")
    assert a["class_code"] != b["class_code"]
    assert client.get(f'/academic/offerings/{a["offering_id"]}?role=teacher', headers=other).status_code == 403
    assert client.get(f'/academic/offerings/{a["offering_id"]}?role=student', headers=student).status_code == 403
    assert client.get(f'/api/courses/{a["offering_id"]}/enrollment', headers=other).status_code == 403
    listing = client.get('/academic/courses?role=teacher', headers=other).json()["items"]
    assert len(listing) == 1 and listing[0]["id"] == b["course_id"]
    assert client.get('/academic/courses?role=student', headers=student).json()["items"] == []
    assert client.post('/api/enrollment/join', headers=student, json={"class_code": "INVALID-CODE"}).status_code == 404
    preview = client.post('/api/enrollment/preview', headers=student, json={"class_code": a["class_code"]})
    assert preview.json()["title"] == "General Science"
    joined = client.post('/api/enrollment/join', headers=student, json={"class_code": a["class_code"]})
    duplicate = client.post('/api/enrollment/join', headers=student, json={"class_code": a["class_code"]})
    assert joined.json()["created"] and not duplicate.json()["created"]
    assert joined.json()["id"] == duplicate.json()["id"]
    assert client.get(f'/academic/offerings/{a["offering_id"]}?role=student', headers=student).status_code == 200
    rotation = client.post(f'/api/courses/{a["offering_id"]}/rotate-code', headers=teacher)
    assert rotation.status_code == 200
    assert client.post('/api/enrollment/join', headers=student, json={"class_code": a["class_code"]}).status_code == 404
    assert client.get(f'/academic/offerings/{a["offering_id"]}?role=student', headers=student).status_code == 200
    removed = client.patch(f'/api/courses/{a["offering_id"]}/enrollment/{joined.json()["id"]}', headers=teacher, json={"status": "removed"})
    assert removed.status_code == 200
    assert client.get(f'/academic/offerings/{a["offering_id"]}?role=student', headers=student).status_code == 403
    assert client.get('/academic/courses?role=student', headers=student).json()["items"] == []
    assert client.post('/api/enrollment/join', headers=student, json={"class_code": rotation.json()["class_code"]}).json()["status"] == "removed"


def test_pending_capacity_and_expired_disabled_codes(platform):
    client, factory, sent = platform
    teacher = identity(client, sent, "teacher@example.com")
    student = identity(client, sent, "student@example.com")
    other = identity(client, sent, "other@example.com")
    course = create_course(client, teacher, approval_required=True, capacity=1)
    joined = client.post('/api/enrollment/join', headers=student, json={"class_code": course["class_code"]}).json()
    assert joined["status"] == "pending"
    assert client.get(f'/academic/offerings/{course["offering_id"]}?role=student', headers=student).status_code == 403
    assert client.post('/api/enrollment/join', headers=other, json={"class_code": course["class_code"]}).status_code == 409
    assert client.patch(f'/api/courses/{course["offering_id"]}/enrollment/{joined["id"]}', headers=teacher, json={"status": "active"}).status_code == 200
    assert client.get(f'/academic/offerings/{course["offering_id"]}?role=student', headers=student).status_code == 200
    assert client.put(f'/api/courses/{course["offering_id"]}/enrollment', headers=teacher, json={"enabled": False}).status_code == 200
    assert client.post('/api/enrollment/preview', headers=other, json={"class_code": course["class_code"]}).status_code == 404
    assert client.put(f'/api/courses/{course["offering_id"]}/enrollment', headers=teacher, json={"closes_at": "2020-01-01T00:00:00Z"}).status_code == 200
    assert client.post('/api/enrollment/join', headers=other, json={"class_code": course["class_code"]}).status_code == 404


def test_linked_legacy_assignment_and_answer_permissions(platform):
    client, factory, sent = platform
    teacher = identity(client, sent, "teacher@example.com")
    other = identity(client, sent, "other@example.com")
    student = identity(client, sent, "student@example.com")
    course = create_course(client, teacher)
    payload = {"offering_id": course["offering_id"], "title": "Lab report", "assignment_type": "lab_report", "maximum_score": 10}
    assert client.post('/academic/assignments', headers=other, json=payload).status_code == 403
    response = client.post('/academic/assignments', headers=teacher, json=payload)
    assert response.status_code == 201, response.text
    assignment = response.json()
    legacy = assignment["legacy_assignment_id"]
    assert client.get(f'/assignments/{legacy}', headers=other).status_code == 403
    assert client.get(f'/assignments/{legacy}', headers=student).status_code == 403
    assert client.get('/assignments', headers=other).status_code == 403
    assert client.get(f'/assignments/{legacy}', headers=teacher).status_code == 200
    assert client.post(f'/academic/assignments/{assignment["id"]}/publish', headers=other).status_code == 403
    assert client.get(f'/academic/teacher/assignments/{assignment["id"]}/archive', headers=other).status_code == 403
    assert client.post('/academic/offerings', headers=other, json={"course_id": course["course_id"], "academic_year": "2027", "term": "Fall"}).status_code == 403
    assert client.get('/api/courses/' + course["offering_id"] + '/roster.csv', headers=teacher).status_code == 200


def test_additive_migration_repeated_and_profile_security(platform):
    client, factory, sent = platform
    headers = identity(client, sent, "profile@example.com")
    assert client.patch('/api/accounts/profile', headers=headers, json={"display_name": "New Name"}).status_code == 200
    assert client.get('/api/accounts/profile', headers=headers).json()["display_name"] == "New Name"
    engine = factory.kw["bind"]
    apply_migrations(engine); apply_migrations(engine)
    with factory() as db:
        assert len(db.scalars(select(account_models.SchemaMigration)).all()) == 11
        assert db.scalar(select(account_models.Account)).display_name == "New Name"
    assert client.post('/api/accounts/password', headers=headers, json={"current_password": "bad", "password": "new-password-123"}).status_code == 400
    assert client.post('/api/accounts/password', headers=headers, json={"current_password": "correct-password-123", "password": "new-password-123"}).status_code == 200
    assert client.get('/api/accounts/profile', headers=headers).status_code == 401


def test_universal_submission_material_visibility_and_rubric_limits(platform, monkeypatch):
    import io
    import pymupdf
    import materials
    import document_review
    from document_models import SubmissionDocument
    client, factory, sent = platform
    monkeypatch.setattr(materials, "SessionLocal", factory)
    monkeypatch.setattr(document_review, "SessionLocal", factory)
    blobs = {}
    monkeypatch.setattr(academic_api, "write_blob", lambda key, content: blobs.update({key: content}))
    monkeypatch.setattr(academic_api, "save_blob", lambda assignment, kind, content, suffix: "test.pdf")
    monkeypatch.setattr(materials, "write_blob", lambda key, content: blobs.update({key: content}))
    monkeypatch.setattr(materials, "read_blob", lambda key: blobs[key])
    teacher = identity(client, sent, "teacher@example.com")
    student = identity(client, sent, "student@example.com")
    other = identity(client, sent, "other@example.com")
    course = create_course(client, teacher)
    assert client.post('/api/enrollment/join', headers=student, json={"class_code": course["class_code"]}).status_code == 201
    payload = {"offering_id": course["offering_id"], "title": "Lab", "assignment_type": "lab_report", "maximum_score": 10, "questions": [{"title": "Lab", "maximum_points": 10, "criteria": [{"id": "method", "description": "Method", "maximum_points": 5}, {"id": "data", "description": "Data", "maximum_points": 5}]}]}
    invalid = {**payload, "maximum_score": 5}
    assert client.post('/academic/assignments', headers=teacher, json=invalid).status_code == 422
    duplicate_criteria = {**payload, "questions": [{"title": "Lab", "maximum_points": 10, "criteria": [{"id": "same", "description": "A", "maximum_points": 5}, {"id": "same", "description": "B", "maximum_points": 5}]}]}
    assert client.post('/academic/assignments', headers=teacher, json=duplicate_criteria).status_code == 422
    assignment = client.post('/academic/assignments', headers=teacher, json=payload).json()
    document = pymupdf.open(); page = document.new_page(); page.insert_text((48, 72), "Introduction\nA synthetic report."); content = document.tobytes(); document.close()
    files = {"file": ("report.pdf", content, "application/pdf")}
    response = client.post(f'/academic/assignments/{assignment["id"]}/submissions', headers=student, files=files)
    assert response.status_code == 201, response.text
    submission = response.json()
    assert submission["originality_reports"] == []
    with factory() as db: assert db.get(SubmissionDocument, submission["id"]).structure["unit_count"] == 1
    assert client.get('/api/submission-documents/' + submission["id"], headers=other).status_code == 403
    assert client.get('/api/submission-documents/' + submission["id"], headers=student).status_code == 200
    assert client.post(f'/academic/assignments/{assignment["id"]}/submissions', headers=student, files=files).status_code == 409
    assert client.post(f'/academic/assignments/{assignment["id"]}/submissions', headers=other, files=files).status_code == 403
    private = client.post(f'/api/course-materials/{course["offering_id"]}', headers=teacher, data={"title": "Private solution", "visibility": "teacher_only"}, files=files)
    public = client.post(f'/api/course-materials/{course["offering_id"]}', headers=teacher, data={"title": "Lecture", "visibility": "student_visible"}, files=files)
    assert private.status_code == 201 and public.status_code == 201
    assert len(client.get(f'/api/course-materials/{course["offering_id"]}', headers=student).json()["items"]) == 1
    assert client.get(f'/api/materials/{private.json()["id"]}/file', headers=student).status_code == 403
    assert client.get(f'/api/materials/{public.json()["id"]}/file', headers=student).status_code == 200
    assert client.get(f'/api/materials/{public.json()["id"]}/file', headers=other).status_code == 403


def test_manual_review_hidden_until_publish_preserves_history(platform, monkeypatch):
    import document_review
    from persistence import AcademicSubmission, AcademicGrade
    from document_models import DocumentReview
    client, factory, sent = platform
    monkeypatch.setattr(document_review, "SessionLocal", factory)
    teacher = identity(client, sent, "teacher@example.com")
    student = identity(client, sent, "student@example.com")
    other = identity(client, sent, "other@example.com")
    course = create_course(client, teacher)
    client.post('/api/enrollment/join', headers=student, json={"class_code": course["class_code"]})
    assignment = client.post('/academic/assignments', headers=teacher, json={"offering_id": course["offering_id"], "title": "Essay", "assignment_type": "essay", "maximum_score": 10, "questions": [{"title": "Essay", "maximum_points": 10, "reference_solution": "PRIVATE REFERENCE SOLUTION"}]}).json()
    student_id = client.get('/api/auth/me', headers=student).json()['student_id']
    with factory() as db:
        row = AcademicSubmission(assignment_id=assignment['id'], student_id=student_id, student_name="Synthetic Student", file_name="essay.pdf", file_path="synthetic.pdf", file_type="pdf")
        db.add(row); db.commit(); submission_id = row.id
    path = '/api/document-review/' + submission_id
    assert client.get('/api/teacher-overview', headers=other).status_code == 403
    assert len(client.get('/api/teacher-overview', headers=teacher).json()['review_queue']) == 1
    assert client.get(path, headers=other).status_code == 403
    assert client.get(path, headers=student).status_code == 403
    assert client.get(f"/academic/teacher/assignments/{assignment['id']}/archive?role=student", headers=student).status_code == 403
    assert client.post(f"/academic/assignments/{assignment['id']}/publish?role=student", headers=student).status_code == 403
    assert client.post(f"/academic/assignments/{assignment['id']}/reuse?role=student", headers=student, json={"offering_id": course['offering_id']}).status_code == 403
    question = assignment['questions'][0]
    criterion = question['criteria'][0]
    body = {"criteria": [{"question_id": question['id'], "criterion_id": criterion['criterion_id'], "points": 8, "comment": "Good evidence"}], "feedback": "Clear argument."}
    assert client.post(path, headers=teacher, json={**body, "criteria": []}).status_code == 422
    assert client.post(path, headers=teacher, json={**body, "criteria": [{**body['criteria'][0], "points": 11}]}).status_code == 422
    review = client.post(path, headers=teacher, json=body)
    assert review.status_code == 201, review.text
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []
    assert client.post(path + '/publish', headers=student, json={"review_id": review.json()['id']}).status_code == 403
    assert client.post(path + '/publish', headers=teacher, json={"review_id": review.json()['id']}).status_code == 200
    published = client.get('/academic/student/grades', headers=student).json()['items'][0]
    assert published['points'] == 8 and published['feedback'] == "Clear argument."
    assert published['criteria'][0]['points'] == 8
    assert "PRIVATE REFERENCE SOLUTION" not in str(published)
    revised = client.post(path, headers=teacher, json={**body, "criteria": [{**body['criteria'][0], "points": 9}]}).json()
    assert client.get('/academic/student/grades', headers=student).json()['items'][0]['points'] == 8
    client.post(path + '/publish', headers=teacher, json={"review_id": revised['id']})
    with factory() as db: assert len(db.scalars(select(DocumentReview)).all()) == 2
    assert client.get('/academic/student/grades', headers=student).json()['items'][0]['points'] == 9


def test_durable_email_outbox_encrypts_tokens_and_recovers_lease(platform, monkeypatch):
    from account_models import EmailOutbox
    client, factory, sent = platform
    token = register(client, sent, "outbox@example.com")
    delivered = []
    monkeypatch.setattr(accounts, "send_action", lambda email, purpose, value: delivered.append((email, purpose, value)))
    with factory() as db:
        item = db.scalar(select(EmailOutbox))
        assert token not in item.encrypted_token
        item.status = "sending"; item.lease_until = now_utc() - timedelta(seconds=1); db.commit()
    assert email_delivery.deliver_one()
    assert delivered == [("outbox@example.com", "verify", token)]
    assert not email_delivery.deliver_one()
    with factory() as db:
        item = db.scalar(select(EmailOutbox))
        assert item.status == "sent" and item.encrypted_token == ""


def test_email_delivery_failure_is_durable_bounded_and_not_reported_as_sent(platform, monkeypatch):
    from account_models import EmailOutbox
    client, factory, sent = platform
    register(client, sent, "failure@example.com")
    def fail(*args): raise OSError("provider secret must not leak")
    monkeypatch.setattr(accounts, "send_action", fail)
    for _ in range(3):
        assert email_delivery.deliver_one()
        with factory() as db:
            item = db.scalar(select(EmailOutbox)); item.available_at = now_utc() - timedelta(seconds=1); db.commit()
    with factory() as db:
        item = db.scalar(select(EmailOutbox)); assert item.status == "failed" and item.attempts == 3
        assert "secret" not in item.error and item.encrypted_token == ""
    assert not email_delivery.deliver_one()


def test_malformed_mutation_body_is_rejected_without_permission_bypass(platform):
    client, factory, sent = platform
    headers = identity(client, sent, "teacher@example.com")
    create_course(client, headers)
    assert client.post('/academic/assignments', headers=headers, content="not-json").status_code == 400
    assert client.post('/academic/offerings', headers=headers, json=[]).status_code == 422


def test_concurrent_submission_respects_no_resubmission_policy(platform, monkeypatch):
    import pymupdf
    from concurrent.futures import ThreadPoolExecutor
    from persistence import AcademicSubmission
    client, factory, sent = platform
    monkeypatch.setattr(academic_api, "write_blob", lambda *args: None)
    monkeypatch.setattr(academic_api, "save_blob", lambda *args: "synthetic.pdf")
    teacher = identity(client, sent, "teacher@example.com")
    student = identity(client, sent, "student@example.com")
    course = create_course(client, teacher)
    client.post('/api/enrollment/join', headers=student, json={"class_code": course['class_code']})
    assignment = client.post('/academic/assignments', headers=teacher, json={"offering_id": course['offering_id'], "title": "Concurrent submission", "maximum_score": 10}).json()
    document = pymupdf.open(); document.new_page().insert_text((48, 72), "Synthetic concurrent upload"); content = document.tobytes(); document.close()
    def submit():
        return client.post(f"/academic/assignments/{assignment['id']}/submissions", headers=student, files={"file": ("synthetic.pdf", content, "application/pdf")}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(statuses) == [201, 409]
    with factory() as db:
        assert len(db.scalars(select(AcademicSubmission)).all()) == 1


def test_expired_email_outbox_discards_token_without_sending(platform, monkeypatch):
    from account_models import EmailOutbox
    client, factory, sent = platform
    register(client, sent, "expired-mail@example.com")
    calls = []
    monkeypatch.setattr(accounts, "send_action", lambda *args: calls.append(args))
    with factory() as db:
        item = db.scalar(select(EmailOutbox)); item.expires_at = now_utc() - timedelta(seconds=1); db.commit()
    assert not email_delivery.deliver_one()
    assert calls == []
    with factory() as db:
        item = db.scalar(select(EmailOutbox)); assert item.status == "failed" and not item.encrypted_token


def test_public_account_image_grading_requests_are_rate_limited(platform):
    client, factory, sent = platform
    headers = identity(client, sent, "processing@example.com")
    create_course(client, headers)
    body = {"problem_statement": "Synthetic", "reference_solution": "Synthetic", "rubric_text": "Synthetic"}
    for _ in range(10):
        response = client.post('/api/grade', headers=headers, data=body, files={"image": ("bad.txt", b"not an image", "text/plain")})
        assert response.status_code == 415
    response = client.post('/api/grade', headers=headers, data=body, files={"image": ("bad.txt", b"not an image", "text/plain")})
    assert response.status_code == 429
