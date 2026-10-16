"""Teacher standards, scoped inference, original citations and revision receipts.

All documents and model responses are synthetic; no external AI is invoked.
"""
import copy
import json
from uuid import uuid4
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from test_accounts_courses import platform
from test_assessment import assessed, suggestion
from services.assessment import evaluate as real_evaluate
from services.teaching_guidance import guide_snapshot, current_questions
from services.ai_providers.engine import configuration
from document_models import DocumentReview, SubmissionDocument
from assessment_models import AssessmentSuggestion
from processing_models import ProcessingJob
from teaching_models import TeachingGuide, RevisionResponse
from persistence import AcademicAssignment, AcademicSubmission, now_utc
import academic_api
import document_review
import document_processing


def confirmed(factory, aid, sid, points=3):
    with factory() as db:
        assignment = db.get(AcademicAssignment, aid)
        review = DocumentReview(submission_id=sid, reviewer='Synthetic teacher',
            rubric_snapshot=current_questions(db, assignment), feedback='Explain the first error.',
            criteria=[{'question_id': q['id'], 'criterion_id': c['criterion_id'], 'points': points,
                'comment': 'Show units in the final step.'} for q in assignment.questions for c in q['criteria']])
        db.add(review); db.commit(); return review.id


def test_guide_is_explicit_versioned_private_and_cannot_use_other_course_or_drafts(assessed):
    values, _, _, spec = assessed
    client, factory, teacher, student, sid, _, assignment, _ = values
    path = '/api/teaching/assignments/' + assignment['id'] + '/guide'
    rid = confirmed(factory, assignment['id'], sid)
    assert client.get(path, headers=student).status_code == 403
    body = {'expected_id': None, 'reference_review_ids': [rid], 'rules': [
        {'question_id': spec['criteria'][0]['question_id'], 'criterion_id': spec['criteria'][0]['criterion_id'],
            'instruction': 'Correct method with arithmetic error earns 3 out of 5.'}], 'feedback_focus': 'One concrete next step.'}
    assert client.post(path, headers=student, json=body).status_code == 403
    first = client.post(path, headers=teacher, json=body)
    assert first.status_code == 201, first.text
    assert 'rubric_key' not in first.json()['content']
    assert client.post(path, headers=teacher, json=body).status_code == 409
    body['expected_id'] = first.json()['id']; body['feedback_focus'] = 'Explain units first.'
    second = client.post(path, headers=teacher, json=body)
    assert second.status_code == 201 and second.json()['id'] != first.json()['id']
    value = client.get(path, headers=teacher)
    assert value.headers['cache-control'] == 'private, no-store'
    assert value.json()['examples'][0]['review_id'] == rid
    with factory() as db:
        row = db.get(AcademicAssignment, assignment['id'])
        own = guide_snapshot(db, row, exclude_sid=sid)
        assert own['rules'] and own['examples'] == []  # No self-grading calibration.
        assert db.scalar(select(func.count()).select_from(TeachingGuide)) == 2
        assert db.scalar(select(func.count()).select_from(AssessmentSuggestion)) == 0
        review = db.get(DocumentReview, rid)
        review.criteria = [{**c, 'confirmed': False} for c in review.criteria]; db.commit()
    body['expected_id'] = second.json()['id']
    assert client.post(path, headers=teacher, json=body).status_code == 409
    body['reference_review_ids'] = ['not-this-assignment']
    assert client.post(path, headers=teacher, json=body).status_code == 404
    with factory() as db:
        row = db.get(AcademicAssignment, assignment['id'])
        row.description += ' New requirements.'; db.commit()
        assert guide_snapshot(db, row)['stale'] and not guide_snapshot(db, row)['rules']
    assert client.get(path, headers=teacher).json()['stale']


