"""Private course creation and enrollment lifecycle without replacing academic tables."""
import csv
import io
import secrets
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from typing import Literal
from account_models import Account, CourseOwner, EnrollmentState, OfferingPolicy
from accounts import account_identity, rate_limit, utc
from auth import request_user
from permissions import enrollment_active, require_teacher
from persistence import AcademicCourse, CourseOffering, CourseEnrollment, SessionLocal, now_utc

router = APIRouter(prefix="/api", tags=["Course enrollment"])
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code():
    return "FORMA-" + "".join(secrets.choice(ALPHABET) for _ in range(10))


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=24)
    description: str = Field(default="", max_length=5000)
    subject: str = Field(min_length=1, max_length=200)
    academic_year: str = Field(min_length=1, max_length=12)
    term: str = Field(min_length=1, max_length=32)
    institution: str = Field(default="", max_length=200)
    approval_required: bool = False
    capacity: int | None = Field(default=None, ge=1, le=100000)
    opens_at: datetime | None = None
    closes_at: datetime | None = None

    @model_validator(mode="after")
    def dates(self):
        if any(not value.strip() for value in (self.title, self.code, self.subject, self.term, self.academic_year)):
            raise ValueError("Course fields cannot be blank.")
        if self.opens_at and self.closes_at and utc(self.opens_at) >= utc(self.closes_at):
            raise ValueError("Enrollment close must follow its opening.")
        return self


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    approval_required: bool = False
    capacity: int | None = Field(default=None, ge=1, le=100000)
    opens_at: datetime | None = None
    closes_at: datetime | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.opens_at and self.closes_at and utc(self.opens_at) >= utc(self.closes_at):
            raise ValueError("Enrollment close must follow its opening.")
        return self


class JoinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    class_code: str = Field(min_length=3, max_length=32)


class EnrollmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "rejected", "removed", "suspended"]


def lock_offering(db, offering_id):
    # SQLite has no row-level FOR UPDATE; acquiring its write lock also makes
    # sequential lookup/insert idempotent for concurrent joins in local tests.
    if db.bind.dialect.name == "sqlite":
        db.execute(update(CourseOffering).where(CourseOffering.id == offering_id).values(status=CourseOffering.status))
    return db.scalar(select(CourseOffering).where(CourseOffering.id == offering_id).with_for_update())


def policy_for(db, offering_id):
    policy = db.get(OfferingPolicy, offering_id)
    if not policy:
        policy = OfferingPolicy(offering_id=offering_id)
        db.add(policy)
        db.flush()
    return policy


def validate_code(db, offering):
    if not offering or offering.status != "active":
        raise HTTPException(404, "Enrollment code is invalid or unavailable.")
    policy = db.get(OfferingPolicy, offering.id)
    if policy and (not policy.enabled or (policy.opens_at and now_utc() < utc(policy.opens_at)) or (policy.closes_at and now_utc() >= utc(policy.closes_at))):
        raise HTTPException(404, "Enrollment code is invalid or unavailable.")
    return policy


def count_enrollments(db, offering_id):
    rows = db.scalars(select(CourseEnrollment).where(CourseEnrollment.offering_id == offering_id)).all()
    count = 0
    for row in rows:
        state = db.get(EnrollmentState, row.id)
        if state is None or state.status in {"active", "pending"}:
            count += 1
    return count


def offering_preview(db, offering, policy):
    course = db.get(AcademicCourse, offering.course_id)
    owner = db.get(CourseOwner, course.id)
    return {"offering_id": offering.id, "title": course.name, "teacher": course.instructor,
            "code": owner.public_code if owner else course.code, "term": offering.term,
            "academic_year": offering.academic_year, "approval_required": bool(policy and policy.approval_required)}


@router.post("/courses", status_code=201)
def create_course(payload: CourseCreate, request: Request):
    identity = account_identity(request)
    rate_limit(request, "create-course", identity, 20)
    with SessionLocal() as db:
        account = db.get(Account, identity)
        # Historic course.code is globally unique; retain it as an internal key
        # and store the educator's reusable display code in ownership metadata.
        course = AcademicCourse(code="C-" + secrets.token_hex(10), name=payload.title.strip(), instructor=account.display_name, department=payload.subject.strip())
        db.add(course)
        db.flush()
        db.add(CourseOwner(course_id=course.id, account_id=identity, public_code=payload.code.strip(), description=payload.description, institution=payload.institution))
        offering = CourseOffering(course_id=course.id, academic_year=payload.academic_year, term=payload.term, section="01", class_code=new_code())
        db.add(offering)
        db.flush()
        db.add(OfferingPolicy(offering_id=offering.id, approval_required=payload.approval_required, capacity=payload.capacity, opens_at=payload.opens_at, closes_at=payload.closes_at))
        db.commit()
        return {"course_id": course.id, "offering_id": offering.id, "class_code": offering.class_code}


