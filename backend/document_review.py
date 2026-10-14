"""Teacher document review with immutable versions and explicit publication."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from auth import request_user
from accounts import utc
from document_models import DocumentReview, PublishedDocumentReview, SubmissionDocument
from materials import access, MIMES
from permissions import require_teacher
from persistence import AcademicAssignment, AcademicGrade, AcademicSubmission, SessionLocal, now_utc, read_blob

router = APIRouter(prefix="/api", tags=["Document review"])

class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=80)
    criterion_id: str = Field(min_length=1, max_length=80)
    points: float = Field(ge=0, le=10000, allow_inf_nan=False)
    comment: str = Field(default="", max_length=4000)

class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criteria: list[CriterionScore] = Field(min_length=1, max_length=1000)
    feedback: str = Field(default="", max_length=10000)

class PublishPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=1, max_length=36)


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
def list_submissions(assignment_id: str, request: Request):
    with SessionLocal() as db:
        assignment = db.get(AcademicAssignment, assignment_id)
        if not assignment:
            raise HTTPException(404, "Assignment not found.")
        require_teacher(db, request_user(request), assignment.offering_id)
        rows = db.scalars(select(AcademicSubmission).where(AcademicSubmission.assignment_id == assignment_id).order_by(AcademicSubmission.created_at.desc())).all()
        return {"title": assignment.title, "offering_id": assignment.offering_id, "items": [{"id": row.id, "student_name": row.student_name, "file_name": row.file_name, "status": row.status, "submitted_at": utc(row.created_at)} for row in rows]}


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
        return {"submission_id": submission_id, "assignment_id": assignment.id, "title": assignment.title, "student_name": submission.student_name, "file_name": submission.file_name, "file_type": submission.file_type, "maximum_score": assignment.maximum_score, "questions": assignment.questions, "structure": document.structure if document else None, "reviews": [review_json(review) for review in reviews], "published_grade": {"points": grade.points, "published_at": utc(grade.published_at) if grade.published_at else None} if grade else None}


@router.post("/document-review/{submission_id}", status_code=201)
def save_review(submission_id: str, payload: ReviewPayload, request: Request):
    with SessionLocal() as db:
        _, assignment = get_submission(db, submission_id, request, teacher=True)
        maximums = {(question["id"], criterion["criterion_id"]): criterion["maximum_points"] for question in assignment.questions for criterion in question["criteria"]}
        keys = [(criterion.question_id, criterion.criterion_id) for criterion in payload.criteria]
        if len(keys) != len(set(keys)) or set(keys) != set(maximums):
            raise HTTPException(422, "Every rubric criterion must be scored exactly once.")
        if any(score.points > maximums[(score.question_id, score.criterion_id)] for score in payload.criteria) or sum(score.points for score in payload.criteria) > assignment.maximum_score:
            raise HTTPException(422, "Scores exceed rubric or assignment bounds.")
        review = DocumentReview(submission_id=submission_id, reviewer=request_user(request).username, criteria=[score.model_dump() for score in payload.criteria], rubric_snapshot=assignment.questions, feedback=payload.feedback)
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
        points = sum(score["points"] for score in review.criteria)
        if points > assignment.maximum_score:
            raise HTTPException(409, "Assignment scoring has changed; create a new review.")
        grade = db.scalar(select(AcademicGrade).where(AcademicGrade.submission_id == submission_id))
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
    rubric = [{"id": question["id"], "title": question["title"], "criteria": [{"criterion_id": criterion["criterion_id"], "description": criterion["description"], "maximum_points": criterion["maximum_points"]} for criterion in question["criteria"]]} for question in review.rubric_snapshot]
    return {"criteria": review.criteria, "feedback": review.feedback, "rubric": rubric}


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
                queue.append({"id": submission.id, "assignment_title": lookup[submission.assignment_id].title, "student_name": submission.student_name, "submitted_at": utc(submission.created_at)})
        return {"review_queue": queue, "upcoming": [{"id": assignment.id, "title": assignment.title, "due_at": utc(assignment.due_at)} for assignment in authorized if assignment.due_at and utc(assignment.due_at) > now_utc()][:10]}
