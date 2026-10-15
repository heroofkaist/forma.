"""Real authenticated upload-to-review path without any template setup."""
import pymupdf
from sqlalchemy import select
from test_accounts_courses import platform, identity, create_course
import analysis_api
import document_review
import document_processing
from persistence import AcademicAssignment, AcademicSubmission, AcademicGrade, read_blob
from processing_models import ProcessingJob


def test_student_pdf_without_template_end_to_end(platform, monkeypatch):
    client, factory, sent = platform
    for module in (analysis_api, document_review):
        monkeypatch.setattr(module, 'SessionLocal', factory)
    teacher = identity(client, sent, 'owner@example.com')
    student = identity(client, sent, 'learner@example.com')
    outsider = identity(client, sent, 'outsider@example.com')
    other_teacher = identity(client, sent, 'other@example.com')
    course = create_course(client, teacher)
    create_course(client, other_teacher)
    response = client.post('/academic/assignments', headers=teacher, json={
        'offering_id': course['offering_id'], 'title': 'Independent PDF',
        'assignment_type': 'problem_set', 'description': 'Explain your method.',
        'originality_enabled': False,
    })
    assert response.status_code == 201, response.text
    assignment = response.json()
    with factory() as db:
        assert db.get(AcademicAssignment, assignment['id']).template_regions == []
    assert client.post('/api/enrollment/join', headers=student, json={'class_code': course['class_code']}).status_code == 201
    document = pymupdf.open()
    for text in ('Problem 1\nF = ma', 'Continuation of the solution', 'Problem 2\nExplanation'):
        document.new_page().insert_text((48, 72), text)
    content = document.tobytes(); document.close()
    path = f"/academic/assignments/{assignment['id']}/submissions"
    upload = lambda headers: client.post(path, headers=headers, files={'file': ('own-solution.pdf', content, 'application/pdf')})
    assert upload(outsider).status_code == 403
    assert upload(teacher).status_code == 403
    receipt = upload(student)
    assert receipt.status_code == 201, receipt.text
    sid = receipt.json()['id']
    analysis = '/api/document-analysis/' + sid
    with factory() as db:
        row = db.get(AcademicSubmission, sid)
        assert read_blob(row.file_path) == content
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.submission_id == sid))
        assert job.status == 'queued'
    for headers in (outsider, other_teacher):
        for endpoint in (analysis + '/status', '/api/submission-files/' + sid, '/api/document-review/' + sid):
            assert client.get(endpoint, headers=headers).status_code == 403
    assert client.get('/api/submission-files/' + sid, headers=student).content == content
    assert client.get(analysis, headers=student).status_code == 403
    listing = '/api/assignment-submissions/' + assignment['id']
    assert client.get(listing, headers=teacher).json()['items'][0]['processing_status'] == 'queued'
    assert document_processing.process_one()
    assert client.get(analysis + '/status', headers=student).json()['jobs'][0]['status'] == 'needs_review'
    review = client.get('/api/document-review/' + sid, headers=teacher).json()
    assert len(review['structure']['pages']) == 3
    item = client.get(analysis, headers=teacher).json()['items'][0]
    correction = {'interpretation_id': item['id'], 'result': item['original'], 'confirmed': True}
    assert client.post(analysis + '/corrections', headers=other_teacher, json=correction).status_code == 403
    assert client.post(analysis + '/corrections', headers=teacher, json=correction).status_code == 201
    assert client.get(listing, headers=teacher).json()['items'][0]['processing_status'] == 'completed'
    with factory() as db:
        assert db.scalar(select(AcademicGrade).where(AcademicGrade.submission_id == sid)) is None


def test_uploaded_pdf_failure_is_visible_and_retryable(platform, monkeypatch):
    from test_document_processing import setup_submission
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    path = '/api/document-analysis/' + sid
    client.post(path, headers=teacher, json={})
    monkeypatch.setattr(document_processing, 'gemini_interpret', lambda *args: (_ for _ in ()).throw(ValueError('sensitive provider response')))
    assert document_processing.process_one()
    status = client.get(path + '/status', headers=student).json()['jobs'][0]
    assert status['status'] == 'failed' and status['error']
    assert 'sensitive' not in status['error']
    assert client.post(path, headers=teacher, json={'reanalyze': True}).status_code == 202