@router.post("/enrollment/preview")
def preview(payload: JoinPayload, request: Request):
    account_identity(request)
    rate_limit(request, "enrollment-code", request_user(request).account_id, 20)
    with SessionLocal() as db:
        offering = db.scalar(select(CourseOffering).where(CourseOffering.class_code == payload.class_code.strip().upper()))
        policy = validate_code(db, offering)
        result = offering_preview(db, offering, policy)
        enrollment = db.scalar(select(CourseEnrollment).where(CourseEnrollment.offering_id == offering.id, CourseEnrollment.student_id == request_user(request).student_id))
        state = db.get(EnrollmentState, enrollment.id) if enrollment else None
        result["enrollment_status"] = state.status if state else "active" if enrollment else "not_enrolled"
        return result


def join_code(payload, request):
    user = request_user(request)
    rate_limit(request, "enrollment-code", user.student_id or user.username, 20)
    with SessionLocal() as db:
        offering = db.scalar(select(CourseOffering).where(CourseOffering.class_code == payload.class_code.strip().upper()))
        if not offering:
            raise HTTPException(404, "Enrollment code is invalid or unavailable.")
        offering = lock_offering(db, offering.id)
        policy = validate_code(db, offering)
        enrollment = db.scalar(select(CourseEnrollment).where(CourseEnrollment.offering_id == offering.id, CourseEnrollment.student_id == user.student_id))
        if enrollment:
            state = db.get(EnrollmentState, enrollment.id)
            return {"id": enrollment.id, "offering_id": offering.id, "student_id": enrollment.student_id, "student_name": enrollment.student_name, "created": False, "status": state.status if state else "active"}
        if policy and policy.capacity and count_enrollments(db, offering.id) >= policy.capacity:
            raise HTTPException(409, "Course enrollment capacity has been reached.")
        account = db.get(Account, user.account_id) if user.account_id else None
        enrollment = CourseEnrollment(offering_id=offering.id, student_id=user.student_id, student_name=account.display_name if account else user.username)
        db.add(enrollment)
        db.flush()
        status = "pending" if policy and policy.approval_required else "active"
        db.add(EnrollmentState(enrollment_id=enrollment.id, status=status))
        db.commit()
        return {"id": enrollment.id, "offering_id": offering.id, "student_id": enrollment.student_id, "student_name": enrollment.student_name, "created": True, "status": status}


@router.post("/enrollment/join", status_code=201)
def join(payload: JoinPayload, request: Request):
    account_identity(request)
    return join_code(payload, request)


@router.get("/courses/{offering_id}/enrollment")
def roster(offering_id: str, request: Request):
    account_identity(request)
    with SessionLocal() as db:
        offering = require_teacher(db, request_user(request), offering_id)
        policy = policy_for(db, offering_id)
        rows = db.scalars(select(CourseEnrollment).where(CourseEnrollment.offering_id == offering_id).order_by(CourseEnrollment.created_at)).all()
        items = []
        for row in rows:
            state = db.get(EnrollmentState, row.id)
            items.append({"id": row.id, "student_name": row.student_name, "status": state.status if state else "active"})
        result = {"class_code": offering.class_code, "enabled": policy.enabled, "approval_required": policy.approval_required, "capacity": policy.capacity, "opens_at": utc(policy.opens_at) if policy.opens_at else None, "closes_at": utc(policy.closes_at) if policy.closes_at else None, "items": items}
        db.commit()
        return result


@router.put("/courses/{offering_id}/enrollment")
def update_policy(offering_id: str, payload: PolicyUpdate, request: Request):
    account_identity(request)
    with SessionLocal() as db:
        require_teacher(db, request_user(request), offering_id)
        lock_offering(db, offering_id)
        policy = policy_for(db, offering_id)
        for key, value in payload.model_dump().items():
            setattr(policy, key, value)
        db.commit()
    return {"message": "Enrollment policy saved."}


@router.post("/courses/{offering_id}/rotate-code")
def rotate_code(offering_id: str, request: Request):
    account_identity(request)
    with SessionLocal() as db:
        require_teacher(db, request_user(request), offering_id)
        offering = lock_offering(db, offering_id)
        offering.class_code = new_code()
        db.commit()
        return {"class_code": offering.class_code}


@router.patch("/courses/{offering_id}/enrollment/{enrollment_id}")
def update_enrollment(offering_id: str, enrollment_id: str, payload: EnrollmentUpdate, request: Request):
    account_identity(request)
    with SessionLocal() as db:
        require_teacher(db, request_user(request), offering_id)
        lock_offering(db, offering_id)
        row = db.get(CourseEnrollment, enrollment_id)
        if not row or row.offering_id != offering_id:
            raise HTTPException(404, "Enrollment not found.")
        state = db.get(EnrollmentState, row.id)
        policy = policy_for(db, offering_id)
        if payload.status == "active" and not enrollment_active(db, row) and (not state or state.status != "pending") and policy.capacity and count_enrollments(db, offering_id) >= policy.capacity:
            raise HTTPException(409, "Course enrollment capacity has been reached.")
        if not state:
            state = EnrollmentState(enrollment_id=row.id)
            db.add(state)
        state.status = payload.status
        db.commit()
    return {"status": payload.status}


@router.get("/courses/{offering_id}/roster.csv")
def export_roster(offering_id: str, request: Request):
    result = roster(offering_id, request)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Enrollment status"])
    for item in result["items"]:
        name = item["student_name"]
        writer.writerow(["'" + name if name.lstrip().startswith(("=", "+", "-", "@")) else name, item["status"]])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="roster.csv"'})