def test_group_summary_counts_latest_attempts_and_never_counts_ai_or_draft_scores(assessed):
    values, _, _, _ = assessed
    client, factory, teacher, student, sid, structure, assignment, _ = values
    confirmed(factory, assignment['id'], sid, 0)
    path = '/api/teaching/assignments/' + assignment['id'] + '/summary'
    assert client.get(path, headers=student).status_code == 403
    data = client.get(path, headers=teacher).json()
    assert (data['reviewed'], data['submitted']) == (1, 1)
    assert data['criteria'][0]['average'] == 0 and data['criteria'][0]['below_full_credit'] == 1
    with factory() as db:
        old = db.get(AcademicSubmission, sid)
        newer = AcademicSubmission(assignment_id=assignment['id'], student_id=old.student_id, student_name=old.student_name,
            file_name='revision.pdf', file_path=old.file_path, file_type='pdf', created_at=now_utc()+timedelta(seconds=1))
        db.add(newer); db.commit(); new_sid = newer.id
    data = client.get(path, headers=teacher).json()
    assert (data['reviewed'], data['submitted']) == (0, 1)
    assert data['criteria'][0]['average'] is None
    rid = confirmed(factory, assignment['id'], new_sid, 4)
    assert client.get(path, headers=teacher).json()['criteria'][0]['average'] == 4
    with factory() as db:
        review = db.get(DocumentReview, rid)
        db.add(DocumentReview(submission_id=new_sid, reviewer='Synthetic teacher', rubric_snapshot=review.rubric_snapshot,
            criteria=[{**c, 'confirmed': False} for c in review.criteria], feedback='Draft only'))
        db.commit()
    assert client.get(path, headers=teacher).json()['reviewed'] == 0


def test_attention_queue_includes_reading_failures_but_a_confirmed_teacher_review_resolves_them(assessed):
    values, _, _, _ = assessed
    client, factory, teacher, _, sid, _, assignment, _ = values
    path = '/api/assignment-submissions/' + assignment['id']
    with factory() as db:
        db.scalar(select(ProcessingJob)).status = 'failed'; db.commit()
    assert client.get(path, headers=teacher).json()['items'][0]['attention']['kind'] == 'processing'
    with factory() as db:
        row = db.scalar(select(ProcessingJob)); row.status = 'completed'; row.usage = {'partial': True}; db.commit()
    assert client.get(path, headers=teacher).json()['items'][0]['attention']['kind'] == 'evidence'
    confirmed(factory, assignment['id'], sid, 0)
    assert client.get(path, headers=teacher).json()['items'][0]['attention']['kind'] == 'reviewed'


def test_scoped_recheck_calls_model_once_preserves_other_scores_and_refuses_changed_standards(assessed, monkeypatch):
    values, path, _, spec = assessed
    client, factory, teacher, student, sid, _, assignment, _ = values
    def baseline(snap, *args, **kwargs):
        criteria = []
        for c in snap['rubric']['criteria']:
            local_source = {'sections': [s for s in snap['source']['sections'] if s.get('question_id') in (None, c['question_id'])]}
            criteria.extend(suggestion({'criteria': [c]}, local_source)['criteria'])
        return {'criteria': criteria}, {'ai_called': True}
    monkeypatch.setattr('services.assessment.evaluate', baseline)
    assert client.post(path, headers=teacher, json={}).status_code == 202
    assert document_processing.process_one()
    base = client.get(path, headers=teacher).json()['items'][0]
    target = spec['criteria'][0]
    body = {'base_suggestion_id': base['id'], 'target_criteria': [[target['question_id'], target['criterion_id']]], 'reanalyze': True}
    assert client.post(path, headers=student, json=body).status_code == 403
    calls = []
    def complete(config, schema, system, context, *args, **kwargs):
        calls.append(context)
        assert len(context['rubric']['criteria']) == 1
        raw = suggestion(context['rubric'], context['source']); raw['criteria'][0]['proposed_score'] = 3
        return {'message': {'content': json.dumps(raw)}, 'done_reason': 'stop'}
    monkeypatch.setattr('services.assessment.evaluate', real_evaluate)
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion', complete)
    response = client.post(path, headers=teacher, json=body)
    assert response.status_code == 202, response.text
    assert document_processing.process_one()
    saved = client.get(path, headers=teacher).json()['items']
    assert len(saved) == 2 and len(calls) == 1
    scores = {(c['question_id'], c['criterion_id']): c['proposed_score'] for c in saved[0]['result']['criteria']}
    assert scores[(target['question_id'], target['criterion_id'])] == 3
    assert saved[0]['result']['criteria'][0 if saved[0]['result']['criteria'][0]['question_id'] != target['question_id'] else 1] in base['result']['criteria']
    # Loading a saved result never calls the model again.
    client.get(path, headers=teacher); assert len(calls) == 1
    guide_path = '/api/teaching/assignments/' + assignment['id'] + '/guide'
    assert client.post(guide_path, headers=teacher, json={'feedback_focus': 'New standard.'}).status_code == 201
    assert client.post(path, headers=teacher, json=body).status_code == 409
    assert len(calls) == 1


