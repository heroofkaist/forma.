"""Teacher-controlled calibration, triage and cohort learning summaries. GET is free."""
from collections import Counter
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from auth import request_user
from accounts import rate_limit
from institutions import audit
from persistence import SessionLocal, AcademicAssignment, AcademicSubmission
from permissions import require_teacher
from document_review import get_submission
from document_models import DocumentReview, PublishedDocumentReview
from assessment_models import AssessmentSuggestion
from processing_models import ProcessingJob
from teaching_models import TeachingGuide, RevisionResponse
from services.teaching_guidance import latest_guide, compatible_review, current_questions, rubric_key


def private(response: Response): response.headers['Cache-Control'] = 'private, no-store'
router = APIRouter(prefix='/api/teaching', tags=['Teaching workflow'], dependencies=[Depends(private)])

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Rule(Strict):
    question_id: str = Field(min_length=1, max_length=80)
    criterion_id: str = Field(min_length=1, max_length=80)
    instruction: str = Field(max_length=500)
class GuideRequest(Strict):
    expected_id: str | None = Field(default=None, max_length=36)
    reference_review_ids: list[str] = Field(default_factory=list, max_length=5)
    rules: list[Rule] = Field(default_factory=list, max_length=12)
    feedback_focus: str = Field(default='', max_length=400)


def assignment_access(db, aid, request):
    assignment = db.get(AcademicAssignment, aid)
    if not assignment: raise HTTPException(404, 'Assignment not found.')
    require_teacher(db, request_user(request), assignment.offering_id)
    return assignment


def latest_attempts(db, aid):
    rows = db.scalars(select(AcademicSubmission).where(AcademicSubmission.assignment_id == aid)
        .order_by(AcademicSubmission.created_at.desc(), AcademicSubmission.id.desc())).all()
    latest = {}
    for row in rows: latest.setdefault(row.student_id, row)
    return list(latest.values())


def current_review(db, sid):
    return db.scalar(select(DocumentReview).where(DocumentReview.submission_id == sid)
        .order_by(DocumentReview.created_at.desc(), DocumentReview.id.desc()).limit(1))


@router.get('/assignments/{aid}/guide')
def get_guide(aid: str, request: Request):
    with SessionLocal() as db:
        assignment = assignment_access(db, aid, request)
        guide = latest_guide(db, aid)
        candidates = []
        for submission in latest_attempts(db, aid):
            review = current_review(db, submission.id)
            if not compatible_review(db, review, assignment): continue
            ai = db.scalar(select(AssessmentSuggestion).where(AssessmentSuggestion.submission_id == submission.id, AssessmentSuggestion.created_at <= review.created_at)
                .order_by(AssessmentSuggestion.created_at.desc()).limit(1))
            from assessment_models import AssessmentRubric
            approved = db.scalar(select(AssessmentRubric).where(AssessmentRubric.assignment_id == aid).order_by(AssessmentRubric.created_at.desc(), AssessmentRubric.id.desc()).limit(1))
            scores = {(c['question_id'], c['criterion_id']): c.get('proposed_score') for c in ai.result['criteria']} if ai and approved and ai.rubric_id == approved.id else {}
            candidates.append({'review_id': review.id, 'submission_id': submission.id, 'file_name': submission.file_name,
                'criteria': [{**c, 'ai_score': scores.get((c['question_id'], c['criterion_id']))} for c in review.criteria]})
        return {'id': guide.id if guide else None, 'content': {k: v for k, v in guide.content.items() if k != 'rubric_key'} if guide else {'rules': [], 'reference_review_ids': [], 'feedback_focus': ''},
            'questions': current_questions(db, assignment), 'examples': candidates[:100], 'stale': bool(guide and guide.content.get('rubric_key') != rubric_key(db, assignment))}


