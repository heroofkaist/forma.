"""Course-private teacher tools. No inference, automatic scores or publication."""
import csv
import hashlib
import io
import json
from copy import deepcopy
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Query, Depends
from fastapi.responses import Response
from pydantic import Field, StrictInt
from sqlalchemy import select, update
from auth import request_user
from accounts import utc, rate_limit
from document_review import get_submission, published_feedback
from document_models import DocumentReview, SubmissionDocument, PublishedDocumentReview
from persistence import SessionLocal, AcademicAssignment, AcademicSubmission, AcademicGrade, CourseOffering
from permissions import require_teacher
from review_status import review_summaries
from student_identity import student_display_name
from review_pilot_models import ReviewDecisionCard, QuestionPageMap
from review_pilot_contracts import Strict, EvidenceAnchor

def private_response(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'

router = APIRouter(prefix='/api/review-pilot', tags=['Teacher review pilot'], dependencies=[Depends(private_response)])


class CardCreate(Strict):
    review_id: str = Field(min_length=1, max_length=36)
    question_id: str = Field(min_length=1, max_length=80)
    criterion_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    rule: str = Field(min_length=1, max_length=2000)
    kind: Literal['decision', 'reference'] = 'decision'
    evidence: EvidenceAnchor

class PageMapping(Strict):
    question_id: str = Field(min_length=1, max_length=80)
    pages: list[StrictInt] = Field(max_length=50)
    expected_mapping_id: str | None = Field(default=None, max_length=36)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def question(assignment, qid, questions=None):
    value = next((q for q in (questions if questions is not None else assignment.questions) if q['id'] == qid), None)
    if value is None: raise HTTPException(422, 'Question is not in the current rubric.')
    return value


def signature(assignment, qid, cid, questions=None):
    q = question(assignment, qid, questions)
    c = next((c for c in q['criteria'] if c['criterion_id'] == cid), None)
    if c is None: raise HTTPException(422, 'Criterion is not in the current rubric.')
    # IDs can differ on an explicitly reused assignment. The full criterion rule
    # and question context must still match; course and category remain scoped.
    return digest({'category': assignment.assignment_type, 'question': {k:v for k,v in q.items() if k not in ('id','criteria')},
                   'criterion': {k:v for k,v in c.items() if k not in ('id','criterion_id')}})


def page_signature(assignment, qid):
    return digest(question(assignment, qid))


def page_count(db, submission):
    source = db.get(SubmissionDocument, submission.id)
    return len(source.structure.get('pages', [])) if source and submission.file_type == 'pdf' else 0


def validate_anchor(db, submission, anchor):
    if anchor.page_number > page_count(db, submission):
        raise HTTPException(422, 'Evidence page is unavailable in this original PDF.')


def questions_for_spec(assignment, spec):
    questions = deepcopy(assignment.questions)
    lookup = {(c['question_id'], c['criterion_id']): c for c in spec['criteria']}
    for q in questions:
        for c in q['criteria']:
            approved = lookup[(q['id'], c['criterion_id'])]
            c.update(description=approved['description'], partial_credit=approved['performance_descriptions'], evidence_expected=approved['feedback_requirements'])
    return questions


def validate_use(db, submission, assignment, qid, cid, use, questions=None):
    if use is None: return
    card = db.get(ReviewDecisionCard, use.card_id)
    course_id = db.get(CourseOffering, assignment.offering_id).course_id
    if not card or card.course_id != course_id: raise HTTPException(404, 'Decision card not found in this course.')
    if card.signature != signature(assignment, qid, cid, questions): raise HTTPException(409, 'Decision card rubric has changed.')
    validate_anchor(db, submission, use.evidence)


def lock_assignment(db, assignment):
    if db.bind.dialect.name == 'sqlite':
        db.execute(update(AcademicAssignment).where(AcademicAssignment.id == assignment.id).values(maximum_score=AcademicAssignment.maximum_score))
    db.scalar(select(AcademicAssignment).where(AcademicAssignment.id == assignment.id).with_for_update())


def card_json(row):
    return {'id': row.id, **row.snapshot, 'created_by': row.created_by, 'created_at': utc(row.created_at)}


@router.get('/submissions/{sid}/cards')
def cards(sid: str, request: Request, question_id: str = Query(max_length=80), criterion_id: str = Query(max_length=80), rubric_id: str | None = Query(default=None, max_length=36)):
    with SessionLocal() as db:
        _, assignment = get_submission(db, sid, request, teacher=True)
        questions = None
        if rubric_id:
            from assessment_models import AssessmentRubric
            from services.assessment import rubric_for_assignment
            rubric = db.get(AssessmentRubric, rubric_id)
            if not rubric or rubric.assignment_id != assignment.id: raise HTTPException(404, 'Rubric not found in this assignment.')
            try: rubric_for_assignment(rubric.spec, assignment)
            except ValueError as error: raise HTTPException(409, 'Rubric changed; reload the current rubric.') from error
            questions = questions_for_spec(assignment, rubric.spec)
        key = signature(assignment, question_id, criterion_id, questions)
        course_id = db.get(CourseOffering, assignment.offering_id).course_id
        rows = db.scalars(select(ReviewDecisionCard).where(ReviewDecisionCard.course_id == course_id, ReviewDecisionCard.signature == key).order_by(ReviewDecisionCard.created_at.desc(), ReviewDecisionCard.id.desc()).limit(100)).all()
        return {'items': [card_json(row) for row in rows]}


@router.post('/submissions/{sid}/cards', status_code=201)
def save_card(sid: str, payload: CardCreate, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, sid, request, teacher=True)
        rate_limit(request, 'decision-card', request_user(request).username, 60)
        lock_assignment(db, assignment)
        review = db.get(DocumentReview, payload.review_id)
        if not review or review.submission_id != sid: raise HTTPException(404, 'Saved review not found.')
        signature(assignment, payload.question_id, payload.criterion_id)  # Validate current criterion identity.
        key = signature(assignment, payload.question_id, payload.criterion_id, review.rubric_snapshot)
        score = next((c for c in review.criteria if c['question_id'] == payload.question_id and c['criterion_id'] == payload.criterion_id), None)
        if not score or score.get('confirmed') is False or score.get('points') is None:
            raise HTTPException(409, 'Confirm this teacher decision before saving a card.')
        validate_anchor(db, submission, payload.evidence)
        snapshot = {**payload.model_dump(), 'criterion_version': key, 'source_submission_id': sid, 'source_hash': db.get(SubmissionDocument, sid).content_hash,
                    'feedback': score.get('comment', ''), 'points': score['points'], 'evidence_kind': 'teacher_observation'}
        dedup = digest(snapshot)
        row = db.scalar(select(ReviewDecisionCard).where(ReviewDecisionCard.dedup_key == dedup))
        if row is None:
            row = ReviewDecisionCard(course_id=db.get(CourseOffering, assignment.offering_id).course_id, source_review_id=review.id,
                                     signature=key, dedup_key=dedup, snapshot=snapshot, created_by=request_user(request).username)
            db.add(row); db.commit(); db.refresh(row)
        return card_json(row)


def latest_mapping(db, sid, qid):
    return db.scalar(select(QuestionPageMap).where(QuestionPageMap.submission_id == sid, QuestionPageMap.question_id == qid).order_by(QuestionPageMap.created_at.desc(), QuestionPageMap.id.desc()))


def mapping_json(row, assignment):
    return {'id': row.id, 'question_id': row.question_id, 'pages': row.pages if row.signature == page_signature(assignment, row.question_id) else [],
            'stale': row.signature != page_signature(assignment, row.question_id)}


@router.get('/submissions/{sid}/pages')
def mappings(sid: str, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, sid, request, teacher=True)
        rows = [latest_mapping(db, sid, q['id']) for q in assignment.questions]
        return {'page_count': page_count(db, submission), 'items': [mapping_json(row, assignment) for row in rows if row]}


@router.post('/submissions/{sid}/pages', status_code=201)
def map_pages(sid: str, payload: PageMapping, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, sid, request, teacher=True)
        key = page_signature(assignment, payload.question_id)
        if any(type(p) is not int or not 1 <= p <= page_count(db, submission) for p in payload.pages) or len(set(payload.pages)) != len(payload.pages):
            raise HTTPException(422, 'Select unique existing PDF pages.')
        if not page_count(db, submission): raise HTTPException(422, 'PDF pages are required for question mapping.')
        lock_assignment(db, assignment)
        old = latest_mapping(db, sid, payload.question_id)
        if payload.expected_mapping_id != (old.id if old else None): raise HTTPException(409, 'Page mapping changed; reload it before saving.')
        row = QuestionPageMap(submission_id=sid, question_id=payload.question_id, signature=key, pages=sorted(payload.pages), created_by=request_user(request).username)
        db.add(row); db.commit(); db.refresh(row)
        return mapping_json(row, assignment)


@router.get('/assignments/{aid}/question-queue')
def question_queue(aid: str, request: Request, question_id: str | None = Query(default=None, max_length=80)):
    with SessionLocal() as db:
        assignment = db.get(AcademicAssignment, aid)
        if not assignment: raise HTTPException(404, 'Assignment not found.')
        require_teacher(db, request_user(request), assignment.offering_id)
        if question_id is not None: question(assignment, question_id)
        rows = db.scalars(select(AcademicSubmission).where(AcademicSubmission.assignment_id == aid).order_by(AcademicSubmission.created_at.desc(), AcademicSubmission.id.desc())).all()
        latest = {}
        for row in rows: latest.setdefault(row.student_id, row)
        rows = sorted(latest.values(), key=lambda row: (row.student_name.casefold(), row.id))
        summaries = review_summaries(db, assignment, [row.id for row in rows])
        items = []
        for row in rows:
            mapping = latest_mapping(db, row.id, question_id) if question_id else None
            items.append({'id': row.id, 'student_name': student_display_name(db, row.student_id, row.student_name), 'file_name': row.file_name,
                          'file_type': row.file_type, 'page_count': page_count(db, row), 'mapping': mapping_json(mapping, assignment) if mapping else None, **summaries[row.id]})
        return {'title': assignment.title, 'questions': [{'id': q['id'], 'title': q['title']} for q in assignment.questions], 'items': items,
                'scope': 'Latest immutable attempt per student; pages are teacher-mapped, never inferred.'}


def safe_csv(value):
    text = str(value if value is not None else '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


@router.get('/assignments/{aid}/grades.csv')
def grade_export(aid: str, request: Request):
    with SessionLocal() as db:
        assignment = db.get(AcademicAssignment, aid)
        if not assignment: raise HTTPException(404, 'Assignment not found.')
        require_teacher(db, request_user(request), assignment.offering_id)
        output = io.StringIO(newline=''); writer = csv.writer(output)
        writer.writerow(['student_id', 'student_name', 'assignment', 'submission_id', 'review_id', 'points', 'maximum_score', 'published_at', 'feedback'])
        rows = db.execute(select(AcademicGrade, AcademicSubmission).join(AcademicSubmission, AcademicGrade.submission_id == AcademicSubmission.id).where(AcademicGrade.assignment_id == aid, AcademicGrade.published.is_(True)).order_by(AcademicGrade.published_at, AcademicGrade.id)).all()
        for grade, submission in rows:
            link = db.get(PublishedDocumentReview, grade.id)
            feedback = published_feedback(db, grade)
            writer.writerow([safe_csv(value) for value in (submission.student_id, student_display_name(db, submission.student_id, submission.student_name), assignment.title,
                             submission.id, link.review_id if link else '', grade.points, grade.maximum_score, utc(grade.published_at), feedback['feedback'])])
        return Response('\ufeff' + output.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="forma-grades-{aid}.csv"', 'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff'})