def test_model_receives_matching_teacher_rules_examples_and_feedback_is_readable(monkeypatch):
    rubric = {'category': 'essay', 'instructions': 'Explain a synthetic argument.', 'reference_material': '', 'criteria': [
        {'question_id': 'q', 'criterion_id': 'argument', 'description': 'Use a supported argument.', 'maximum_points': 5}]}
    source = {'sections': [{'id': 's1', 'question_id': 'q', 'page_number': 1, 'transcription': 'A synthetic argument.', 'readability': 'readable'}]}
    guide = {'rules': [{'question_id': 'q', 'criterion_id': 'argument', 'instruction': 'An unsupported claim earns at most 2.'}],
        'examples': [{'question_id': 'q', 'criterion_id': 'argument', 'teacher_score': 2, 'example_answer': 'Different answer.'}], 'feedback_focus': 'One next step.'}
    captured = []
    def complete(config, schema, system, context, *args, **kwargs):
        captured.append(context)
        raw = suggestion(rubric, source); raw['criteria'][0]['rationale'] = 'undefined'
        raw['criteria'][0]['suggested_improvement'] = '[object Object]'
        return {'message': {'content': json.dumps(raw)}, 'done_reason': 'stop'}
    monkeypatch.setattr('services.ai_providers.ollama.structured_completion', complete)
    result, _ = real_evaluate({'rubric': rubric, 'title': 'Essay', 'source': source, 'source_limitations': {}, 'teaching_guide': guide}, configuration('ollama'))
    assert captured[0]['teacher_guidance']['rules'] == guide['rules']
    assert captured[0]['teacher_guidance']['reference_examples'] == guide['examples']
    c = result['criteria'][0]
    assert c['proposed_score'] is None and c['evidence'][0]['quote'] == source['sections'][0]['transcription'][:10]
    assert 'undefined' not in c['rationale'] and c['suggested_improvement'] == ''


def test_evidence_highlight_uses_actual_original_boxes_and_never_guesses(assessed, monkeypatch):
    values, path, _, _ = assessed
    client, factory, teacher, student, sid, _, _, content = values
    monkeypatch.setattr(document_review, 'read_blob', lambda _: content)
    assert client.post(path, headers=teacher, json={}).status_code == 202
    assert document_processing.process_one()
    saved = client.get(path, headers=teacher).json()['items'][0]
    c = saved['result']['criteria'][0]
    body = {'suggestion_id': saved['id'], 'question_id': c['question_id'], 'criterion_id': c['criterion_id'], 'evidence_index': 0}
    route = '/api/document-review/' + sid + '/evidence-location'
    assert client.post(route, headers=student, json=body).status_code == 403
    result = client.post(route, headers=teacher, json=body)
    assert result.status_code == 200 and result.json()['rectangles'], result.text
    for box in result.json()['rectangles']:
        assert all(0 <= n <= 1 for n in box.values())
    with factory() as db:
        row = db.get(AssessmentSuggestion, saved['id']); value = copy.deepcopy(row.result)
        value['criteria'][0]['evidence'][0]['quote'] = 'A scan transcription without embedded text.'
        row.result = value; db.commit()
    assert client.post(route, headers=teacher, json=body).json()['rectangles'] == []
    assert client.post(route, headers=teacher, json={**body, 'suggestion_id': 'another-document'}).status_code == 404
    monkeypatch.setattr(document_review, 'read_blob', lambda _: b'changed')
    assert client.post(route, headers=teacher, json=body).status_code == 409