@router.post('/assignments/{aid}/guide', status_code=201)
def save_guide(aid: str, payload: GuideRequest, request: Request):
    from review_pilot import lock_assignment
    with SessionLocal() as db:
        assignment = assignment_access(db, aid, request)
        rate_limit(request, 'teaching-guide', request_user(request).username, 20)
        lock_assignment(db, assignment)
        old = latest_guide(db, aid)
        if payload.expected_id != (old.id if old else None): raise HTTPException(409, 'Teaching guide changed. Reload before saving.')
        keys = {(q['id'], c['criterion_id']) for q in assignment.questions for c in q['criteria']}
        selected = [(r.question_id, r.criterion_id) for r in payload.rules]
        if len(selected) != len(set(selected)) or not set(selected) <= keys: raise HTTPException(422, 'Use current criteria once per teaching rule.')
        if len(set(payload.reference_review_ids)) != len(payload.reference_review_ids): raise HTTPException(422, 'Choose distinct reference reviews.')
        for rid in payload.reference_review_ids:
            review = db.get(DocumentReview, rid)
            submission = db.get(AcademicSubmission, review.submission_id) if review else None
            if not submission or submission.assignment_id != aid: raise HTTPException(404, 'Reference review not found in this assignment.')
            if not compatible_review(db, review, assignment): raise HTTPException(409, 'Only confirmed current reviews can be reference examples.')
        content = {**payload.model_dump(exclude={'expected_id'}), 'rubric_key': rubric_key(db, assignment)}
        row = TeachingGuide(assignment_id=aid, content=content, created_by=request_user(request).username)
        db.add(row); db.flush(); audit(db, request_user(request), 'teaching.guide.save', row.id, {'assignment_id': aid})
        db.commit(); return {'id': row.id, 'content': {k: v for k, v in content.items() if k != 'rubric_key'}}


def attention_for(db, sid):
    submission = db.get(AcademicSubmission, sid)
    assignment = db.get(AcademicAssignment, submission.assignment_id)
    review = current_review(db, sid)
    if compatible_review(db, review, assignment):
        return {'kind': 'reviewed', 'label': 'Баллы подтверждены преподавателем', 'count': 0}
    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.submission_id == sid).order_by(ProcessingJob.created_at.desc())).all()
    job = next((j for j in jobs if j.context.get('task') == 'assessment'), None)
    if job and job.status in {'queued', 'awaiting_source', 'extracting', 'interpreting'}:
        return {'kind': 'working', 'label': 'ИИ проверяет работу', 'count': 0}
    if job and job.status in {'failed', 'awaiting_budget'}:
        return {'kind': 'processing', 'label': 'Проверка ИИ требует внимания', 'count': 1}
    reading = next((j for j in jobs if j.context.get('task') not in {'assessment', 'integrity'}), None)
    if not job and reading:
        if reading.status in {'failed', 'awaiting_budget'}:
            return {'kind': 'processing', 'label': 'Распознавание требует внимания', 'count': 1}
        if reading.status in {'queued', 'extracting', 'interpreting'}:
            return {'kind': 'working', 'label': 'Распознаётся документ', 'count': 0}
        if reading.usage.get('partial'):
            return {'kind': 'evidence', 'label': 'Распознаны не все страницы', 'count': 1}
    if review and not compatible_review(db, review, assignment):
        return {'kind': 'draft', 'label': 'Завершите черновик проверки', 'count': sum(c.get('points') is None or c.get('confirmed') is False for c in review.criteria) or 1}
    ai = db.scalar(select(AssessmentSuggestion).where(AssessmentSuggestion.submission_id == sid).order_by(AssessmentSuggestion.created_at.desc()).limit(1))
    if ai:
        from assessment_models import AssessmentRubric
        from processing_models import DocumentInterpretation
        from services.assessment_pipeline import snapshot
        approved = db.scalar(select(AssessmentRubric).where(AssessmentRubric.assignment_id == assignment.id)
            .order_by(AssessmentRubric.created_at.desc(), AssessmentRubric.id.desc()).limit(1))
        source = db.scalar(select(DocumentInterpretation).where(DocumentInterpretation.submission_id == sid)
            .order_by(DocumentInterpretation.created_at.desc()).limit(1))
        prior = db.get(ProcessingJob, ai.job_id)
        old = {k: v for k, v in prior.context.get('assessment', {}).items() if k not in {'target_criteria', 'reuse_criteria', 'base_suggestion_id'}}
        try: fresh = bool(approved and source and old == snapshot(db, submission, assignment, approved, source))
        except ValueError: fresh = False
        if not fresh: return {'kind': 'outdated', 'label': 'Условия или распознавание изменились после оценки ИИ', 'count': 1}
        missing = [c for c in ai.result['criteria'] if c.get('proposed_score') is None]
        if missing:
            first = missing[0]
            return {'kind': 'evidence', 'label': 'Есть критерии без балла ИИ', 'count': len(missing),
                'question_id': first['question_id'], 'criterion_id': first['criterion_id']}
        return {'kind': 'ready', 'label': 'Оценка ИИ готова к вашей проверке', 'count': 0}
    return {'kind': 'not_started', 'label': 'Можно запустить оценивание', 'count': 0}


