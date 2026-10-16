import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    inspect,
    select,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.getenv("FORMA_STORAGE_DIR", str(BACKEND_DIR / "storage")))
STORAGE_BACKEND = os.getenv("FORMA_STORAGE_BACKEND", "local").strip().lower()
if STORAGE_BACKEND not in {"local", "r2"}:
    raise ValueError("FORMA_STORAGE_BACKEND must be 'local' or 'r2'.")

def _normalize_database_url(database_url: str | None) -> str:
    value = database_url or f"sqlite:///{BACKEND_DIR / 'forma.sqlite3'}"
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


DATABASE_URL = _normalize_database_url(os.getenv("FORMA_DATABASE_URL"))

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
_r2_client = None
_r2_bucket = os.getenv("R2_BUCKET_NAME", "").strip()
if STORAGE_BACKEND == "r2":
    _r2_account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    _r2_access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    _r2_secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    _missing_r2 = [
        key
        for key, value in (
            ("R2_ACCOUNT_ID", _r2_account_id),
            ("R2_ACCESS_KEY_ID", _r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", _r2_secret_access_key),
            ("R2_BUCKET_NAME", _r2_bucket),
        )
        if not value
    ]
    if _missing_r2:
        raise RuntimeError(
            "R2 storage is enabled but configuration is missing: " + ", ".join(_missing_r2)
        )
    _r2_client = boto3.client(
        "s3",
        endpoint_url=f"https://{_r2_account_id}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=_r2_access_key_id,
        aws_secret_access_key=_r2_secret_access_key,
    )

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    questions: Mapped[list] = mapped_column(JSON, default=list)
    template_regions: Mapped[list] = mapped_column(JSON, default=list)
    template_rotation: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_name: Mapped[str] = mapped_column(String(200))
    anonymous_student_id: Mapped[str] = mapped_column(String(64), default="")
    source_path: Mapped[str] = mapped_column(String(500))
    page_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(80))
    anonymous_student_id: Mapped[str] = mapped_column(String(24), default="")
    crop_path: Mapped[str] = mapped_column(String(500))
    page_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    suggested_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    criteria_results: Mapped[list] = mapped_column(JSON, default=list)
    human_criteria_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    grading_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    transcription: Mapped[str] = mapped_column(Text, default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    teacher_comment: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(24), default="unreviewed")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    teacher_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    has_source_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class AcademicCourse(Base):
    __tablename__ = "academic_courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    instructor: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200))


