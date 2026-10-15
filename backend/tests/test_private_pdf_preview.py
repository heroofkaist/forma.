"""Original PDFs remain private behind institutional and submission checks."""
import io
from types import SimpleNamespace
from botocore.response import StreamingBody
from test_accounts_courses import platform, identity, create_course
from test_document_processing import setup_submission
import document_review
import persistence
from institution_models import InstitutionMembership
from sqlalchemy import select


def test_teacher_pdf_preview_and_cross_account_denials(platform, monkeypatch):
    client, factory, teacher, student, sid, structure, assignment, pdf = setup_submission(platform, monkeypatch)
    unrelated = identity(client, platform[2], 'unrelated-preview@example.com')
    peer = identity(client, platform[2], 'enrolled-peer@example.com')
    create_course(client, unrelated)
    # An enrolled peer reaches the actual same-course ownership check.
    from persistence import CourseOffering
    with factory() as db:
        code = db.get(CourseOffering, assignment['offering_id']).class_code
    assert client.post('/api/enrollment/join', headers=peer, json={'class_code': code}).status_code == 201
    reads = []
    streams = []
    def get_object(**kwargs):
        reads.append(kwargs)
        stream = io.BytesIO(pdf); streams.append(stream)
        return {'Body': StreamingBody(stream, len(pdf))}
    monkeypatch.setattr(persistence, 'STORAGE_BACKEND', 'r2')
    monkeypatch.setattr(persistence, '_r2_bucket', 'synthetic-private-bucket')
    monkeypatch.setattr(persistence, '_r2_client', SimpleNamespace(get_object=get_object))
    endpoint = '/api/submission-files/' + sid
    assert client.get('/api/document-review/' + sid, headers=teacher).status_code == 200
    # This is the exact malformed path previously forwarded by the frontend.
    rejected = client.get('/api/backend' + endpoint, headers=teacher)
    assert rejected.status_code == 403
    assert rejected.json()['detail'] == 'This route has no access policy.'
    assert reads == []  # Rejected before retrieval, not an R2 403.
    response = client.get(endpoint, headers=teacher)
    assert response.status_code == 200 and response.content == pdf
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert reads == [{'Bucket': 'synthetic-private-bucket', 'Key': 'synthetic.pdf'}]
    assert streams[0].closed
    assert client.get(endpoint, headers=student).content == pdf
    for headers in (unrelated, peer):
        before = len(reads)
        denied = client.get(endpoint, headers=headers)
        assert denied.status_code == 403 and len(reads) == before
    assert client.get(endpoint, headers=peer).json()['detail'] == 'This submission belongs to another student.'
    # Revoked institutional access denies the same teacher before reading R2.
    account_id = client.get('/api/auth/me', headers=teacher).json()['account_id']
    with factory() as db:
        db.scalar(select(InstitutionMembership).where(InstitutionMembership.account_id == account_id)).status = 'suspended'
        db.commit()
    before = len(reads)
    assert client.get(endpoint, headers=teacher).status_code == 403
    assert len(reads) == before
