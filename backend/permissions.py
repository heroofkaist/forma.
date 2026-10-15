"""Course-scoped access gates for existing academic and linked legacy routes."""
import re
from fastapi import HTTPException
from sqlalchemy import select
from account_models import AssignmentOwner, CourseOwner, EnrollmentState
from persistence import (SessionLocal, CourseOffering, CourseEnrollment, AcademicAssignment,
                         AcademicSubmission, Answer, OriginalityReport)


def can_teach(db, user, course_id):
    from institution_models import CourseInstitution
    from institutions import membership, TEACHING_ROLES
    if user.role not in TEACHING_ROLES:
        return False
    owner = db.get(CourseOwner, course_id)
    tenant = db.get(CourseInstitution, course_id)
    if user.role == "platform_admin":
        return True
    if tenant:
        member = membership(db, user.account_id, tenant.institution_id, {"teacher", "school_admin"})
        if not member:
            return False
        return member.role == "school_admin" or bool(owner and owner.account_id == user.account_id)
    return owner.account_id == user.account_id if owner else user.role == "teacher" and not user.account_id


def require_teacher(db, user, offering_id):
    offering = db.get(CourseOffering, offering_id)
    if not offering or not can_teach(db, user, offering.course_id):
        raise HTTPException(403, "You do not have teaching access to this course.")
    return offering


def enrollment_active(db, enrollment):
    if not enrollment:
        return False
    state = db.get(EnrollmentState, enrollment.id)
    return state is None or state.status == "active"


def require_student(db, user, offering_id):
    if user.role != "student":
        raise HTTPException(403, "Student account required.")
    enrollment = db.scalar(select(CourseEnrollment).where(CourseEnrollment.offering_id == offering_id, CourseEnrollment.student_id == user.student_id))
    if not enrollment_active(db, enrollment):
        raise HTTPException(403, "Active course enrollment is required.")


def legacy_access(db, user, assignment_id):
    from institutions import TEACHING_ROLES
    if user.role not in TEACHING_ROLES:
        return False
    direct = db.get(AssignmentOwner, assignment_id)
    if direct:
        return direct.account_id == user.account_id
    academic = db.scalar(select(AcademicAssignment).where(AcademicAssignment.legacy_assignment_id == assignment_id))
    if academic:
        offering = db.get(CourseOffering, academic.offering_id)
        return bool(offering and can_teach(db, user, offering.course_id))
    return user.role == "teacher" and not user.account_id


async def authorize_request(request, user):
    path = request.url.path
    method = request.method
    if path.startswith("/api/assignment-briefs/"):
        if user.role == "student":
            raise HTTPException(403,"Teacher permission required.")
        return
    if path.startswith(("/api/institutions", "/api/document-analysis/")):
        return
    common = path.startswith("/api/accounts/") or path in {"/api/auth/me", "/api/auth/logout"}
    student = path.startswith(("/academic/student/", "/api/enrollment/")) or path == "/academic/enroll" or (method == "POST" and re.fullmatch(r"/academic/assignments/[^/]+/submissions", path))
    shared = (method == "GET" and path.startswith(("/api/course-materials/", "/api/materials/", "/api/submission-documents/", "/api/submission-files/"))) or (method == "GET" and (path == "/academic/courses" or re.fullmatch(r"/academic/offerings/[^/]+(?:/assignments)?", path)))
    if not common and not shared:
        if student and user.role != "student":
            raise HTTPException(403, "Student account required.")
        if not student and user.role == "student":
            raise HTTPException(403, "Teacher permission required.")
    if path.startswith(("/api/assessment/", "/api/assessment-rubrics/", "/api/course-materials/", "/api/materials/", "/api/submission-documents/", "/api/submission-files/", "/api/assignment-submissions/", "/api/document-review/", "/api/teacher-overview")):
        return  # Dedicated document handlers validate memberships and visibility.
    if path.startswith("/api/accounts/") or path.startswith("/api/courses") or path.startswith("/api/enrollment"):
        return  # These handlers require an account and check course ownership.
    if path in {"/api/auth/me", "/api/auth/logout", "/academic/courses", "/academic/enroll"} or path.startswith("/academic/student/"):
        return
    with SessionLocal() as db:
        if path.startswith("/academic/"):
            # Only the two shared offering GET routes support a student view.
            # A role query string must never turn archive/publish/reuse into
            # student-accessible endpoints.
            student_view = method == "GET" and re.fullmatch(r"/academic/offerings/[^/]+(?:/assignments)?", path) is not None and request.query_params.get("role") == "student"
            teacher_view = not student_view
            match = re.match(r"/academic/offerings/([^/]+)", path)
            offering_id = match.group(1) if match else None
            match = re.search(r"/assignments/([^/]+)", path)
            if match:
                assignment = db.get(AcademicAssignment, match.group(1))
                if not assignment:
                    raise HTTPException(404, "Assignment not found.")
                offering_id = assignment.offering_id
                if path.endswith("/submissions") and method == "POST":
                    teacher_view = False
            match = re.match(r"/academic/submissions/([^/]+)", path)
            if match:
                submission = db.get(AcademicSubmission, match.group(1))
                assignment = db.get(AcademicAssignment, submission.assignment_id) if submission else None
                if not assignment:
                    raise HTTPException(404, "Submission not found.")
                offering_id = assignment.offering_id
                teacher_view = True
            match = re.match(r"/academic/reports/([^/]+)", path)
            if match:
                report = db.get(OriginalityReport, match.group(1))
                submission = db.get(AcademicSubmission, report.submission_id) if report else None
                assignment = db.get(AcademicAssignment, submission.assignment_id) if submission else None
                if not assignment:
                    raise HTTPException(404, "Report not found.")
                offering_id = assignment.offering_id
                teacher_view = True
            if method == "POST" and path in {"/academic/offerings", "/academic/assignments"}:
                payload = await json_payload(request)
                if path.endswith("/offerings"):
                    if not can_teach(db, user, payload.get("course_id", "")):
                        raise HTTPException(403, "You do not own this course.")
                else:
                    require_teacher(db, user, payload.get("offering_id", ""))
                return
            if method == "POST" and path.endswith("/reuse"):
                payload = await json_payload(request)
                require_teacher(db, user, payload.get("offering_id", ""))
            if offering_id:
                if teacher_view:
                    require_teacher(db, user, offering_id)
                else:
                    require_student(db, user, offering_id)
                return
            if path == "/academic/teacher/originality":
                return  # Query is additionally filtered by owned course.
            raise HTTPException(403, "This academic route has no access policy.")
        if path.startswith(("/assignments", "/answers")):
            if user.role == "student":
                raise HTTPException(403, "Teacher access required.")
            match = re.match(r"/assignments/([^/]+)", path)
            assignment_id = match.group(1) if match else None
            match = re.match(r"/answers/([^/]+)", path)
            if match:
                answer = db.get(Answer, match.group(1))
                if not answer:
                    raise HTTPException(404, "Answer not found.")
                assignment_id = answer.assignment_id
            if assignment_id and not legacy_access(db, user, assignment_id):
                raise HTTPException(403, "You do not own this assignment.")
            return
        if path in {"/api/pdf/preview", "/api/pdf/crop", "/api/grade"} and user.role != "student":
            return
        raise HTTPException(403, "This route has no access policy.")


async def json_payload(request):
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, "Invalid JSON request.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(422, "Request body must be a JSON object.")
    return payload