@router.get('/assignments/{aid}/summary')
def cohort_summary(aid: str, request: Request):
    with SessionLocal() as db:
        assignment = assignment_access(db, aid, request)
        submissions = latest_attempts(db, aid)
        reviews = [(s, current_review(db, s.id)) for s in submissions]
        reviewed = [(s, r) for s, r in reviews if compatible_review(db, r, assignment)]
        criteria = []
        for q in current_questions(db, assignment):
            for c in q['criteria']:
                observations, comments = [], Counter()
                examples = []
                for submission, review in reviewed:
                    result = next(v for v in review.criteria if (v['question_id'], v['criterion_id']) == (q['id'], c['criterion_id']))
                    observations.append(result['points'])
                    if result['points'] < c['maximum_points']:
                        text = ' '.join(result.get('comment', '').split())[:350]
                        if text: comments[text] += 1
                        examples.append({'submission_id': submission.id, 'points': result['points']})
                criteria.append({'question_id': q['id'], 'criterion_id': c['criterion_id'], 'description': c['description'],
                    'maximum_points': c['maximum_points'], 'reviewed': len(observations),
                    'below_full_credit': sum(p < c['maximum_points'] for p in observations),
                    'average': round(sum(observations)/len(observations), 2) if observations else None,
                    'common_comments': [{'text': text, 'count': count} for text, count in comments.most_common(3) if count > 1], 'examples': examples[:5]})
        return {'reviewed': len(reviewed), 'submitted': len(submissions), 'criteria': criteria,
            'scope': 'Только последние попытки студентов с полностью подтверждённой проверкой. Недобор баллов сам по себе не определяет причину ошибки.'}


class RevisionDraft(Strict):
    source_review_id: str = Field(min_length=1, max_length=36)
    criterion_keys: list[tuple[str, str]] = Field(min_length=1, max_length=12)
    explanation: str = Field(min_length=5, max_length=2000)


def validate_revision(db, assignment, student_id, payload):
    review = db.get(DocumentReview, payload.source_review_id)
    source = db.get(AcademicSubmission, review.submission_id) if review else None
    if not source or source.student_id != student_id or source.assignment_id != assignment.id:
        raise HTTPException(404, 'Published feedback not found for this student.')
    published = db.scalar(select(PublishedDocumentReview).where(PublishedDocumentReview.review_id == review.id))
    from persistence import AcademicGrade
    grade = db.get(AcademicGrade, published.grade_id) if published else None
    if not published or not grade or not grade.published: raise HTTPException(409, 'Revision must refer to published feedback.')
    allowed = {(c['question_id'], c['criterion_id']) for c in review.criteria}
    if len(set(payload.criterion_keys)) != len(payload.criterion_keys) or not set(payload.criterion_keys) <= allowed:
        raise HTTPException(422, 'Select criteria from the published review.')
    return review


@router.get('/submissions/{sid}/revision')
def revision_context(sid: str, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, sid, request)
        row = db.get(RevisionResponse, sid)
        if not row: return {'revision': None}
        review = db.get(DocumentReview, row.source_review_id)
        original = db.get(AcademicSubmission, review.submission_id)
        from document_models import SubmissionDocument
        before, after = db.get(SubmissionDocument, original.id), db.get(SubmissionDocument, sid)
        import difflib
        # Compare bounded extracted text; no image/OCR equivalence claim.
        diff = list(difflib.unified_diff((before.structure.get('extracted_text', '')[:20000] if before else '').splitlines(),
            (after.structure.get('extracted_text', '')[:20000] if after else '').splitlines(), lineterm='', n=2))[:250]
        return {'revision': {'source_review_id': review.id, 'source_submission_id': original.id, **row.content,
            'source_feedback': review.feedback, 'source_criteria': [{k: c.get(k) for k in ('question_id', 'criterion_id', 'points', 'comment')} for c in review.criteria],
            'text_diff': '\n'.join(diff), 'text_comparison_available': bool(before and after and before.structure.get('extracted_text') and after.structure.get('extracted_text'))}}