class CourseOffering(Base):
    __tablename__ = "academic_offerings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("academic_courses.id"), index=True)
    academic_year: Mapped[str] = mapped_column(String(12))
    term: Mapped[str] = mapped_column(String(32))
    section: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="active")
    class_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CourseEnrollment(Base):
    __tablename__ = "academic_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    offering_id: Mapped[str] = mapped_column(ForeignKey("academic_offerings.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(80), index=True)
    student_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AssignmentFamily(Base):
    __tablename__ = "academic_assignment_families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("academic_courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AcademicAssignment(Base):
    __tablename__ = "academic_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    offering_id: Mapped[str] = mapped_column(ForeignKey("academic_offerings.id"), index=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("academic_assignment_families.id"), index=True)
    legacy_assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    assignment_type: Mapped[str] = mapped_column(String(48), default="homework")
    description: Mapped[str] = mapped_column(Text, default="")
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    maximum_score: Mapped[float] = mapped_column(Float, default=100)
    allow_resubmission: Mapped[bool] = mapped_column(Boolean, default=False)
    originality_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    originality_scope: Mapped[str] = mapped_column(String(32), default="family_then_course")
    questions: Mapped[list] = mapped_column(JSON, default=list)
    template_regions: Mapped[list] = mapped_column(JSON, default=list)
    template_rotation: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AcademicSubmission(Base):
    __tablename__ = "academic_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey("academic_assignments.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(80), index=True)
    student_name: Mapped[str] = mapped_column(String(200))
    legacy_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class OriginalityAnalysis(Base):
    """Execution receipt; absence of pairwise matches is not an execution receipt."""
    __tablename__ = "academic_originality_analyses"
    submission_id: Mapped[str] = mapped_column(ForeignKey("academic_submissions.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    eligible_token_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[str] = mapped_column(String(32))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OriginalityReport(Base):
    __tablename__ = "academic_originality_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(ForeignKey("academic_submissions.id"), index=True)
    candidate_submission_id: Mapped[str] = mapped_column(ForeignKey("academic_submissions.id"), index=True)
    assignment_family_id: Mapped[str] = mapped_column(ForeignKey("academic_assignment_families.id"), index=True)
    match_scope: Mapped[str] = mapped_column(String(24))
    match_ratio: Mapped[float] = mapped_column(Float)
    eligible_token_count: Mapped[int] = mapped_column(Integer)
    matched_token_count: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(24), default="unreviewed")
    teacher_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AcademicGrade(Base):
    __tablename__ = "academic_grades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(ForeignKey("academic_assignments.id"), index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("academic_submissions.id"), index=True)
    answer_id: Mapped[str | None] = mapped_column(
        ForeignKey("answers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    points: Mapped[float] = mapped_column(Float)
    maximum_score: Mapped[float] = mapped_column(Float)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


def init_db(
    database_bind: Engine | Connection | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> None:
    if database_bind is None:
        database_bind = engine
    if session_factory is None:
        session_factory = (
            SessionLocal
            if database_bind is engine
            else sessionmaker(bind=database_bind, expire_on_commit=False)
        )
    identity_tables = {"guardian_registrations", "academic_originality_analyses", "accounts", "account_sessions", "account_actions", "account_rate_buckets", "course_owners", "offering_policies", "enrollment_states", "assignment_owners", "schema_migrations", "submission_documents", "course_materials", "document_reviews", "published_document_reviews", "email_outbox", "account_roles", "institutions", "institution_memberships", "course_institutions", "teacher_invitations", "audit_events", "document_processing_jobs", "document_interpretations", "interpretation_corrections", "document_interpretation_cache", "assignment_briefs", "ai_budget_periods", "ai_budget_controls", "ai_request_charges", "assessment_rubrics", "assessment_suggestions", "assessment_decisions"}
    identity_tables.update({'assignment_comparisons', 'review_decision_cards', 'review_question_page_maps', 'submission_upload_receipts'})
    Base.metadata.create_all(database_bind, tables=[table for name, table in Base.metadata.tables.items() if name not in identity_tables])
    migrations = {
        "assignments": {
            "template_rotation": "INTEGER NOT NULL DEFAULT 0",
        },
        "answers": {
            "is_demo": "BOOLEAN NOT NULL DEFAULT FALSE",
            "has_source_pdf": "BOOLEAN NOT NULL DEFAULT FALSE",
            "grading_metadata": "JSON NOT NULL DEFAULT '{}'",
            "teacher_comment": "TEXT NOT NULL DEFAULT ''",
            "anonymous_student_id": "TEXT NOT NULL DEFAULT ''",
        },
        "submissions": {
            "anonymous_student_id": "TEXT NOT NULL DEFAULT ''",
        },
    }
    for table, new_columns in migrations.items():
        columns = {
            column["name"] for column in inspect(database_bind).get_columns(table)
        }
        for column_name, column_type in new_columns.items():
            if column_name not in columns:
                if isinstance(database_bind, Connection):
                    database_bind.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"
                    )
                else:
                    with database_bind.begin() as connection:
                        connection.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"
                        )
    with session_factory() as db:
        submissions = db.scalars(
            select(Submission).order_by(
                Submission.assignment_id,
                Submission.created_at,
                Submission.id,
            )
        ).all()
        next_by_assignment: dict[str, int] = {}
        for submission in submissions:
            number = next_by_assignment.get(submission.assignment_id, 0) + 1
            pseudonym = submission.anonymous_student_id
            if not pseudonym:
                pseudonym = f"Student {number:02d}"
            else:
                try:
                    number = max(number, int(pseudonym.removeprefix("Student ")))
                except ValueError:
                    pass
            next_by_assignment[submission.assignment_id] = number
            submission.anonymous_student_id = pseudonym
            submission.student_name = pseudonym
            for answer in db.scalars(
                select(Answer).where(Answer.submission_id == submission.id)
            ):
                answer.anonymous_student_id = pseudonym
        db.commit()


def storage_path(*parts: str) -> Path:
    """Resolve only application-generated relative paths below STORAGE_DIR."""
    candidate = STORAGE_DIR.joinpath(*parts).resolve()
    if not candidate.is_relative_to(STORAGE_DIR.resolve()):
        raise ValueError("Invalid storage path.")
    return candidate


def _storage_key(relative_path: str) -> str:
    parts = PurePosixPath(relative_path).parts
    if (
        not parts
        or PurePosixPath(relative_path).is_absolute()
        or any(part in {".", ".."} for part in parts)
    ):
        raise ValueError("Invalid storage path.")
    storage_path(*parts)
    return PurePosixPath(*parts).as_posix()


def write_blob(relative_path: str, content: bytes) -> None:
    key = _storage_key(relative_path)
    if STORAGE_BACKEND == "r2":
        assert _r2_client is not None
        _r2_client.put_object(Bucket=_r2_bucket, Key=key, Body=content)
        return
    path = storage_path(*PurePosixPath(key).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def blob_exists(relative_path: str) -> bool:
    key = _storage_key(relative_path)
    if STORAGE_BACKEND == "r2":
        assert _r2_client is not None
        try:
            _r2_client.head_object(Bucket=_r2_bucket, Key=key)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404 or error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True
    return storage_path(*PurePosixPath(key).parts).is_file()


def delete_blobs(prefix: str) -> None:
    key = _storage_key(prefix)
    if STORAGE_BACKEND == "r2":
        assert _r2_client is not None
        paginator = _r2_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_r2_bucket, Prefix=f"{key.rstrip('/')}/"):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                _r2_client.delete_objects(
                    Bucket=_r2_bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )
        return
    path = storage_path(*PurePosixPath(key).parts)
    if path.is_dir():
        shutil.rmtree(path)


def save_blob(assignment_id: str, kind: str, content: bytes, suffix: str) -> str:
    if kind not in {"sources", "crops"} or suffix not in {".pdf", ".png"}:
        raise ValueError("Invalid storage type.")
    relative = Path(assignment_id) / kind / f"{uuid4().hex}{suffix}"
    key = relative.as_posix()
    write_blob(key, content)
    return key


def read_blob(relative_path: str) -> bytes:
    key = _storage_key(relative_path)
    if STORAGE_BACKEND == "r2":
        assert _r2_client is not None
        try:
            response = _r2_client.get_object(Bucket=_r2_bucket, Key=key)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404 or error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(relative_path) from exc
            raise
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()
    return storage_path(*PurePosixPath(key).parts).read_bytes()
