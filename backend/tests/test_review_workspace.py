"""Inexpensive Phase 4.2 contracts: saved results only, never live inference."""
from io import BytesIO
from PIL import Image
from sqlalchemy import select, func
from test_accounts_courses import platform, identity
from test_document_processing import setup_submission
from test_assessment import assessed
import document_review
import document_processing
from document_models import DocumentReview
from persistence import AcademicGrade


def test_assessment_draft_reload_and_confirmation_are_distinct(assessed):
    values, path, *_ = assessed
    client, factory, teacher, student, sid, *_ = values
    assert client.post(path, headers=teacher, json={}).status_code == 202
    document_processing.process_one()  # Fixture's mocked evaluator, no transport.
    suggestion = client.get(path, headers=teacher).json()['items'][0]
    decisions = [{'question_id': c['question_id'], 'criterion_id': c['criterion_id'], 'action': 'accepted',
        'points': 3, 'feedback': 'Teacher draft', 'finding': 'concern'} for c in suggestion['result']['criteria']]
    payload = {'suggestion_id': suggestion['id'], 'decisions': decisions, 'draft': True, 'feedback': 'Overall draft feedback'}
    response = client.post(path + '/decisions', headers=teacher, json=payload)
    assert response.status_code == 201 and response.json()['review_id'] is None
    reloaded = client.get(path, headers=teacher).json()['items'][0]['decisions'][0]['decisions']
    assert reloaded[0]['points'] == 3 and reloaded[0]['confirmed'] is False
    assert reloaded[0]['overall_feedback'] == payload['feedback']
    assert client.get(path + '/insights', headers=teacher).json()['items'] == []
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DocumentReview)) == 0
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
    payload['draft'] = False
    confirmed = client.post(path + '/decisions', headers=teacher, json=payload)
    assert confirmed.status_code == 201 and confirmed.json()['review_id']
    with factory() as db:
        assert db.get(DocumentReview, confirmed.json()['review_id']).feedback == payload['feedback']
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
    prior = client.get(path + '/insights', headers=teacher).json()['items']
    assert prior
    # A later working draft must not erase a prior authoritative decision.
    payload['draft'] = True
    for d in decisions: d.update(action='rejected', points=None)
    assert client.post(path + '/decisions', headers=teacher, json=payload).status_code == 201
    assert client.get(path + '/insights', headers=teacher).json()['items'] == prior
    assert client.post(path + '/decisions', headers=student, json=payload).status_code == 403


def test_incomplete_manual_draft_is_saved_and_cannot_be_published(platform, monkeypatch):
    client, factory, teacher, student, sid, _, _, _ = setup_submission(platform, monkeypatch)
    path = '/api/document-review/' + sid
    data = client.get(path, headers=teacher).json()
    assert data['submitted_at'] and data['assignment_type'] == 'problem_set'
    assert data['published_grade'] is None
    scores = [{'question_id': q['id'], 'criterion_id': c['criterion_id'], 'points': None, 'comment': 'Draft'} for q in data['questions'] for c in q['criteria']]
    scores[0]['points'] = 0  # Explicit zero differs from ungraded.
    body = {'criteria': scores, 'feedback': 'Incomplete feedback', 'draft': True}
    response = client.post(path, headers=teacher, json=body)
    assert response.status_code == 201
    assert client.get(path, headers=teacher).json()['reviews'][0]['criteria'][1]['points'] is None
    assert client.post(path + '/publish', headers=teacher, json={'review_id': response.json()['id']}).status_code == 409
    body['criteria'][1]['points'] = 4
    complete_draft = client.post(path, headers=teacher, json=body)
    assert complete_draft.status_code == 201
    assert client.post(path + '/publish', headers=teacher, json={'review_id': complete_draft.json()['id']}).status_code == 409
    body['criteria'][1]['points'] = None
    body['draft'] = False
    assert client.post(path, headers=teacher, json=body).status_code == 422
    body['criteria'][1]['points'] = 4
    response = client.post(path, headers=teacher, json=body)
    assert response.status_code == 201
    assert client.post(path + '/publish', headers=student, json={'review_id': response.json()['id']}).status_code == 403
    with factory() as db: assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
    published = client.post(path + '/publish', headers=teacher, json={'review_id': response.json()['id']})
    assert published.status_code == 200 and published.json()['points'] == 4
    grade = client.get(path, headers=teacher).json()['published_grade']
    assert grade['review_id'] == response.json()['id']
    assert client.post(path + '/publish', headers=teacher, json={'review_id': response.json()['id'], 'expected_published_review_id': None}).status_code == 409
    assert client.get(path, headers=teacher).json()['published_grade']['points'] == 4


def test_preview_is_private_bounded_and_does_not_invoke_analysis(platform, monkeypatch):
    client, factory, teacher, student, sid, _, _, content = setup_submission(platform, monkeypatch)
    monkeypatch.setattr(document_review, 'read_blob', lambda _: content)
    outsider = identity(client, platform[2], 'unrelated-reviewer@example.com')
    path = '/api/document-review/' + sid + '/pages/'
    for denied in (student, outsider): assert client.get(path + '1', headers=denied).status_code == 403
    response = client.get(path + '2', headers=teacher)
    assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
    assert response.headers['cache-control'] == 'private, no-store'
    with Image.open(BytesIO(response.content)) as image: assert max(image.size) <= 1601
    for invalid in ('0', '4', '99'): assert client.get(path + invalid, headers=teacher).status_code == 404