def test_revision_attaches_atomically_to_upload_retries_and_hides_private_provenance(assessed, monkeypatch):
    values, _, _, _ = assessed
    client, factory, teacher, student, sid, _, assignment, content = values
    # Publish current assignment criteria through the normal manual route.
    scores = [{'question_id': q['id'], 'criterion_id': c['criterion_id'], 'points': 3, 'comment': 'Explain units.'}
        for q in assignment['questions'] for c in q['criteria']]
    review = client.post('/api/document-review/' + sid, headers=teacher, json={'criteria': scores, 'feedback': 'Improve units.'}).json()
    assert client.post('/api/document-review/' + sid + '/publish', headers=teacher, json={'review_id': review['id']}).status_code == 200
    grade = client.get('/academic/student/grades', headers=student).json()['items'][0]
    assert grade['review_id'] == review['id']
    revision = {'source_review_id': review['id'], 'criterion_keys': [[scores[0]['question_id'], scores[0]['criterion_id']]], 'explanation': 'Added units and explained the method.'}
    monkeypatch.setattr(academic_api, 'write_blob', lambda *args: None)
    monkeypatch.setattr(academic_api, 'save_blob', lambda *args: 'synthetic.pdf')
    with factory() as db:
        db.get(AcademicAssignment, assignment['id']).allow_resubmission = True; db.commit()
    route = '/academic/assignments/' + assignment['id'] + '/submissions'
    form = {'request_id': str(uuid4()), 'revision_response': json.dumps(revision)}
    files = {'file': ('revision.pdf', content, 'application/pdf')}
    first = client.post(route, headers=student, data=form, files=files)
    assert first.status_code == 201, first.text
    new_sid = first.json()['id']
    assert client.post(route, headers=student, data=form, files=files).json()['id'] == new_sid
    changed = {**revision, 'explanation': 'Different explanation.'}
    assert client.post(route, headers=student, data={**form, 'revision_response': json.dumps(changed)}, files=files).status_code == 409
    response = client.get('/api/teaching/submissions/' + new_sid + '/revision', headers=teacher)
    assert response.status_code == 200 and response.json()['revision']['explanation'] == revision['explanation']
    assert 'card_use' not in response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RevisionResponse)) == 1
        db.get(AcademicAssignment, assignment['id']).due_at = now_utc()-timedelta(days=1); db.commit()
    # Receipt replay is valid even after deadline; a new attempt is not.
    assert client.post(route, headers=student, data=form, files=files).json()['id'] == new_sid
    assert client.post(route, headers=student, data={**form, 'request_id': str(uuid4())}, files=files).status_code == 409


def test_teaching_routes_deny_unrelated_teachers_and_other_students_feedback(assessed, platform):
    from test_accounts_courses import identity
    from persistence import CourseOffering
    values, _, _, _ = assessed
    client, factory, teacher, student, sid, _, assignment, content = values
    outsider = identity(client, platform[2], 'unrelated-teaching@example.com')
    peer = identity(client, platform[2], 'peer-teaching@example.com')
    for suffix in ('guide', 'summary'):
        assert client.get(f'/api/teaching/assignments/{assignment["id"]}/{suffix}', headers=outsider).status_code == 403
    route = '/api/teaching/submissions/' + sid + '/revision'
    assert client.get(route, headers=student).json() == {'revision': None}
    assert client.get(route, headers=outsider).status_code == 403
    with factory() as db: code = db.get(CourseOffering, assignment['offering_id']).class_code
    assert client.post('/api/enrollment/join', headers=peer, json={'class_code': code}).status_code == 201
    assert client.get(route, headers=peer).status_code == 403
    rid = confirmed(factory, assignment['id'], sid)
    revision = {'source_review_id': rid, 'criterion_keys': [[assignment['questions'][0]['id'], assignment['questions'][0]['criteria'][0]['criterion_id']]],
        'explanation': 'Attempt to refer to another student feedback.'}
    before = client.get('/api/assignment-submissions/' + assignment['id'], headers=teacher).json()['items']
    response = client.post('/academic/assignments/' + assignment['id'] + '/submissions', headers=peer,
        files={'file': ('revision.pdf', content, 'application/pdf')}, data={'revision_response': json.dumps(revision)})
    assert response.status_code == 404
    assert len(client.get('/api/assignment-submissions/' + assignment['id'], headers=teacher).json()['items']) == len(before)
