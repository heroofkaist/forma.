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
