"""Teacher document review with immutable versions and explicit publication."""
from fastapi import APIRouter, HTTPException, Request, Response
import pymupdf
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from auth import request_user
from accounts import utc
from document_models import DocumentReview, PublishedDocumentReview, SubmissionDocument
from materials import access, MIMES
from permissions import require_teacher
from student_identity import student_display_name
from review_status import review_summaries
from persistence import AcademicAssignment, AcademicGrade, AcademicSubmission, SessionLocal, now_utc, read_blob
from review_pilot_contracts import CardUse

router = APIRouter(prefix="/api", tags=["Document review"])

class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=80)
    criterion_id: str = Field(min_length=1, max_length=80)
    points: float | None = Field(ge=0, le=10000, allow_inf_nan=False)
    comment: str = Field(default="", max_length=4000)
    card_use: CardUse | None = None

class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criteria: list[CriterionScore] = Field(min_length=1, max_length=1000)
    feedback: str = Field(default="", max_length=10000)
    draft: bool = False

class PublishPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=1, max_length=36)
    expected_published_review_id: str | None = Field(default=None, max_length=36)


def get_submission(db, submission_id, request, teacher=False):
    submission = db.get(AcademicSubmission, submission_id)
    assignment = db.get(AcademicAssignment, submission.assignment_id) if submission else None
    if not assignment:
        raise HTTPException(404, "Submission not found.")
    if teacher:
        require_teacher(db, request_user(request), assignment.offering_id)
    else:
        role = access(db, request, assignment.offering_id)
        if role == "student" and submission.student_id != request_user(request).student_id:
            raise HTTPException(403, "This submission belongs to another student.")
    return submission, assignment


def review_json(review):
    return {"id": review.id, "criteria": review.criteria, "feedback": review.feedback, "created_at": utc(review.created_at), "reviewer": review.reviewer}


