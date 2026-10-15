"""Production QA regressions using isolated synthetic records; no inference or publication."""
from datetime import timedelta
from uuid import uuid4
import copy
import pytest
from sqlalchemy import select, inspect, func, delete
from test_accounts_courses import platform, identity
from test_document_processing import setup_submission
from test_assessment import assessed
import academic_api
import document_processing
from persistence import (AcademicSubmission, AcademicAssignment, AcademicGrade, OriginalityAnalysis,
                         OriginalityReport, CourseEnrollment, Assignment, now_utc)
from document_models import DocumentReview, PublishedDocumentReview
from processing_models import ProcessingJob
from account_models import EnrollmentState
from assessment_models import AssessmentRubric
from migrations import apply_migrations

TEXT = 'one two three four five six seven eight nine ten eleven twelve'
OTHER = 'alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu'


def add_submission(db, aid, student, text):
    row = AcademicSubmission(assignment_id=aid, student_id=student, student_name='Synthetic author',
        file_path='unused.pdf', file_name='synthetic.pdf', file_type='pdf', extracted_text=text)
    db.add(row); db.flush()
    return row


def test_similarity_receipts_missing_zero_positive_incomplete_and_access(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    path = '/academic/submissions/' + sid + '/originality'
    assert client.get(path, headers=teacher).json()['analysis']['analysis_status'] == 'missing'
    with factory() as db:
        source = db.get(AcademicSubmission, sid); source.extracted_text = TEXT
        candidate = add_submission(db, assignment['id'], 'another-synthetic-author', OTHER)
        assert academic_api._compare_submission(db, source) == []
        db.commit()
    data = client.get(path, headers=teacher).json()
    assert data['items'] == [] and data['analysis']['analysis_status'] == 'completed'
    assert data['analysis']['match_ratio'] == 0 and data['analysis']['candidate_count'] == 1
    with factory() as db:
        positive = add_submission(db, assignment['id'], 'third-synthetic-author', TEXT)
        reports = academic_api._compare_submission(db, positive)
        assert len(reports) == 1
        pid, rid = positive.id, reports[0].id
        db.commit()
    positive_path = '/academic/submissions/' + pid + '/originality'
    body = client.get(positive_path, headers=teacher).json()
    report = body['items'][0]
    assert body['analysis']['analysis_status'] == report['analysis_status'] == 'completed'
    assert report['match_ratio'] == 1 and report['candidate_submission_id'] == sid
    e = report['evidence'][0]
    assert TEXT[e['source_offsets']['start']:e['source_offsets']['end']] == e['source_excerpt']
    assert client.patch('/academic/reports/' + rid + '/review', headers=teacher,
        json={'review_status':'follow_up', 'teacher_notes':'Check quotation context.'}).status_code == 200
    with factory() as db:
        db.get(OriginalityReport, rid).eligible_token_count = 0; db.commit()
    incomplete = client.get(positive_path, headers=teacher).json()
    assert incomplete['analysis']['analysis_status'] == 'incomplete'
    assert incomplete['analysis']['match_ratio'] is None
    assert client.patch('/academic/reports/' + rid + '/review', headers=teacher,
        json={'review_status':'reviewed'}).status_code == 409
    with factory() as db:
        # A missing pair row must not turn a previously positive run into zero.
        db.execute(delete(OriginalityReport).where(OriginalityReport.id == rid)); db.commit()
    missing_pair = client.get(positive_path, headers=teacher).json()['analysis']
    assert missing_pair['analysis_status'] == 'incomplete' and missing_pair['match_ratio'] is None
    outsider = identity(client, platform[2], 'qa-outsider@example.test')
    for denied in (student, outsider):
        assert client.get(positive_path, headers=denied).status_code == 403
        assert client.patch('/academic/reports/' + rid + '/review', headers=denied, json={'review_status':'reviewed'}).status_code == 403
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 0
        assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0


@pytest.mark.parametrize('state', ['queued', 'analyzing', 'failed', 'insufficient_text', 'no_sources', 'disabled', 'incomplete'])
def test_similarity_noncompleted_contract_never_has_percentage(platform, monkeypatch, state):
    client, factory, teacher, _, sid, _, _, _ = setup_submission(platform, monkeypatch)
    with factory() as db:
        db.add(OriginalityAnalysis(submission_id=sid, status=state, scope='family', eligible_token_count=0, candidate_count=0))
        db.commit()
    result = client.get('/academic/submissions/' + sid + '/originality', headers=teacher).json()
    assert result['analysis']['analysis_status'] == state
    assert result['analysis']['match_ratio'] is None


def test_similarity_actual_short_no_source_failure_unicode_and_migration(platform, monkeypatch):
    client, factory, teacher, _, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    with factory() as db:
        source = db.get(AcademicSubmission, sid); source.extracted_text = 'short text'
        academic_api._compare_submission(db, source)
        assert db.get(OriginalityAnalysis, sid).status == 'insufficient_text'
        no_sources = add_submission(db, assignment['id'], source.student_id, TEXT)
        academic_api._compare_submission(db, no_sources)
        assert db.get(OriginalityAnalysis, no_sources.id).status == 'no_sources'  # Same author excluded.
        failed = add_submission(db, assignment['id'], 'other', TEXT)
        monkeypatch.setattr(academic_api, '_compare_submission_pairs', lambda *_: (_ for _ in ()).throw(RuntimeError('private input')))
        assert academic_api._compare_submission(db, failed) == []
        assert db.get(OriginalityAnalysis, failed.id).status == 'failed'
        db.commit()
    text = '😀 Straße один два три четыре пять шесть семь восемь девять'
    matched, eligible, evidence = academic_api._match_evidence(text, text)
    assert matched == eligible >= 8
    for e in evidence:
        assert text[e['source_offsets']['start']:e['source_offsets']['end']] == e['source_excerpt']
    # A fresh/previously migrated database can apply the additive receipt version twice.
    apply_migrations(factory.kw['bind']); apply_migrations(factory.kw['bind'])
    assert 'academic_originality_analyses' in inspect(factory.kw['bind']).get_table_names()


def test_human_state_dominates_ai_matrix_and_counters_without_publication(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    expected = {}
    with factory() as db:
        a = db.get(AcademicAssignment, assignment['id'])
        original = db.get(AcademicSubmission, sid); student_id = original.student_id
        for human in ['unreviewed', 'draft', 'confirmed', 'published']:
            for ai in [None, 'failed', 'completed']:
                sub = add_submission(db, a.id, student_id, TEXT)
                expected[sub.id] = human
                if ai:
                    db.add(ProcessingJob(submission_id=sub.id, requested_by='synthetic', input_hash=str(uuid4()),
                        content_hash='synthetic', model='mocked', prompt_version='test', context={}, status=ai, error='private failure' if ai == 'failed' else ''))
                if human != 'unreviewed':
                    scores = [{'question_id':q['id'], 'criterion_id':c['criterion_id'], 'points':0,
                               'comment':'Teacher zero', 'confirmed':human != 'draft'} for q in a.questions for c in q['criteria']]
                    review = DocumentReview(submission_id=sub.id, reviewer='synthetic teacher', criteria=scores, rubric_snapshot=a.questions)
                    db.add(review); db.flush()
                    if human == 'published':
                        grade = AcademicGrade(assignment_id=a.id, submission_id=sub.id, points=0, maximum_score=10, published=True, published_at=now_utc())
                        db.add(grade); db.flush(); db.add(PublishedDocumentReview(grade_id=grade.id, review_id=review.id))
                    if human in ['confirmed', 'published']:
                        # A later draft cannot erase the authoritative human result.
                        draft_scores = copy.deepcopy(scores); draft_scores[0]['confirmed'] = False
                        db.add(DocumentReview(submission_id=sub.id, reviewer='synthetic teacher', criteria=draft_scores,
                            rubric_snapshot=a.questions, created_at=now_utc()+timedelta(seconds=1)))
        db.commit()
    listing = client.get('/api/assignment-submissions/' + assignment['id'], headers=teacher).json()['items']
    for item in listing:
        if item['id'] == sid: continue
        assert item['review_status'] == expected[item['id']]
        if item['review_status'] in ['confirmed', 'published']:
            assert item['review_points'] == 0 and item['has_draft']
    summary = client.get('/assignments/' + assignment['legacy_assignment_id'], headers=teacher).json()
    assert summary['reviewed_count'] == 6 and summary['submission_count'] == 13
    queue = client.get('/api/teacher-overview', headers=teacher).json()['review_queue']
    assert all(expected.get(item['id']) != 'published' for item in queue)
    grades = client.get('/academic/student/grades', headers=student).json()['items']
    assert len(grades) == 3 and all(g['points'] == 0 for g in grades)
    assert client.get('/api/assignment-submissions/' + assignment['id'], headers=student).status_code == 403


def test_active_enrollment_count_and_archive_human_identity(platform, monkeypatch):
    client, factory, teacher, student, sid, _, assignment, _ = setup_submission(platform, monkeypatch)
    with factory() as db:
        for status in ['pending', 'suspended', 'removed']:
            enrollment = CourseEnrollment(offering_id=assignment['offering_id'], student_id='synthetic-' + status, student_name=status)
            db.add(enrollment); db.flush(); db.add(EnrollmentState(enrollment_id=enrollment.id, status=status))
        source = db.get(AcademicSubmission, sid)
        source.student_name = source.student_id
        db.commit()
    course = client.get('/academic/offerings/' + assignment['offering_id'], headers=teacher).json()
    assert course['enrollment_count'] == 1
    summaries = client.get('/academic/courses?role=teacher', headers=teacher).json()['items']
    assert next(o for c in summaries for o in c['offerings'] if o['id'] == assignment['offering_id'])['enrollment_count'] == 1
    archive = client.get('/academic/teacher/assignments/' + assignment['id'] + '/archive', headers=teacher).json()['items']
    assert archive[0]['student_name'] == 'student' and archive[0]['submission_id'] == sid
    assert archive[0]['student_name'] != archive[0]['student_id']
    assert client.get('/academic/teacher/assignments/' + assignment['id'] + '/archive', headers=student).status_code == 403


def test_insights_distinct_denominator_latest_decisions_and_no_ai_only(assessed):
    values, path, _, spec = assessed
    client, factory, teacher, student, sid, *_ = values
    assert client.post(path, headers=teacher, json={}).status_code == 202
    assert document_processing.process_one()  # Mocked evaluator from assessed fixture.
    suggestion = client.get(path, headers=teacher).json()['items'][0]
    assert client.get(path + '/insights', headers=teacher).json()['items'] == []
    decisions = [{'question_id':c['question_id'], 'criterion_id':c['criterion_id'], 'action':'accepted',
        'points':1, 'feedback':'Human', 'finding':'strength' if i == 0 else 'concern'} for i,c in enumerate(spec['criteria'])]
    def save(draft=False):
        response = client.post(path + '/decisions', headers=teacher, json={'suggestion_id':suggestion['id'], 'decisions':decisions, 'draft':draft})
        assert response.status_code == 201, response.text
    save()
    result = client.get(path + '/insights', headers=teacher).json()['items']
    assert len(result) == 2 and all(i['reviewed_submissions'] == 1 for i in result)
    assert sum(i['confirmed_concerns'] for i in result) == 1
    assert next(i for i in result if i['confirmed_concerns'])['evidence'][0]['submission_id'] == sid
    decisions[1].update(action='rejected', points=None)
    save(draft=True)
    assert client.get(path + '/insights', headers=teacher).json()['items'] == result
    save()
    result = client.get(path + '/insights', headers=teacher).json()['items']
    assert len(result) == 1 and result[0]['reviewed_submissions'] == 1 and result[0]['confirmed_concerns'] == 0
    assert client.get(path + '/insights', headers=student).status_code == 403
    with factory() as db: assert db.scalar(select(func.count()).select_from(AcademicGrade)) == 0
