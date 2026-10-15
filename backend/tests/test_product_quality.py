"""Synthetic regressions for production identity, counting and student diagnostics."""
from sqlalchemy import select
from test_accounts_courses import platform
from test_document_processing import setup_submission
from persistence import AcademicSubmission, AcademicAssignment, Submission, Assignment, Answer
from account_models import Account
from processing_models import ProcessingJob
import document_review
import analysis_api


def test_authorized_identity_repairs_historical_uuid_on_read(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, content = setup_submission(platform, monkeypatch)
    monkeypatch.setattr(document_review, 'SessionLocal', factory)
    with factory() as db:
        row = db.get(AcademicSubmission, sid)
        row.student_name = row.student_id  # Existing bad mapping, no data migration needed.
        db.get(Account, row.student_id).display_name = 'Анна Ким'
        db.commit()
    assert client.get('/api/document-review/' + sid, headers=teacher).json()['student_name'] == 'Анна Ким'
    aid = client.get('/api/document-review/' + sid, headers=teacher).json()['assignment_id']
    assert client.get('/api/assignment-submissions/' + aid, headers=teacher).json()['items'][0]['student_name'] == 'Анна Ким'
    assert client.get('/api/teacher-overview', headers=teacher).json()['review_queue'][0]['student_name'] == 'Анна Ким'
    assert client.get('/api/document-review/' + sid, headers=student).status_code == 403
    # Fix future persistence as well, using the authenticated account, never upload data.
    from academic_api import _student_identity
    from auth import AuthUser
    monkeypatch.setattr('academic_api.request_user',lambda _:AuthUser('student','student@example.com',row.student_id,row.student_id))
    assert _student_identity(None) == (row.student_id, 'Анна Ким')
    with factory() as db:
        db.get(AcademicAssignment, assignment['id']).allow_resubmission = True; db.commit()
    response = client.post('/academic/assignments/' + assignment['id'] + '/submissions', headers=student,
                           files={'file': ('synthetic.pdf', content, 'application/pdf')})
    assert response.status_code == 201, response.text
    with factory() as db:
        new = db.get(AcademicSubmission, response.json()['id'])
        assert new.student_name == 'Анна Ким'
        legacy = db.get(Submission, new.legacy_submission_id)
        assert legacy.anonymous_student_id == 'Student ' + row.student_id[:8]
        assert legacy.student_name == legacy.anonymous_student_id



def test_student_progress_excludes_provider_and_budget_diagnostics(platform, monkeypatch):
    client, factory, teacher, student, sid, *_ = setup_submission(platform, monkeypatch)
    monkeypatch.setattr(analysis_api, 'SessionLocal', factory)
    client.post('/api/document-analysis/' + sid, headers=teacher, json={})
    with factory() as db:
        job=db.scalar(select(ProcessingJob));job.status='awaiting_budget';job.error='Ollama OpenRouter backend monthly budget';db.commit()
    student_data=client.get('/api/document-analysis/' + sid + '/status',headers=student).json()
    assert set(student_data['jobs'][0]) == {'id','status','error'}
    assert 'Ollama' not in str(student_data) and 'backend' not in str(student_data)
    assert 'monthly budget' not in str(student_data)
    teacher_data=client.get('/api/document-analysis/' + sid + '/status',headers=teacher).json()
    assert teacher_data['jobs'][0]['error'] == 'Ollama OpenRouter backend monthly budget'


def test_review_counter_counts_complete_distinct_submissions_not_answers(platform):
    _,factory,_=platform
    from assignment_api import _assignment_json
    with factory() as db:
        a=Assignment(title='Synthetic',questions=[{'id':'q1'},{'id':'q2'}]);db.add(a);db.flush()
        sub=Submission(assignment_id=a.id,student_name='Student 01',source_path='unused',page_count=1);db.add(sub);db.flush()
        answers=[Answer(assignment_id=a.id,submission_id=sub.id,question_id=q,anonymous_student_id='Student 01',crop_path='unused',page_index=0,review_status='reviewed',human_score=1) for q in ['q1','q2']]
        db.add_all(answers);db.flush()
        assert _assignment_json(db,a)['reviewed_count']==1
        answers[0].human_score=None;db.flush()
        assert _assignment_json(db,a)['reviewed_count']==0  # AI or incomplete draft isn't confirmation.
        answers[0].human_score=0;db.flush()
        result=_assignment_json(db,a)
        assert result['reviewed_count']==result['submission_count']==1
        assert result['answer_count']==2
        assert answers[0].anonymous_student_id=='Student 01'


def test_academic_review_routes_share_submission_identity_and_count(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    legacy_id = assignment['legacy_assignment_id']
    for _ in range(2):  # Direct entry and refresh resolve the same canonical assignment.
        legacy = client.get('/assignments/' + legacy_id, headers=teacher).json()
        course = client.get('/academic/offerings/' + assignment['offering_id'], headers=teacher).json()
        item = next(a for a in course['assignments'] if a['id'] == legacy['academic_assignment_id'])
        submissions = client.get('/api/assignment-submissions/' + item['id'], headers=teacher).json()
        assert legacy['academic_assignment_id'] == assignment['id']
        assert legacy['submission_count'] == item['submission_count'] == len(submissions['items']) == 1
        assert submissions['items'][0]['id'] == sid
    assert client.get('/assignments/' + legacy_id, headers=student).status_code == 403
    from test_accounts_courses import identity
    outsider = identity(client, platform[2], 'outside-audit@example.com')
    assert client.get('/assignments/' + legacy_id, headers=outsider).status_code == 403
    assert client.get('/api/assignment-submissions/' + assignment['id'], headers=outsider).status_code == 403
    with factory() as db:
        standalone = Assignment(title='Separate scan workflow', questions=[])
        db.add(standalone); db.flush()
        from assignment_api import _assignment_json
        assert _assignment_json(db, standalone)['academic_assignment_id'] is None


def test_published_result_is_shared_and_uses_historical_rubric_despite_failed_ai(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    from document_models import DocumentReview
    path = '/api/document-review/' + sid
    scores = [{'question_id': q['id'], 'criterion_id': c['criterion_id'], 'points': 0,
               'comment': 'Human feedback'} for q in assignment['questions'] for c in q['criteria']]
    saved = client.post(path, headers=teacher, json={'criteria': scores, 'feedback': 'Published human feedback'})
    assert saved.status_code == 201
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []
    assert client.post(path + '/publish', headers=teacher, json={'review_id': saved.json()['id']}).status_code == 200
    with factory() as db:
        # Simulate an existing failed analysis. No inference is requested.
        from processing_models import ProcessingJob
        job = ProcessingJob(submission_id=sid, requested_by='Synthetic teacher', input_hash='audit-failed',
            content_hash='synthetic', model='not-invoked', prompt_version='synthetic', context={},
            status='failed', error='Private upstream failure')
        db.add(job)
        current = db.get(AcademicAssignment, assignment['id'])
        changed = __import__('copy').deepcopy(current.questions)
        changed[0]['criteria'][0]['description'] = 'Changed after publication'
        changed[0]['criteria'][0]['maximum_points'] = 1
        current.questions = changed
        db.commit()
        frozen = db.get(DocumentReview, saved.json()['id']).rubric_snapshot
    draft_scores = [{**score, 'points': None, 'comment': 'Unpublished draft'} for score in scores]
    assert client.post(path, headers=teacher, json={'criteria': draft_scores, 'draft': True,
        'feedback': 'Unpublished feedback'}).status_code == 201
    legacy = client.get('/assignments/' + assignment['legacy_assignment_id'], headers=teacher).json()
    assert legacy['reviewed_count'] == 1  # A working draft does not erase confirmed history.
    grades = client.get('/academic/student/grades', headers=student).json()['items']
    assignments = client.get('/academic/student/assignments', headers=student).json()['items']
    result = next(a for a in assignments if a['id'] == assignment['id'])['published_grade']
    assert result == grades[0]
    assert result['points'] == 0 and result['maximum_score'] == 10
    assert result['feedback'] == 'Published human feedback'
    assert result['criteria'][0]['description'] == frozen[0]['criteria'][0]['description']
    assert result['criteria'][0]['maximum_points'] == frozen[0]['criteria'][0]['maximum_points']
    assert 'Changed after publication' not in str(result) and 'Private upstream' not in str(result)
    # Another student's account cannot read this published result.
    from test_accounts_courses import identity
    outsider = identity(client, platform[2], 'other-student-audit@example.com')
    assert client.get('/academic/student/grades', headers=outsider).json()['items'] == []
    with factory() as db:
        from persistence import AcademicGrade
        db.scalar(select(AcademicGrade)).published = False
        db.commit()
    assert client.get('/academic/student/grades', headers=student).json()['items'] == []
    assert next(a for a in client.get('/academic/student/assignments', headers=student).json()['items']
                if a['id'] == assignment['id'])['published_grade'] is None


def test_historical_feedback_without_criterion_description_gets_neutral_label(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    from document_models import DocumentReview, PublishedDocumentReview
    from persistence import AcademicGrade
    with factory() as db:
        review = DocumentReview(submission_id=sid, reviewer='Synthetic teacher', rubric_snapshot=[],
            criteria=[{'question_id': 'q1', 'criterion_id': 'q1-overall', 'points': 0, 'comment': 'Historical'}])
        db.add(review); db.flush()
        grade = AcademicGrade(assignment_id=assignment['id'], submission_id=sid, points=0, maximum_score=10, published=True)
        db.add(grade); db.flush()
        db.add(PublishedDocumentReview(grade_id=grade.id, review_id=review.id)); db.commit()
    result = client.get('/academic/student/grades', headers=student).json()['items'][0]
    assert result['criteria'][0]['description'] == 'Критерий 1'
    assert result['criteria'][0]['maximum_points'] is None
    assert result['criteria'][0]['comment'] == 'Historical'