@router.get("/assignment-submissions/{assignment_id}")
def list_submissions(assignment_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    with SessionLocal() as db:
        assignment = db.get(AcademicAssignment, assignment_id)
        if not assignment:
            raise HTTPException(404, "Assignment not found.")
        require_teacher(db, request_user(request), assignment.offering_id)
        rows = db.scalars(select(AcademicSubmission).where(AcademicSubmission.assignment_id == assignment_id).order_by(AcademicSubmission.created_at.desc(), AcademicSubmission.id.desc())).all()
        from processing_models import ProcessingJob
        jobs = db.scalars(select(ProcessingJob).join(AcademicSubmission, ProcessingJob.submission_id == AcademicSubmission.id).where(AcademicSubmission.assignment_id == assignment_id).order_by(ProcessingJob.created_at.desc())).all()
        latest = {}
        for job in jobs:
            if job.context.get('task') != 'integrity': latest.setdefault(job.submission_id, job)
        summaries = review_summaries(db, assignment, [row.id for row in rows])
        from similarity_status import similarity_summaries
        from persistence import CourseEnrollment, AcademicCourse, CourseOffering
        from permissions import enrollment_active
        similarities = similarity_summaries(db, rows)
        from document_integrity import summaries as integrity_summaries
        integrity = integrity_summaries(db, [row.id for row in rows])
        offering = db.get(CourseOffering, assignment.offering_id)
        course = db.get(AcademicCourse, offering.course_id)
        roster = {e.student_id: {'student_id': e.student_id, 'student_name': student_display_name(db, e.student_id, e.student_name), 'active': True}
                  for e in db.scalars(select(CourseEnrollment).where(CourseEnrollment.offering_id == offering.id)) if enrollment_active(db, e)}
        items = []
        for row in rows:
            roster.setdefault(row.student_id, {'student_id': row.student_id, 'student_name': student_display_name(db, row.student_id, row.student_name), 'active': False})
            items.append({**summaries[row.id], 'id': row.id, 'student_id': row.student_id,
                'student_name': roster[row.student_id]['student_name'], 'file_name': row.file_name, 'file_type': row.file_type,
                'status': row.status, 'processing_status': latest[row.id].status if row.id in latest else 'not_scheduled',
                'processing_error': latest[row.id].error if row.id in latest else '', 'submitted_at': utc(row.created_at),
                'similarity': similarities[row.id], 'integrity': integrity[row.id]})
        from assignment_comparison import fingerprint
        latest_sources = {}
        for row in rows:
            latest_sources.setdefault(row.student_id, row)
        comparison_revision = fingerprint(db, assignment, sorted(latest_sources.values(), key=lambda row: row.id), '')
        return {'comparison_revision': comparison_revision, 'id': assignment.id, 'title': assignment.title, 'description': assignment.description,
            'assignment_type': assignment.assignment_type, 'offering_id': offering.id, 'course_name': course.name,
            'course_code': course.code, 'maximum_score': assignment.maximum_score, 'due_at': utc(assignment.due_at) if assignment.due_at else None,
            'originality_enabled': assignment.originality_enabled,
            'students': sorted(roster.values(), key=lambda s: (s['student_name'].casefold(), s['student_id'])), 'items': items}



@router.get("/submission-files/{submission_id}")
def original_file(submission_id: str, request: Request):
    with SessionLocal() as db:
        submission, _ = get_submission(db, submission_id, request)
        return Response(read_blob(submission.file_path), media_type=MIMES.get(submission.file_type, "text/plain" if submission.file_type != "zip" else "application/zip"), headers={"Content-Disposition": f'attachment; filename="submission.{submission.file_type}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/document-review/{submission_id}")
def get_review(submission_id: str, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, submission_id, request, teacher=True)
        document = db.get(SubmissionDocument, submission_id)
        reviews = db.scalars(select(DocumentReview).where(DocumentReview.submission_id == submission_id).order_by(DocumentReview.created_at.desc())).all()
        grade = db.scalar(select(AcademicGrade).where(AcademicGrade.submission_id == submission_id, AcademicGrade.published.is_(True)))
        published = db.get(PublishedDocumentReview, grade.id) if grade else None
        return {"submission_id": submission_id, "assignment_id": assignment.id, "title": assignment.title, "assignment_type": assignment.assignment_type, "instructions": assignment.description, "submitted_at": utc(submission.created_at), "student_id": submission.student_id, "student_name": student_display_name(db, submission.student_id, submission.student_name), "file_name": submission.file_name, "file_type": submission.file_type, "maximum_score": assignment.maximum_score, "questions": assignment.questions, "structure": document.structure if document else None, "reviews": [review_json(review) for review in reviews], "published_grade": {"points": grade.points, "maximum_score": grade.maximum_score, "review_id": published.review_id if published else None, "published_at": utc(grade.published_at) if grade.published_at else None} if grade else None}


@router.get('/document-review/{submission_id}/pages/{page_number}')
def preview_page(submission_id: str, page_number: int, request: Request):
    """Single bounded raster page: private, inert and independent of AI processing."""
    with SessionLocal() as db:
        submission, _ = get_submission(db, submission_id, request, teacher=True)
        if submission.file_type != 'pdf': raise HTTPException(415, 'PDF preview only.')
        try: content = read_blob(submission.file_path)
        except FileNotFoundError as error: raise HTTPException(404, 'Original document unavailable.') from error
    if len(content) > 30 * 1024 * 1024: raise HTTPException(413, 'PDF exceeds preview limits.')
    try:
        with pymupdf.open(stream=content, filetype='pdf') as document:
            if document.needs_pass or not 1 <= document.page_count <= 50:
                raise HTTPException(422, 'PDF is unavailable for preview.')
            if not 1 <= page_number <= document.page_count: raise HTTPException(404, 'Page not found.')
            page = document[page_number - 1]
            longest = max(page.rect.width, page.rect.height)
            if longest <= 0: raise HTTPException(422, 'Invalid PDF dimensions.')
            png = page.get_pixmap(matrix=pymupdf.Matrix(1600 / longest, 1600 / longest), alpha=False).tobytes('png')
    except (pymupdf.FileDataError, RuntimeError, ValueError) as error:
        raise HTTPException(422, 'PDF is unavailable for preview.') from error
    return Response(png, media_type='image/png', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post("/document-review/{submission_id}", status_code=201)
def save_review(submission_id: str, payload: ReviewPayload, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, submission_id, request, teacher=True)
        maximums = {(question["id"], criterion["criterion_id"]): criterion["maximum_points"] for question in assignment.questions for criterion in question["criteria"]}
        keys = [(criterion.question_id, criterion.criterion_id) for criterion in payload.criteria]
        if len(keys) != len(set(keys)) or set(keys) != set(maximums):
            raise HTTPException(422, "Every rubric criterion must be scored exactly once.")
        if not payload.draft and any(score.points is None for score in payload.criteria):
            raise HTTPException(422, 'Every criterion needs a teacher score before confirmation.')
        if any(score.points is not None and score.points > maximums[(score.question_id, score.criterion_id)] for score in payload.criteria) or sum(score.points or 0 for score in payload.criteria) > assignment.maximum_score:
            raise HTTPException(422, "Scores exceed rubric or assignment bounds.")
        from review_pilot import validate_use
        for score in payload.criteria:
            validate_use(db, submission, assignment, score.question_id, score.criterion_id, score.card_use)
        review = DocumentReview(submission_id=submission_id, reviewer=request_user(request).username, criteria=[dict(score.model_dump(), confirmed=not payload.draft) for score in payload.criteria], rubric_snapshot=assignment.questions, feedback=payload.feedback)
        db.add(review); db.commit()
        return review_json(review)


@router.post("/document-review/{submission_id}/publish")
def publish_review(submission_id: str, payload: PublishPayload, request: Request):
    with SessionLocal() as db:
        submission, assignment = get_submission(db, submission_id, request, teacher=True)
        # Serialize publication against the same submission to avoid duplicate
        # grade records if two requests are sent concurrently.
        from sqlalchemy import update
        if db.bind.dialect.name == "sqlite":
            db.execute(update(AcademicSubmission).where(AcademicSubmission.id == submission_id).values(status=AcademicSubmission.status))
        db.scalar(select(AcademicSubmission).where(AcademicSubmission.id == submission_id).with_for_update())
        review = db.get(DocumentReview, payload.review_id)
        if not review or review.submission_id != submission_id:
            raise HTTPException(404, "Review does not belong to this submission.")
        expected = {(q['id'], c['criterion_id']): c['maximum_points'] for q in assignment.questions for c in q['criteria']}
        keys = [(c['question_id'], c['criterion_id']) for c in review.criteria]
        if (len(set(keys)) != len(keys) or set(keys) != set(expected) or
            any(c.get('confirmed') is False or c['points'] is None or c['points'] < 0 or c['points'] > expected[(c['question_id'], c['criterion_id'])] for c in review.criteria)):
            raise HTTPException(409, 'Complete the current rubric before publishing this review.')
        points = sum(score["points"] for score in review.criteria)
        if points > assignment.maximum_score:
            raise HTTPException(409, "Assignment scoring has changed; create a new review.")
        grade = db.scalar(select(AcademicGrade).where(AcademicGrade.submission_id == submission_id))
        existing_link = db.get(PublishedDocumentReview, grade.id) if grade else None
        if ('expected_published_review_id' in payload.model_fields_set and
                payload.expected_published_review_id != (existing_link.review_id if existing_link else None)):
            raise HTTPException(409, 'The published review changed. Refresh and review it before publishing again.')
        if not grade:
            grade = AcademicGrade(assignment_id=assignment.id, submission_id=submission_id, points=points, maximum_score=assignment.maximum_score)
            db.add(grade); db.flush()
        grade.points = points; grade.maximum_score = assignment.maximum_score; grade.published = True; grade.published_at = now_utc()
        link = db.get(PublishedDocumentReview, grade.id)
        if link:
            link.review_id = review.id
        else:
            db.add(PublishedDocumentReview(grade_id=grade.id, review_id=review.id))
        submission.status = "completed"
        db.commit()
        return {"message": "Teacher-reviewed grade published.", "points": points}


def published_feedback(db, grade):
    link = db.get(PublishedDocumentReview, grade.id)
    review = db.get(DocumentReview, link.review_id) if link else None
    if not review:
        return {"criteria": [], "feedback": "", "rubric": []}
    # Use the immutable review snapshot, never today's assignment rubric.
    rubric = review.rubric_snapshot or []
    lookup = {(q.get("id"), c.get("criterion_id", c.get("id"))): c
              for q in rubric for c in q.get("criteria", [])}
    criteria = []
    for index, score in enumerate(review.criteria):
        criterion = lookup.get((score.get("question_id"), score.get("criterion_id")), {})
        description = str(criterion.get("description") or "").strip()
        if not description or description == score.get("criterion_id"):
            description = f"Критерий {index + 1}"
        criteria.append({**{key: value for key, value in score.items() if key != 'card_use'}, "description": description,
                         "maximum_points": criterion.get("maximum_points")})
    public_rubric = [{"id": q.get("id"), "title": q.get("title", ""), "criteria": [
        {key: c.get(key) for key in ("criterion_id", "description", "maximum_points")}
        for c in q.get("criteria", [])]} for q in rubric]
    return {"criteria": criteria, "feedback": review.feedback, "rubric": public_rubric}


@router.get("/teacher-overview")
def teacher_overview(request: Request):
    from persistence import CourseOffering
    from permissions import can_teach
    with SessionLocal() as db:
        user = request_user(request)
        assignments = db.scalars(select(AcademicAssignment).order_by(AcademicAssignment.created_at.desc())).all()
        authorized = [assignment for assignment in assignments if can_teach(db, user, db.get(CourseOffering, assignment.offering_id).course_id)]
        identifiers = [assignment.id for assignment in authorized]
        submissions = db.scalars(select(AcademicSubmission).where(AcademicSubmission.assignment_id.in_(identifiers)).order_by(AcademicSubmission.created_at.desc()).limit(100)).all() if identifiers else []
        lookup = {assignment.id: assignment for assignment in authorized}
        queue = []
        for submission in submissions:
            published = db.scalar(select(AcademicGrade.id).where(AcademicGrade.submission_id == submission.id, AcademicGrade.published.is_(True)))
            if not published:
                queue.append({"id": submission.id, "assignment_title": lookup[submission.assignment_id].title, "student_name": student_display_name(db, submission.student_id, submission.student_name), "submitted_at": utc(submission.created_at)})
        return {"review_queue": queue, "upcoming": [{"id": assignment.id, "title": assignment.title, "due_at": utc(assignment.due_at)} for assignment in authorized if assignment.due_at and utc(assignment.due_at) > now_utc()][:10]}
